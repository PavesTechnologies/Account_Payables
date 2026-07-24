from typing import Optional, TYPE_CHECKING
import datetime
import decimal

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.invoice import Invoice
    from Backend.Data_Access_Layer.models.vendor import Vendor

class InboundDocument(Base):
    __tablename__ = 'inbound_document'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], name='fk_inbound_document_invoice'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='inbound_document_vendor_id_fkey'),
        PrimaryKeyConstraint('inbound_document_id', name='inbound_document_pkey'),
        Index('idx_inbound_document_message_id', 'email_message_id'),
        Index('idx_inbound_document_raw_data', 'raw_extracted_data', postgresql_using='gin'),
        Index('idx_inbound_document_status', 'extraction_status'),
        {'schema': 'ap'}
    )

    inbound_document_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'EMAIL'::character varying"))
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    email_from: Mapped[Optional[str]] = mapped_column(String(200))
    email_subject: Mapped[Optional[str]] = mapped_column(String(255))
    email_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    extraction_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    raw_extracted_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    vendor_id: Mapped[Optional[int]] = mapped_column(Integer)
    invoice_id: Mapped[Optional[int]] = mapped_column(Integer)

    invoice: Mapped[Optional['Invoice']] = relationship('Invoice', foreign_keys=[invoice_id])
    vendor: Mapped[Optional['Vendor']] = relationship('Vendor', back_populates='inbound_document')
