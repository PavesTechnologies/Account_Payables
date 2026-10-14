-- Rollback of migration_accounting_export.sql. Removes the export history (the next export lists every
-- voucher as "not yet exported"). Ledger names in system_configuration are kept (ACCT_LEDGER_* keys);
-- remove them with: DELETE FROM ap.system_configuration WHERE config_key LIKE 'ACCT\_LEDGER\_%';
BEGIN;
DROP TABLE IF EXISTS ap.accounting_export_item;
DROP TABLE IF EXISTS ap.accounting_export;
COMMIT;
