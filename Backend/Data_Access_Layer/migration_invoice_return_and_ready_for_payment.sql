-- Manual migration for two new INVOICE-module statuses (this app has no migration tool —
-- every status_master row is inserted by hand the same way as every other one; see
-- migration_rfq_workflow.sql / migration_pr_return_resubmit.sql for the identical precedent).
--
-- RETURNED_FOR_REVIEW: an approver sent the invoice back to the AP Executive for correction
-- (InvoiceApprovalService.send_back) instead of approving/rejecting it outright. The AP
-- Executive edits and resubmits via the existing OCR-review endpoint, which already always ends
-- at PENDING_APPROVAL, and a fresh send-for-approval call creates a brand new InvoiceApproval
-- cycle (the old one is marked CANCELLED, not deleted).
--
-- READY_FOR_PAYMENT: sits between APPROVED and PARTIALLY_PAID/PAID — Finance explicitly marks an
-- approved invoice ready (PaymentService.mark_ready_for_payment) before any payment can be
-- created against it; this was not automatic before and is still not automatic.
--
-- No schema changes beyond these two rows: RETURNED_FOR_REVIEW/CANCELLED are used on
-- Invoice.status_id and InvoiceApproval/InvoiceApprovalStep.status respectively, both of which
-- already accept these values without a CHECK-constraint change (CANCELLED was already a valid
-- value on both; RETURNED_FOR_REVIEW only needs to exist in status_master, not in any CHECK
-- constraint, since Invoice.status_id has no CHECK — it's a plain FK).
--
-- display_order values below are placeholders picked to sit logically between the existing
-- INVOICE rows (no in-repo seed file exists to read the real current values from — see the audit
-- note in invoice_status.py) — adjust to match the live status_master table's actual numbering
-- before/after applying if it differs.

INSERT INTO ap.status_master (module_name, status_code, status_name, display_order) VALUES
    ('INVOICE', 'RETURNED_FOR_REVIEW', 'Returned for Review', 45),
    ('INVOICE', 'READY_FOR_PAYMENT', 'Ready for Payment', 55),
    ('INVOICE', 'DISPUTED', 'Disputed', 90)
ON CONFLICT (module_name, status_code) DO NOTHING;
