import httpx

from app.config import get_settings

settings = get_settings()

RESEND_API_URL = "https://api.resend.com/emails"


def _send_email(to_email: str, subject: str, body: str, dev_label: str) -> None:
    if not settings.resend_api_key:
        # Dev fallback — no Resend key configured, so just log the content.
        print("=" * 60)
        print(f"[DEV] {dev_label} for {to_email}:")
        print(body)
        print("=" * 60)
        return

    payload = {
        "from": settings.email_from,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    response = httpx.post(RESEND_API_URL, json=payload, headers=headers, timeout=10)
    response.raise_for_status()


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    subject = "Reset your SmartStock AI password"
    body = (
        "We received a request to reset your SmartStock AI password.\n\n"
        f"Click the link below to set a new password. This link expires in "
        f"{settings.reset_token_expire_minutes} minutes:\n\n"
        f"{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email."
    )
    _send_email(to_email, subject, body, dev_label="Password reset link")


def send_license_key_email(to_email: str, license_key: str, expires_at, plan: str) -> None:
    subject = "Your SmartStock AI license key"
    body = (
        "Thanks for subscribing to SmartStock AI!\n\n"
        f"Plan: {plan}\n"
        f"Your license key: {license_key}\n"
        f"Valid until: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "Enter this key in the app to activate/renew your subscription. "
        "Keep it safe — you'll need a new one every 30 days when it renews.\n\n"
        "If you didn't request this, please contact support."
    )
    _send_email(to_email, subject, body, dev_label="License key email")