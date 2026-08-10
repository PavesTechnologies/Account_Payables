from typing import List, Optional
from Backend.Data_Access_Layer.models.invoice import (
    Invoice,
    InvoiceAttachment,
    InvoiceLine,
    InvoiceIssue,
)

class InvoiceDAO:
    def __init__(self, db):
        self.db = db

    def create_invoice(self, invoice: Invoice) -> Invoice:
        self.db.add(invoice)
        self.db.flush()
        return invoice