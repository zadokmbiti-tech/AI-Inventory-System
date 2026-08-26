from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, PasswordResetToken
from app.schemas.schemas import (
    UserCreate, UserOut, Token, ForgotPasswordRequest, ResetPasswordRequest,
)
from app.services.auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    generate_reset_token, hash_reset_token, set_auth_cookie, clear_auth_cookie,
    log_login_event,
)
from app.services.email import send_password_reset_email
from app.config import get_settings
from app.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["Auth"])
settings = get_settings()


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("5/hour")
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        business_name=payload.business_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # No license is issued here on purpose — a new business can sign in
    # right away, but every feature stays behind require_active_license
    # (402) until a super_admin approves and activates them from the
    # Admin panel. See app/routers/license.py for the request-activation
    # flow and app/routers/admin.py for the approval side.

    return user


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been suspended. Contact support.")
    token = create_access_token({"sub": str(user.id)})
    # httpOnly cookie is what the web app actually uses; the token is also
    # returned in the body for API clients and the /docs "Authorize" button.
    set_auth_cookie(response, token)
    log_login_event(db, user.id, request)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password")
@limiter.limit("5/hour")
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    # Always return the same message whether or not the email is registered,
    # so the endpoint can't be used to check which emails have accounts.
    if user:
        raw_token, token_hash = generate_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.reset_token_expire_minutes
        )
        db.add(PasswordResetToken(
            user_id=user.id, token_hash=token_hash, expires_at=expires_at,
        ))
        db.commit()

        reset_link = f"{settings.frontend_base_url}/?reset_token={raw_token}"
        send_password_reset_email(user.email, reset_link)

    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
@limiter.limit("10/hour")
def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_reset_token(payload.token)
    entry = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash, PasswordResetToken.used == False)  # noqa: E712
        .first()
    )
    if not entry or entry.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user = db.query(User).filter(User.id == entry.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hashed_password = hash_password(payload.new_password)
    entry.used = True
    db.commit()

    return {"message": "Password updated. You can now sign in."}
