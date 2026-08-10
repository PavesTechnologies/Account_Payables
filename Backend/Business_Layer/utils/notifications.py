# Backend/Business_Layer/utils/notifications.py
"""Vendor-not-found notification for the Invoice Intake team.

Reuses the existing internal mail mechanism (Backend.API_Layer.routes
.intake_route.send_mail, which wraps Microsoft Graph) directly in-process
rather than re-implementing Graph auth here or making a self-addressed
HTTP call back into this same API (which would need its own JWT and a
configured base URL for no benefit). Recipient resolution is isolated
in its own function so it can be swapped for a real UMS role lookup
later without touching any caller.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from Backend.API_Layer.interface.invoice_process_interface import ExtractedInvoice
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument

logger = logging.getLogger(__name__)

INVOICE_INTAKE_RECIPIENTS_CONFIG_KEY = "INVOICE_INTAKE_NOTIFICATION_EMAILS"


def resolve_invoice_intake_recipients(db) -> List[str]:
    """Read the comma-separated Invoice Intake recipient list from system_config.

    No UMS role-lookup mechanism exists in this codebase today, so this
    reads a DB-backed config value instead (same pattern as other
    admin-tunable thresholds, e.g. vendor_service's bank-duplicate-config
    key) rather than hardcoding any address. Never raises — a missing
    config row just means no notification is sent, which is logged.
    """
    config = MasterDAO(db).get_system_config_by_key(INVOICE_INTAKE_RECIPIENTS_CONFIG_KEY)
    if config is None or not getattr(config, "config_value", None):
        logger.warning(
            "No Invoice Intake recipients configured under system_config key '%s'; "
            "vendor-not-found notification will not be sent",
            INVOICE_INTAKE_RECIPIENTS_CONFIG_KEY,
        )
        return []

    return [email.strip() for email in config.config_value.split(",") if email.strip()]


def _build_message(extracted: ExtractedInvoice, inbound_document: InboundDocument, reason: str) -> dict:
    lines = [
        "A new invoice was processed but could not be matched to an existing vendor.",
        "",
        f"Invoice number: {extracted.invoice_number or 'Not extracted'}",
        f"Vendor name (as extracted): {extracted.vendor_name or 'Not extracted'}",
        f"Vendor GSTIN (as extracted): {extracted.gstin or 'Not extracted'}",
        f"Document reference: {inbound_document.file_path}",
        f"Reason: {reason}",
        "",
        "Action required: onboard this vendor, then complete OCR review for this document.",
    ]
    return {
        "subject": "New Vendor Detected - Vendor Onboarding Required",
        "body": "\n".join(lines),
    }


def notify_vendor_not_found(
    db, extracted: ExtractedInvoice, inbound_document: InboundDocument, reason: str
) -> None:
    """Best-effort notification. Never raises — a failed send must never roll back
    an already-committed InboundDocument/Invoice."""
    from Backend.API_Layer.routes.intake_route import send_mail

    recipients = resolve_invoice_intake_recipients(db)
    if not recipients:
        return

    message = _build_message(extracted, inbound_document, reason)
    for recipient in recipients:
        try:
            send_mail(message=message, to_address=recipient)
        except Exception:
            logger.exception(
                "Failed to send vendor-not-found notification to '%s' for inbound_document_id=%s",
                recipient,
                inbound_document.inbound_document_id,
            )
