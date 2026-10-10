-- Rollback for migration_tds_challan.sql. Drops ONLY the challan / filing tables. Per-invoice TDS
-- status, dates, challan numbers and filing references in ap.invoice_tds_tracking are NOT touched.
-- Deploy the previous code version first, otherwise create_all recreates the tables.

BEGIN;

DROP TABLE IF EXISTS ap.tds_return_filing_invoice;
DROP TABLE IF EXISTS ap.tds_return_filing;
DROP TABLE IF EXISTS ap.tds_challan_allocation;
DROP TABLE IF EXISTS ap.tds_challan;

DELETE FROM ap.system_configuration WHERE config_key = 'TDS_CHALLAN_TOLERANCE';

COMMIT;
