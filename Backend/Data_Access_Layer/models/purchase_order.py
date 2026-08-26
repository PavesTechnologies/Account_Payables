from typing import Optional, TYPE_CHECKING
import datetime
import decimal
import decimal
from sqlalchemy import Date, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, Numeric, PrimaryKeyConstraint, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.master import Currency, StatusMaster
    from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceLine
    from Backend.Data_Access_Layer.models.vendor import Vendor


class PurchaseOrder(Base):
    __tablename__ = 'purchase_order'
    __table_args__ = (
        ForeignKeyConstraint(['currency_id'], ['ap.currency.currency_id'], name='purchase_order_currency_id_fkey'),
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
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    po_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    expected_delivery_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    currency_id: Mapped[Optional[int]] = mapped_column(Integer)
    subtotal: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    total_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))

    currency: Mapped[Optional['Currency']] = relationship('Currency', back_populates='purchase_order')
    po_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    expected_delivery_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    currency_id: Mapped[Optional[int]] = mapped_column(Integer)
    subtotal: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    total_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))

    currency: Mapped[Optional['Currency']] = relationship('Currency', back_populates='purchase_order')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='purchase_order')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='purchase_order')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='po')
    goods_receipt: Mapped[list['GoodsReceipt']] = relationship('GoodsReceipt', back_populates='po')
    # passive_deletes='all': po_id is NOT NULL with ON DELETE CASCADE at the
    # DB level, so deleting a PurchaseOrder must let the DB cascade the
    # delete rather than have the ORM try to null out po_id first.
    purchase_order_line: Mapped[list['PurchaseOrderLine']] = relationship(
        'PurchaseOrderLine', back_populates='po', passive_deletes='all'
    )


class PurchaseOrderLine(Base):
    __tablename__ = 'purchase_order_line'
    __table_args__ = (
        ForeignKeyConstraint(['po_id'], ['ap.purchase_order.po_id'], ondelete='CASCADE', name='purchase_order_line_po_id_fkey'),
        PrimaryKeyConstraint('po_line_id', name='purchase_order_line_pkey'),
        Index('idx_po_line_po', 'po_id'),
        {'schema': 'ap'}
    )

    po_line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text('1'))
    unit_price: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    line_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    item_code: Mapped[Optional[str]] = mapped_column(String(50))

    po: Mapped['PurchaseOrder'] = relationship('PurchaseOrder', back_populates='purchase_order_line')
    # passive_deletes='all': po_line_id is nullable with ON DELETE SET NULL,
    # so let the DB clear it rather than have the ORM issue per-row UPDATEs.
    goods_receipt_line: Mapped[list['GoodsReceiptLine']] = relationship(
        'GoodsReceiptLine', back_populates='po_line', passive_deletes='all'
    )
    invoice_line: Mapped[list['InvoiceLine']] = relationship(
        'InvoiceLine', back_populates='po_line', passive_deletes='all'
    )


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
    grn_number: Mapped[Optional[str]] = mapped_column(String(50))
    receipt_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    grn_number: Mapped[Optional[str]] = mapped_column(String(50))
    receipt_date: Mapped[Optional[datetime.date]] = mapped_column(Date)

    po: Mapped[Optional['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='goods_receipt')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='goods_receipt')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='grn')
    # passive_deletes='all': grn_id is NOT NULL with ON DELETE CASCADE at the
    # DB level, so deleting a GoodsReceipt must let the DB cascade the
    # delete rather than have the ORM try to null out grn_id first.
    goods_receipt_line: Mapped[list['GoodsReceiptLine']] = relationship(
        'GoodsReceiptLine', back_populates='grn', passive_deletes='all'
    )


class GoodsReceiptLine(Base):
    __tablename__ = 'goods_receipt_line'
    __table_args__ = (
        ForeignKeyConstraint(['grn_id'], ['ap.goods_receipt.grn_id'], ondelete='CASCADE', name='goods_receipt_line_grn_id_fkey'),
        ForeignKeyConstraint(['po_line_id'], ['ap.purchase_order_line.po_line_id'], ondelete='SET NULL', name='goods_receipt_line_po_line_id_fkey'),
        PrimaryKeyConstraint('grn_line_id', name='goods_receipt_line_pkey'),
        Index('idx_grn_line_grn', 'grn_id'),
        Index('idx_grn_line_po_line', 'po_line_id'),
        {'schema': 'ap'}
    )

    grn_line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grn_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    received_quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    po_line_id: Mapped[Optional[int]] = mapped_column(Integer)
    item_code: Mapped[Optional[str]] = mapped_column(String(50))

    grn: Mapped['GoodsReceipt'] = relationship('GoodsReceipt', back_populates='goods_receipt_line')
    po_line: Mapped[Optional['PurchaseOrderLine']] = relationship('PurchaseOrderLine', back_populates='goods_receipt_line')
