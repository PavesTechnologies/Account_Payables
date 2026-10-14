-- Rollback of migration_vendor_bank_verification.sql. Vendor bank accounts themselves are untouched.
BEGIN;
DROP TABLE IF EXISTS ap.vendor_bank_verification;
COMMIT;
