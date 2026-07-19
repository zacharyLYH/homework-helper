import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


def send_verification_email(to_email: str, code: str) -> bool:
    if not settings.smtp_user or not settings.smtp_password:
        log.warning("SMTP not configured, skipping email send")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Homework Helper Verification Code"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 400px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">Verification Code</h2>
        <p>Your verification code is:</p>
        <div style="background: #f4f4f4; padding: 15px; text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 5px; border-radius: 8px;">
            {code}
        </div>
        <p style="color: #666; margin-top: 20px;">This code expires in 10 minutes.</p>
    </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        log.info("Verification email sent to %s", to_email)
        return True
    except Exception as e:
        log.error("Failed to send email to %s: %s", to_email, e)
        return False
