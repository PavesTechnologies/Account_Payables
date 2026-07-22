from typing import Optional
import datetime
import decimal

from sqlalchemy import Boolean, CHAR, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Backend.Data_Access_Layer.models.base import Base


class Country(Base):
    __tablename__ = 'country'
    __table_args__ = (
        PrimaryKeyConstraint('country_id', name='country_pkey'),
        UniqueConstraint('country_code', name='country_country_code_key'),
        {'schema': 'ap'}
    )

    country_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))

    tax_type: Mapped[list['TaxType']] = relationship('TaxType', back_populates='country')
    vendor: Mapped[list['Vendor']] = relationship('Vendor', back_populates='country')
    vendor_address: Mapped[list['VendorAddress']] = relationship('VendorAddress', back_populates='country')


class Currency(Base):
    __tablename__ = 'currency'
    __table_args__ = (
        PrimaryKeyConstraint('currency_id', name='currency_pkey'),
        UniqueConstraint('currency_code', name='currency_currency_code_key'),
        {'schema': 'ap'}
    )

    currency_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    currency_name: Mapped[str] = mapped_column(String(50), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    decimal_places: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('2'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))

    vendor: Mapped[list['Vendor']] = relationship('Vendor', back_populates='currency')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='currency')
    payment: Mapped[list['Payment']] = relationship('Payment', back_populates='currency')


class PaymentTerm(Base):
    __tablename__ = 'payment_term'
    __table_args__ = (
        PrimaryKeyConstraint('payment_term_id', name='payment_term_pkey'),
        UniqueConstraint('term_name', name='payment_term_term_name_key'),
        {'schema': 'ap'}
    )

    payment_term_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term_name: Mapped[str] = mapped_column(String(50), nullable=False)
    due_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    discount_percent: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text('0'))
    discount_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    is_system_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    vendor: Mapped[list['Vendor']] = relationship('Vendor', back_populates='payment_term')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='payment_term')


class StatusMaster(Base):
    __tablename__ = 'status_master'
    __table_args__ = (
        PrimaryKeyConstraint('status_id', name='status_master_pkey'),
        UniqueConstraint('module_name', 'status_code', name='status_master_module_name_status_code_key'),
        {'schema': 'ap'}
    )

    status_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    status_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))

    vendor: Mapped[list['Vendor']] = relationship('Vendor', back_populates='status')
    purchase_order: Mapped[list['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='status')
    invoice: Mapped[list['Invoice']] = relationship('Invoice', back_populates='status')
    invoice_issue: Mapped[list['InvoiceIssue']] = relationship('InvoiceIssue', back_populates='status')
    payment: Mapped[list['Payment']] = relationship('Payment', back_populates='status')


class SystemConfiguration(Base):
    __tablename__ = 'system_configuration'
    __table_args__ = (
        PrimaryKeyConstraint('config_key', name='system_configuration_pkey'),
        {'schema': 'ap'}
    )

    config_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    config_value: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'STRING'::character varying"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))


class TaxType(Base):
    __tablename__ = 'tax_type'
    __table_args__ = (
        CheckConstraint(
            "calculation_type = 'PERCENTAGE' AND rate_percent IS NOT NULL OR calculation_type = 'FIXED' AND fixed_amount IS NOT NULL",
            name='tax_type_check'
        ),
        ForeignKeyConstraint(['country_id'], ['ap.country.country_id'], name='tax_type_country_id_fkey'),
        PrimaryKeyConstraint('tax_type_id', name='tax_type_pkey'),
        UniqueConstraint('country_id', 'tax_code', 'effective_from', name='tax_type_country_id_tax_code_effective_from_key'),
        {'schema': 'ap'}
    )

    tax_type_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_code: Mapped[str] = mapped_column(String(30), nullable=False)
    calculation_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PERCENTAGE'::character varying"))
    is_withholding: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    effective_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    is_system_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    rate_percent: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 3))
    fixed_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    effective_to: Mapped[Optional[datetime.date]] = mapped_column(Date)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    country: Mapped['Country'] = relationship('Country', back_populates='tax_type')
    vendor_tax: Mapped[list['VendorTax']] = relationship('VendorTax', back_populates='tax_type')
    invoice_line: Mapped[list['InvoiceLine']] = relationship('InvoiceLine', back_populates='tax_type')
