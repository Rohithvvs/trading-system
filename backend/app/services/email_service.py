from __future__ import annotations

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from ..config import settings

logger = logging.getLogger("app.email")

PASSWORD_RESET_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background-color:#f4f4f4">
<table width="100%%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4;padding:40px 20px">
<tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
<tr><td style="padding:40px 32px 24px;text-align:center;background:linear-gradient(135deg,#2563eb,#1d4ed8)">
<h1 style="margin:0;font-size:22px;color:#ffffff;font-weight:600">Reset Your Password</h1>
</td></tr>
<tr><td style="padding:32px 32px 24px">
<p style="margin:0 0 16px;font-size:15px;color:#374151;line-height:1.5">Hello,</p>
<p style="margin:0 0 20px;font-size:15px;color:#374151;line-height:1.5">We received a request to reset your password. Click the button below to set a new password.</p>
<table cellpadding="0" cellspacing="0" style="margin:0 auto 24px"><tr><td style="background-color:#2563eb;border-radius:8px;padding:12px 32px">
<a href="%s" style="color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;display:inline-block">Reset Password</a>
</td></tr></table>
<p style="margin:0 0 4px;font-size:13px;color:#9ca3af;line-height:1.5">If you didn't request this, you can safely ignore this email.</p>
<p style="margin:0;font-size:13px;color:#9ca3af;line-height:1.5">This link expires in 15 minutes.</p>
</td></tr>
<tr><td style="padding:16px 32px;text-align:center;border-top:1px solid #e5e7eb">
<p style="margin:0;font-size:12px;color:#9ca3af">TradeX Trading System</p>
</td></tr>
</table>
</td></tr></table>
</body>
</html>
"""

PASSWORD_RESET_TEXT = """\
Reset Your Password

We received a request to reset your password. Open this link to set a new password:

%s

If you didn't request this, you can safely ignore this email.
This link expires in 15 minutes.

— TradeX Trading System
"""


def smtp_is_configured() -> bool:
    """True when enough SMTP settings exist to attempt delivery."""
    return bool(
        (settings.smtp_host or "").strip()
        and (settings.smtp_user or "").strip()
        and (settings.smtp_password or "").strip()
    )


def _smtp_config_status() -> str:
    return (
        f"host={'set' if (settings.smtp_host or '').strip() else 'MISSING'} "
        f"user={'set' if (settings.smtp_user or '').strip() else 'MISSING'} "
        f"password={'set' if (settings.smtp_password or '').strip() else 'MISSING'} "
        f"from={settings.smtp_from or settings.smtp_user or 'MISSING'} "
        f"port={settings.smtp_port}"
    )


def send_password_reset_email(recipient: str, reset_url: str) -> bool:
    """Send a password-reset email. Always logs outcome (configured / skip / success / error)."""
    configured = smtp_is_configured()
    logger.info(
        "PASSWORD_RESET_EMAIL_ATTEMPT | to=%s | smtp_configured=%s | %s",
        recipient,
        configured,
        _smtp_config_status(),
    )

    if not configured:
        logger.warning(
            "SMTP not configured; skipping password reset email to %s | %s | "
            "Set SMTP_HOST/SMTP_USER/SMTP_PASSWORD (or MAIL_SERVER/MAIL_USERNAME/MAIL_PASSWORD) "
            "in repo-root .env and restart the backend",
            recipient,
            _smtp_config_status(),
        )
        return False

    subject = "Reset Your Password"
    html = PASSWORD_RESET_HTML % reset_url
    text = PASSWORD_RESET_TEXT % reset_url

    from_addr = (settings.smtp_from or settings.smtp_user or "").strip()
    from_name = (getattr(settings, "smtp_from_name", None) or "TradeX").strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_addr)) if from_name else from_addr
    msg["To"] = recipient
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    host = settings.smtp_host.strip()
    port = int(settings.smtp_port or 587)
    use_tls = bool(getattr(settings, "smtp_use_tls", True))

    try:
        logger.info(
            "PASSWORD_RESET_EMAIL_SMTP_CONNECT | host=%s port=%s use_tls=%s user=%s from=%s",
            host,
            port,
            use_tls,
            settings.smtp_user,
            from_addr,
        )
        # Port 465 = implicit SSL; 587 = STARTTLS (typical Gmail)
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                if use_tls:
                    server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        logger.info(
            "Password reset email sent to %s via %s:%s | PASSWORD_RESET_EMAIL_SENT",
            recipient,
            host,
            port,
        )
        return True
    except Exception as exc:
        # Log full traceback + exception class so Gmail auth/TLS issues are visible.
        logger.exception(
            "Failed to send password reset email to %s via %s:%s | "
            "PASSWORD_RESET_EMAIL_FAILED | error_type=%s | error=%s",
            recipient,
            host,
            port,
            type(exc).__name__,
            exc,
        )
        return False
