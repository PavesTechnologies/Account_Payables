-- Rollback of migration_invoice_gst.sql. Removes the ITC register only; invoices are untouched.
BEGIN;
DROP TABLE IF EXISTS ap.invoice_gst;
COMMIT;
