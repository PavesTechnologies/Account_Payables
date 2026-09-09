# Backend/Business_Layer/utils/pr_workflow_events.py
"""Canonical PR workflow timeline event names, persisted via the existing
ap.audit_log table (table_name='purchase_requisition'). Shared between
ProcurementService and RFQService - procurement_service.py already imports
from rfq_service.py, so a shared module (rather than either service
importing the other's constants) avoids a circular import.
"""

PR_REQUEST_RAISED = "PR_REQUEST_RAISED"
SUBMITTED_FOR_APPROVAL = "SUBMITTED_FOR_APPROVAL"
PR_APPROVED = "PR_APPROVED"
PR_REJECTED = "PR_REJECTED"
PR_SENT_BACK_FOR_CLARIFICATION = "PR_SENT_BACK_FOR_CLARIFICATION"
PR_UPDATED = "PR_UPDATED"
PR_RESUBMITTED = "PR_RESUBMITTED"
VENDOR_INVITED = "VENDOR_INVITED"
RFQ_SENT = "RFQ_SENT"
QUOTATION_RECEIVED = "QUOTATION_RECEIVED"
VENDOR_SELECTED = "VENDOR_SELECTED"
