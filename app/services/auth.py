from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User
from app.config import get_settings

settings = get_settings()

COOKIE_NAME = "ss_access_token"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# auto_error=False: don't 401 just because the header is missing — we also
# accept the token from an httpOnly cookie (see get_current_user below), so
# the header is only one of two valid ways to authenticate.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def set_auth_cookie(response, token: str) -> None:
    """
    Store the JWT in an httpOnly cookie so it's inaccessible to page
    JavaScript (mitigates token theft via XSS). `secure=True` restricts the
    cookie to HTTPS; disabled only when DEBUG is on for local http://
    development. `samesite="lax"` blocks the cookie being sent on
    cross-site requests, which covers CSRF for state-changing endpoints.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def _truncate_bytes(password: str, max_bytes: int = 72) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) <= max_bytes:
        return password
    truncated = encoded[:max_bytes]
    while truncated:
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return ""

def hash_password(password: str) -> str:
    return pwd_context.hash(_truncate_bytes(password))

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_truncate_bytes(plain), hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Prefer an explicit Authorization header (useful for /docs and API
    # clients); fall back to the httpOnly cookie the browser sends
    # automatically for the web app.
    raw_token = token or request.cookies.get(COOKIE_NAME)
    if not raw_token:
        raise credentials_exception

    try:
        payload = jwt.decode(raw_token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def generate_reset_token() -> tuple[str, str]:
    """Returns (raw_token_for_email, hash_to_store_in_db)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_reset_token(raw)


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

