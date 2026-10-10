# Backend/Data_Access_Layer/dao/review_workbench_dao.py
"""Read-only queries behind the review workbench (invoice_review_automation_service.py):
invoices waiting for review / send, their coding suggestions and readiness inputs."""
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func

from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceIssue
from Backend.Data_Access_Layer.models.invoice_upload_batch import InvoiceUploadBatch, InvoiceUploadBatchItem
from Backend.Data_Access_Layer.models.master import Currency, StatusMaster
from Backend.Data_Access_Layer.models.purchase import Department, PurchaseCategory, PurchaseRequisition
from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder
from Backend.Data_Access_Layer.models.tds import InvoiceTds
from Backend.Data_Access_Layer.models.vendor import Vendor, VendorEngagement


class ReviewWorkbenchDAO:
    def __init__(self, db):
        self.db = db

    def invoices_in_status(self, status_codes: Sequence[str], limit: int,
                           invoice_ids: Optional[Sequence[int]] = None) -> List[tuple]:
        """(invoice, vendor_name, status_code, currency_code), oldest first (FIFO review)."""
        query = (
            self.db.query(Invoice, Vendor.vendor_name, StatusMaster.status_code, Currency.currency_code)
            .join(StatusMaster, StatusMaster.status_id == Invoice.status_id)
            .join(Vendor, Vendor.vendor_id == Invoice.vendor_id)
            .outerjoin(Currency, Currency.currency_id == Invoice.currency_id)
            .filter(StatusMaster.status_code.in_(list(status_codes)))
        )
        if invoice_ids is not None:
            query = query.filter(Invoice.invoice_id.in_(list(invoice_ids)))
        return (
            query.order_by(Invoice.created_at.asc(), Invoice.invoice_id.asc())
            .limit(limit)
            .all()
        )

    def inbound_document_ids(self, invoice_ids: Sequence[int]) -> Dict[int, int]:
        if not invoice_ids:
            return {}
        rows = (self.db.query(InboundDocument.invoice_id, func.min(InboundDocument.inbound_document_id))
                .filter(InboundDocument.invoice_id.in_(list(invoice_ids)))
                .group_by(InboundDocument.invoice_id).all())
        return {r[0]: r[1] for r in rows}

    def upload_items(self, invoice_ids: Sequence[int]) -> Dict[int, tuple]:
        """invoice_id -> (validation_result, batch_id, source_type, sender_known) for bulk / email invoices."""
        if not invoice_ids:
            return {}
        rows = (self.db.query(InvoiceUploadBatchItem.invoice_id, InvoiceUploadBatchItem.validation_result,
                              InvoiceUploadBatch.batch_id, InvoiceUploadBatch.source_type, InvoiceUploadBatch.sender_known)
                .join(InvoiceUploadBatch, InvoiceUploadBatch.batch_id == InvoiceUploadBatchItem.batch_id)
                .filter(InvoiceUploadBatchItem.invoice_id.in_(list(invoice_ids)),
                        InvoiceUploadBatchItem.status == "CREATED")
                .all())
        return {r[0]: tuple(r[1:]) for r in rows}

    def open_issue_counts(self, invoice_ids: Sequence[int]) -> Dict[int, int]:
        if not invoice_ids:
            return {}
        rows = (self.db.query(InvoiceIssue.invoice_id, func.count())
                .filter(InvoiceIssue.invoice_id.in_(list(invoice_ids)), InvoiceIssue.resolved_at.is_(None))
                .group_by(InvoiceIssue.invoice_id).all())
        return {r[0]: r[1] for r in rows}

    def tds_rows(self, invoice_ids: Sequence[int]) -> Dict[int, InvoiceTds]:
        if not invoice_ids:
            return {}
        return {t.invoice_id: t for t in self.db.query(InvoiceTds).filter(InvoiceTds.invoice_id.in_(list(invoice_ids))).all()}

    def vendor_mappings(self, vendor_ids: Sequence[int]) -> Dict[int, List[tuple]]:
        """vendor_id -> [(department_id, purchase_category_id, is_primary)] from vendor onboarding."""
        if not vendor_ids:
            return {}
        out: Dict[int, List[tuple]] = {}
        for vendor_id, dept, cat, primary in (
            self.db.query(VendorEngagement.vendor_id, VendorEngagement.department_id,
                          VendorEngagement.purchase_category_id, VendorEngagement.is_primary)
            .filter(VendorEngagement.vendor_id.in_(list(vendor_ids))).all()
        ):
            out.setdefault(vendor_id, []).append((dept, cat, bool(primary)))
        return out

    def last_coded_non_po(self, vendor_ids: Sequence[int], exclude_ids: Sequence[int]) -> Dict[int, Tuple[int, int]]:
        """vendor_id -> (department_id, purchase_category_id) of that vendor's most recent coded NON_PO invoice."""
        if not vendor_ids:
            return {}
        rows = (self.db.query(Invoice.vendor_id, Invoice.department_id, Invoice.purchase_category_id)
                .filter(Invoice.vendor_id.in_(list(vendor_ids)), Invoice.invoice_type == "NON_PO",
                        Invoice.department_id.isnot(None), Invoice.purchase_category_id.isnot(None),
                        ~Invoice.invoice_id.in_(list(exclude_ids) or [-1]))
                .order_by(Invoice.vendor_id, Invoice.updated_at.desc(), Invoice.invoice_id.desc()).all())
        out: Dict[int, Tuple[int, int]] = {}
        for vendor_id, dept, cat in rows:
            out.setdefault(vendor_id, (dept, cat))
        return out

    def po_coding(self, po_ids: Sequence[int]) -> Dict[int, Tuple[Optional[int], Optional[int], Optional[str]]]:
        """po_id -> (department_id, purchase_category_id, po_number) from the PO's requisition."""
        if not po_ids:
            return {}
        rows = (self.db.query(PurchaseOrder.po_id, PurchaseRequisition.department_id,
                              PurchaseRequisition.purchase_category_id, PurchaseOrder.po_number)
                .outerjoin(PurchaseRequisition, PurchaseRequisition.id == PurchaseOrder.pr_id)
                .filter(PurchaseOrder.po_id.in_(list(po_ids))).all())
        return {r[0]: (r[1], r[2], r[3]) for r in rows}

    def departments(self) -> Dict[int, Tuple[str, bool]]:
        return {d.id: (d.name, d.is_active) for d in self.db.query(Department).all()}

    def categories(self) -> Dict[int, Tuple[str, bool, int]]:
        return {c.id: (c.name, c.is_active, c.department_id) for c in self.db.query(PurchaseCategory).all()}
