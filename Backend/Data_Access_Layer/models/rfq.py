# Backend/Data_Access_Layer/models/rfq.py
import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKeyConstraint, Index,
    PrimaryKeyConstraint, String, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.master import StatusMaster
    from Backend.Data_Access_Layer.models.purchase import PurchaseRequisition, Quotation
    from Backend.Data_Access_Layer.models.vendor import Vendor


class RFQ(Base):
    __tablename__ = 'rfq'
    __table_args__ = (
        ForeignKeyConstraint(['pr_id'], ['ap.purchase_requisition.id'], ondelete='CASCADE', name='fk_rfq_pr'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='fk_rfq_status'),
        PrimaryKeyConstraint('id', name='rfq_pkey'),
        UniqueConstraint('rfq_number', name='rfq_rfq_number_key'),
        Index('idx_rfq_pr', 'pr_id'),
        Index('idx_rfq_status', 'status_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rfq_number: Mapped[str] = mapped_column(String(50), nullable=False)
    pr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    due_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    closed_by: Mapped[Optional[str]] = mapped_column(String(100))
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    pr: Mapped['PurchaseRequisition'] = relationship('PurchaseRequisition', foreign_keys=[pr_id])
    status: Mapped['StatusMaster'] = relationship('StatusMaster')
    rfq_vendor: Mapped[list['RFQVendor']] = relationship(
        'RFQVendor', back_populates='rfq', passive_deletes='all'
    )
    quotation: Mapped[list['Quotation']] = relationship('Quotation', back_populates='rfq')


class RFQVendor(Base):
    __tablename__ = 'rfq_vendor'
    __table_args__ = (
        ForeignKeyConstraint(['rfq_id'], ['ap.rfq.id'], ondelete='CASCADE', name='fk_rfq_vendor_rfq'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='fk_rfq_vendor_vendor'),
        PrimaryKeyConstraint('id', name='rfq_vendor_pkey'),
        UniqueConstraint('rfq_id', 'vendor_id', name='rfq_vendor_rfq_id_vendor_id_key'),
        Index('idx_rfq_vendor_rfq', 'rfq_id'),
        Index('idx_rfq_vendor_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rfq_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vendor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invited_by: Mapped[str] = mapped_column(String(100), nullable=False)
    invited_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    rfq: Mapped['RFQ'] = relationship('RFQ', back_populates='rfq_vendor')
    vendor: Mapped['Vendor'] = relationship('Vendor')
