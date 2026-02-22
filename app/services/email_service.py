"""Send transactional email (e.g. password reset)."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import get_settings


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    """
    Send email with reset link. Link is frontend_url + password_reset_link_path + ?token=...
    """
    settings = get_settings()
    if not settings.smtp_host:
        return  # Email not configured; skip silently (token still created)
    link = f"{settings.frontend_url.rstrip('/')}{settings.password_reset_link_path}?token={reset_token}"
    subject = "Reset your password"
    body = f"""Hello,

You requested a password reset. Click the link below to set a new password:

{link}

This link expires in 60 minutes. If you didn't request this, you can ignore this email.
"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.sendmail(settings.smtp_from, [to_email], msg.as_string())
