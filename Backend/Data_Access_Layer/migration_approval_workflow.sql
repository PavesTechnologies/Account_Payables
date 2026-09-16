-- Manual migration: supports the configurable, policy-driven invoice
-- approval workflow (Backend/Business_Layer/services/approval_policy_service.py,
-- approver_resolver_service.py, invoice_approval_service.py).
--
-- This codebase has no migration tool (Base.metadata.create_all only
-- creates missing tables and never alters existing ones), so these ALTERs
-- are applied by hand, the same way as every other schema change in this
-- project (see migration_workflow_history_action_length.sql etc). The
-- brand-new tables this feature needs (approval_policy,
-- approval_policy_level, invoice_approval_step,
-- invoice_approval_step_approver, department_approver) do NOT need a
-- hand-written CREATE TABLE - they're created automatically by
-- create_all() the next time the app starts, now that their SQLAlchemy
-- models exist (Backend/Data_Access_Layer/models/approval.py).
--
-- 1) ap.department.eos_department_uuid: an earlier revision of this
--    feature added this column to bridge ap.department to the EOS-sourced
--    department in ap.approver_directory, for DEPARTMENT_APPROVER
--    resolution. Superseded before ever being populated (confirmed all
--    NULL) by ap.department_approver - an AP-owned admin mapping,
--    deliberately not tied to a UMS role or an EOS department UUID (see
--    approval.py's DepartmentApprover docstring for why). Dropped below
--    rather than left as dead weight.
--
-- 2) ap.invoice: department_id/purchase_category_id carry the approval
--    context for an invoice - derived from the PR/PO chain for a PO
--    invoice, or collected during OCR review for a NON-PO invoice.
--    Nullable and unbackfilled by design: only invoices actually sent
--    through the new approval flow need these populated; every existing
--    historical invoice is unaffected.
--
-- 3) ap.invoice_approval: the old single-level shape (approver_name,
--    decision) is being replaced by a policy/step/step-approver runtime
--    model - see approval.py's InvoiceApproval docstring. Renamed rather
--    than dropped, per this project's rule to never blindly discard
--    existing data even though the live table currently has 0 rows (per
--    the 2026-09-15 data snapshot) - create_all() then creates the new
--    shape fresh under the original table name.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ap' AND table_name = 'department' AND column_name = 'eos_department_uuid'
    ) THEN
        ALTER TABLE ap.department
            DROP COLUMN eos_department_uuid;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ap' AND table_name = 'invoice' AND column_name = 'department_id'
    ) THEN
        ALTER TABLE ap.invoice
            ADD COLUMN department_id BIGINT REFERENCES ap.department(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ap' AND table_name = 'invoice' AND column_name = 'purchase_category_id'
    ) THEN
        ALTER TABLE ap.invoice
            ADD COLUMN purchase_category_id BIGINT REFERENCES ap.purchase_category(id);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'ap' AND table_name = 'invoice_approval'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'ap' AND table_name = 'invoice_approval_legacy'
    ) THEN
        ALTER TABLE ap.invoice_approval RENAME TO invoice_approval_legacy;
        ALTER TABLE ap.invoice_approval_legacy
            RENAME CONSTRAINT invoice_approval_pkey TO invoice_approval_legacy_pkey;
        ALTER TABLE ap.invoice_approval_legacy
            RENAME CONSTRAINT invoice_approval_invoice_id_fkey TO invoice_approval_legacy_invoice_id_fkey;
        ALTER TABLE ap.invoice_approval_legacy
            RENAME CONSTRAINT invoice_approval_invoice_issue_id_fkey TO invoice_approval_legacy_invoice_issue_id_fkey;
        -- Postgres index names are unique per-schema, not per-table, and
        -- ALTER TABLE ... RENAME TO does not rename a table's indexes -
        -- this one must be renamed explicitly or it collides with the
        -- identically-named index create_all() creates on the new
        -- ap.invoice_approval table.
        ALTER INDEX ap.idx_invoice_approval_invoice RENAME TO idx_invoice_approval_legacy_invoice;
    END IF;
END $$;
