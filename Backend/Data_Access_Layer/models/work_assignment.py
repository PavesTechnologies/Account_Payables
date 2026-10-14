# Backend/Data_Access_Layer/models/work_assignment.py
"""Who works which invoice (P3): AP teams with several executives.

  work_assignment_rule  a vendor (or department) belongs to one AP Executive: new invoices from that
                        vendor land in their queue. Vendor rules win over department rules.
  invoice_assignment    the current owner of an invoice, how they got it (RULE / CLAIM / REASSIGN)
                        and who assigned it. Every change is also written to audit_log.

An invoice with no row is unassigned - anyone in the team may claim it. Created by
migration_work_assignment.sql (create_all also creates the tables).
"""
from typing import Optional
import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer,
                        PrimaryKeyConstraint, String, text)
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base

SCOPE_VENDOR, SCOPE_DEPARTMENT = "VENDOR", "DEPARTMENT"
SOURCE_RULE, SOURCE_CLAIM, SOURCE_REASSIGN = "RULE", "CLAIM", "REASSIGN"


class WorkAssignmentRule(Base):
    __tablename__ = "work_assignment_rule"
    __table_args__ = (
        ForeignKeyConstraint(["vendor_id"], ["ap.vendor.vendor_id"], name="work_assignment_rule_vendor_fk"),
        ForeignKeyConstraint(["department_id"], ["ap.department.id"], name="work_assignment_rule_department_fk"),
        PrimaryKeyConstraint("rule_id", name="work_assignment_rule_pkey"),
        CheckConstraint("scope IN ('VENDOR','DEPARTMENT')", name="work_assignment_rule_scope_chk"),
        CheckConstraint("(scope = 'VENDOR' AND vendor_id IS NOT NULL) OR (scope = 'DEPARTMENT' AND department_id IS NOT NULL)",
                        name="work_assignment_rule_target_chk"),
        Index("uq_work_assignment_rule_vendor", "vendor_id", unique=True, postgresql_where=text("is_active AND scope = 'VENDOR'")),
        Index("uq_work_assignment_rule_department", "department_id", unique=True,
              postgresql_where=text("is_active AND scope = 'DEPARTMENT'")),
        {"schema": "ap"},
    )

    rule_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    assignee_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    vendor_id: Mapped[Optional[int]] = mapped_column(Integer)
    department_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))


class InvoiceAssignment(Base):
    __tablename__ = "invoice_assignment"
    __table_args__ = (
        ForeignKeyConstraint(["invoice_id"], ["ap.invoice.invoice_id"], ondelete="CASCADE", name="invoice_assignment_invoice_fk"),
        ForeignKeyConstraint(["rule_id"], ["ap.work_assignment_rule.rule_id"], name="invoice_assignment_rule_fk"),
        PrimaryKeyConstraint("invoice_id", name="invoice_assignment_pkey"),
        CheckConstraint("source IN ('RULE','CLAIM','REASSIGN')", name="invoice_assignment_source_chk"),
        Index("idx_invoice_assignment_assignee", "assignee_user_id"),
        {"schema": "ap"},
    )

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignee_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    assigned_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text("now()"))
    assigned_by: Mapped[Optional[str]] = mapped_column(String(100))
    rule_id: Mapped[Optional[int]] = mapped_column(Integer)
    note: Mapped[Optional[str]] = mapped_column(String(300))
