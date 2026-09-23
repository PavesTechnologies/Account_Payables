-- Manual migration: persist the editable NDA content on ap.vendor_nda.
--
-- This codebase has no migration tool (Base.metadata.create_all only creates
-- MISSING tables and never alters existing ones), so an ALTER on the already
-- existing ap.vendor_nda must be applied by hand - exactly like
-- migration_rfq_workflow.sql and migration_purchase_category_department.sql.
-- Without this file a deployment that already ran migration_nda.sql will fail
-- at runtime with:
--     psycopg2.errors.UndefinedColumn:
--     column vendor_nda.content does not exist
--
-- WHAT THIS ADDS AND WHY
-- ----------------------
-- The NDA editor persists the user's edits server-side so that Send delivers
-- the edited wording rather than the original generated document. The latest
-- editable text lives directly on ap.vendor_nda (no new table): there is one
-- current working copy per NDA, and the per-revision history is already
-- captured in ap.audit_log under table_name='vendor_nda'.
--
--   content            - latest editable NDA wording (INTERNAL working copy)
--   content_version    - revision counter used for optimistic concurrency
--   content_updated_at - when the working copy last changed
--   content_updated_by - who last changed it
--
-- content is NOT the vendor-signed document. The signed PDF stays in the
-- private S3 bucket behind vendor_nda.signed_document_key and is never
-- written into this column.
--
-- NOTHING EXISTING IS TOUCHED
-- ---------------------------
-- No status_master row is added, changed or renumbered; no NDA status id is
-- referenced; document_key / signed_document_key and every existing FK and
-- index are left exactly as they are. No row is deleted or updated except the
-- one-off backfill of content_version on pre-existing rows (see below), which
-- only fills a value that was NULL for a column that did not exist before.
--
-- Safe to re-run: every statement is IF NOT EXISTS / guarded.

-- ---------------------------------------------------------------
-- 1) Editable content columns.
--
-- content_version is added nullable first, backfilled, and only then made NOT
-- NULL. Adding it as NOT NULL DEFAULT 1 in one step also works on modern
-- Postgres, but the three-step form is safe on every version and makes the
-- backfill of existing rows explicit.
-- ---------------------------------------------------------------
ALTER TABLE ap.vendor_nda
    ADD COLUMN IF NOT EXISTS content            TEXT,
    ADD COLUMN IF NOT EXISTS content_version    INTEGER,
    ADD COLUMN IF NOT EXISTS content_updated_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS content_updated_by VARCHAR(100);

-- Pre-existing NDAs have no editable copy yet; they start at revision 1 so the
-- first save from the editor behaves identically to a freshly generated NDA.
UPDATE ap.vendor_nda
SET content_version = 1
WHERE content_version IS NULL;

ALTER TABLE ap.vendor_nda
    ALTER COLUMN content_version SET DEFAULT 1;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ap'
          AND table_name   = 'vendor_nda'
          AND column_name  = 'content_version'
          AND is_nullable  = 'YES'
    ) THEN
        ALTER TABLE ap.vendor_nda
            ALTER COLUMN content_version SET NOT NULL;
    END IF;
END $$;

-- ---------------------------------------------------------------
-- 2) Column comments (documentation only - no behaviour change).
-- ---------------------------------------------------------------
COMMENT ON COLUMN ap.vendor_nda.content IS
    'Latest editable NDA wording (internal working copy). Never the vendor-signed document - that is signed_document_key.';
COMMENT ON COLUMN ap.vendor_nda.content_version IS
    'Revision counter for the editable content; used for optimistic concurrency on PUT /apm/nda/{nda_id}/content.';
COMMENT ON COLUMN ap.vendor_nda.content_updated_at IS
    'When the editable content was last saved.';
COMMENT ON COLUMN ap.vendor_nda.content_updated_by IS
    'User identifier of whoever last saved the editable content.';

-- Verification:
--   SELECT column_name, data_type, is_nullable, column_default
--   FROM information_schema.columns
--   WHERE table_schema='ap' AND table_name='vendor_nda'
--     AND column_name LIKE 'content%'
--   ORDER BY ordinal_position;          -- expect 4 rows, content_version NOT NULL DEFAULT 1
--
--   SELECT count(*) FROM ap.vendor_nda WHERE content_version IS NULL;  -- expect 0
--
--   -- Existing columns must be untouched:
--   SELECT count(*) FROM information_schema.columns
--   WHERE table_schema='ap' AND table_name='vendor_nda'
--     AND column_name IN ('document_key','signed_document_key');       -- expect 2
