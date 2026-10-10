# Backend/Business_Layer/services/invoice_email_intake_service.py
"""Email invoice intake (APM_AUTOMATION_PLAN.md Phase 3b).

Reads the intake mailbox (MAIL_ADDRESS) through Microsoft Graph and turns every qualifying email
into one bulk-upload batch (source EMAIL). From there it is exactly the bulk pipeline - and so
exactly the single-upload operations - so invoices land in the OCR review queue; nothing new
happens to review, approval, TDS or payment.

Which emails qualify:
  * received at/after EMAIL_INTAKE_START_DATE (go-live - older mail is never imported) and within
    the last EMAIL_INTAKE_LOOKBACK_HOURS (so a run after downtime still catches up);
  * has at least one usable attachment (PDF / TIFF / ZIP, or a JPG/PNG that is not an inline
    signature image or tiny logo);
  * sender: when VENDOR_EMAIL is set (comma-separated), ONLY mail from those addresses, any
    subject. Otherwise all mail whose subject or attachment name looks like an invoice; the batch
    records whether the sender matches a vendor's email so reviewers see unknown senders.

Each message is imported at most once (unique source_reference = internetMessageId). The mailbox
is only read, never changed.
"""
import datetime
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from Backend.Business_Layer.services import invoice_bulk_upload_service as bulk
from Backend.Business_Layer.services.email_intake_settings_service import EmailIntakeSettingsService
from Backend.Business_Layer.utils import bulk_upload_files as bf
from Backend.Business_Layer.utils.graph_mail_client import GraphMailClient
from Backend.config.env_loader import get_env_var
from Backend.Data_Access_Layer.dao.invoice_upload_batch_dao import InvoiceUploadBatchDAO
from Backend.Data_Access_Layer.models.invoice_upload_batch import SOURCE_EMAIL
from Backend.Data_Access_Layer.utils.database import SessionLocal

logger = logging.getLogger(__name__)

ACTOR = "EMAIL_INTAKE"
DEFAULT_KEYWORDS = "invoice,inv,bill,tax invoice,e-invoice,gst invoice"
MIN_IMAGE_BYTES = 20 * 1024  # smaller JPG/PNG attachments are logos / signatures, not invoices
# Postgres advisory-lock key: only one intake run at a time, however many runners are scheduled.
_LOCK_KEY = 0x41504D45  # "APME"

# Shared mail domains: a vendor using gmail does not make every gmail sender a known vendor.
_PUBLIC_DOMAINS = {"gmail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com", "live.com",
                   "rediffmail.com", "icloud.com", "protonmail.com", "zoho.com", "aol.com"}


@dataclass
class IntakeConfig:
    start: datetime.datetime
    lookback_hours: int = 72
    allowed_senders: Sequence[str] = ()
    keywords: Sequence[str] = ()
    max_messages: int = 50

    @classmethod
    def from_env(cls) -> "IntakeConfig":
        raw_start = (get_env_var("EMAIL_INTAKE_START_DATE", "") or "").strip()
        if not raw_start:
            raise ValueError("EMAIL_INTAKE_START_DATE is not set in .env - set the go-live date "
                             "(e.g. 2026-10-10) so older mail is never imported.")
        start = datetime.datetime.fromisoformat(raw_start)
        if start.tzinfo is None:
            start = start.replace(tzinfo=datetime.timezone.utc)
        senders = [s.strip().lower() for s in (get_env_var("VENDOR_EMAIL", "") or "").split(",") if s.strip()]
        keywords = [k.strip().lower() for k in (get_env_var("EMAIL_INTAKE_SUBJECT_KEYWORDS", DEFAULT_KEYWORDS) or "").split(",") if k.strip()]
        return cls(start=start, lookback_hours=int(get_env_var("EMAIL_INTAKE_LOOKBACK_HOURS", "72")),
                   allowed_senders=senders, keywords=keywords,
                   max_messages=int(get_env_var("EMAIL_INTAKE_MAX_MESSAGES", "50")))

    def since(self, now: datetime.datetime) -> datetime.datetime:
        return max(self.start, now - datetime.timedelta(hours=self.lookback_hours))


@dataclass
class RunReport:
    examined: int = 0
    already_imported: int = 0
    skipped: int = 0
    imported: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    disabled: bool = False  # the UI switch (EMAIL_INTAKE_ENABLED) is off - nothing was read
    automation_rechecked: int = 0  # waiting PO invoices re-checked by AP automation this run


# ======================================================================
# Pure selection rules (unit-tested)
# ======================================================================
def sender_of(message: Dict[str, Any]) -> str:
    return (((message.get("from") or {}).get("emailAddress") or {}).get("address") or "").strip().lower()


def _keyword_hit(text_value: str, keywords: Sequence[str]) -> bool:
    lowered = (text_value or "").lower()
    # whole-word match so "inv" does not hit "invite" / "investor"
    return any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", lowered) for k in keywords)


def message_qualifies(message: Dict[str, Any], config: IntakeConfig) -> bool:
    """Header-level check (before downloading attachments)."""
    if not message.get("hasAttachments"):
        return False
    received = message.get("receivedDateTime")
    if received:
        when = datetime.datetime.fromisoformat(received.replace("Z", "+00:00"))
        if when < config.start:
            return False
    if config.allowed_senders:
        return sender_of(message) in config.allowed_senders
    return True  # subject OR attachment name is checked once attachment names are known


