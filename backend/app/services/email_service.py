from __future__ import annotations

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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


def send_password_reset_email(recipient: str, reset_url: str) -> bool:
    if not settings.smtp_host:
        logger.warning("SMTP not configured; skipping password reset email to %s", recipient)
        return False

    subject = "Reset Your Password"
    html = PASSWORD_RESET_HTML % reset_url

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("Password reset email sent to %s", recipient)
        return True
    except Exception as exc:
        logger.exception("Failed to send password reset email to %s: %s", recipient, exc)
        return False
