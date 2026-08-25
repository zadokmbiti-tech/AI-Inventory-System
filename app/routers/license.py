from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User, LicenseStatus
from app.schemas.schemas import LicenseOut, LicenseRenewRequest
from app.services.auth import get_current_user
from app.services.email import send_license_key_email
from app.services.license import (
    get_current_license,
    is_license_valid,
    issue_license,
    LICENSE_PERIOD_DAYS,
)

router = APIRouter(prefix="/api/license", tags=["Licensing"])


def _to_out(license_) -> LicenseOut:
    now = datetime.now(timezone.utc)
    expires_at = license_.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    days_remaining = max(0, (expires_at - now).days)
    return LicenseOut(
        license_key=license_.license_key,
        status=license_.status,
        plan=license_.plan,
        issued_at=license_.issued_at,
        expires_at=license_.expires_at,
        days_remaining=days_remaining,
    )


@router.get("/status", response_model=LicenseOut)
def license_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Current license for the logged-in business — active, expired, or none yet."""
    license_ = get_current_license(db, user.id)
    if not license_:
        raise HTTPException(status_code=404, detail="No license found. Subscribe to get started.")
    return _to_out(license_)


@router.post("/renew", response_model=LicenseOut, status_code=201)
def renew_license(
    payload: LicenseRenewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Issue a fresh 30-day license for the logged-in business.

    NOTE: this is a placeholder self-service endpoint. In production this
    should only be called from your M-Pesa Daraja STK Push callback once
    payment is CONFIRMED — not directly from the frontend "Pay" button —
    otherwise anyone could renew for free. Wire the callback handler to
    call `issue_license()` from app/services/license.py the same way this
    endpoint does, passing the real mpesa_receipt.
    """
    license_ = issue_license(
        db,
        user_id=user.id,
        days=LICENSE_PERIOD_DAYS,
        plan=payload.plan,
        amount_paid=payload.amount_paid,
        mpesa_receipt=payload.mpesa_receipt,
    )
    send_license_key_email(user.email, license_.license_key, license_.expires_at, license_.plan)
    return _to_out(license_)
