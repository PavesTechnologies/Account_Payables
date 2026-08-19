# Backend/Data_Access_Layer/dao/invoice_dao.py
from typing import List, Optional

from sqlalchemy.orm import selectinload

from Backend.Data_Access_Layer.models.invoice import (
    Invoice,
    InvoiceAttachment,
    InvoiceLine,
    InvoiceIssue,
)
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
from Backend.Data_Access_Layer.models.master import StatusMaster

INVOICE_STATUS_MODULE = "INVOICE"


class InvoiceDAO:
    def __init__(self, db):
        self.db = db

    def create_invoice(self, invoice: Invoice) -> Invoice:
        self.db.add(invoice)
        self.db.flush()
        return invoice

    def create_invoice_attachment(self, attachment: InvoiceAttachment) -> InvoiceAttachment:
        self.db.add(attachment)
        self.db.flush()
        return attachment

    def create_invoice_line(self, line: InvoiceLine) -> InvoiceLine:
        self.db.add(line)
        self.db.flush()
        return line

    def create_invoice_lines(self, lines: List[InvoiceLine]) -> List[InvoiceLine]:
        self.db.add_all(lines)
        self.db.flush()
        return lines

    def create_invoice_issue(self, issue: InvoiceIssue) -> InvoiceIssue:
        self.db.add(issue)
        self.db.flush()
        return issue

    def get_invoice_by_id(self, invoice_id: int) -> Optional[Invoice]:
        return (
            self.db.query(Invoice)
            .options(
                selectinload(Invoice.invoice_line),
                selectinload(Invoice.invoice_attachment),
                selectinload(Invoice.invoice_issue),
            )
            .filter(Invoice.invoice_id == invoice_id)
            .first()
        )

    def get_invoice_by_vendor_and_number(
        self, vendor_id: int, invoice_number: str
    ) -> Optional[Invoice]:
        return (
            self.db.query(Invoice)
            .filter(
                Invoice.vendor_id == vendor_id,
                Invoice.invoice_number == invoice_number,
            )
            .first()
        )

    def get_open_invoice_issues(self, invoice_id: int) -> List[InvoiceIssue]:
        return (
            self.db.query(InvoiceIssue)
            .filter(
                InvoiceIssue.invoice_id == invoice_id,
                InvoiceIssue.resolved_at.is_(None),
            )
            .all()
        )

    def get_status_by_code(self, status_code: str) -> Optional[StatusMaster]:
        return (
            self.db.query(StatusMaster)
            .filter(
                StatusMaster.module_name == INVOICE_STATUS_MODULE,
                StatusMaster.status_code == status_code,
            )
            .first()
        )

    def get_invoices_by_status_code(self, status_code: str) -> List[Invoice]:
        """Path A of the OCR review queue: invoices already created but still
        awaiting the AP Executive's OCR confirmation."""
        return (
            self.db.query(Invoice)
            .join(StatusMaster, Invoice.status_id == StatusMaster.status_id)
            .filter(
                StatusMaster.module_name == INVOICE_STATUS_MODULE,
                StatusMaster.status_code == status_code,
            )
            .order_by(Invoice.created_at.desc())
            .all()
        )

    def get_invoice_by_id_locked(self, invoice_id: int) -> Optional[Invoice]:
        """Row-locks the invoice for the duration of the current transaction —
        used wherever amount_paid/status_id are read-then-written (approval,
        payment allocation) so two concurrent requests can't both act on a
        stale remaining-balance/status."""
        return (
            self.db.query(Invoice)
            .filter(Invoice.invoice_id == invoice_id)
            .with_for_update()
            .first()
        )
    def get_status_details(self, status_id:int):
        return (
            self.db.query(StatusMaster)
            .filter(StatusMaster.status_id == status_id)
            .first()
        )

    def update_invoice(self, invoice: Invoice) -> Invoice:
        self.db.merge(invoice)
        return invoice
    def get_all_statuses(self) -> List[StatusMaster]:
        return (
            self.db.query(StatusMaster)
            .filter(StatusMaster.module_name == INVOICE_STATUS_MODULE)
            .order_by(StatusMaster.display_order)
            .all()
        )
