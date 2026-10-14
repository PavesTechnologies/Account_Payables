-- Rollback of migration_recurring_schedule.sql. Removes the recurring schedule tables only;
-- invoices are untouched (occurrences only point at them).
BEGIN;
DROP TABLE IF EXISTS ap.recurring_occurrence;
DROP TABLE IF EXISTS ap.recurring_schedule;
COMMIT;
