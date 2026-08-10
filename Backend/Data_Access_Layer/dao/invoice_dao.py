# Backend/Data_Access_Layer/dao/invoice_dao.py
from typing import List, Optional
from Backend.Data_Access_Layer.models.invoice import (
    Invoice,
    InvoiceAttachment,
    InvoiceLine,
    InvoiceIssue,
)
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument

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
    