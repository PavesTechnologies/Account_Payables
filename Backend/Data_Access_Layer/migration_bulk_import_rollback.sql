-- Rollback for migration_bulk_import.sql. Drops ONLY the import tracking tables; payments, challans
-- and filings recorded through an import are ordinary records and are NOT touched.
BEGIN;
DROP TABLE IF EXISTS ap.bulk_import_row;
DROP TABLE IF EXISTS ap.bulk_import_job;
DELETE FROM ap.system_configuration WHERE config_key IN ('BULK_IMPORT_SHAREPOINT_ENABLED', 'BULK_IMPORT_SHAREPOINT_LAST_RUN');
COMMIT;
