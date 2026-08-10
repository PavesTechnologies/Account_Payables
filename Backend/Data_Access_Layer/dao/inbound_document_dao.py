# Backend/Data_Access_Layer/dao/inbound_document_dao.py
from typing import Optional

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
