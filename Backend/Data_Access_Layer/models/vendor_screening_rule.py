# Backend/Data_Access_Layer/models/vendor_screening_rule.py
"""Minimal Business Rule Engine used by Vendor Pre-Screen to produce an
NDA recommendation for a Department + Purchase Category combination.

Mirrors the ``ApprovalPolicy`` pattern (see Data_Access_Layer/models/approval.py):
department_id/purchase_category_id are nullable "wildcard" scoping columns,
and a rule with both NULL is a catch-all (``is_default``). Unlike
``ApprovalPolicy``/``TaxRule`` there is no separate conditions table - NDA
recommendation is a single boolean per scope, not a condition tree, so a
header-only table is enough. Overlapping active rules for the same scope are
rejected in the service layer at write time, not by a DB constraint - the
same choice ``ApprovalPolicy`` makes for the same reason (a partial unique
index on nullable columns can't express "same scope" cleanly).
"""
from typing import Optional, TYPE_CHECKING
import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKeyConstraint, Index,
    PrimaryKeyConstraint, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.purchase import Department, PurchaseCategory


class VendorScreeningRule(Base):
    __tablename__ = 'vendor_screening_rule'
    __table_args__ = (
        ForeignKeyConstraint(['department_id'], ['ap.department.id'], name='fk_vendor_screening_rule_department'),
        ForeignKeyConstraint(['purchase_category_id'], ['ap.purchase_category.id'], name='fk_vendor_screening_rule_category'),
        PrimaryKeyConstraint('id', name='vendor_screening_rule_pkey'),
        UniqueConstraint('name', name='vendor_screening_rule_name_key'),
        Index('idx_vendor_screening_rule_department', 'department_id'),
        Index('idx_vendor_screening_rule_category', 'purchase_category_id'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    requires_nda: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    department_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    purchase_category_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    department: Mapped[Optional['Department']] = relationship('Department')
    purchase_category: Mapped[Optional['PurchaseCategory']] = relationship('PurchaseCategory')
