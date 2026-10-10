# Backend/Data_Access_Layer/dao/ap_automation_dao.py
"""Queries for touchless PO-invoice automation (ap_automation_service.py). Automation outcomes are
stored as audit_log rows (action AP_AUTOMATION_RESULT) - no table of its own."""
import datetime
import re
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func

from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceLine
from Backend.Data_Access_Layer.models.invoice_upload_batch import InvoiceUploadBatchItem
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder

RESULT_ACTION = "AP_AUTOMATION_RESULT"
# Invoices that no longer bill a PO (excluded from the cumulative "already invoiced" check).
NOT_BILLING_STATUSES = ("REJECTED", "OCR_FAILED", "DRAFT")


def normalize_po_number(value: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


class APAutomationDAO:
    def __init__(self, db):
        self.db = db

    def open_pos_for_vendor(self, vendor_id: int) -> List[PurchaseOrder]:
        return (self.db.query(PurchaseOrder)
                .join(StatusMaster, StatusMaster.status_id == PurchaseOrder.status_id)
                .filter(PurchaseOrder.vendor_id == vendor_id, StatusMaster.status_code == "OPEN").all())

    def find_open_po(self, vendor_id: int, po_number: str) -> Optional[PurchaseOrder]:
        """The vendor's OPEN purchase order whose number matches, ignoring case / spaces / dashes.
        None when there is no match or more than one (never guesses)."""
        wanted = normalize_po_number(po_number)
        if not wanted:
            return None
        matches = [po for po in self.open_pos_for_vendor(vendor_id) if normalize_po_number(po.po_number) == wanted]
        return matches[0] if len(matches) == 1 else None

    def lines(self, invoice_id: int) -> List[InvoiceLine]:
        return (self.db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice_id)
                .order_by(InvoiceLine.line_number).all())

    def invoiced_quantity_elsewhere(self, po_line_ids: Sequence[int], invoice_id: int) -> Dict[int, object]:
        """po_line_id -> quantity already billed on OTHER invoices that still bill the PO."""
        if not po_line_ids:
            return {}
        rows = (self.db.query(InvoiceLine.po_line_id, func.coalesce(func.sum(InvoiceLine.quantity), 0))
                .join(Invoice, Invoice.invoice_id == InvoiceLine.invoice_id)
                .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)
                .filter(InvoiceLine.po_line_id.in_(list(po_line_ids)), Invoice.invoice_id != invoice_id,
                        ~StatusMaster.status_code.in_(NOT_BILLING_STATUSES))
                .group_by(InvoiceLine.po_line_id).all())
        return {r[0]: r[1] for r in rows}

    def upload_item_for_invoice(self, invoice_id: int) -> Optional[InvoiceUploadBatchItem]:
        return (self.db.query(InvoiceUploadBatchItem)
                .filter(InvoiceUploadBatchItem.invoice_id == invoice_id, InvoiceUploadBatchItem.status == "CREATED")
                .order_by(InvoiceUploadBatchItem.item_id.desc()).first())

    def pending_po_invoices(self, limit: int) -> List[int]:
        """Bulk / email PO invoices still waiting for review - candidates for a re-check (e.g. the
        goods receipt was recorded after the invoice arrived)."""
        rows = (self.db.query(Invoice.invoice_id)
                .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)
                .join(InvoiceUploadBatchItem, InvoiceUploadBatchItem.invoice_id == Invoice.invoice_id)
                .filter(StatusMaster.status_code == "OCR_REVIEW_PENDING", Invoice.invoice_type == "PO")
                .order_by(Invoice.created_at.asc()).limit(limit).all())
        return [r[0] for r in rows]

    def latest_results(self, invoice_ids: Sequence[int]) -> Dict[int, dict]:
        if not invoice_ids:
            return {}
        rows = (self.db.query(AuditLog.record_id, AuditLog.new_values, AuditLog.changed_at)
                .filter(AuditLog.table_name == "invoice", AuditLog.action == RESULT_ACTION,
                        AuditLog.record_id.in_(list(invoice_ids)))
                .order_by(AuditLog.record_id, AuditLog.changed_at.desc(), AuditLog.audit_log_id.desc()).all())
        out: Dict[int, dict] = {}
        for record_id, values, changed_at in rows:
            if record_id not in out:
                out[record_id] = {**(values or {}), "at": changed_at}
        return out

    def results_since(self, since: datetime.datetime) -> List[tuple]:
        """(invoice_id, new_values) of every automation result since a date, newest first."""
        return (self.db.query(AuditLog.record_id, AuditLog.new_values)
                .filter(AuditLog.table_name == "invoice", AuditLog.action == RESULT_ACTION,
                        AuditLog.changed_at >= since)
                .order_by(AuditLog.changed_at.desc(), AuditLog.audit_log_id.desc()).all())
