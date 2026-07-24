from typing import Optional, TYPE_CHECKING
import datetime
import decimal

from sqlalchemy import Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.master import Currency, StatusMaster
    from Backend.Data_Access_Layer.models.vendor import VendorBank, Vendor
    from Backend.Data_Access_Layer.models.invoice import Invoice

class Payment(Base):
    __tablename__ = 'payment'
    __table_args__ = (
        ForeignKeyConstraint(['currency_id'], ['ap.currency.currency_id'], name='payment_currency_id_fkey'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='payment_status_id_fkey'),
        ForeignKeyConstraint(['vendor_bank_id'], ['ap.vendor_bank.vendor_bank_id'], name='payment_vendor_bank_id_fkey'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='payment_vendor_id_fkey'),
        PrimaryKeyConstraint('payment_id', name='payment_pkey'),
        Index('idx_payment_scheduled_date', 'scheduled_date'),
        Index('idx_payment_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    payment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    vendor_bank_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100))
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    currency: Mapped['Currency'] = relationship('Currency', back_populates='payment')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='payment')
    vendor_bank: Mapped[Optional['VendorBank']] = relationship('VendorBank', back_populates='payment')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='payment')
    payment_invoice: Mapped[list['PaymentInvoice']] = relationship('PaymentInvoice', back_populates='payment')


class PaymentInvoice(Base):
    __tablename__ = 'payment_invoice'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], name='payment_invoice_invoice_id_fkey'),
        ForeignKeyConstraint(['payment_id'], ['ap.payment.payment_id'], ondelete='CASCADE', name='payment_invoice_payment_id_fkey'),
        PrimaryKeyConstraint('payment_invoice_id', name='payment_invoice_pkey'),
        UniqueConstraint('payment_id', 'invoice_id', name='payment_invoice_payment_id_invoice_id_key'),
        Index('idx_payment_invoice_invoice', 'invoice_id'),
        Index('idx_payment_invoice_payment', 'payment_id'),
        {'schema': 'ap'}
    )

    payment_invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))

    payment: Mapped['Payment'] = relationship('Payment', back_populates='payment_invoice')
    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='payment_invoice')