def usable_attachments(attachments: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for a in attachments:
        if a.get("@odata.type", "#microsoft.graph.fileAttachment") != "#microsoft.graph.fileAttachment":
            continue  # attached emails / cloud links
        if a.get("isInline"):
            continue  # signature images
        ext = bf.extension(a.get("name") or "")
        if ext == ".zip" or ext in (".pdf", ".tif", ".tiff"):
            out.append(a)
        elif ext in (".jpg", ".jpeg", ".png") and (a.get("size") or 0) >= MIN_IMAGE_BYTES:
            out.append(a)
    return out


def looks_like_invoice(message: Dict[str, Any], attachments: Sequence[Dict[str, Any]], config: IntakeConfig) -> bool:
    if config.allowed_senders:
        return True  # the sender list is the filter; any subject
    if _keyword_hit(message.get("subject") or "", config.keywords):
        return True
    return any(_keyword_hit(re.sub(r"[_\-.]+", " ", a.get("name") or ""), config.keywords) for a in attachments)


def sender_is_known(sender: str, vendor_emails: Iterable[str]) -> bool:
    if not sender:
        return False
    known = {e.strip().lower() for e in vendor_emails if e}
    if sender in known:
        return True
    domain = sender.rsplit("@", 1)[-1]
    if domain in _PUBLIC_DOMAINS:
        return False
    return any(e.rsplit("@", 1)[-1] == domain for e in known)


# ======================================================================
# Run
# ======================================================================
def _received_at(message) -> Optional[datetime.datetime]:
    raw = message.get("receivedDateTime")
    return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None


async def run_once(execute: bool, client: Optional[GraphMailClient] = None, config: Optional[IntakeConfig] = None,
                   now: Optional[datetime.datetime] = None) -> RunReport:
    """One intake pass. With execute=False (dry run) nothing is stored - the report lists what
    would be imported."""
    config = config or IntakeConfig.from_env()
    client = client or GraphMailClient()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    report = RunReport()
    since = config.since(now).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    db = SessionLocal()
    try:
        dao = InvoiceUploadBatchDAO(db)
        vendor_emails = dao.vendor_emails()
        for message in client.messages_since(since):
            if len(report.imported) >= config.max_messages:
                break
            report.examined += 1
            if not message_qualifies(message, config):
                report.skipped += 1
                continue
            reference = (message.get("internetMessageId") or message.get("id"))[:500]
            if dao.batch_for_source(SOURCE_EMAIL, reference) is not None:
                report.already_imported += 1
                continue
            try:
                attachments = usable_attachments(client.attachments(message["id"]))
            except Exception as exc:
                report.errors.append(f"{message.get('subject')!r}: could not list attachments ({exc})")
                continue
            if not attachments or not looks_like_invoice(message, attachments, config):
                report.skipped += 1
                continue

            sender = sender_of(message)
            summary = {"subject": message.get("subject"), "from": sender, "received": message.get("receivedDateTime"),
                       "files": [a.get("name") for a in attachments]}
            if not execute:
                report.imported.append(summary)
                continue

            try:
                parts = [(a.get("name"), a.get("contentType"), client.attachment_bytes(message["id"], a["id"]))
                         for a in attachments]
            except Exception as exc:
                report.errors.append(f"{message.get('subject')!r}: could not download attachments ({exc})")
                continue
            candidates = bf.expand_attachments(parts)
            service = bulk.InvoiceBulkUploadService(db)
            try:
                batch_id = service.create_batch(
                    candidates, (message.get("subject") or "(no subject)")[:255], ACTOR,
                    f"Email intake ({sender or 'unknown sender'})"[:200],
                    source_type=SOURCE_EMAIL, source_reference=reference,
                    email={"email_from": sender[:320] or None, "email_subject": (message.get("subject") or "")[:500],
                           "email_received_at": _received_at(message),
                           "sender_known": sender_is_known(sender, vendor_emails)},
                )
            except IntegrityError:
                db.rollback()  # another runner imported it a moment ago
                report.already_imported += 1
                continue
            await bulk.process_batch(batch_id, ACTOR)
            report.imported.append({**summary, "batch_id": batch_id})
    finally:
        db.close()
    return report


def _automation_sweep() -> int:
    """Step B: re-check waiting PO invoices on every scheduled run (a goods receipt recorded after
    the invoice arrived turns an exception into a touchless invoice). No-op while automation is off."""
    from Backend.Business_Layer.services.ap_automation_service import APAutomationService  # avoid import cycle
    db = SessionLocal()
    try:
        return len(APAutomationService(db).sweep())
    except Exception:
        logger.exception("AP automation sweep failed")
        return 0
    finally:
        db.close()


def try_lock(db) -> bool:
    return bool(db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}).scalar())


def unlock(db) -> None:
    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})


async def run_locked(execute: bool) -> Optional[RunReport]:
    """run_once guarded by a Postgres advisory lock; None when another run holds it. An --execute
    run does nothing while the EMAIL_INTAKE_ENABLED switch is off, and records its outcome for the
    status card. A dry run ignores the switch (it changes nothing) so the connection can be tested
    before intake is turned on."""
    lock_db = SessionLocal()
    try:
        if not try_lock(lock_db):
            return None
        try:
            settings = EmailIntakeSettingsService(lock_db)
            if execute and not settings.is_enabled():
                return RunReport(disabled=True)
            try:
                report = await run_once(execute)
            except Exception as exc:
                if execute:
                    settings.record_run({"status": "error", "error": str(exc)[:120]})
                    lock_db.commit()
                raise
            if execute:
                settings.record_run({"status": "ok", "examined": report.examined, "imported": len(report.imported),
                                     "errors": len(report.errors)})
                lock_db.commit()
                report.automation_rechecked = _automation_sweep()
            return report
        finally:
            unlock(lock_db)
            lock_db.commit()
    finally:
        lock_db.close()
