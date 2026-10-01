-- Rollback for migration_payment_tds_tracking.sql. Deploy the previous code
-- version FIRST. DESTROYS recorded TDS tracking details, TDS documents and
-- payment receipt metadata (the S3 objects themselves are not deleted) and
-- payment remarks - export them first if they matter.

BEGIN;
DROP TABLE IF EXISTS ap.invoice_tds_document;
DROP TABLE IF EXISTS ap.invoice_tds_tracking;
DROP TABLE IF EXISTS ap.payment_document;
DROP INDEX IF EXISTS ap.idx_payment_invoice_invoice_payment;
DROP INDEX IF EXISTS ap.idx_invoice_tds_applicable;
ALTER TABLE ap.payment DROP COLUMN IF EXISTS remarks;
COMMIT;
