# Backend/Business_Layer/utils/notification_types.py
"""Catalog of Phase 1 IN-APP notification types.

Role -> Business Responsibility -> Required Action -> Notification.

Each type fixes its default priority, the action label shown to the user,
and the UMS role used ONLY as a fallback when the workflow has no concrete
owner/assignee for the work (see NotificationDispatcher). Role codes are the
real ones synced from UMS into ap.approver_directory_role - no new role is
invented here.

PR workflow: a submitted/resubmitted PR goes to the PR_Approver role (PR
approval is permission-based - there is no concrete per-PR approver to target),
and a PR returned for clarification goes to its own requester (pr.created_by).
Nothing else is ever sent to PR_Creator / PR_Approver users.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Priorities (ap.notification.priority CHECK constraint)
# ---------------------------------------------------------------------------
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CRITICAL = "CRITICAL"
PRIORITIES = (LOW, MEDIUM, HIGH, CRITICAL)

# ---------------------------------------------------------------------------
# UMS role codes (as synced into ap.approver_directory_role.role_code)
# ---------------------------------------------------------------------------
ROLE_PROCUREMENT_OFFICER = "Procurement_Officer"
ROLE_PR_APPROVER = "PR_Approver"
ROLE_VENDOR_INTAKE = "Vendor_Intake"
ROLE_AP_EXECUTIVE = "AP_EXECUTIVE"
ROLE_PAYMENT_PROCESSOR = "Payment_Processor"
ROLE_FINANCE_MANAGER = "Finance_Manager"
ROLE_FINANCE_EXECUTIVE = "Finance_Executive"
ROLE_ADMIN = "Admin"

# ---------------------------------------------------------------------------
# Entity types
# ---------------------------------------------------------------------------
ENTITY_PURCHASE_REQUISITION = "PURCHASE_REQUISITION"
ENTITY_RFQ = "RFQ"
ENTITY_QUOTATION = "QUOTATION"
ENTITY_VENDOR_ONBOARDING_REQUEST = "VENDOR_ONBOARDING_REQUEST"
ENTITY_VENDOR_NDA = "VENDOR_NDA"
ENTITY_INVOICE = "INVOICE"
ENTITY_INVOICE_APPROVAL_STEP = "INVOICE_APPROVAL_STEP"
ENTITY_PAYMENT = "PAYMENT"
ENTITY_CDC_FAILURE = "CDC_FAILURE"

# ---------------------------------------------------------------------------
# Source AP module. Every notification type belongs to exactly one module, so
# the module is DERIVED from notification_type (see module_for) and never
# stored - entity_type alone is not enough (an INVOICE entity carries invoice,
# payment and configuration notifications).
# ---------------------------------------------------------------------------
MODULE_PROCUREMENT = "PROCUREMENT"
MODULE_VENDOR_MANAGEMENT = "VENDOR_MANAGEMENT"
MODULE_INVOICE_MANAGEMENT = "INVOICE_MANAGEMENT"
MODULE_PAYMENTS = "PAYMENTS"
MODULE_SYSTEM_CONFIGURATION = "SYSTEM_CONFIGURATION"
MODULES = (
    MODULE_PROCUREMENT, MODULE_VENDOR_MANAGEMENT, MODULE_INVOICE_MANAGEMENT,
    MODULE_PAYMENTS, MODULE_SYSTEM_CONFIGURATION,
)

# ---------------------------------------------------------------------------
# Notification codes
# ---------------------------------------------------------------------------
# PR workflow (PR Approver / PR Requester)
PR_APPROVAL_REQUIRED = "PR_APPROVAL_REQUIRED"
PR_RETURNED = "PR_RETURNED"
# Procurement Officer
PR_APPROVED_SOURCING = "PR_APPROVED_SOURCING"
VENDOR_ONBOARDING_COMPLETED = "VENDOR_ONBOARDING_COMPLETED"
VENDOR_ONBOARDING_FAILED = "VENDOR_ONBOARDING_FAILED"
NDA_REQUIRED = "NDA_REQUIRED"
NDA_PENDING = "NDA_PENDING"
NDA_SIGNED_REVIEW_PENDING = "NDA_SIGNED_REVIEW_PENDING"
NDA_EXPIRED_RFQ_BLOCKED = "NDA_EXPIRED_RFQ_BLOCKED"
RFQ_VENDOR_EMAIL_FAILURE = "RFQ_VENDOR_EMAIL_FAILURE"
QUOTATION_RECEIVED = "QUOTATION_RECEIVED"
RFQ_DEADLINE_REACHED = "RFQ_DEADLINE_REACHED"
VENDOR_SELECTION_REQUIRED = "VENDOR_SELECTION_REQUIRED"
QUOTATION_VALIDITY_ENDING = "QUOTATION_VALIDITY_ENDING"
PO_GENERATION_REQUIRED = "PO_GENERATION_REQUIRED"
PROCUREMENT_BLOCKED = "PROCUREMENT_BLOCKED"
# Vendor Intake
VENDOR_ONBOARDING_REQUESTED = "VENDOR_ONBOARDING_REQUESTED"
VENDOR_ONBOARDING_ASSIGNED = "VENDOR_ONBOARDING_ASSIGNED"
VENDOR_INFORMATION_REQUIRED = "VENDOR_INFORMATION_REQUIRED"
VENDOR_PRESCREEN_REQUIRED = "VENDOR_PRESCREEN_REQUIRED"
# AP Executive
INVOICE_REVIEW_REQUIRED = "INVOICE_REVIEW_REQUIRED"
INVOICE_VALIDATION_EXCEPTION = "INVOICE_VALIDATION_EXCEPTION"
INVOICE_RETURNED = "INVOICE_RETURNED"
INVOICE_PAYMENT_ACTION_REQUIRED = "INVOICE_PAYMENT_ACTION_REQUIRED"
INVOICE_DUE = "INVOICE_DUE"
INVOICE_OVERDUE = "INVOICE_OVERDUE"
# Invoice approver (runtime-assigned user)
INVOICE_APPROVAL_REQUIRED = "INVOICE_APPROVAL_REQUIRED"
INVOICE_APPROVAL_AGEING = "INVOICE_APPROVAL_AGEING"
# Finance payment user
PAYMENT_READY = "PAYMENT_READY"
PAYMENT_DUE = "PAYMENT_DUE"
PAYMENT_FAILED = "PAYMENT_FAILED"
PAYMENT_EXCEPTION = "PAYMENT_EXCEPTION"
# Finance executive (holds INVOICE_TDS_VERIFY)
INVOICE_TDS_VERIFICATION_REQUIRED = "INVOICE_TDS_VERIFICATION_REQUIRED"
# Finance manager
FINANCE_ACTION_REQUIRED = "FINANCE_ACTION_REQUIRED"
FINANCE_ESCALATION = "FINANCE_ESCALATION"
# Admin
WORKFLOW_CONFIGURATION_BLOCKED = "WORKFLOW_CONFIGURATION_BLOCKED"
SYSTEM_CONFIGURATION_EXCEPTION = "SYSTEM_CONFIGURATION_EXCEPTION"


@dataclass(frozen=True)
class NotificationTypeDef:
    code: str
    priority: str
    headline: str
    action_label: str
    fallback_role: Optional[str]
    module: str


def _t(code, priority, headline, action_label, fallback_role, module) -> NotificationTypeDef:
    return NotificationTypeDef(code, priority, headline, action_label, fallback_role, module)


CATALOG: Dict[str, NotificationTypeDef] = {d.code: d for d in (
    # --- PR workflow ------------------------------------------------------------
    _t(PR_APPROVAL_REQUIRED, HIGH, "PR approval required", "Review PR", ROLE_PR_APPROVER, MODULE_PROCUREMENT),
    # Concrete requester only - never broadcast to the PR_Creator role.
    _t(PR_RETURNED, HIGH, "PR returned for clarification", "Update and resubmit", None, MODULE_PROCUREMENT),
    # --- Procurement Officer ------------------------------------------------
    _t(PR_APPROVED_SOURCING, HIGH, "Procurement action required", "Start RFQ", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(VENDOR_ONBOARDING_COMPLETED, MEDIUM, "Vendor onboarding completed", "Continue procurement", ROLE_PROCUREMENT_OFFICER, MODULE_VENDOR_MANAGEMENT),
    _t(VENDOR_ONBOARDING_FAILED, HIGH, "Vendor onboarding failed", "Review onboarding issue", ROLE_PROCUREMENT_OFFICER, MODULE_VENDOR_MANAGEMENT),
    _t(NDA_REQUIRED, HIGH, "NDA required", "Complete NDA process", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(NDA_PENDING, HIGH, "NDA still pending", "Review NDA", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(NDA_SIGNED_REVIEW_PENDING, HIGH, "Signed NDA awaiting review", "Review and complete NDA", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(NDA_EXPIRED_RFQ_BLOCKED, CRITICAL, "NDA expired - RFQ blocked", "Resolve NDA", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(RFQ_VENDOR_EMAIL_FAILURE, HIGH, "RFQ email delivery failed", "Review vendor communication", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(QUOTATION_RECEIVED, MEDIUM, "Quotation received", "Review quotation", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(RFQ_DEADLINE_REACHED, HIGH, "RFQ deadline reached", "Review RFQ", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(VENDOR_SELECTION_REQUIRED, HIGH, "Vendor selection required", "Select vendor", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(QUOTATION_VALIDITY_ENDING, HIGH, "Quotation validity ending", "Complete vendor selection", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(PO_GENERATION_REQUIRED, HIGH, "PO generation pending", "Generate PO", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    _t(PROCUREMENT_BLOCKED, CRITICAL, "Procurement blocked", "Resolve procurement blocker", ROLE_PROCUREMENT_OFFICER, MODULE_PROCUREMENT),
    # --- Vendor Intake --------------------------------------------------------
    _t(VENDOR_ONBOARDING_REQUESTED, HIGH, "Vendor onboarding requested", "Start vendor onboarding", ROLE_VENDOR_INTAKE, MODULE_VENDOR_MANAGEMENT),
    _t(VENDOR_ONBOARDING_ASSIGNED, HIGH, "Onboarding request assigned to you", "Process onboarding request", ROLE_VENDOR_INTAKE, MODULE_VENDOR_MANAGEMENT),
    _t(VENDOR_INFORMATION_REQUIRED, HIGH, "Vendor information required", "Collect missing information", ROLE_VENDOR_INTAKE, MODULE_VENDOR_MANAGEMENT),
    _t(VENDOR_PRESCREEN_REQUIRED, HIGH, "Vendor pre-screen required", "Complete pre-screening", ROLE_VENDOR_INTAKE, MODULE_VENDOR_MANAGEMENT),
    # --- AP Executive ---------------------------------------------------------
    _t(INVOICE_REVIEW_REQUIRED, HIGH, "Invoice review required", "Review invoice", ROLE_AP_EXECUTIVE, MODULE_INVOICE_MANAGEMENT),
    _t(INVOICE_VALIDATION_EXCEPTION, HIGH, "Invoice validation exception", "Resolve invoice exception", ROLE_AP_EXECUTIVE, MODULE_INVOICE_MANAGEMENT),
    _t(INVOICE_RETURNED, HIGH, "Invoice returned for correction", "Review and correct invoice", ROLE_AP_EXECUTIVE, MODULE_INVOICE_MANAGEMENT),
    _t(INVOICE_PAYMENT_ACTION_REQUIRED, HIGH, "Invoice payment action required", "Process payment action", ROLE_AP_EXECUTIVE, MODULE_INVOICE_MANAGEMENT),
    _t(INVOICE_DUE, HIGH, "Invoice payment due", "Review payment status", ROLE_AP_EXECUTIVE, MODULE_INVOICE_MANAGEMENT),
    _t(INVOICE_OVERDUE, CRITICAL, "Invoice overdue", "Resolve overdue invoice", ROLE_AP_EXECUTIVE, MODULE_INVOICE_MANAGEMENT),
    # --- Invoice approver: runtime-assigned users only, never a role broadcast
    _t(INVOICE_APPROVAL_REQUIRED, HIGH, "Invoice approval required", "Approve or reject", None, MODULE_INVOICE_MANAGEMENT),
    _t(INVOICE_APPROVAL_AGEING, HIGH, "Invoice approval pending", "Complete approval", None, MODULE_INVOICE_MANAGEMENT),
    # --- Finance payment user -------------------------------------------------
    _t(PAYMENT_READY, HIGH, "Invoice ready for payment", "Process payment", ROLE_PAYMENT_PROCESSOR, MODULE_PAYMENTS),
    _t(PAYMENT_DUE, HIGH, "Scheduled payment due", "Process scheduled payment", ROLE_PAYMENT_PROCESSOR, MODULE_PAYMENTS),
    _t(PAYMENT_FAILED, CRITICAL, "Payment failed", "Resolve payment failure", ROLE_PAYMENT_PROCESSOR, MODULE_PAYMENTS),
    _t(PAYMENT_EXCEPTION, HIGH, "Payment exception", "Resolve payment exception", ROLE_PAYMENT_PROCESSOR, MODULE_PAYMENTS),
    # --- Finance executive ----------------------------------------------------
    # AP has no permission -> user mapping (only UMS roles are synced), so the
    # INVOICE_TDS_VERIFY holders are reached through their UMS role.
    _t(INVOICE_TDS_VERIFICATION_REQUIRED, MEDIUM, "TDS verification required", "Verify TDS", ROLE_FINANCE_EXECUTIVE, MODULE_PAYMENTS),
    # --- Finance manager ------------------------------------------------------
    _t(FINANCE_ACTION_REQUIRED, HIGH, "Finance action required", "Review finance action", ROLE_FINANCE_MANAGER, MODULE_PAYMENTS),
    _t(FINANCE_ESCALATION, CRITICAL, "Finance escalation", "Review escalated issue", ROLE_FINANCE_MANAGER, MODULE_PAYMENTS),
    # --- Admin ----------------------------------------------------------------
    _t(WORKFLOW_CONFIGURATION_BLOCKED, CRITICAL, "Workflow configuration blocked", "Review workflow configuration", ROLE_ADMIN, MODULE_SYSTEM_CONFIGURATION),
    _t(SYSTEM_CONFIGURATION_EXCEPTION, CRITICAL, "System configuration exception", "Resolve system exception", ROLE_ADMIN, MODULE_SYSTEM_CONFIGURATION),
)}


# ---------------------------------------------------------------------------
# Catalogued but deliberately NOT emitted (yet). Kept so the contract with the
# frontend is stable; each reason is why no trigger exists today.
# ---------------------------------------------------------------------------
_NEEDS_SCHEDULER = "time-based; needs a scheduler, which the backend does not have"
UNEMITTED_TYPES: Dict[str, str] = {
    RFQ_DEADLINE_REACHED: _NEEDS_SCHEDULER,
    QUOTATION_VALIDITY_ENDING: _NEEDS_SCHEDULER,
    INVOICE_DUE: _NEEDS_SCHEDULER,
    INVOICE_OVERDUE: _NEEDS_SCHEDULER,
    INVOICE_APPROVAL_AGEING: _NEEDS_SCHEDULER,
    PAYMENT_DUE: _NEEDS_SCHEDULER,
    PAYMENT_EXCEPTION: "no payment state represents an exception (only SCHEDULED/SENT/CLEARED/FAILED)",
    FINANCE_ACTION_REQUIRED: "no finance-management action state exists (TDS verification is "
                             "INVOICE_TDS_VERIFICATION_REQUIRED)",
    INVOICE_PAYMENT_ACTION_REQUIRED: "the post-approval payment step is Finance's (PAYMENT_READY), "
                                     "not an AP Executive action",
}


# ---------------------------------------------------------------------------
# Deep links (frontend-relative routes; one place to align with the UI)
# ---------------------------------------------------------------------------
_DEEP_LINKS = {
    ENTITY_PURCHASE_REQUISITION: "/procurement/purchase-requisitions/{id}",
    ENTITY_RFQ: "/procurement/rfq/{id}",
    ENTITY_QUOTATION: "/procurement/quotations/{id}",
    ENTITY_VENDOR_ONBOARDING_REQUEST: "/vendor-onboarding-requests/{id}",
    ENTITY_VENDOR_NDA: "/nda/{id}",
    ENTITY_INVOICE: "/invoices/{id}",
    ENTITY_PAYMENT: "/payments/{id}",
}


def module_for(notification_type: str) -> Optional[str]:
    definition = CATALOG.get(notification_type)
    return definition.module if definition else None


def types_for_module(module: str) -> tuple:
    return tuple(code for code, d in CATALOG.items() if d.module == module)


def deep_link_for(entity_type: str, entity_id) -> Optional[str]:
    template = _DEEP_LINKS.get(entity_type)
    return template.format(id=entity_id) if template else None


def threshold_bucket(kind: str, bucket) -> str:
    """Event identifier for deadline/threshold reminders (future scheduler):
    one notification per recipient per entity per bucket, e.g.
    threshold_bucket("due-in-days", 3) -> "due-in-days:3"."""
    return f"{kind}:{bucket}"
