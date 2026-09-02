# Backend/Data_Access_Layer/models/purchase.py
import datetime
import decimal
import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime,
    ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint,
    String, Table, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.master import StatusMaster
    from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceLine
    from Backend.Data_Access_Layer.models.vendor import Vendor
    from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder, PurchaseOrderLine


department_purchase_category = Table(
    'department_purchase_category', Base.metadata,
    Column('department_id', BigInteger, nullable=False),
    Column('purchase_category_id', BigInteger, nullable=False),
    ForeignKeyConstraint(['department_id'], ['ap.department.id'],
                         ondelete='CASCADE', name='fk_dpc_department'),
    ForeignKeyConstraint(['purchase_category_id'], ['ap.purchase_category.id'],
                         ondelete='CASCADE', name='fk_dpc_purchase_category'),
    PrimaryKeyConstraint('department_id', 'purchase_category_id',
                         name='department_purchase_category_pkey'),
    schema='ap',
)


class Department(Base):
    __tablename__ = 'department'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='department_pkey'),
        UniqueConstraint('code', name='department_code_key'),
        UniqueConstraint('name', name='department_name_key'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)

    purchase_category: Mapped[list['PurchaseCategory']] = relationship(
        'PurchaseCategory', secondary=department_purchase_category,
        back_populates='department'
    )
    purchase_requisition: Mapped[list['PurchaseRequisition']] = relationship(
        'PurchaseRequisition', back_populates='department'
    )


class PurchaseCategory(Base):
    __tablename__ = 'purchase_category'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='purchase_category_pkey'),
        UniqueConstraint('code', name='purchase_category_code_key'),
        UniqueConstraint('name', name='purchase_category_name_key'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)

    department: Mapped[list['Department']] = relationship(
        'Department', secondary=department_purchase_category,
        back_populates='purchase_category'
    )
    purchase_requisition: Mapped[list['PurchaseRequisition']] = relationship(
        'PurchaseRequisition', back_populates='purchase_category'
    )


class PurchaseRequisition(Base):
    __tablename__ = 'purchase_requisition'
    __table_args__ = (
        CheckConstraint('estimated_total >= 0', name='chk_pr_estimated_total'),
        CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')",
            name='chk_pr_priority'
        ),
        ForeignKeyConstraint(['department_id'], ['ap.department.id'], name='fk_pr_department'),
        ForeignKeyConstraint(['purchase_category_id'], ['ap.purchase_category.id'], name='fk_pr_purchase_category'),
        ForeignKeyConstraint(['selected_quotation_id'], ['ap.quotation.id'], name='fk_pr_selected_quotation'),
        ForeignKeyConstraint(['selected_vendor_id'], ['ap.vendor.vendor_id'], name='fk_pr_vendor'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='fk_pr_status'),
        PrimaryKeyConstraint('id', name='purchase_requisition_pkey'),
        UniqueConstraint('pr_number', name='purchase_requisition_pr_number_key'),
        Index('idx_pr_category', 'purchase_category_id'),
        Index('idx_pr_created_by', 'created_by'),
        Index('idx_pr_department', 'department_id'),
        Index('idx_pr_selected_quotation', 'selected_quotation_id'),
        Index('idx_pr_selected_vendor', 'selected_vendor_id'),
        Index('idx_pr_status', 'status_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pr_number: Mapped[str] = mapped_column(String(50), nullable=False)
    department_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'NORMAL'::character varying"))
    estimated_total: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    required_by: Mapped[Optional[datetime.date]] = mapped_column(Date)
    delivery_location: Mapped[Optional[str]] = mapped_column(String(255))
    justification: Mapped[Optional[str]] = mapped_column(Text)
    selected_vendor_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    selected_quotation_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    approval_comment: Mapped[Optional[str]] = mapped_column(Text)

    department: Mapped['Department'] = relationship('Department', back_populates='purchase_requisition')
    purchase_category: Mapped['PurchaseCategory'] = relationship('PurchaseCategory', back_populates='purchase_requisition')
    status: Mapped['StatusMaster'] = relationship('StatusMaster', back_populates='purchase_requisition')
    selected_vendor: Mapped[Optional['Vendor']] = relationship('Vendor', back_populates='purchase_requisition')

    # Two FK paths to quotation (pr_id inbound, selected_quotation_id outbound),
    # so foreign_keys must be explicit on both sides.
    selected_quotation: Mapped[Optional['Quotation']] = relationship(
        'Quotation', foreign_keys=[selected_quotation_id], post_update=True
    )
    quotation: Mapped[list['Quotation']] = relationship(
        'Quotation', back_populates='pr',
        foreign_keys='Quotation.pr_id', passive_deletes='all'
    )

    purchase_requisition_line: Mapped[list['PurchaseRequisitionLine']] = relationship(
        'PurchaseRequisitionLine', back_populates='pr', passive_deletes='all'
    )
    purchase_order: Mapped[list['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='pr')


class PurchaseRequisitionLine(Base):
    __tablename__ = 'purchase_requisition_line'
    __table_args__ = (
        CheckConstraint('estimated_amount IS NULL OR estimated_amount >= 0', name='chk_pr_line_estimated_amount'),
        CheckConstraint('estimated_unit_price IS NULL OR estimated_unit_price >= 0', name='chk_pr_line_estimated_price'),
        CheckConstraint('quantity > 0', name='chk_pr_line_quantity'),
        ForeignKeyConstraint(['pr_id'], ['ap.purchase_requisition.id'], ondelete='CASCADE', name='fk_pr_line_pr'),
        PrimaryKeyConstraint('id', name='purchase_requisition_line_pkey'),
        Index('idx_pr_line_pr', 'pr_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)
    uom: Mapped[Optional[str]] = mapped_column(String(50))
    estimated_unit_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    estimated_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))

    pr: Mapped['PurchaseRequisition'] = relationship(
        'PurchaseRequisition', back_populates='purchase_requisition_line'
    )
    purchase_order_line: Mapped[list['PurchaseOrderLine']] = relationship(
        'PurchaseOrderLine', back_populates='pr_line'
    )


class Quotation(Base):
    __tablename__ = 'quotation'
    __table_args__ = (
        CheckConstraint('total_amount IS NULL OR total_amount >= 0', name='chk_quotation_total'),
        ForeignKeyConstraint(['pr_id'], ['ap.purchase_requisition.id'], ondelete='CASCADE', name='fk_quotation_pr'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='fk_quotation_status'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='fk_quotation_vendor'),
        PrimaryKeyConstraint('id', name='quotation_pkey'),
        Index('idx_quotation_pr', 'pr_id'),
        Index('idx_quotation_status', 'status_id'),
        Index('idx_quotation_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vendor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    status_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    quotation_number: Mapped[Optional[str]] = mapped_column(String(100))
    quotation_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    valid_until: Mapped[Optional[datetime.date]] = mapped_column(Date)
    total_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))

    pr: Mapped['PurchaseRequisition'] = relationship(
        'PurchaseRequisition', back_populates='quotation', foreign_keys=[pr_id]
    )
    vendor: Mapped['Vendor'] = relationship('Vendor', back_populates='quotation')
    status: Mapped['StatusMaster'] = relationship('StatusMaster', back_populates='quotation')
    purchase_order: Mapped[list['PurchaseOrder']] = relationship('PurchaseOrder', back_populates='quotation')