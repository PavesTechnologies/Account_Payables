from typing import Optional
import datetime
import decimal

from sqlalchemy import Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base


class Invoice(Base):
    __tablename__ = 'invoice'
    __table_args__ = (
        ForeignKeyConstraint(['currency_id'], ['ap.currency.currency_id'], name='invoice_currency_id_fkey'),
        ForeignKeyConstraint(['payment_term_id'], ['ap.payment_term.payment_term_id'], name='invoice_payment_term_id_fkey'),
        ForeignKeyConstraint(['po_id'], ['ap.purchase_order.po_id'], name='invoice_po_id_fkey'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='invoice_status_id_fkey'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='invoice_vendor_id_fkey'),
        PrimaryKeyConstraint('invoice_id', name='invoice_pkey'),
        UniqueConstraint('vendor_id', 'invoice_number', name='invoice_vendor_id_invoice_number_key'),
        Index('idx_invoice_due_date', 'due_date'),
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
    subtotal_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_paid: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    po_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_term_id: Mapped[Optional[int]] = mapped_column(Integer)
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    currency: Mapped['Currency'] = relationship('Currency', back_populates='invoice')
    payment_term: Mapped[Optional['PaymentTerm']] = relationship('PaymentTerm', back_populates='invoice')
    po: Mapped[Optional['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='invoice')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='invoice')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='invoice')
    invoice_approval: Mapped[list['InvoiceApproval']] = relationship('InvoiceApproval', back_populates='invoice')
    invoice_attachment: Mapped[list['InvoiceAttachment']] = relationship('InvoiceAttachment', back_populates='invoice')
    invoice_exception: Mapped[list['InvoiceException']] = relationship('InvoiceException', back_populates='invoice')
    invoice_line: Mapped[list['InvoiceLine']] = relationship('InvoiceLine', back_populates='invoice')
    invoice_validation: Mapped[list['InvoiceValidation']] = relationship('InvoiceValidation', back_populates='invoice')
    payment: Mapped[list['Payment']] = relationship('Payment', back_populates='invoice')


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
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(100))

    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_attachment')


class InvoiceException(Base):
    __tablename__ = 'invoice_exception'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], ondelete='CASCADE', name='invoice_exception_invoice_id_fkey'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='invoice_exception_status_id_fkey'),
        PrimaryKeyConstraint('invoice_exception_id', name='invoice_exception_pkey'),
        Index('idx_invoice_exception_invoice', 'invoice_id'),
        {'schema': 'ap'}
    )

    invoice_exception_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    exception_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100))
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_exception')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='invoice_exception')


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


class InvoiceValidation(Base):
    __tablename__ = 'invoice_validation'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], ondelete='CASCADE', name='invoice_validation_invoice_id_fkey'),
        PrimaryKeyConstraint('invoice_validation_id', name='invoice_validation_pkey'),
        Index('idx_invoice_validation_invoice', 'invoice_id'),
        {'schema': 'ap'}
    )

    invoice_validation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    validated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    remarks: Mapped[Optional[str]] = mapped_column(String(255))

    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_validation')
