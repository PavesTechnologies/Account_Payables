from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceAttachment
from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
from Backend.Data_Access_Layer.models.master import StatusMaster

class InvoiceDetailsDAO:
    def __init__(self, db):
        self.db = db
    def get_invoice_details_by_id(
        self,
        invoice_id: int,
    ) -> Invoice | None:

        if invoice_id is None:
            return None

        return (
            self.db.query(Invoice)
            .filter(Invoice.invoice_id == invoice_id)
            .first()
        )
    def get_all_invoice_details(self) -> list[Invoice]:
        return self.db.query(Invoice).all()
    def get_status_master_by_id(self, status_id: int) -> StatusMaster | None:
        if status_id is None:
            return None

        result = self.db.query(StatusMaster).filter(StatusMaster.status_id == status_id).first()
        return result.status_code if result else None
    def file_name_by_inbound_document_id(self, inbound_document_id: int) -> str | None:
        if inbound_document_id is None:
            return None

        result = (
            self.db.query(InboundDocument)
            .filter(InboundDocument.inbound_document_id == inbound_document_id)
            .first()
        )
        return result.file_path if result else None