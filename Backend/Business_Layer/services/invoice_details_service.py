from Backend.Data_Access_Layer.dao.invoice_details_dao import InvoiceDetailsDao

class InvoiceDetailsService:
    def __init__(self, db):
        self.invoice_details_dao = InvoiceDetailsDao(db)

    def get_invoice_details_by_id(self, invoice_id):
        return self.invoice_details_dao.get_invoice_details_by_id(invoice_id)