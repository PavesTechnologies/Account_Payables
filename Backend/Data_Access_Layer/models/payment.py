from typing import Optional
import datetime
import decimal

from sqlalchemy import Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base


class Payment(Base):
    __tablename__ = 'payment'
    __table_args__ = (
        ForeignKeyConstraint(['currency_id'], ['ap.currency.currency_id'], name='payment_currency_id_fkey'),
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], name='payment_invoice_id_fkey'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='payment_status_id_fkey'),
        ForeignKeyConstraint(['vendor_bank_id'], ['ap.vendor_bank.vendor_bank_id'], name='payment_vendor_bank_id_fkey'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='payment_vendor_id_fkey'),
        PrimaryKeyConstraint('payment_id', name='payment_pkey'),
        Index('idx_payment_invoice', 'invoice_id'),
        Index('idx_payment_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    payment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    vendor_bank_id: Mapped[Optional[int]] = mapped_column(Integer)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100))
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    currency: Mapped['Currency'] = relationship('Currency', back_populates='payment')
    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='payment')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='payment')
    vendor_bank: Mapped[Optional['VendorBank']] = relationship('VendorBank', back_populates='payment')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='payment')
