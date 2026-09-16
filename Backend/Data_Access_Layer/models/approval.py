# Backend/Data_Access_Layer/models/approval.py
"""Policy-driven, multi-level invoice approval engine.

ApprovalPolicy / ApprovalPolicyLevel are the admin-configured template:
WHAT should happen for invoices matching a department + purchase
category + amount range, and WHO approves at each level.
InvoiceApproval / InvoiceApprovalStep / InvoiceApprovalStepApprover are
the runtime instance: a snapshot of the levels/approvers resolved *once*,
when an invoice is sent for approval - never re-derived from the policy
afterward, so a later policy edit never affects an already-running
approval (see InvoiceApprovalService.send_for_approval).

Approver identity, for both the template (role_code/user_uuid) and the
runtime resolution, comes from ap.approver_directory /
ap.approver_directory_role (CDC-synced from UMS/EOS, see
Backend/cdc_consumer/) via
Backend/Business_Layer/services/approver_resolver_service.py - never a
local user table. Neither of those CDC tables is FK'd to anything (by
design - CDC delivery order isn't guaranteed), so user_uuid/role_code
columns below are plain, unconstrained columns too.

DEPARTMENT_APPROVER is deliberately NOT a UMS role. Investigated and
confirmed (2026-09-16): UMS has no department-scoped, non-role assignment
primitive to reuse, and no reachable analog exists elsewhere (a sibling
system, XMS, has its own such concept but isn't part of this deployment).
Inventing a UMS role here would mean a role that exists only for this one
purpose, kept in sync out of band. Instead DepartmentApprover below is
AP's own admin-owned mapping - "which users can approve for department
X" - independent of the UMS role system entirely.
"""
from typing import Optional, TYPE_CHECKING
import datetime
import decimal
import uuid as uuid_module

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKeyConstraint,
    Index, Integer, Numeric, PrimaryKeyConstraint, String, UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.invoice import Invoice, InvoiceIssue
    from Backend.Data_Access_Layer.models.purchase import Department, PurchaseCategory


class ApprovalPolicy(Base):
    """WHEN a policy applies. Deliberately no priority/ordering column:
    overlapping active policies for the same department+category+amount
    range are rejected at write time (ApprovalPolicyService), not
    resolved by priority at match time.

    is_default: a catch-all fallback, used only when no department+
    category+amount-scoped policy matches an invoice (see
    ApprovalPolicyService.match_policy). A default policy has no
    department/category/amount scoping at all - those three columns are
    NULL for it, enforced by the service, not a DB constraint (matches
    this project's existing pattern of validating cross-field business
    rules in the service layer, e.g. purchase_category.department_id
    consistency). At most one default policy may be active at a time."""

    __tablename__ = 'approval_policy'
    __table_args__ = (
        CheckConstraint(
            'min_amount IS NULL OR max_amount IS NULL OR min_amount <= max_amount',
            name='chk_approval_policy_amount_range',
        ),
        ForeignKeyConstraint(['department_id'], ['ap.department.id'], name='fk_approval_policy_department'),
        ForeignKeyConstraint(['purchase_category_id'], ['ap.purchase_category.id'], name='fk_approval_policy_purchase_category'),
        PrimaryKeyConstraint('id', name='approval_policy_pkey'),
        UniqueConstraint('name', name='approval_policy_name_key'),
        Index('idx_approval_policy_department', 'department_id'),
        Index('idx_approval_policy_category', 'purchase_category_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    department_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    purchase_category_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(String(500))
    min_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))

    department: Mapped[Optional['Department']] = relationship('Department')
    purchase_category: Mapped[Optional['PurchaseCategory']] = relationship('PurchaseCategory')
    levels: Mapped[list['ApprovalPolicyLevel']] = relationship(
        'ApprovalPolicyLevel', back_populates='approval_policy',
        order_by='ApprovalPolicyLevel.level_number', cascade='all, delete-orphan',
    )


