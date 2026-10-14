# Backend/Business_Layer/services/vendor_note_service.py
"""Credit and debit notes (P2) - record a vendor's credit note or our debit note, and apply it to
one of that vendor's unpaid invoices.

Effects of applying a note to an invoice (all audited on the invoice):
  * payable       = net amount - TDS - applied notes   (applied_notes_total, used by
                    PaymentService._net_payable and the reporting row model, so the payment limit,
                    the PAID threshold, dashboards and reports all agree)
  * TDS           while the deduction is not yet recorded, the TDS base drops by the note's taxable
                    value and the TDS is recalculated at the same rate; once deducted, TDS stays as
                    deducted (correct it in the quarterly return) and the note says so
  * status        an invoice whose payable is now fully paid moves to PAID
  * GST           a vendor credit note's GST reduces the input credit claimed (GstItcService.claim)

A debit note is a commercial document: it carries no GST (the vendor's credit note does).
"""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, select, text

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.tds import InvoiceTds, InvoiceTdsTracking
from Backend.Data_Access_Layer.models.vendor import Vendor
from Backend.Data_Access_Layer.models.vendor_note import (
    CREDIT_NOTE,
    DEBIT_NOTE,
    NOTE_APPLIED,
    NOTE_CANCELLED,
    NOTE_OPEN,
    NOTE_TYPES,
    VendorNote,
)

logger = logging.getLogger(__name__)

VIEW_PERMISSIONS = ["VENDOR_NOTE_MANAGE", "PAYMENT_VIEW", "PAYMENT_PROCESS", "INVOICE_VIEW", "AP_AUTOMATION_MANAGE"]
MANAGE_PERMISSIONS = ["VENDOR_NOTE_MANAGE", "PAYMENT_PROCESS", "AP_AUTOMATION_MANAGE"]
APPLICABLE_STATUSES = ("APPROVED", "READY_FOR_PAYMENT", "PARTIALLY_PAID")
CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
S3_PREFIX = "vendor-notes/"

_table_ready = False


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS, ROUND_HALF_UP)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _notes_table_exists(db) -> bool:
    """Payables must work exactly as before until the migration has run."""
    global _table_ready
    if not _table_ready:
        _table_ready = bool(db.execute(text("select to_regclass('ap.vendor_note')")).scalar())
    return _table_ready


def applied_notes_totals(db, invoice_ids: Iterable[int]) -> Dict[int, Decimal]:
    ids = [i for i in invoice_ids if i is not None]
    if not ids:
        return {}
    try:
        if not _notes_table_exists(db):
            return {}
        rows = db.execute(select(VendorNote.applied_invoice_id, func.sum(VendorNote.total_amount)).where(
            VendorNote.applied_invoice_id.in_(ids), VendorNote.status == NOTE_APPLIED).group_by(VendorNote.applied_invoice_id)).all()
    except (AttributeError, TypeError):  # a test double without a real session
        return {}
    return {invoice_id: _money(total) for invoice_id, total in rows}


def applied_notes_total(db, invoice_id: int) -> Decimal:
    return applied_notes_totals(db, [invoice_id]).get(invoice_id, ZERO)


