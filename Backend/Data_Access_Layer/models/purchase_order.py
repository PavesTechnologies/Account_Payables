from typing import Optional
import datetime
import decimal

from sqlalchemy import Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base


class PurchaseOrder(Base):
    __tablename__ = 'purchase_order'
    __table_args__ = (
        ForeignKeyConstraint(['currency_id'], ['ap.currency.currency_id'], name='purchase_order_currency_id_fkey'),
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
    po_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    currency_id: Mapped[Optional[int]] = mapped_column(Integer)
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    currency: Mapped[Optional['Currency']] = relationship('Currency', back_populates='purchase_order')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='purchase_order')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='purchase_order')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='po')
    purchase_order_line: Mapped[list['PurchaseOrderLine']] = relationship('PurchaseOrderLine', back_populates='po')
    goods_receipt: Mapped[list['GoodsReceipt']] = relationship('GoodsReceipt', back_populates='po')


class PurchaseOrderLine(Base):
    __tablename__ = 'purchase_order_line'
    __table_args__ = (
        ForeignKeyConstraint(['po_id'], ['ap.purchase_order.po_id'], ondelete='CASCADE', name='purchase_order_line_po_id_fkey'),
        PrimaryKeyConstraint('po_line_id', name='purchase_order_line_pkey'),
        UniqueConstraint('po_id', 'line_number', name='purchase_order_line_po_id_line_number_key'),
        {'schema': 'ap'}
    )

    po_line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(Integer, nullable=False)
    line_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text('1'))
    unit_price: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))

    po: Mapped['PurchaseOrder'] = relationship('PurchaseOrder', back_populates='purchase_order_line')
    goods_receipt: Mapped[list['GoodsReceipt']] = relationship('GoodsReceipt', back_populates='po_line')


class GoodsReceipt(Base):
    __tablename__ = 'goods_receipt'
    __table_args__ = (
        ForeignKeyConstraint(['po_id'], ['ap.purchase_order.po_id'], name='goods_receipt_po_id_fkey'),
        ForeignKeyConstraint(['po_line_id'], ['ap.purchase_order_line.po_line_id'], name='goods_receipt_po_line_id_fkey'),
        PrimaryKeyConstraint('grn_id', name='goods_receipt_pkey'),
        Index('idx_grn_po', 'po_id'),
        {'schema': 'ap'}
    )

    grn_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(Integer, nullable=False)
    received_quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    received_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    po_line_id: Mapped[Optional[int]] = mapped_column(Integer)
    received_by: Mapped[Optional[str]] = mapped_column(String(100))

    po: Mapped['PurchaseOrder'] = relationship('PurchaseOrder', back_populates='goods_receipt')
    po_line: Mapped[Optional['PurchaseOrderLine']] = relationship('PurchaseOrderLine', back_populates='goods_receipt')
