from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, PasswordResetToken
from app.schemas.schemas import (
    UserCreate, UserOut, Token, ForgotPasswordRequest, ResetPasswordRequest,
)
from app.services.auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    generate_reset_token, hash_reset_token,
)
from app.services.email import send_password_reset_email
from app.services.license import issue_license, TRIAL_PERIOD_DAYS
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["Auth"])
settings = get_settings()


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
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

    # Give every new business a free trial so they're not locked out immediately
    issue_license(db, user_id=user.id, days=TRIAL_PERIOD_DAYS, plan="trial")

    return user


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
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
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
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
