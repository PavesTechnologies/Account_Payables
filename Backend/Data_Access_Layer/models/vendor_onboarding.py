# Backend/Data_Access_Layer/models/vendor_onboarding.py
"""Procurement -> Vendor Intaker handoff record.

This is NOT a second vendor-registration flow. When a PR Officer finds no
eligible vendor for an approved PR, this row captures the request and the PR
context (department, category, business requirement) and hands it to a Vendor
Intaker, who then runs the EXISTING Vendor Intake + Pre-Screen
(``VendorIntakeService``). ``vendor_id``/``engagement_id`` are filled in from
that existing flow's results - nothing about vendor creation, GST verification,
engagement or Pre-Screen is re-implemented here.

Workflow status lives in ``ap.status_master`` under module
``VENDOR_ONBOARDING``, resolved by (module_name, status_code) exactly like
every other module in this app - never a hardcoded status id.

``closed_at`` is set when the request reaches a terminal state
(COMPLETED/FAILED/CANCELLED). It exists so the partial unique index in
migration_vendor_onboarding.sql can enforce "only one OPEN request per
PR + department + category" at the database level without encoding any
status id into the schema.
"""
from typing import Optional, TYPE_CHECKING
import datetime

from sqlalchemy import (
    BigInteger, DateTime, ForeignKeyConstraint, Index, Integer,
    PrimaryKeyConstraint, String, Text, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.master import StatusMaster
    from Backend.Data_Access_Layer.models.purchase import (
        Department,
        PurchaseCategory,
        PurchaseRequisition,
    )
    from Backend.Data_Access_Layer.models.vendor import Vendor, VendorEngagement


class VendorOnboardingRequest(Base):
    __tablename__ = 'vendor_onboarding_request'
    __table_args__ = (
        ForeignKeyConstraint(['pr_id'], ['ap.purchase_requisition.id'], name='fk_vor_pr'),
        ForeignKeyConstraint(['department_id'], ['ap.department.id'], name='fk_vor_department'),
        ForeignKeyConstraint(['purchase_category_id'], ['ap.purchase_category.id'], name='fk_vor_purchase_category'),
        ForeignKeyConstraint(['status_id'], ['ap.status_master.status_id'], name='fk_vor_status'),
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='fk_vor_vendor'),
        ForeignKeyConstraint(
            ['engagement_id'],
            ['ap.vendor_category_mapping.vendor_category_mapping_id'],
            name='fk_vor_engagement',
        ),
        PrimaryKeyConstraint('id', name='vendor_onboarding_request_pkey'),
        Index('idx_vor_pr', 'pr_id'),
        Index('idx_vor_status', 'status_id'),
        Index('idx_vor_assigned_to', 'assigned_to'),
        Index('idx_vor_vendor', 'vendor_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    department_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    business_requirement: Mapped[Optional[str]] = mapped_column(Text)
    purpose_of_onboarding: Mapped[Optional[str]] = mapped_column(Text)
    requested_vendor_name: Mapped[Optional[str]] = mapped_column(String(200))
    requested_vendor_email: Mapped[Optional[str]] = mapped_column(String(150))
    vendor_id: Mapped[Optional[int]] = mapped_column(Integer)
    engagement_id: Mapped[Optional[int]] = mapped_column(Integer)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100))
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    pr: Mapped['PurchaseRequisition'] = relationship('PurchaseRequisition')
    department: Mapped['Department'] = relationship('Department')
    purchase_category: Mapped['PurchaseCategory'] = relationship('PurchaseCategory')
    status: Mapped['StatusMaster'] = relationship('StatusMaster')
    vendor: Mapped[Optional['Vendor']] = relationship('Vendor')
    engagement: Mapped[Optional['VendorEngagement']] = relationship('VendorEngagement')
