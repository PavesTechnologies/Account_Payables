from typing import Optional
import datetime
import decimal

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, String, UniqueConstraint, Boolean, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base


class ApprovalWorkflow(Base):
    __tablename__ = 'approval_workflow'
    __table_args__ = (
        ForeignKeyConstraint(['vendor_category_id'], ['ap.vendor_category.vendor_category_id'], name='approval_workflow_vendor_category_id_fkey'),
        PrimaryKeyConstraint('approval_workflow_id', name='approval_workflow_pkey'),
        {'schema': 'ap'}
    )

    approval_workflow_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_name: Mapped[str] = mapped_column(String(100), nullable=False)
    min_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text('0'))
    approval_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('1'))
    approver_role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    max_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    vendor_category_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    vendor_category: Mapped[Optional['VendorCategory']] = relationship('VendorCategory', back_populates='approval_workflow')
    invoice_approval: Mapped[list['InvoiceApproval']] = relationship('InvoiceApproval', back_populates='approval_workflow')


class InvoiceApproval(Base):
    __tablename__ = 'invoice_approval'
    __table_args__ = (
        ForeignKeyConstraint(['approval_workflow_id'], ['ap.approval_workflow.approval_workflow_id'], name='invoice_approval_approval_workflow_id_fkey'),
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], ondelete='CASCADE', name='invoice_approval_invoice_id_fkey'),
        PrimaryKeyConstraint('invoice_approval_id', name='invoice_approval_pkey'),
        UniqueConstraint('invoice_id', 'step_number', name='invoice_approval_invoice_id_step_number_key'),
        Index('idx_invoice_approval_invoice', 'invoice_id'),
        {'schema': 'ap'}
    )

    invoice_approval_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    step_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    approver_name: Mapped[str] = mapped_column(String(150), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    approval_workflow_id: Mapped[Optional[int]] = mapped_column(Integer)
    comments: Mapped[Optional[str]] = mapped_column(String(500))
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    approval_workflow: Mapped[Optional['ApprovalWorkflow']] = relationship('ApprovalWorkflow', back_populates='invoice_approval')
    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_approval')
