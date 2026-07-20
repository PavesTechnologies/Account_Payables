from typing import Optional
import datetime

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Index, Integer, PrimaryKeyConstraint, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base


class Vendor(Base):
    __tablename__ = 'vendor'
    __table_args__ = (
        ForeignKeyConstraint(['country_id'], ['ap.country.country_id'], name='vendor_country_id_fkey'),
        ForeignKeyConstraint(['currency_id'], ['ap.currency.currency_id'], name='vendor_currency_id_fkey'),
        ForeignKeyConstraint(['payment_term_id'], ['ap.payment_term.payment_term_id'], name='vendor_payment_term_id_fkey'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='vendor_status_id_fkey'),
        ForeignKeyConstraint(['vendor_category_id'], ['ap.vendor_category.vendor_category_id'], name='vendor_vendor_category_id_fkey'),
        PrimaryKeyConstraint('vendor_id', name='vendor_pkey'),
        UniqueConstraint('vendor_code', name='vendor_vendor_code_key'),
        Index('idx_vendor_country', 'country_id'),
        Index('idx_vendor_status', 'status_id'),
        {'schema': 'ap'}
    )

    vendor_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    country_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    vendor_code: Mapped[Optional[str]] = mapped_column(String(30))
    vendor_category_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_term_id: Mapped[Optional[int]] = mapped_column(Integer)
    currency_id: Mapped[Optional[int]] = mapped_column(Integer)
    address: Mapped[Optional[str]] = mapped_column(String(255))
    phone_number: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(150))
    status_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    country: Mapped['Country'] = relationship('Country', back_populates='vendor')
    currency: Mapped[Optional['Currency']] = relationship('Currency', back_populates='vendor')
    payment_term: Mapped[Optional['PaymentTerm']] = relationship('PaymentTerm', back_populates='vendor')
    status: Mapped[Optional['StatusMaster']] = relationship('StatusMaster', back_populates='vendor')
    vendor_category: Mapped[Optional['VendorCategory']] = relationship('VendorCategory', back_populates='vendor')
    purchase_order: Mapped[list['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='vendor')
    vendor_address: Mapped[list['VendorAddress']] = relationship('VendorAddress', back_populates='vendor')
    vendor_bank: Mapped[list['VendorBank']] = relationship('VendorBank', back_populates='vendor')
    vendor_tax: Mapped[list['VendorTax']] = relationship('VendorTax', back_populates='vendor')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='vendor')
    payment: Mapped[list['Payment']] = relationship('Payment', back_populates='vendor')


class VendorAddress(Base):
    __tablename__ = 'vendor_address'
    __table_args__ = (
        ForeignKeyConstraint(['country_id'], ['ap.country.country_id'], name='vendor_address_country_id_fkey'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], ondelete='CASCADE', name='vendor_address_vendor_id_fkey'),
        PrimaryKeyConstraint('vendor_address_id', name='vendor_address_pkey'),
        Index('idx_vendor_address_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    vendor_address_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    address_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'REGISTERED'::character varying"))
    address_line1: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    address_line2: Mapped[Optional[str]] = mapped_column(String(200))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    country: Mapped['Country'] = relationship('Country', back_populates='vendor_address')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='vendor_address')


class VendorBank(Base):
    __tablename__ = 'vendor_bank'
    __table_args__ = (
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], ondelete='CASCADE', name='vendor_bank_vendor_id_fkey'),
        PrimaryKeyConstraint('vendor_bank_id', name='vendor_bank_pkey'),
        Index('idx_vendor_bank_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    vendor_bank_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_holder_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    account_number: Mapped[Optional[str]] = mapped_column(String(50))
    iban: Mapped[Optional[str]] = mapped_column(String(50))
    swift_code: Mapped[Optional[str]] = mapped_column(String(20))
    routing_number: Mapped[Optional[str]] = mapped_column(String(20))
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(20))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='vendor_bank')
    payment: Mapped[list['Payment']] = relationship('Payment', back_populates='vendor_bank')


class VendorTax(Base):
    __tablename__ = 'vendor_tax'
    __table_args__ = (
        ForeignKeyConstraint(['tax_type_id'], ['ap.tax_type.tax_type_id'], name='vendor_tax_tax_type_id_fkey'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], ondelete='CASCADE', name='vendor_tax_vendor_id_fkey'),
        PrimaryKeyConstraint('vendor_tax_id', name='vendor_tax_pkey'),
        UniqueConstraint('vendor_id', 'tax_type_id', name='vendor_tax_vendor_id_tax_type_id_key'),
        {'schema': 'ap'}
    )

    vendor_tax_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_type_id: Mapped[int] = mapped_column(Integer, nullable=False)
    registration_number: Mapped[str] = mapped_column(String(50), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    tax_type: Mapped['TaxType'] = relationship('TaxType', back_populates='vendor_tax')
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='vendor_tax')
