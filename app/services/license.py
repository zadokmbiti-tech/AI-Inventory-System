"""
License key generation, issuance, and validation for the monthly
subscription model. This is deliberately payment-gateway-agnostic —
`issue_license()` is the single choke point that should be called
once a payment is confirmed (e.g. from an M-Pesa Daraja STK Push
callback). Until that's wired in, `POST /api/license/renew` lets an
authenticated user self-issue a renewal, which is fine for testing
but should be removed/gated once M-Pesa is live.
"""
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import License, LicenseStatus, User
from app.services.auth import get_current_user

LICENSE_PERIOD_DAYS = 30
TRIAL_PERIOD_DAYS = 7
KEY_PREFIX = "SSA"  # SmartStock AI


def _random_block(length: int = 4) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_license_key() -> str:
    """e.g. SSA-4F9K-2XQ1-8B3T"""
    return f"{KEY_PREFIX}-{_random_block()}-{_random_block()}-{_random_block()}"


def issue_license(
    db: Session,
    user_id: int,
    days: int = LICENSE_PERIOD_DAYS,
    plan: str = "monthly",
    amount_paid: Optional[float] = None,
    mpesa_receipt: Optional[str] = None,
) -> License:
    """
    Create a new license for a user. Any of the user's currently-ACTIVE
    licenses are marked EXPIRED first, so there's only ever one active
    license per business at a time (renewals extend from *now*, not from
    the old expiry — keeps things simple and matches "pay again to keep
    using it" rather than stacking unused days).
    """
    now = datetime.now(timezone.utc)

    db.query(License).filter(
        License.user_id == user_id,
        License.status == LicenseStatus.ACTIVE,
    ).update({"status": LicenseStatus.EXPIRED})

    # Guarantee key uniqueness (astronomically unlikely to collide, but check anyway)
    key = generate_license_key()
    while db.query(License).filter(License.license_key == key).first():
        key = generate_license_key()

    license_ = License(
        user_id=user_id,
        license_key=key,
        status=LicenseStatus.ACTIVE,
        plan=plan,
        amount_paid=amount_paid,
        mpesa_receipt=mpesa_receipt,
        expires_at=now + timedelta(days=days),
    )
    db.add(license_)
    db.commit()
    db.refresh(license_)
    return license_


def get_current_license(db: Session, user_id: int) -> Optional[License]:
    """Most recently issued license for this user, regardless of status."""
    return (
        db.query(License)
        .filter(License.user_id == user_id)
        .order_by(License.issued_at.desc())
        .first()
    )


def is_license_valid(license_: Optional[License]) -> bool:
    if license_ is None:
        return False
    if license_.status != LicenseStatus.ACTIVE:
        return False
    expires_at = license_.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


def require_active_license(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """
    FastAPI dependency — attach to any router/endpoint that should be
    locked behind an active subscription. Raises 402 Payment Required
    (not 403 — this isn't a permissions issue, it's "please pay/renew").
    """
    license_ = get_current_license(db, user.id)
    if not is_license_valid(license_):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your SmartStock AI license has expired or is inactive. Renew to continue.",
        )
    return user

