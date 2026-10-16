"""Send the daily summary email over SMTP. Config from env:
SMTP_HOST (default smtp.gmail.com), SMTP_PORT (default 587), SMTP_USER,
SMTP_PASS (an app password, NOT your normal password), MAIL_FROM, MAIL_TO."""
from __future__ import annotations
import email.message
import os
import smtplib


class MailError(RuntimeError):
    pass


def mail_config() -> dict:
    """Read SMTP config from environment. Raises MailError if required vars missing."""
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    mail_to = os.environ.get("MAIL_TO")
    missing = [k for k, v in [("SMTP_USER", user), ("SMTP_PASS", password), ("MAIL_TO", mail_to)] if not v]
    if missing:
        raise MailError(f"Missing required env vars: {', '.join(missing)}")
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": user,
        "password": password,
        "from": os.environ.get("MAIL_FROM") or user,
        "to": mail_to,
    }


def build_message(subject: str, body: str, cfg: dict) -> email.message.EmailMessage:
    """Construct an EmailMessage from subject/body/cfg."""
    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    msg.set_content(body)
    return msg


def send_email(subject: str, body: str, *, cfg: dict | None = None,
               transport=None) -> None:
    """Build and send the message.

    If transport is given (callable(msg, cfg)) it is called instead of opening
    a real SMTP connection — used for offline tests.
    """
    if cfg is None:
        cfg = mail_config()
    msg = build_message(subject, body, cfg)
    if transport is not None:
        transport(msg, cfg)
        return
    with smtplib.SMTP(cfg["host"], cfg["port"]) as conn:
        conn.starttls()
        conn.login(cfg["user"], cfg["password"])
        conn.send_message(msg)
