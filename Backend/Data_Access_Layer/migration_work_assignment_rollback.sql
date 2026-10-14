-- Rollback of migration_work_assignment.sql. Removes assignments and rules; invoices are untouched.
BEGIN;
DROP TABLE IF EXISTS ap.invoice_assignment;
DROP TABLE IF EXISTS ap.work_assignment_rule;
COMMIT;