class VendorNoteService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------ helpers
    def _audit(self, table, record_id, action, user_id, new, old=None):
        self.db.add(AuditLog(table_name=table, record_id=record_id, action=action, changed_by=str(user_id),
                             old_values=old, new_values=new))

    def _status(self, invoice: Invoice) -> Optional[str]:
        row = self.db.get(StatusMaster, invoice.status_id) if invoice.status_id else None
        return row.status_code if row else None

    def _require(self, note_id: int) -> VendorNote:
        note = self.db.get(VendorNote, note_id)
        if note is None:
            raise LookupError(f"Note {note_id} not found")
        return note

    def payable_before_notes(self, invoice: Invoice) -> Decimal:
        from Backend.Business_Layer.services.tds_determination_service import compute_payable_amount
        tds = self.db.execute(select(InvoiceTds).where(InvoiceTds.invoice_id == invoice.invoice_id)).scalar_one_or_none()
        return _money(compute_payable_amount(invoice.net_amount, tds))

    def outstanding(self, invoice: Invoice) -> Decimal:
        pending = self.db.execute(text("""
            select coalesce(sum(pi.allocated_amount), 0) from ap.payment_invoice pi
            join ap.payment p on p.payment_id = pi.payment_id
            join ap.status_master s on s.status_id = p.status_id
            where pi.invoice_id = :i and s.status_code in ('SCHEDULED', 'SENT')"""), {"i": invoice.invoice_id}).scalar()
        return (self.payable_before_notes(invoice) - applied_notes_total(self.db, invoice.invoice_id)
                - _money(invoice.amount_paid) - _money(pending))

    # ------------------------------------------------------------------ record
    def record(self, data: Dict[str, Any], user_id, document: Optional[Tuple[str, bytes, Optional[str]]] = None) -> VendorNote:
        note_type = (data.get("note_type") or "").upper()
        if note_type not in NOTE_TYPES:
            raise ValueError("Note type must be CREDIT_NOTE (from the vendor) or DEBIT_NOTE (raised by us)")
        vendor_id = data.get("vendor_id")
        if not vendor_id or self.db.get(Vendor, int(vendor_id)) is None:
            raise ValueError("Vendor not found")
        number = str(data.get("note_number") or "").strip()
        if not number:
            raise ValueError("Note number is required")
        note_date = data.get("note_date")
        if isinstance(note_date, str):
            note_date = datetime.date.fromisoformat(note_date)
        if note_date is None or note_date > datetime.date.today():
            raise ValueError("Note date is required and cannot be in the future")
        reason = str(data.get("reason") or "").strip()
        if len(reason) < 5:
            raise ValueError("Give the reason for the note (at least 5 characters)")
        taxable = _money(data.get("taxable_value"))
        if taxable <= 0:
            raise ValueError("Taxable value must be greater than zero")
        cgst, sgst, igst = (_money(data.get(k)) for k in ("cgst", "sgst", "igst"))
        if note_type == DEBIT_NOTE and (cgst or sgst or igst):
            raise ValueError("A debit note we raise carries no GST - ask the vendor for a GST credit note instead")
        if (cgst or sgst) and igst:
            raise ValueError("Use either CGST + SGST (same state) or IGST (other state), not both")
        reference = data.get("reference_invoice_id")
        if reference:
            invoice = self.db.get(Invoice, int(reference))
            if invoice is None or invoice.vendor_id != int(vendor_id):
                raise ValueError("The referenced invoice is not from this vendor")
            if invoice.invoice_date and note_date < invoice.invoice_date:
                raise ValueError("A note cannot be dated before the invoice it corrects")
        if self.db.execute(select(VendorNote.note_id).where(VendorNote.vendor_id == int(vendor_id),
                                                            VendorNote.note_type == note_type,
                                                            VendorNote.note_number == number)).first():
            raise ValueError(f"{number} is already recorded for this vendor")

        note = VendorNote(note_type=note_type, vendor_id=int(vendor_id), note_number=number[:60], note_date=note_date,
                          reason=reason, taxable_value=taxable, cgst=cgst, sgst=sgst, igst=igst,
                          total_amount=taxable + cgst + sgst + igst, status=NOTE_OPEN,
                          reference_invoice_id=int(reference) if reference else None, created_by=str(user_id))
        if document is not None:
            from Backend.API_Layer.utils.s3_utils import upload_to_s3
            name, content, ctype = document
            stored = upload_to_s3(name, content, ctype, prefix=S3_PREFIX)
            note.file_name, note.file_path, note.content_type = name[:255], stored["filepath"], ctype
        self.db.add(note)
        self.db.flush()
        self._audit("vendor_note", note.note_id, f"{note_type}_RECORDED", user_id, {
            "note_number": number, "vendor_id": note.vendor_id, "total_amount": str(note.total_amount),
            "reference_invoice_id": note.reference_invoice_id, "reason": reason})
        if note.reference_invoice_id:
            self._audit("invoice", note.reference_invoice_id, f"{note_type}_RECEIVED" if note_type == CREDIT_NOTE else "DEBIT_NOTE_RAISED",
                        user_id, {"note_id": note.note_id, "note_number": number, "total_amount": str(note.total_amount)})
        self.db.commit()
        if data.get("apply_to_invoice_id"):
            return self.apply(note.note_id, int(data["apply_to_invoice_id"]), user_id)
        return note

    # ------------------------------------------------------------------ apply
    def apply(self, note_id: int, invoice_id: int, user_id) -> VendorNote:
        note = self._require(note_id)
        if note.status != NOTE_OPEN:
            raise ValueError(f"Only an open note can be applied (this one is {note.status.lower()})")
        invoice = self.db.get(Invoice, invoice_id)
        if invoice is None:
            raise LookupError(f"Invoice {invoice_id} not found")
        if invoice.vendor_id != note.vendor_id:
            raise ValueError("A note can only be applied to an invoice of the same vendor")
        status = self._status(invoice)
        if status not in APPLICABLE_STATUSES:
            raise ValueError(f"Apply notes to an approved, unpaid invoice (this one is {status}); "
                             "keep the note open and apply it to the vendor's next invoice")
        tds = self.db.execute(select(InvoiceTds).where(InvoiceTds.invoice_id == invoice_id)).scalar_one_or_none()
        tracking = self.db.execute(select(InvoiceTdsTracking).where(InvoiceTdsTracking.invoice_id == invoice_id)).scalar_one_or_none()
        deducted = tracking is not None and tracking.tracking_status not in (None, "TDS_PENDING")
        tds_change, tds_note = ZERO, None
        if tds is not None and tds.tds_applicable and tds.tds_amount:
            if deducted:
                tds_note = "TDS already deducted on the original amount - correct it in the quarterly TDS return."
            else:
                old_base, old_tds = _money(tds.taxable_base), _money(tds.tds_amount)
                new_base = max(old_base - note.taxable_value, ZERO)
                new_tds = _money(new_base * Decimal(str(tds.tds_rate)) / 100)
                tds_change = old_tds - new_tds
                tds.taxable_base, tds.tds_amount = new_base, new_tds
                self._audit("invoice", invoice_id, "INVOICE_TDS_ADJUSTED", user_id,
                            {"taxable_base": str(new_base), "tds_amount": str(new_tds), "note_number": note.note_number},
                            {"taxable_base": str(old_base), "tds_amount": str(old_tds)})
                tds_note = f"TDS base lowered by {note.taxable_value:,}; TDS {old_tds:,} -> {new_tds:,}"
        # what is still owed once TDS is recalculated - the note may not exceed it
        owed = self.outstanding(invoice)
        if note.total_amount > owed:
            self.db.rollback()
            raise ValueError(f"The note ({note.total_amount:,}) is more than this invoice's outstanding {owed:,}")

        note.status, note.applied_invoice_id, note.applied_by, note.applied_at = NOTE_APPLIED, invoice_id, str(user_id), _now()
        note.tds_adjusted, note.tds_note, note.updated_at = tds_change, tds_note, _now()
        self.db.flush()
        self._audit("invoice", invoice_id, f"{note.note_type}_APPLIED", user_id, {
            "note_id": note.note_id, "note_number": note.note_number, "amount": str(note.total_amount),
            "tds_adjusted": str(tds_change), "outstanding_after": str(owed - note.total_amount)})
        if owed - note.total_amount <= 0 and _money(invoice.amount_paid) > 0:
            from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
            paid = InvoiceDAO(self.db).get_status_by_code("PAID")
            if paid is not None:
                invoice.status_id, invoice.updated_by = paid.status_id, str(user_id)
                self._audit("invoice", invoice_id, "INVOICE_SETTLED_BY_NOTE", user_id,
                            {"status_code": "PAID", "note_number": note.note_number}, {"status_code": status})
        self.db.commit()
        return note

    def cancel(self, note_id: int, reason: str, user_id) -> VendorNote:
        note = self._require(note_id)
        if note.status != NOTE_OPEN:
            raise ValueError("Only an open (not yet applied) note can be cancelled")
        if len((reason or "").strip()) < 5:
            raise ValueError("Give a reason (at least 5 characters)")
        note.status, note.cancelled_by, note.cancel_reason, note.updated_at = NOTE_CANCELLED, str(user_id), reason.strip()[:500], _now()
        self._audit("vendor_note", note_id, "NOTE_CANCELLED", user_id, {"reason": note.cancel_reason})
        self.db.commit()
        return note

    # ------------------------------------------------------------------ views
    def view(self, note: VendorNote, vendor_names: Dict[int, str], numbers: Dict[int, str]) -> dict:
        return {
            "note_id": note.note_id, "note_type": note.note_type, "vendor_id": note.vendor_id,
            "vendor_name": vendor_names.get(note.vendor_id), "note_number": note.note_number, "note_date": note.note_date,
            "reason": note.reason, "taxable_value": note.taxable_value, "cgst": note.cgst, "sgst": note.sgst,
            "igst": note.igst, "gst": note.cgst + note.sgst + note.igst, "total_amount": note.total_amount,
            "status": note.status, "reference_invoice_id": note.reference_invoice_id,
            "reference_invoice_number": numbers.get(note.reference_invoice_id), "applied_invoice_id": note.applied_invoice_id,
            "applied_invoice_number": numbers.get(note.applied_invoice_id), "tds_adjusted": note.tds_adjusted,
            "tds_note": note.tds_note, "itc_period": note.itc_period, "has_document": bool(note.file_path),
            "created_by": note.created_by, "created_at": note.created_at, "applied_at": note.applied_at,
            "cancel_reason": note.cancel_reason,
        }

    def list(self, status: Optional[str] = None, note_type: Optional[str] = None, vendor_id: Optional[int] = None) -> Dict[str, Any]:
        stmt = select(VendorNote).order_by(VendorNote.note_date.desc(), VendorNote.note_id.desc())
        if status:
            stmt = stmt.where(VendorNote.status == status.upper())
        if note_type:
            stmt = stmt.where(VendorNote.note_type == note_type.upper())
        if vendor_id:
            stmt = stmt.where(VendorNote.vendor_id == vendor_id)
        notes = self.db.execute(stmt).scalars().all()
        vendor_names = dict(self.db.execute(select(Vendor.vendor_id, Vendor.vendor_name)).all())
        ids = {i for n in notes for i in (n.reference_invoice_id, n.applied_invoice_id) if i}
        numbers = dict(self.db.execute(select(Invoice.invoice_id, Invoice.invoice_number).where(Invoice.invoice_id.in_(ids))).all()) if ids else {}
        rows = [self.view(n, vendor_names, numbers) for n in notes]
        open_rows = [r for r in rows if r["status"] == NOTE_OPEN]
        return {"notes": rows, "summary": {
            "open": len(open_rows), "open_amount": sum((r["total_amount"] for r in open_rows), ZERO),
            "applied": sum(1 for r in rows if r["status"] == NOTE_APPLIED),
            "credit_gst": sum((r["gst"] for r in rows if r["note_type"] == CREDIT_NOTE and r["status"] != NOTE_CANCELLED), ZERO)}}

    def applicable_invoices(self, vendor_id: int) -> List[dict]:
        rows = self.db.execute(select(Invoice, StatusMaster.status_code).join(
            StatusMaster, StatusMaster.status_id == Invoice.status_id).where(
            Invoice.vendor_id == vendor_id, StatusMaster.status_code.in_(APPLICABLE_STATUSES)).order_by(Invoice.invoice_date)).all()
        return [{"invoice_id": i.invoice_id, "invoice_number": i.invoice_number, "invoice_date": i.invoice_date,
                 "status_code": s, "outstanding": self.outstanding(i)} for i, s in rows]

    def document(self, note_id: int) -> VendorNote:
        note = self._require(note_id)
        if not note.file_path:
            raise LookupError("This note has no document")
        return note
