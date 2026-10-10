# Backend/Business_Layer/services/tds_tracking_service.py
"""TDS Tracking: record what Finance did, OUTSIDE this system, about the TDS
withheld on an invoice - nothing here files anything with the tax authority.

    TDS_PENDING --record deduction--> TDS_DEDUCTED
                --record deposit (challan)--> TDS_DEPOSITED
                --record filing (return)--> TDS_FILED

Rules:
  - only invoices whose TDS determination is tds_applicable and VERIFIED can
    be tracked (the amount/rate come from that immutable snapshot and are
    never edited here);
  - steps go forward one at a time; the CURRENT step may be re-recorded to
    correct its details, earlier steps may not once a later one exists;
  - dates must be on/after the previous step's date and not in the future;
  - TDS tracking status is independent of the invoice's payment status.
Each recorded activity / document is an INVOICE_TDS_* event on the invoice's
own audit trail (the activity timeline).

Conventions as tds_determination_service.py: ValueError for business rules,
service owns commit/rollback.
"""
from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Optional

from Backend.Business_Layer.services.payment_tracking_service import MAX_PAGE_SIZE, PaymentTrackingService
from Backend.Business_Layer.services.tds_determination_service import DETERMINATION_STATUS_VERIFIED
from Backend.Data_Access_Layer.dao.tds_tracking_dao import TRACKING_STATUS_PENDING, TdsTrackingDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.tds import InvoiceTdsDocument, InvoiceTdsTracking

TRACKING_STATUS_DEDUCTED = "TDS_DEDUCTED"
TRACKING_STATUS_DEPOSITED = "TDS_DEPOSITED"
TRACKING_STATUS_FILED = "TDS_FILED"

TRACKING_STATUSES = [
    {"value": TRACKING_STATUS_PENDING, "label": "TDS Pending", "order": 1},
    {"value": TRACKING_STATUS_DEDUCTED, "label": "TDS Deducted", "order": 2},
    {"value": TRACKING_STATUS_DEPOSITED, "label": "TDS Deposited", "order": 3},
    {"value": TRACKING_STATUS_FILED, "label": "TDS Return Filed", "order": 4},
]
_STATUS_LABELS = {s["value"]: s["label"] for s in TRACKING_STATUSES}

ACTION_DEDUCTION = "RECORD_DEDUCTION"
ACTION_DEPOSIT = "RECORD_DEPOSIT"
ACTION_FILING = "RECORD_FILING"
ACTIONS = [
    {"value": ACTION_DEDUCTION, "label": "Record TDS Deduction", "results_in": TRACKING_STATUS_DEDUCTED},
    {"value": ACTION_DEPOSIT, "label": "Record TDS Payment (Challan)", "results_in": TRACKING_STATUS_DEPOSITED},
    {"value": ACTION_FILING, "label": "Record Filing Details", "results_in": TRACKING_STATUS_FILED},
]
# action -> statuses it may be recorded from (its predecessor, or itself = correction)
_ACTION_FROM = {
    ACTION_DEDUCTION: {TRACKING_STATUS_PENDING, TRACKING_STATUS_DEDUCTED},
    ACTION_DEPOSIT: {TRACKING_STATUS_DEDUCTED, TRACKING_STATUS_DEPOSITED},
    ACTION_FILING: {TRACKING_STATUS_DEPOSITED, TRACKING_STATUS_FILED},
}

TDS_DOCUMENT_TYPES = [
    {"value": "CHALLAN", "label": "Challan"},
    {"value": "CERTIFICATE", "label": "TDS Certificate (Form 16A)"},
    {"value": "FILING_ACKNOWLEDGEMENT", "label": "Filing Acknowledgement"},
    {"value": "OTHER", "label": "Other Supporting Document"},
]
_TDS_DOCUMENT_TYPE_VALUES = {d["value"] for d in TDS_DOCUMENT_TYPES}

_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/\-_. ]*$")
_BSR_RE = re.compile(r"^[0-9]{7}$")
_CENTS = Decimal("0.01")


class TdsTrackingNotFoundError(ValueError):
    """-> 404"""


def _money(value) -> Optional[Decimal]:
    return Decimal(value).quantize(_CENTS) if value is not None else None


def _user(user_id) -> Optional[str]:
    return str(user_id) if user_id is not None else None


def allowed_actions(determination_status: Optional[str], tracking_status: str) -> list[str]:
    if determination_status != DETERMINATION_STATUS_VERIFIED:
        return []
    return [action for action, sources in _ACTION_FROM.items() if tracking_status in sources]


def tds_document_view(doc: InvoiceTdsDocument) -> dict:
    return {
        "id": doc.id,
        "document_type": doc.document_type,
        "file_name": doc.file_name,
        "content_type": doc.content_type,
        "file_size": doc.file_size,
        "uploaded_by": doc.uploaded_by,
        "uploaded_at": doc.uploaded_at,
    }


