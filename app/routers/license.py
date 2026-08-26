from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User, LicenseRequest, LicenseRequestStatus
from app.schemas.schemas import LicenseOut, LicenseRequestCreate, LicenseRequestOut
from app.services.auth import get_current_user
from app.services.license import get_current_license

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
        raise HTTPException(status_code=404, detail="No license yet. Request activation to get started.")
    return _to_out(license_)


@router.get("/request-status", response_model=LicenseRequestOut)
def request_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The business's most recent activation/renewal request, if any."""
    req = (
        db.query(LicenseRequest)
        .filter(LicenseRequest.user_id == user.id)
        .order_by(LicenseRequest.created_at.desc())
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="No activation request on file yet.")
    return req


@router.post("/request", response_model=LicenseRequestOut, status_code=201)
def request_license(
    payload: LicenseRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Ask a super_admin to activate or renew this business's license. This
    does NOT grant access by itself — it only shows up in the Admin panel
    for a human to review and approve. Only one pending request is kept
    per business at a time to avoid spamming the queue.
    """
    existing = (
        db.query(LicenseRequest)
        .filter(LicenseRequest.user_id == user.id, LicenseRequest.status == LicenseRequestStatus.PENDING)
        .first()
    )
    if existing:
        return existing

    req = LicenseRequest(user_id=user.id, plan=payload.plan, message=payload.message)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req
