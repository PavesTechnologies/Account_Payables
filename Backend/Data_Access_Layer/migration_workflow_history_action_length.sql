-- Manual migration: widen ap.audit_log.action to accommodate the PR
-- workflow-history event vocabulary (Business_Layer/utils/pr_workflow_events.py).
--
-- Root cause: the PR workflow history feature reuses the existing generic
-- ap.audit_log table (table_name='purchase_requisition') for its event
-- trail, but action was VARCHAR(20) - too short for the mandated canonical
-- event names, e.g. 'SUBMITTED_FOR_APPROVAL' (22 chars) and
-- 'PR_SENT_BACK_FOR_CLARIFICATION' (30 chars). This was masked by the unit
-- test suite (which uses fake, non-DB-backed DAOs) and only surfaced when
-- exercised against the real database.
--
-- This codebase has no migration tool (Base.metadata.create_all only creates
-- missing tables and never alters existing ones), so this ALTER is applied
-- by hand, the same way as every other schema change in this project (see
-- migration_uom_master.sql etc). Widening a VARCHAR column is a safe,
-- backward-compatible, non-destructive change - every existing shorter
-- action value (used across goods_receipt/invoice_approval/payment/
-- purchase_order/vendor/procurement/rfq services) remains valid as-is.

DO $$
BEGIN
    IF (
        SELECT character_maximum_length FROM information_schema.columns
        WHERE table_schema = 'ap' AND table_name = 'audit_log' AND column_name = 'action'
    ) < 50 THEN
        ALTER TABLE ap.audit_log
            ALTER COLUMN action TYPE VARCHAR(50);
    END IF;
END $$;
