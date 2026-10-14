-- Rollback of migration_payment_run.sql. Payments created by runs stay in ap.payment (they are ordinary
-- payments); only the run grouping is removed.
BEGIN;
DROP TABLE IF EXISTS ap.payment_run_item;
DROP TABLE IF EXISTS ap.payment_run;
COMMIT;
