-- Manual migration for the Vendor Onboarding Request workflow
-- (PR Officer -> Vendor Intaker handoff).
--
-- This codebase has no migration tool (Base.metadata.create_all only creates
-- missing tables and never alters existing ones), so:
--   * ap.vendor_onboarding_request is a NEW table -> created automatically by
--     create_all() the next time the app starts (model registered in
--     Data_Access_Layer/models/__init__.py).
--   * The status_master rows and the partial unique index below must be
--     applied by hand, the same way every other status_master row in this app
--     already is (see migration_rfq_workflow.sql).
--
-- Safe to re-run: the INSERT is ON CONFLICT DO NOTHING and the index is
-- CREATE INDEX IF NOT EXISTS.

-- ---------------------------------------------------------------
-- 1) Workflow statuses for the VENDOR_ONBOARDING module.
--
-- Added, never replaced: existing status_master rows for other modules are
-- untouched, and re-running this file inserts nothing. Application code
-- always resolves these by (module_name, status_code) - no status id is ever
-- hardcoded, so the ids these rows happen to receive do not matter.
-- ---------------------------------------------------------------
INSERT INTO ap.status_master (module_name, status_code, status_name, display_order) VALUES
    ('VENDOR_ONBOARDING', 'CREATED',            'Created',             10),
    ('VENDOR_ONBOARDING', 'ASSIGNED',           'Assigned',            20),
    ('VENDOR_ONBOARDING', 'IN_PROGRESS',        'In Progress',         30),
    ('VENDOR_ONBOARDING', 'PRE_SCREEN_PENDING', 'Pre-Screen Pending',  40),
    ('VENDOR_ONBOARDING', 'NEED_INFORMATION',   'Need Information',    50),
    ('VENDOR_ONBOARDING', 'PASSED',             'Passed',              60),
    ('VENDOR_ONBOARDING', 'FAILED',             'Failed',              70),
    ('VENDOR_ONBOARDING', 'COMPLETED',          'Completed',           80),
    ('VENDOR_ONBOARDING', 'CANCELLED',          'Cancelled',           90)
ON CONFLICT (module_name, status_code) DO NOTHING;

-- ---------------------------------------------------------------
-- 2) Duplicate-request prevention.
--
-- "Only one OPEN onboarding request per PR + department + category."
-- Keyed on closed_at (set by the service when the request reaches
-- COMPLETED/FAILED/CANCELLED) rather than on status_id, so the constraint
-- encodes no status ids and a failed/cancelled attempt correctly frees the
-- slot for a retry.
--
-- Run this only AFTER the app has started once and create_all() has created
-- ap.vendor_onboarding_request - same ordering caveat as fk_quotation_rfq in
-- migration_rfq_workflow.sql.
-- ---------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_onboarding_request_open
    ON ap.vendor_onboarding_request (pr_id, department_id, purchase_category_id)
    WHERE closed_at IS NULL;

-- Verification:
--   SELECT status_code, status_name, display_order FROM ap.status_master
--   WHERE module_name = 'VENDOR_ONBOARDING' ORDER BY display_order;   -- expect 9 rows
--
--   SELECT column_name, data_type, is_nullable FROM information_schema.columns
--   WHERE table_schema='ap' AND table_name='vendor_onboarding_request'
--   ORDER BY ordinal_position;                                        -- expect 17 columns
--
--   SELECT indexname FROM pg_indexes
--   WHERE schemaname='ap' AND tablename='vendor_onboarding_request';