class TdsTrackingService:
    def __init__(self, db):
        self.db = db
        self.dao = TdsTrackingDAO(db)

    # =========================================================
    # Metadata
    # =========================================================

    @staticmethod
    def metadata() -> dict:
        from Backend.API_Layer.utils.file_validation import MAX_UPLOAD_SIZE_BYTES, _ALLOWED_EXTENSIONS

        return {
            "tracking_statuses": TRACKING_STATUSES,
            "actions": ACTIONS,
            "document_types": TDS_DOCUMENT_TYPES,
            "allowed_file_extensions": sorted(_ALLOWED_EXTENSIONS),
            "max_file_size_bytes": MAX_UPLOAD_SIZE_BYTES,
        }

    # =========================================================
    # Views
    # =========================================================

    @staticmethod
    def _row_view(row) -> dict:
        invoice, vendor_name, status, tds, nature, rule, tracking = row
        snapshot = tds.rule_snapshot or {}
        tracking_status = tracking.tracking_status if tracking else TRACKING_STATUS_PENDING
        invoice_amount = _money(invoice.net_amount)
        tds_amount = _money(tds.tds_amount) or Decimal("0.00")
        return {
            "invoice_id": invoice.invoice_id,
            "invoice_number": invoice.invoice_number,
            "vendor_id": invoice.vendor_id,
            "vendor_name": vendor_name,
            "invoice_date": invoice.invoice_date,
            "currency_code": invoice.currency.currency_code if invoice.currency else None,
            "currency_symbol": invoice.currency.symbol if invoice.currency else None,
            "invoice_status_code": status.status_code if status else None,
            "invoice_status_name": status.status_name if status else None,
            "payment_nature": {"id": nature.id, "code": nature.code, "name": nature.name} if nature else None,
            "rule_code": snapshot.get("rule_code") or (rule.rule_code if rule else None),
            "old_section": snapshot.get("old_section") or (rule.old_section if rule else None),
            "new_section": snapshot.get("new_section") or (rule.new_section if rule else None),
            "invoice_amount": invoice_amount,
            "taxable_base": _money(tds.taxable_base),
            "tds_rate": tds.tds_rate,
            "tds_amount": tds_amount,
            "net_payable": (invoice_amount or Decimal("0.00")) - tds_amount,
            "determination_status": tds.determination_status,
            "tds_tracking_status": tracking_status,
            "tds_tracking_status_label": _STATUS_LABELS.get(tracking_status, tracking_status),
            "deduction_date": tracking.deduction_date if tracking else None,
            "deposit_date": tracking.deposit_date if tracking else None,
            "challan_number": tracking.challan_number if tracking else None,
            "filing_date": tracking.filing_date if tracking else None,
            "filing_reference": tracking.filing_reference if tracking else None,
            "allowed_actions": allowed_actions(tds.determination_status, tracking_status),
        }

    def list_tds_invoices(self, search=None, tds_status=None, payment_nature=None, determination_status=None,
                          invoice_status=None, vendor_id=None, invoice_date_from=None, invoice_date_to=None,
                          page=1, page_size=20) -> dict:
        tracking_statuses = self._codes(tds_status)
        unknown = [s for s in tracking_statuses or [] if s not in _STATUS_LABELS]
        if unknown:
            raise ValueError(f"tds_status must be one of {', '.join(_STATUS_LABELS)}")
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 20), 1), MAX_PAGE_SIZE)
        rows, total = self.dao.list_tds_invoices(
            search, tracking_statuses, payment_nature, determination_status, self._codes(invoice_status),
            vendor_id, invoice_date_from, invoice_date_to, (page - 1) * page_size, page_size,
        )
        return {"items": [self._row_view(r) for r in rows], "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def _codes(value: Optional[str]):
        if not value:
            return None
        return [v.strip().upper() for v in value.split(",") if v.strip()] or None

    def get_tds_detail(self, invoice_id: int) -> dict:
        row = self._require_row(invoice_id)
        invoice, _, _, tds, _, rule, _ = row
        view = self._row_view(row)
        tracking = self.dao.get_tracking(invoice_id)
        payment = PaymentTrackingService(self.db).get_invoice_payments(invoice_id)

        view["determination"] = {
            "tds_applicable": tds.tds_applicable,
            "determination_status": tds.determination_status,
            "determination_reason": tds.determination_reason,
            "threshold_amount": tds.threshold_amount,
            "threshold_type": tds.threshold_type,
            "pan_status": tds.pan_status,
            "entity_type": tds.entity_type,
            "rule_name": (tds.rule_snapshot or {}).get("rule_name") or (rule.rule_name if rule else None),
            "rule_snapshot": tds.rule_snapshot,
            "determined_at": tds.determined_at,
            "determined_by": tds.determined_by,
            "verified_at": tds.verified_at,
            "verified_by": tds.verified_by,
        }
        view["payment"] = {
            k: payment[k]
            for k in ("status_code", "status_name", "net_payable", "amount_paid", "pending_amount",
                      "remaining_amount", "last_payment_date", "payment_count")
        }
        view["tracking"] = {
            "tracking_status": view["tds_tracking_status"],
            "deduction_date": tracking.deduction_date if tracking else None,
            "challan_number": tracking.challan_number if tracking else None,
            "bsr_code": tracking.bsr_code if tracking else None,
            "deposit_date": tracking.deposit_date if tracking else None,
            "filing_date": tracking.filing_date if tracking else None,
            "filing_reference": tracking.filing_reference if tracking else None,
            "remarks": tracking.remarks if tracking else None,
            "updated_by": tracking.updated_by if tracking else None,
            "updated_at": tracking.updated_at if tracking else None,
        }
        view["documents"] = [tds_document_view(d) for d in (tracking.documents if tracking else [])]
        view["activity"] = [
            {
                "action": a.action,
                "changed_at": a.changed_at,
                "changed_by": a.changed_by,
                "old_values": a.old_values,
                "new_values": a.new_values,
            }
            for a in self.dao.list_tds_audit(invoice_id)
        ]
        return view

    def _require_row(self, invoice_id: int):
        row = self.dao.get_tds_invoice(invoice_id)
        if row is None:
            raise TdsTrackingNotFoundError(f"Invoice {invoice_id} not found or has no applicable TDS")
        return row

    # =========================================================
    # Activities
    # =========================================================

    def record_deduction(self, invoice_id: int, data, user_id) -> dict:
        def apply(tracking, invoice, errors):
            date = self._date(data.deduction_date, "Deduction Date", errors)
            if date and invoice.invoice_date and date < invoice.invoice_date:
                errors.append("Deduction Date cannot be before the invoice date")
            if date and tracking.deposit_date and date > tracking.deposit_date:
                errors.append("Deduction Date cannot be after the deposit date")
            if not errors:
                tracking.deduction_date = date
            return {"deduction_date": date}

        return self._record(invoice_id, ACTION_DEDUCTION, TRACKING_STATUS_DEDUCTED, "INVOICE_TDS_DEDUCTION_RECORDED", data, user_id, apply)

    def record_deposit(self, invoice_id: int, data, user_id, commit: bool = True) -> Optional[dict]:
        def apply(tracking, invoice, errors):
            date = self._date(data.deposit_date, "TDS Payment Date", errors)
            if date and tracking.deduction_date and date < tracking.deduction_date:
                errors.append("TDS Payment Date cannot be before the deduction date")
            challan = self._reference(data.challan_number, "Challan Number", 50, errors)
            bsr = (data.bsr_code or "").strip() or None
            if bsr and not _BSR_RE.match(bsr):
                errors.append("BSR Code must be 7 digits")
            if not errors:
                tracking.deposit_date, tracking.challan_number, tracking.bsr_code = date, challan, bsr
            return {"deposit_date": date, "challan_number": challan, "bsr_code": bsr}

        return self._record(invoice_id, ACTION_DEPOSIT, TRACKING_STATUS_DEPOSITED, "INVOICE_TDS_DEPOSIT_RECORDED", data, user_id, apply, commit)

    def record_filing(self, invoice_id: int, data, user_id, commit: bool = True) -> Optional[dict]:
        def apply(tracking, invoice, errors):
            date = self._date(data.filing_date, "Filing Date", errors)
            if date and tracking.deposit_date and date < tracking.deposit_date:
                errors.append("Filing Date cannot be before the TDS payment date")
            reference = self._reference(data.filing_reference, "Filing Reference", 100, errors)
            if not errors:
                tracking.filing_date, tracking.filing_reference = date, reference
            return {"filing_date": date, "filing_reference": reference}

        return self._record(invoice_id, ACTION_FILING, TRACKING_STATUS_FILED, "INVOICE_TDS_FILING_RECORDED", data, user_id, apply, commit)

    def _record(self, invoice_id, action, target_status, audit_action, data, user_id, apply, commit: bool = True) -> Optional[dict]:
        """commit=False (shared challan / quarterly filing, Phase 5): run the same checks and writes
        but leave the transaction to the caller, so a challan covering many invoices is recorded for
        all of them or for none. Errors are raised without a rollback in that mode."""
        try:
            invoice, _, _, tds, _, _, _ = self._require_row(invoice_id)
            if tds.determination_status != DETERMINATION_STATUS_VERIFIED:
                raise ValueError("TDS must be verified by Finance before TDS activity can be recorded")
            tracking = self._get_or_create_tracking(invoice_id, user_id)
            current = tracking.tracking_status
            if current not in _ACTION_FROM[action]:
                label = next(a["label"] for a in ACTIONS if a["value"] == action)
                raise ValueError(f"'{label}' is not allowed while TDS status is {_STATUS_LABELS.get(current, current)}")

            errors: list[str] = []
            remarks = (data.remarks or "").strip() or None
            if remarks and len(remarks) > 1000:
                errors.append("Remarks cannot exceed 1000 characters")
            old_values = {
                "tracking_status": current,
                "deduction_date": tracking.deduction_date, "deposit_date": tracking.deposit_date,
                "challan_number": tracking.challan_number, "bsr_code": tracking.bsr_code,
                "filing_date": tracking.filing_date, "filing_reference": tracking.filing_reference,
            }
            new_values = apply(tracking, invoice, errors)
            if errors:
                raise ValueError("; ".join(errors))

            tracking.tracking_status = target_status
            if remarks is not None:
                tracking.remarks = remarks
            tracking.updated_by = _user(user_id)
            tracking.updated_at = datetime.datetime.now()
            self.db.flush()

            self.dao.create_audit_log(AuditLog(
                table_name="invoice",
                record_id=invoice_id,
                action=audit_action,
                changed_by=_user(user_id),
                old_values=_jsonable({k: v for k, v in old_values.items() if v is not None}) or None,
                new_values=_jsonable({**new_values, "tracking_status": target_status, "remarks": remarks,
                                      "correction": current == target_status}),
            ))
            if not commit:
                return None
            self.db.commit()
            return self.get_tds_detail(invoice_id)
        except Exception:
            if commit:
                self.db.rollback()
            raise

    def _get_or_create_tracking(self, invoice_id: int, user_id) -> InvoiceTdsTracking:
        tracking = self.dao.get_tracking_locked(invoice_id)
        if tracking is None:
            tracking = self.dao.add(InvoiceTdsTracking(
                invoice_id=invoice_id, tracking_status=TRACKING_STATUS_PENDING,
                created_by=_user(user_id), updated_by=_user(user_id),
            ))
        return tracking

    @staticmethod
    def _date(value, label, errors) -> Optional[datetime.date]:
        if value is None:
            errors.append(f"{label} is required")
            return None
        if value > datetime.date.today():
            errors.append(f"{label} cannot be in the future")
        return value

    @staticmethod
    def _reference(value, label, max_length, errors) -> Optional[str]:
        text = (value or "").strip()
        if not text:
            errors.append(f"{label} is required")
            return None
        if len(text) > max_length or not _REFERENCE_RE.match(text):
            errors.append(f"{label} may contain only letters, digits, spaces and / - _ . (max {max_length})")
            return None
        return text

    # =========================================================
    # Documents
    # =========================================================

    def upload_document(self, invoice_id: int, filename: str, content: bytes, content_type: Optional[str],
                        document_type: str, user_id) -> dict:
        from Backend.API_Layer.utils.s3_utils import upload_to_s3

        try:
            _, _, _, tds, _, _, _ = self._require_row(invoice_id)
            if tds.determination_status != DETERMINATION_STATUS_VERIFIED:
                raise ValueError("TDS must be verified by Finance before TDS documents can be uploaded")
            document_type = (document_type or "OTHER").strip().upper()
            if document_type not in _TDS_DOCUMENT_TYPE_VALUES:
                raise ValueError(f"document_type must be one of {', '.join(sorted(_TDS_DOCUMENT_TYPE_VALUES))}")

            tracking = self._get_or_create_tracking(invoice_id, user_id)
            upload = upload_to_s3(filename, content, content_type, prefix="tds/")
            document = self.dao.add(InvoiceTdsDocument(
                invoice_tds_tracking_id=tracking.id,
                document_type=document_type,
                file_name=filename,
                file_path=upload["filepath"],
                content_type=content_type,
                file_size=len(content),
                uploaded_by=_user(user_id),
            ))
            self.dao.create_audit_log(AuditLog(
                table_name="invoice",
                record_id=invoice_id,
                action="INVOICE_TDS_DOCUMENT_UPLOADED",
                changed_by=_user(user_id),
                new_values={"document_id": document.id, "document_type": document_type, "file_name": filename},
            ))
            self.db.commit()
            self.db.refresh(document)
            return tds_document_view(document)
        except Exception:
            self.db.rollback()
            raise

    def get_document(self, invoice_id: int, document_id: int) -> InvoiceTdsDocument:
        document = self.dao.get_document(invoice_id, document_id)
        if document is None:
            raise TdsTrackingNotFoundError(f"Document {document_id} not found for invoice {invoice_id}")
        return document


def _jsonable(values: dict) -> dict:
    return {
        k: (v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v)
        for k, v in values.items()
    }
