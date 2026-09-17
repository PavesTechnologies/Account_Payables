-- Manual migration: fixes a stale foreign key left over from
-- migration_approval_workflow.sql's table rename.
--
-- What happened: ap.invoice_approval_step (and its FK to ap.invoice_approval) got created by
-- create_all() while the OLD single-level ap.invoice_approval table still existed under that
-- name. When migration_approval_workflow.sql later ran `ALTER TABLE ap.invoice_approval RENAME
-- TO invoice_approval_legacy`, Postgres keeps every existing foreign key pointed at the same
-- table by OID, not by name — so fk_invoice_approval_step_approval silently started pointing at
-- invoice_approval_legacy instead of the table it was meant to reference. create_all() then
-- created a fresh, empty ap.invoice_approval table under the now-free name (the new multi-level
-- shape), but never revisits an existing constraint, so the FK was left targeting the wrong
-- table indefinitely. The application has been inserting real InvoiceApproval rows into the new
-- table the whole time — every subsequent invoice_approval_step insert referencing one of those
-- rows fails with a ForeignKeyViolation ("Key (invoice_approval_id)=(N) is not present in table
-- invoice_approval_legacy"), since invoice_approval_legacy has been empty since the rename.
--
-- Fix: drop and recreate the constraint against the correct table. Guarded so it only acts if
-- the constraint is actually still misdirected — safe to run more than once, and safe to run
-- before or after the app has been restarted since the rename.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_class frel ON frel.oid = con.confrelid
        JOIN pg_namespace ns ON ns.oid = rel.relnamespace
        WHERE ns.nspname = 'ap'
          AND rel.relname = 'invoice_approval_step'
          AND con.conname = 'fk_invoice_approval_step_approval'
          AND frel.relname = 'invoice_approval_legacy'
    ) THEN
        ALTER TABLE ap.invoice_approval_step
            DROP CONSTRAINT fk_invoice_approval_step_approval;

        ALTER TABLE ap.invoice_approval_step
            ADD CONSTRAINT fk_invoice_approval_step_approval
            FOREIGN KEY (invoice_approval_id)
            REFERENCES ap.invoice_approval (invoice_approval_id)
            ON DELETE CASCADE;
    END IF;
END $$;
