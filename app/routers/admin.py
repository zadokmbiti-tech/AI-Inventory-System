"""
Platform-operator (super_admin) endpoints. These sit outside the normal
per-business data model  a super_admin isn't "a business" and never goes
through require_active_license; they manage every business's account and
subscription instead of using the product themselves.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import (
    User, UserRole, LoginEvent, License, LicenseStatus, Product, Sale,
    LicenseRequest, LicenseRequestStatus,
)
from app.schemas.schemas import (
    AdminBusinessOut, AdminBusinessDetailOut, AdminLicenseAdjustRequest,
    AdminLicenseRequestOut,
)
from app.services.auth import require_super_admin
from app.services.license import issue_license, get_current_license

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_super_admin)])

# Login-sharing heuristic: within a 7-day window, this many *distinct* IPs
# or *distinct* devices on one login is treated as a flag. Neither signal
# alone is proof (people travel, IPs rotate on mobile data)  it's a
# starting point for you to look closer at, not an automatic ban.
SHARING_WINDOW_DAYS = 7
DISTINCT_IP_FLAG_THRESHOLD = 3
DISTINCT_DEVICE_FLAG_THRESHOLD = 3


def _login_stats(db: Session, user_id: int, since: datetime) -> dict:
    rows = (
        db.query(LoginEvent.ip_address, LoginEvent.user_agent)
        .filter(LoginEvent.user_id == user_id, LoginEvent.created_at >= since)
        .all()
    )
    distinct_ips = {r.ip_address for r in rows if r.ip_address}
    distinct_devices = {r.user_agent for r in rows if r.user_agent}
    last_login = (
        db.query(func.max(LoginEvent.created_at))
        .filter(LoginEvent.user_id == user_id)
        .scalar()
    )
    return {
        "login_count_7d": len(rows),
        "distinct_ips_7d": len(distinct_ips),
        "distinct_devices_7d": len(distinct_devices),
        "last_login_at": last_login,
    }


def _to_admin_out(db: Session, user: User, since: datetime, cls=AdminBusinessOut) -> AdminBusinessOut:
    license_ = get_current_license(db, user.id)
    stats = _login_stats(db, user.id, since)
    flagged = (
        stats["distinct_ips_7d"] >= DISTINCT_IP_FLAG_THRESHOLD
        or stats["distinct_devices_7d"] >= DISTINCT_DEVICE_FLAG_THRESHOLD
    )
    return cls(
        id=user.id,
        name=user.name,
        email=user.email,
        business_name=user.business_name,
        is_active=user.is_active,
        created_at=user.created_at,
        license_status=license_.status.value if license_ else None,
        license_plan=license_.plan if license_ else None,
        license_expires_at=license_.expires_at if license_ else None,
        product_count=db.query(func.count(Product.id)).filter(Product.user_id == user.id).scalar() or 0,
        sales_count=db.query(func.count(Sale.id)).filter(Sale.user_id == user.id).scalar() or 0,
        flagged_sharing=flagged,
        **stats,
    )


@router.get("/businesses", response_model=List[AdminBusinessOut])
def list_businesses(db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=SHARING_WINDOW_DAYS)
    users = (
        db.query(User)
        .filter(User.role == UserRole.OWNER)
        .order_by(User.created_at.desc())
        .all()
    )
    return [_to_admin_out(db, u, since) for u in users]


@router.get("/businesses/{user_id}", response_model=AdminBusinessDetailOut)
def get_business(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.OWNER).first()
    if not user:
        raise HTTPException(status_code=404, detail="Business not found")
    since = datetime.now(timezone.utc) - timedelta(days=SHARING_WINDOW_DAYS)
    out = _to_admin_out(db, user, since, cls=AdminBusinessDetailOut)
    recent = (
        db.query(LoginEvent)
        .filter(LoginEvent.user_id == user_id)
        .order_by(LoginEvent.created_at.desc())
        .limit(20)
        .all()
    )
    out.recent_logins = recent
    return out


@router.post("/businesses/{user_id}/suspend", response_model=AdminBusinessOut)
def suspend_business(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.OWNER).first()
    if not user:
        raise HTTPException(status_code=404, detail="Business not found")
    user.is_active = False
    db.commit()
    db.refresh(user)
    since = datetime.now(timezone.utc) - timedelta(days=SHARING_WINDOW_DAYS)
    return _to_admin_out(db, user, since)


@router.post("/businesses/{user_id}/activate", response_model=AdminBusinessOut)
def activate_business(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.OWNER).first()
    if not user:
        raise HTTPException(status_code=404, detail="Business not found")
    user.is_active = True
    db.commit()
    db.refresh(user)
    since = datetime.now(timezone.utc) - timedelta(days=SHARING_WINDOW_DAYS)
    return _to_admin_out(db, user, since)


@router.post("/businesses/{user_id}/license", response_model=AdminBusinessOut)
def adjust_license(user_id: int, payload: AdminLicenseAdjustRequest, db: Session = Depends(get_db)):
    """Manually grant/extend a license  e.g. after confirming payment outside the app."""
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.OWNER).first()
    if not user:
        raise HTTPException(status_code=404, detail="Business not found")
    issue_license(db, user_id=user.id, days=payload.days, plan=payload.plan)
    since = datetime.now(timezone.utc) - timedelta(days=SHARING_WINDOW_DAYS)
    return _to_admin_out(db, user, since)


@router.post("/businesses/{user_id}/revoke-license", response_model=AdminBusinessOut)
def revoke_license(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.OWNER).first()
    if not user:
        raise HTTPException(status_code=404, detail="Business not found")
    db.query(License).filter(
        License.user_id == user.id, License.status == LicenseStatus.ACTIVE
    ).update({"status": LicenseStatus.REVOKED})
    db.commit()
    since = datetime.now(timezone.utc) - timedelta(days=SHARING_WINDOW_DAYS)
    return _to_admin_out(db, user, since)


# ─── Activation requests ─────────────────────────────────────────────────────
# A business can't activate itself  see app/routers/license.py. This is the
# queue of "please activate/renew me" requests for you to act on.

@router.get("/license-requests", response_model=List[AdminLicenseRequestOut])
def list_license_requests(status: Optional[str] = "PENDING", db: Session = Depends(get_db)):
    q = db.query(LicenseRequest, User).join(User, LicenseRequest.user_id == User.id)
    if status:
        try:
            q = q.filter(LicenseRequest.status == LicenseRequestStatus(status.upper()))
        except ValueError:
            raise HTTPException(status_code=400, detail="status must be PENDING, FULFILLED, or DISMISSED")
    rows = q.order_by(LicenseRequest.created_at.asc()).all()
    return [
        AdminLicenseRequestOut(
            id=req.id,
            user_id=req.user_id,
            business_name=user.business_name,
            owner_name=user.name,
            email=user.email,
            plan=req.plan,
            message=req.message,
            status=req.status.value,
            created_at=req.created_at,
        )
        for req, user in rows
    ]


@router.post("/license-requests/{request_id}/approve", response_model=AdminBusinessOut)
def approve_license_request(request_id: int, payload: AdminLicenseAdjustRequest, db: Session = Depends(get_db)):
    req = db.query(LicenseRequest).filter(LicenseRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Business not found")

    issue_license(db, user_id=user.id, days=payload.days, plan=payload.plan)
    req.status = LicenseRequestStatus.FULFILLED
    req.resolved_at = datetime.now(timezone.utc)
    db.commit()

    since = datetime.now(timezone.utc) - timedelta(days=SHARING_WINDOW_DAYS)
    return _to_admin_out(db, user, since)


@router.post("/license-requests/{request_id}/dismiss")
def dismiss_license_request(request_id: int, db: Session = Depends(get_db)):
    req = db.query(LicenseRequest).filter(LicenseRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = LicenseRequestStatus.DISMISSED
    req.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Request dismissed"}
