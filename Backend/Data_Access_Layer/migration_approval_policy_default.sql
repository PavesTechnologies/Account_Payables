-- Manual migration: adds default/catch-all policy support to
-- ap.approval_policy (Backend/Business_Layer/services/approval_policy_service.py's
-- match_policy fallback). This codebase has no migration tool
-- (Base.metadata.create_all only creates missing tables and never alters
-- existing ones), so this is applied by hand, same as every other schema
-- change in this project.
--
-- department_id/purchase_category_id become nullable because a default
-- policy has no department/category/amount scoping at all - it applies
-- only when nothing more specific matches (see ApprovalPolicy's
-- docstring in Data_Access_Layer/models/approval.py). Every existing
-- row keeps its current NOT NULL values; nothing is backfilled or reset.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ap' AND table_name = 'approval_policy' AND column_name = 'is_default'
    ) THEN
        ALTER TABLE ap.approval_policy
            ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT false;
    END IF;

    ALTER TABLE ap.approval_policy ALTER COLUMN department_id DROP NOT NULL;
    ALTER TABLE ap.approval_policy ALTER COLUMN purchase_category_id DROP NOT NULL;
END $$;
