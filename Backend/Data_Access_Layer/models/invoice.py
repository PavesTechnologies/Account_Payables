from typing import Optional, TYPE_CHECKING
import datetime
import decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder, GoodsReceipt
    from Backend.Data_Access_Layer.models.vendor import Vendor
    from Backend.Data_Access_Layer.models.inbound_document import InboundDocument
    from Backend.Data_Access_Layer.models.approval import InvoiceApproval
    from Backend.Data_Access_Layer.models.payment import PaymentInvoice
    from Backend.Data_Access_Layer.models.master import Currency, PaymentTerm, StatusMaster

class Invoice(Base):
    __tablename__ = 'invoice'
    __table_args__ = (
        ForeignKeyConstraint(['currency_id'], ['ap.currency.currency_id'], name='invoice_currency_id_fkey'),
        ForeignKeyConstraint(['grn_id'], ['ap.goods_receipt.grn_id'], name='invoice_grn_id_fkey'),
        ForeignKeyConstraint(['inbound_document_id'], ['ap.inbound_document.inbound_document_id'], name='invoice_inbound_document_id_fkey'),
        ForeignKeyConstraint(['payment_term_id'], ['ap.payment_term.payment_term_id'], name='invoice_payment_term_id_fkey'),
        ForeignKeyConstraint(['po_id'], ['ap.purchase_order.po_id'], name='invoice_po_id_fkey'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='invoice_status_id_fkey'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='invoice_vendor_id_fkey'),
        PrimaryKeyConstraint('invoice_id', name='invoice_pkey'),
        UniqueConstraint('vendor_id', 'invoice_number', name='invoice_vendor_id_invoice_number_key'),
        Index('idx_invoice_due_date', 'due_date'),
        Index('idx_invoice_po', 'po_id'),
        Index('idx_invoice_status', 'status_id'),
        Index('idx_invoice_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'NON_PO'::character varying"))
    invoice_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    currency_id: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    tax_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    net_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_paid: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    inbound_document_id: Mapped[Optional[int]] = mapped_column(Integer)
    po_id: Mapped[Optional[int]] = mapped_column(Integer)
    grn_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_term_id: Mapped[Optional[int]] = mapped_column(Integer)
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    currency: Mapped['Currency'] = relationship('Currency', back_populates='invoice')
    grn: Mapped[Optional['GoodsReceipt']] = relationship('GoodsReceipt', back_populates='invoice')
    inbound_document: Mapped[Optional['InboundDocument']] = relationship('InboundDocument', foreign_keys=[inbound_document_id])
    payment_term: Mapped[Optional['PaymentTerm']] = relationship('PaymentTerm', back_populates='invoice')
    po: Mapped[Optional['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='invoice')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='invoice')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='invoice')
    invoice_approval: Mapped[list['InvoiceApproval']] = relationship('InvoiceApproval', back_populates='invoice')
    invoice_attachment: Mapped[list['InvoiceAttachment']] = relationship('InvoiceAttachment', back_populates='invoice')
    invoice_issue: Mapped[list['InvoiceIssue']] = relationship('InvoiceIssue', back_populates='invoice')
    invoice_line: Mapped[list['InvoiceLine']] = relationship('InvoiceLine', back_populates='invoice')
    payment_invoice: Mapped[list['PaymentInvoice']] = relationship('PaymentInvoice', back_populates='invoice')


class InvoiceAttachment(Base):
    __tablename__ = 'invoice_attachment'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], ondelete='CASCADE', name='invoice_attachment_invoice_id_fkey'),
        PrimaryKeyConstraint('invoice_attachment_id', name='invoice_attachment_pkey'),
        {'schema': 'ap'}
    )

    invoice_attachment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))

    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_attachment')


class InvoiceIssue(Base):
    __tablename__ = 'invoice_issue'
    __table_args__ = (
        CheckConstraint("severity::text = ANY (ARRAY['INFO'::character varying, 'WARNING'::character varying, 'ERROR'::character varying]::text[])", name='invoice_issue_severity_check'),
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], ondelete='CASCADE', name='invoice_issue_invoice_id_fkey'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='invoice_issue_status_id_fkey'),
        PrimaryKeyConstraint('invoice_issue_id', name='invoice_issue_pkey'),
        Index('idx_invoice_issue_invoice', 'invoice_id'),
        Index('idx_invoice_issue_severity', 'severity'),
        {'schema': 'ap'}
    )

    invoice_issue_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_source: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'ERROR'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    result: Mapped[Optional[str]] = mapped_column(String(10))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100))
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_issue')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='invoice_issue')
    invoice_approval: Mapped[list['InvoiceApproval']] = relationship('InvoiceApproval', back_populates='invoice_issue')


class InvoiceLine(Base):
    __tablename__ = 'invoice_line'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], ondelete='CASCADE', name='invoice_line_invoice_id_fkey'),
        ForeignKeyConstraint(['tax_type_id'], ['ap.tax_type.tax_type_id'], name='invoice_line_tax_type_id_fkey'),
        PrimaryKeyConstraint('invoice_line_id', name='invoice_line_pkey'),
        UniqueConstraint('invoice_id', 'line_number', name='invoice_line_invoice_id_line_number_key'),
        {'schema': 'ap'}
    )

    invoice_line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    line_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text('1'))
    unit_price: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    line_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    tax_type_id: Mapped[Optional[int]] = mapped_column(Integer)

    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_line')
    tax_type: Mapped[Optional['TaxType']] = relationship('TaxType', back_populates='invoice_line')
