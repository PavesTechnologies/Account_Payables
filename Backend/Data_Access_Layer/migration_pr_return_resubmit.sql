-- Manual migration for the PR "Return for Clarification" / "Resubmit" workflow.
-- No schema changes: this feature reuses purchase_requisition's existing
-- approved_by/approved_at/approval_comment columns (the same fields
-- approve/reject already overload) and the existing generic ap.audit_log
-- table (already used by PurchaseOrderService) for history. The only new
-- ingredient is one status_master row.

INSERT INTO ap.status_master (module_name, status_code, status_name, display_order) VALUES
    ('PURCHASE_REQUISITION', 'RETURNED', 'Returned for Clarification', 25)
ON CONFLICT (module_name, status_code) DO NOTHING;
