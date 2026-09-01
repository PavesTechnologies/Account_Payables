# Backend/Data_Access_Layer/models/purchase_order.py
from typing import Optional, TYPE_CHECKING
import datetime
import decimal
import uuid
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.master import Currency, StatusMaster
    from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceLine
    from Backend.Data_Access_Layer.models.vendor import Vendor
    from Backend.Data_Access_Layer.models.purchase import PurchaseRequisition, Quotation


class PurchaseOrder(Base):
    __tablename__ = 'purchase_order'
    __table_args__ = (
        CheckConstraint('subtotal >= 0', name='chk_po_subtotal'),
        CheckConstraint('tax_amount >= 0', name='chk_po_tax'),
        CheckConstraint('total_amount >= 0', name='chk_po_total'),
        ForeignKeyConstraint(['pr_id'], ['ap.purchase_requisition.id'], name='fk_po_pr'),
        ForeignKeyConstraint(['quotation_id'], ['ap.quotation.id'], name='fk_po_quotation'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='fk_po_status'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='fk_po_vendor'),
        PrimaryKeyConstraint('id', name='purchase_order_pkey'),
        UniqueConstraint('po_number', name='purchase_order_po_number_key'),
        Index('idx_po_pr', 'pr_id'),
        Index('idx_po_quotation', 'quotation_id'),
        Index('idx_po_status', 'status_id'),
        Index('idx_po_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    # DB column is "id"; attribute kept as po_id so existing services still work.
    po_id: Mapped[int] = mapped_column('id', BigInteger, primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String(50), nullable=False)
    pr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vendor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    po_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, server_default=text('CURRENT_DATE'))
    subtotal: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    tax_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    status_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    quotation_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    expected_delivery_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    delivery_location: Mapped[Optional[str]] = mapped_column(String(255))
    payment_terms: Mapped[Optional[str]] = mapped_column(Text)
    delivery_terms: Mapped[Optional[str]] = mapped_column(Text)

    pr: Mapped['PurchaseRequisition'] = relationship('PurchaseRequisition', back_populates='purchase_order')
    quotation: Mapped[Optional['Quotation']] = relationship('Quotation', back_populates='purchase_order')
    status: Mapped['StatusMaster'] = relationship('StatusMaster', back_populates='purchase_order')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='purchase_order')
    goods_receipt: Mapped[list['GoodsReceipt']] = relationship('GoodsReceipt', back_populates='po')
    purchase_order_line: Mapped[list['PurchaseOrderLine']] = relationship(
        'PurchaseOrderLine', back_populates='po', passive_deletes='all'
    )

    # invoice.po_id has no DB FK in this schema — ORM-only join.
    invoice: Mapped[list['Invoice']] = relationship(
        'Invoice', back_populates='po', viewonly=True,
        primaryjoin='foreign(Invoice.po_id) == PurchaseOrder.po_id',
    )


class PurchaseOrderLine(Base):
    __tablename__ = 'purchase_order_line'
    __table_args__ = (
        CheckConstraint('quantity > 0', name='chk_po_line_quantity'),
        CheckConstraint('tax_amount >= 0', name='chk_po_line_tax_amount'),
        CheckConstraint('tax_rate >= 0', name='chk_po_line_tax_rate'),
        CheckConstraint('total_amount >= 0', name='chk_po_line_total'),
        CheckConstraint('unit_price >= 0', name='chk_po_line_unit_price'),
        ForeignKeyConstraint(['po_id'], ['ap.purchase_order.id'], ondelete='CASCADE', name='fk_po_line_po'),
        ForeignKeyConstraint(['pr_line_id'], ['ap.purchase_requisition_line.id'], name='fk_po_line_pr_line'),
        PrimaryKeyConstraint('id', name='purchase_order_line_pkey'),
        Index('idx_po_line_po', 'po_id'),
        Index('idx_po_line_pr_line', 'pr_line_id'),
        {'schema': 'ap'}
    )

    po_line_id: Mapped[int] = mapped_column('id', BigInteger, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    tax_rate: Mapped[decimal.Decimal] = mapped_column(Numeric(8, 4), nullable=False, server_default=text('0'))
    tax_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    pr_line_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    description: Mapped[Optional[str]] = mapped_column(Text)
    uom: Mapped[Optional[str]] = mapped_column(String(50))

    po: Mapped['PurchaseOrder'] = relationship('PurchaseOrder', back_populates='purchase_order_line')
    pr_line: Mapped[Optional['PurchaseRequisitionLine']] = relationship(
        'PurchaseRequisitionLine', back_populates='purchase_order_line'
    )

    # goods_receipt_line.po_line_id / invoice_line.po_line_id have no DB FK — ORM-only joins.
    goods_receipt_line: Mapped[list['GoodsReceiptLine']] = relationship(
        'GoodsReceiptLine', back_populates='po_line', viewonly=True,
        primaryjoin='foreign(GoodsReceiptLine.po_line_id) == PurchaseOrderLine.po_line_id',
    )
    invoice_line: Mapped[list['InvoiceLine']] = relationship(
        'InvoiceLine', back_populates='po_line', viewonly=True,
        primaryjoin='foreign(InvoiceLine.po_line_id) == PurchaseOrderLine.po_line_id',
    )


class GoodsReceipt(Base):
    __tablename__ = 'goods_receipt'
    __table_args__ = (
        ForeignKeyConstraint(['po_id'], ['ap.purchase_order.id'], name='fk_goods_receipt_po'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='goods_receipt_vendor_id_fkey'),
        PrimaryKeyConstraint('grn_id', name='goods_receipt_pkey'),
        Index('idx_grn_po', 'po_id'),
        Index('idx_grn_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    grn_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    po_id: Mapped[Optional[int]] = mapped_column(BigInteger)   # widened: purchase_order.id is bigint
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    grn_number: Mapped[Optional[str]] = mapped_column(String(50))
    receipt_date: Mapped[Optional[datetime.date]] = mapped_column(Date)

    po: Mapped[Optional['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='goods_receipt')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='goods_receipt')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='grn')
    goods_receipt_line: Mapped[list['GoodsReceiptLine']] = relationship(
        'GoodsReceiptLine', back_populates='grn', passive_deletes='all'
    )


class GoodsReceiptLine(Base):
    __tablename__ = 'goods_receipt_line'
    __table_args__ = (
        ForeignKeyConstraint(['grn_id'], ['ap.goods_receipt.grn_id'], ondelete='CASCADE', name='goods_receipt_line_grn_id_fkey'),
        PrimaryKeyConstraint('grn_line_id', name='goods_receipt_line_pkey'),
        Index('idx_grn_line_grn', 'grn_id'),
        Index('idx_grn_line_po_line', 'po_line_id'),
        {'schema': 'ap'}
    )

    grn_line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grn_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    received_quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    po_line_id: Mapped[Optional[int]] = mapped_column(Integer)   # no FK in current schema
    item_code: Mapped[Optional[str]] = mapped_column(String(50))

    grn: Mapped['GoodsReceipt'] = relationship('GoodsReceipt', back_populates='goods_receipt_line')
    po_line: Mapped[Optional['PurchaseOrderLine']] = relationship(
        'PurchaseOrderLine', back_populates='goods_receipt_line', viewonly=True,
        primaryjoin='foreign(GoodsReceiptLine.po_line_id) == PurchaseOrderLine.po_line_id',
    )