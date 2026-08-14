# Backend/Data_Access_Layer/dao/inbound_document_dao.py
from typing import List, Optional

from Backend.Data_Access_Layer.models.inbound_document import InboundDocument


class InboundDocumentDAO:
    def __init__(self, db):
        self.db = db

    def create_inbound_document(self, inbound_document: InboundDocument) -> InboundDocument:
        self.db.add(inbound_document)
        self.db.flush()
        return inbound_document

    def get_by_id(self, inbound_document_id: int) -> Optional[InboundDocument]:
        return (
            self.db.query(InboundDocument)
            .filter(InboundDocument.inbound_document_id == inbound_document_id)
            .first()
        )

    def get_awaiting_vendor_assignment(self) -> List[InboundDocument]:
        """Path B of the OCR review queue: extraction finished but no vendor
        could be matched, so no Invoice was ever created for this document."""
        return (
            self.db.query(InboundDocument)
            .filter(
                InboundDocument.extraction_status == "EXTRACTED",
                InboundDocument.invoice_id.is_(None),
            )
            .order_by(InboundDocument.received_at.desc())
            .all()
        )
