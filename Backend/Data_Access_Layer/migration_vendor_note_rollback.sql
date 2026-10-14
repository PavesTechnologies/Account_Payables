-- Rollback of migration_vendor_note.sql. Removes credit / debit notes; payables go back to
-- net amount - TDS (any TDS base already lowered by an applied note stays as recorded).
BEGIN;
DROP TABLE IF EXISTS ap.vendor_note;
COMMIT;
