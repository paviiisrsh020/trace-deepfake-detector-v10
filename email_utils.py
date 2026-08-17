"""
email_utils.py
---------------
Sends transactional email (password reset, welcome) via SMTP using
Python's built-in smtplib - no extra dependency needed.

SETUP (any SMTP provider works - Gmail, Outlook, Brevo/Sendinblue free
tier, SendGrid, etc.)
--------------------------------------------------------------------
Set these environment variables before running the app:

  SMTP_HOST      e.g. smtp.gmail.com
  SMTP_PORT      e.g. 587
  SMTP_USER      your SMTP account username/email
  SMTP_PASS      your SMTP account password or app-specific password
  SMTP_FROM      the "from" address shown to recipients (often same as SMTP_USER)

Gmail specifically requires an "App Password" (not your normal login
password) - generate one at https://myaccount.google.com/apppasswords
once 2-factor auth is enabled on the account.

DEV FALLBACK
------------
If SMTP_HOST is not set, emails are NOT sent - instead the content is
printed to the server console/log. This lets password reset and signup
work end-to-end during local development without any email setup.
Never rely on this fallback in a real deployment: anyone with server
log access could see reset links. Set real SMTP env vars on Render
(or wherever you deploy) before going live.
"""

import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER).strip()

CONFIGURED = bool(SMTP_HOST and SMTP_USER and SMTP_PASS)


def send_email(to_email, subject, body_text):
    if not CONFIGURED:
        print("=" * 60)
        print(f"[email_utils] SMTP not configured - printing email instead of sending.")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print("-" * 60)
        print(body_text)
        print("=" * 60)
        return True

    try:
        msg = MIMEText(body_text)
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[email_utils] Failed to send email to {to_email}: {e}")
        return False


def send_welcome_email(to_email, name):
    subject = "Welcome to TRACE"
    body = (
        f"Hi {name},\n\n"
        "Your TRACE account is ready. Upload a clip or paste a video link any time "
        "to check it for signs of manipulation.\n\n"
        "— TRACE"
    )
    return send_email(to_email, subject, body)


def send_password_reset_email(to_email, reset_url):
    subject = "Reset your TRACE password"
    body = (
        f"We received a request to reset your TRACE password.\n\n"
        f"Reset it here (link expires in 1 hour):\n{reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email.\n\n"
        "— TRACE"
    )
    return send_email(to_email, subject, body)
