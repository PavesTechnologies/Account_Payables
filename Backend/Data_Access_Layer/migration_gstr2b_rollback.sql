-- Rollback of migration_gstr2b.sql. Removes the GSTR-2B imports and matches; ITC claims go back to
-- "claim what is in the books" (no 2B gate).
BEGIN;
DROP TABLE IF EXISTS ap.gstr2b_entry;
DROP TABLE IF EXISTS ap.gstr2b_import;
COMMIT;
