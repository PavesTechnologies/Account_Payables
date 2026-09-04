# Backend/Business_Layer/utils/email_service.py
"""Centralized outbound SMTP email service.

Generic on purpose - knows nothing about RFQs, vendors, or any other
domain concept. It exists so `smtplib`/MIME/credential-handling logic
lives in exactly one place instead of being duplicated per feature (see
API_Layer/routes/intake_route.py:send_mail for the pre-existing,
route-file-embedded, always-raising precedent this intentionally does
NOT reuse: it has no attachment support and offers no way for a caller
to keep going after one recipient fails).

`send_email` never raises on an SMTP/connection/auth failure - it always
returns an `EmailSendResult` so a caller sending to many recipients can
record a success for recipient A even if recipient B's send fails.

SMTP_PASSWORD is read once per call straight from the environment and is
never included in a log line, an exception message we construct, or an
`EmailSendResult`.
"""
from __future__ import annotations

import datetime
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Dict, List, Optional

from Backend.config.env_loader import get_env_var

logger = logging.getLogger(__name__)


@dataclass
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass
class EmailSendResult:
    success: bool
    sent_at: datetime.datetime
    error: Optional[str] = None


def get_smtp_config() -> Dict[str, object]:
    """Reads SMTP connection settings from the environment.

    SMTP_HOST/SMTP_PORT default to Gmail's well-known values so a minimal
    .env only needs to set the credentials; SMTP_USERNAME, SMTP_PASSWORD
    and RFQ_FROM_EMAIL have no defaults and raise (via get_env_var) if
    unset - never fall back to a hardcoded credential.
    """
    return {
        "host": get_env_var("SMTP_HOST", "smtp.gmail.com"),
        "port": int(get_env_var("SMTP_PORT", "587")),
        "username": get_env_var("SMTP_USERNAME"),
        "password": get_env_var("SMTP_PASSWORD"),
        "from_address": get_env_var("RFQ_FROM_EMAIL"),
    }


def send_email(
    to_address: str,
    subject: str,
    html_body: Optional[str] = None,
    text_body: Optional[str] = None,
    attachments: Optional[List[EmailAttachment]] = None,
    smtp_config: Optional[Dict[str, object]] = None,
) -> EmailSendResult:
    """Sends one email to one recipient over SMTP (STARTTLS, Gmail-compatible).

    Supports a plain-text body, an HTML body, or both (HTML is sent as the
    preferred alternative with the plain text as fallback), plus optional
    attachments. Every failure mode (bad address, connection error, auth
    failure, timeout) is caught and reported via the returned
    EmailSendResult rather than raised, so callers sending to a list of
    recipients can keep going after one failure without extra try/except
    scaffolding at every call site.
    """
    if not html_body and not text_body:
        raise ValueError("Either html_body or text_body is required")
    if not to_address:
        return EmailSendResult(
            success=False,
            sent_at=datetime.datetime.now(datetime.timezone.utc),
            error="No recipient email address provided",
        )

    try:
        config = smtp_config or get_smtp_config()
    except ValueError as exc:
        # Missing SMTP configuration is a setup problem, not a per-recipient
        # one - still reported through the result, never raised, so a batch
        # send fails visibly for every recipient instead of crashing.
        return EmailSendResult(
            success=False,
            sent_at=datetime.datetime.now(datetime.timezone.utc),
            error=f"SMTP is not configured: {exc}",
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["from_address"]
    message["To"] = to_address

    message.set_content(text_body or "This email requires an HTML-capable client.")
    if html_body:
        message.add_alternative(html_body, subtype="html")

    for attachment in attachments or []:
        maintype, _, subtype = (attachment.content_type or "").partition("/")
        message.add_attachment(
            attachment.content,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=attachment.filename,
        )

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(config["username"], config["password"])
            smtp.send_message(message)

        logger.info("Email sent to %s (subject=%r)", to_address, subject)
        return EmailSendResult(success=True, sent_at=datetime.datetime.now(datetime.timezone.utc))

    except Exception as exc:
        logger.warning("Email send to %s failed: %s", to_address, exc)
        return EmailSendResult(
            success=False,
            sent_at=datetime.datetime.now(datetime.timezone.utc),
            error=str(exc),
        )