class DepartmentApprover(Base):
    """Admin-configured: this user_uuid may act as DEPARTMENT_APPROVER
    for this department. See the module docstring for why this is an
    AP-owned table rather than a UMS role. user_uuid is still validated
    live against ap.approver_directory.is_user_active at resolution time
    (ApproverResolverService) - a mapping row surviving an employee's
    departure/deactivation must not make them a phantom approver."""

    __tablename__ = 'department_approver'
    __table_args__ = (
        ForeignKeyConstraint(
            ['department_id'], ['ap.department.id'],
            ondelete='CASCADE', name='fk_department_approver_department',
        ),
        PrimaryKeyConstraint('id', name='department_approver_pkey'),
        UniqueConstraint('department_id', 'user_uuid', name='department_approver_department_id_user_uuid_key'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    department: Mapped['Department'] = relationship('Department')


class ApprovalPolicyLevel(Base):
    """One configured level: WHO approves and under what quorum rule
    (ANY_ONE/ALL). For approver_type DEPARTMENT_APPROVER, the department
    is implicitly the policy's own department_id - no separate column
    here, to avoid duplicate department configuration."""

    __tablename__ = 'approval_policy_level'
    __table_args__ = (
        CheckConstraint(
            "approver_type IN ('DEPARTMENT_APPROVER', 'ROLE', 'USER')",
            name='chk_approval_policy_level_approver_type',
        ),
        CheckConstraint(
            "approval_rule IN ('ANY_ONE', 'ALL')",
            name='chk_approval_policy_level_approval_rule',
        ),
        ForeignKeyConstraint(
            ['approval_policy_id'], ['ap.approval_policy.id'],
            ondelete='CASCADE', name='fk_approval_policy_level_policy',
        ),
        PrimaryKeyConstraint('id', name='approval_policy_level_pkey'),
        UniqueConstraint('approval_policy_id', 'level_number', name='approval_policy_level_policy_id_level_number_key'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    approval_policy_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    level_number: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_type: Mapped[str] = mapped_column(String(30), nullable=False)
    approval_rule: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ANY_ONE'::character varying"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    role_code: Mapped[Optional[str]] = mapped_column(String(50))
    user_uuid: Mapped[Optional[uuid_module.UUID]] = mapped_column(UUID(as_uuid=True))

    approval_policy: Mapped['ApprovalPolicy'] = relationship('ApprovalPolicy', back_populates='levels')


class InvoiceApproval(Base):
    """Runtime approval instance for one invoice - created once by
    InvoiceApprovalService.send_for_approval, from a snapshot of whichever
    ApprovalPolicy matched at that moment."""

    __tablename__ = 'invoice_approval'
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'IN_PROGRESS', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name='chk_invoice_approval_status',
        ),
        ForeignKeyConstraint(['approval_policy_id'], ['ap.approval_policy.id'], name='fk_invoice_approval_policy'),
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], ondelete='CASCADE', name='invoice_approval_invoice_id_fkey'),
        ForeignKeyConstraint(['invoice_issue_id'], ['ap.invoice_issue.invoice_issue_id'], name='invoice_approval_invoice_issue_id_fkey'),
        PrimaryKeyConstraint('invoice_approval_id', name='invoice_approval_pkey'),
        Index('idx_invoice_approval_invoice', 'invoice_id'),
        {'schema': 'ap'}
    )

    invoice_approval_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_policy_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    invoice_issue_id: Mapped[Optional[int]] = mapped_column(Integer)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_approval')
    invoice_issue: Mapped[Optional['InvoiceIssue']] = relationship('InvoiceIssue', back_populates='invoice_approval')
    approval_policy: Mapped['ApprovalPolicy'] = relationship('ApprovalPolicy')
    steps: Mapped[list['InvoiceApprovalStep']] = relationship(
        'InvoiceApprovalStep', back_populates='invoice_approval',
        order_by='InvoiceApprovalStep.level_number', cascade='all, delete-orphan',
    )


class InvoiceApprovalStep(Base):
    """One resolved runtime level. approver_type/role_code/department_id/
    approval_rule are copied from the matched ApprovalPolicyLevel at
    send_for_approval time - a frozen snapshot, not a live FK-driven view,
    so the policy level it came from can later be edited/deleted without
    affecting this step."""

    __tablename__ = 'invoice_approval_step'
    __table_args__ = (
        CheckConstraint(
            "approver_type IN ('DEPARTMENT_APPROVER', 'ROLE', 'USER')",
            name='chk_invoice_approval_step_approver_type',
        ),
        CheckConstraint(
            "approval_rule IN ('ANY_ONE', 'ALL')",
            name='chk_invoice_approval_step_approval_rule',
        ),
        CheckConstraint(
            "status IN ('WAITING', 'PENDING', 'APPROVED', 'REJECTED', 'SKIPPED', 'CANCELLED')",
            name='chk_invoice_approval_step_status',
        ),
        ForeignKeyConstraint(
            ['invoice_approval_id'], ['ap.invoice_approval.invoice_approval_id'],
            ondelete='CASCADE', name='fk_invoice_approval_step_approval',
        ),
        ForeignKeyConstraint(['department_id'], ['ap.department.id'], name='fk_invoice_approval_step_department'),
        PrimaryKeyConstraint('id', name='invoice_approval_step_pkey'),
        UniqueConstraint('invoice_approval_id', 'level_number', name='invoice_approval_step_approval_id_level_number_key'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_approval_id: Mapped[int] = mapped_column(Integer, nullable=False)
    level_number: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_type: Mapped[str] = mapped_column(String(30), nullable=False)
    approval_rule: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'WAITING'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    role_code: Mapped[Optional[str]] = mapped_column(String(50))
    department_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    invoice_approval: Mapped['InvoiceApproval'] = relationship('InvoiceApproval', back_populates='steps')
    department: Mapped[Optional['Department']] = relationship('Department')
    approvers: Mapped[list['InvoiceApprovalStepApprover']] = relationship(
        'InvoiceApprovalStepApprover', back_populates='approval_step', cascade='all, delete-orphan',
    )


class InvoiceApprovalStepApprover(Base):
    """One of possibly-several approvers eligible for one step - e.g. all
    active DEPARTMENT_APPROVER-role users in a department, or all
    active users holding a given role_code. Multiple rows under an
    ANY_ONE step represent alternatives, not a sequence; under ALL, every
    row must reach APPROVED."""

    __tablename__ = 'invoice_approval_step_approver'
    __table_args__ = (
        CheckConstraint(
            "status IN ('WAITING', 'PENDING', 'APPROVED', 'REJECTED', 'SKIPPED')",
            name='chk_invoice_approval_step_approver_status',
        ),
        ForeignKeyConstraint(
            ['approval_step_id'], ['ap.invoice_approval_step.id'],
            ondelete='CASCADE', name='fk_invoice_approval_step_approver_step',
        ),
        PrimaryKeyConstraint('id', name='invoice_approval_step_approver_pkey'),
        UniqueConstraint('approval_step_id', 'user_uuid', name='invoice_approval_step_approver_step_id_user_uuid_key'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    approval_step_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_uuid: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'WAITING'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    comments: Mapped[Optional[str]] = mapped_column(String(500))

    approval_step: Mapped['InvoiceApprovalStep'] = relationship('InvoiceApprovalStep', back_populates='approvers')
