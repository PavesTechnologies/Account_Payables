from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceAttachment

class InvoiceDetailsDao:
    def __init__(self, db):
        self.db = db
    def get_invoice_details_by_id(self, invoice_id):
        if invoice_id is None:
            return None
        result = self.db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
        if result is None:
            return None
        return result