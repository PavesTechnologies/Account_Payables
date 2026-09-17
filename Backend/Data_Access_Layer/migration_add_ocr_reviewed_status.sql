-- Manual migration: introduces OCR_REVIEWED as a real, distinct invoice status.
--
-- Before this: apply_ocr_review (the "review & save" action) left the invoice at
-- PENDING_APPROVAL directly, and send_for_approval never changed invoice.status_id at all — so
-- "just reviewed, never sent" and "sent, awaiting a decision" were the exact same status, with
-- no way to tell them apart from invoice.status_id alone.
--
-- After this: apply_ocr_review ends at OCR_REVIEWED; send_for_approval performs the real
-- OCR_REVIEWED -> PENDING_APPROVAL transition. PENDING_APPROVAL now means "sent" and nothing
-- else. See Business_Layer/services/invoice_process_service.py's apply_ocr_review docstring and
-- invoice_approval_service.py's send_for_approval.
--
-- 1) Add the status_master row, same pattern as every other hand-applied status addition in
--    this file (migration_invoice_return_and_ready_for_payment.sql etc.) — display_order is a
--    placeholder between OCR_REVIEW_PENDING and PENDING_APPROVAL; verify/adjust against the
--    live table's real ordering.
INSERT INTO ap.status_master (module_name, status_code, status_name, display_order) VALUES
    ('INVOICE', 'OCR_REVIEWED', 'Reviewed', 15)
ON CONFLICT (module_name, status_code) DO NOTHING;

-- 2) Data fixup for every invoice that already sits at PENDING_APPROVAL under the OLD meaning
--    (reviewed, but never actually sent — no InvoiceApproval row exists for it at all). Under
--    the new rule these need to be OCR_REVIEWED so Send for Approval accepts them again;
--    otherwise they'd be stuck, since the new guard now requires OCR_REVIEWED specifically.
--    Anything that genuinely IS in flight (has an InvoiceApproval row, active or historical) is
--    deliberately left untouched — its PENDING_APPROVAL is real under either meaning.
UPDATE ap.invoice i
SET status_id = (
        SELECT status_id FROM ap.status_master
        WHERE module_name = 'INVOICE' AND status_code = 'OCR_REVIEWED'
    )
WHERE i.status_id = (
        SELECT status_id FROM ap.status_master
        WHERE module_name = 'INVOICE' AND status_code = 'PENDING_APPROVAL'
    )
    AND NOT EXISTS (
        SELECT 1 FROM ap.invoice_approval ia WHERE ia.invoice_id = i.invoice_id
    );
