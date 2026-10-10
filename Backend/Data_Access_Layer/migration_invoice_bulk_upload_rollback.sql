-- Rollback for migration_invoice_bulk_upload.sql.
-- Drops ONLY the two batch-tracking tables. Invoices created through bulk upload are ordinary
-- invoices and are NOT touched; only the batch history (which file became which invoice, failed
-- files, retry state) is lost - export it first if it matters. Deploy the previous code version
-- first, otherwise create_all recreates the tables on the next backend start.

BEGIN;

DROP TABLE IF EXISTS ap.invoice_upload_batch_item;
DROP TABLE IF EXISTS ap.invoice_upload_batch;

DELETE FROM ap.system_configuration WHERE config_key IN ('EMAIL_INTAKE_ENABLED', 'EMAIL_INTAKE_LAST_RUN');

COMMIT;
