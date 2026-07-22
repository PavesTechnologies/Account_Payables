from typing import Optional
import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, Integer, PrimaryKeyConstraint, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base


class PurchaseOrder(Base):
    __tablename__ = 'purchase_order'
    __table_args__ = (
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='purchase_order_status_id_fkey'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='purchase_order_vendor_id_fkey'),
        PrimaryKeyConstraint('po_id', name='purchase_order_pkey'),
        UniqueConstraint('po_number', name='purchase_order_po_number_key'),
        Index('idx_po_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    po_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String(50), nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='purchase_order')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='purchase_order')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='po')
    goods_receipt: Mapped[list['GoodsReceipt']] = relationship('GoodsReceipt', back_populates='po')


class GoodsReceipt(Base):
    __tablename__ = 'goods_receipt'
    __table_args__ = (
        ForeignKeyConstraint(['po_id'], ['ap.purchase_order.po_id'], name='goods_receipt_po_id_fkey'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='goods_receipt_vendor_id_fkey'),
        PrimaryKeyConstraint('grn_id', name='goods_receipt_pkey'),
        Index('idx_grn_vendor', 'vendor_id'),
        Index('idx_grn_po', 'po_id'),
        {'schema': 'ap'}
    )

    grn_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    po_id: Mapped[Optional[int]] = mapped_column(Integer)
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    po: Mapped[Optional['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='goods_receipt')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='goods_receipt')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='grn')
