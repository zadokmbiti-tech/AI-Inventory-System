import smtplib
from email.mime.text import MIMEText

from app.config import get_settings

settings = get_settings()


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    subject = "Reset your SmartStock AI password"
    body = (
        "We received a request to reset your SmartStock AI password.\n\n"
        f"Click the link below to set a new password. This link expires in "
        f"{settings.reset_token_expire_minutes} minutes:\n\n"
        f"{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email."
    )

    if not settings.smtp_host:
        # Dev fallback — no SMTP configured, so just log the link.
        print("=" * 60)
        print(f"[DEV] Password reset link for {to_email}:")
        print(reset_link)
        print("=" * 60)
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(msg["From"], [to_email], msg.as_string())


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

    if not settings.smtp_host:
        print("=" * 60)
        print(f"[DEV] License key email for {to_email}:")
        print(body)
        print("=" * 60)
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(msg["From"], [to_email], msg.as_string())
