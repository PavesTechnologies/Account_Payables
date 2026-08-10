-- Adds the INVOICE/OCR_REVIEW_PENDING and INVOICE/OCR_FAILED status_master
-- rows required by the /process-invoice pipeline. Additive and idempotent:
-- safe to run against a database that already has them (e.g. one that
-- picked up the corrected seed in Database/ap_schema.sql).
--
-- Display order matches Database/ap_schema.sql: DRAFT(1) < OCR_REVIEW_PENDING(2)
-- < OCR_FAILED(3) < PENDING_APPROVAL(4) < ... existing rows shift down by 2
-- from their previous display_order to keep ordering consistent.

UPDATE status_master
   SET display_order = display_order + 2
 WHERE module_name = 'INVOICE'
   AND status_code IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'PARTIALLY_PAID', 'PAID', 'DISPUTED')
   AND NOT EXISTS (
       SELECT 1 FROM status_master
        WHERE module_name = 'INVOICE' AND status_code = 'OCR_REVIEW_PENDING'
   );

INSERT INTO status_master (module_name, status_code, status_name, display_order)
VALUES
    ('INVOICE', 'OCR_REVIEW_PENDING', 'Under OCR Review', 2),
    ('INVOICE', 'OCR_FAILED', 'OCR Failed', 3)
ON CONFLICT (module_name, status_code) DO NOTHING;
