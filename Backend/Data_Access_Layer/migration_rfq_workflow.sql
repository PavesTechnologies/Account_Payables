-- Manual migration for the RFQ workflow feature.
-- This codebase has no migration tool (Base.metadata.create_all only creates
-- missing tables and never alters existing ones), so:
--   * ap.rfq and ap.rfq_vendor are new tables -> created automatically by
--     create_all() the next time the app starts (models registered in
--     Data_Access_Layer/models/__init__.py).
--   * The ALTER TABLE statements below are required manually, the same way
--     status_master rows already have to be inserted manually in this app.

ALTER TABLE ap.purchase_requisition
    ADD COLUMN IF NOT EXISTS sourcing_type VARCHAR(20),
    ADD COLUMN IF NOT EXISTS selection_reason TEXT;

-- Postgres has no "ADD CONSTRAINT IF NOT EXISTS", so these are wrapped to
-- stay safely re-runnable (this file is applied by hand, not by a tracked
-- migration tool, so re-runs are a real scenario to guard against).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_pr_sourcing_type'
    ) THEN
        ALTER TABLE ap.purchase_requisition
            ADD CONSTRAINT chk_pr_sourcing_type
            CHECK (sourcing_type IS NULL OR sourcing_type IN ('CATALOG', 'RFQ'));
    END IF;
END $$;

ALTER TABLE ap.quotation
    ADD COLUMN IF NOT EXISTS rfq_id BIGINT,
    ADD COLUMN IF NOT EXISTS delivery_days INTEGER,
    ADD COLUMN IF NOT EXISTS payment_terms VARCHAR(100);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_quotation_delivery_days'
    ) THEN
        ALTER TABLE ap.quotation
            ADD CONSTRAINT chk_quotation_delivery_days
            CHECK (delivery_days IS NULL OR delivery_days >= 0);
    END IF;
END $$;

-- fk_quotation_rfq is added after ap.rfq exists (create_all creates it on
-- app startup); run this only after that table is present.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_quotation_rfq'
    ) THEN
        ALTER TABLE ap.quotation
            ADD CONSTRAINT fk_quotation_rfq
            FOREIGN KEY (rfq_id) REFERENCES ap.rfq(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_quotation_rfq ON ap.quotation (rfq_id);

-- New status_master rows for the RFQ module (no seed mechanism exists in
-- this app; every other module's statuses were already inserted the same
-- manual way). display_order is illustrative - align it with your existing
-- rows' numbering convention if one is already in use.
INSERT INTO ap.status_master (module_name, status_code, status_name, display_order) VALUES
    ('RFQ', 'DRAFT',             'Draft',             10),
    ('RFQ', 'SENT',              'Sent',              20),
    ('RFQ', 'RESPONSE_RECEIVED', 'Response Received', 30),
    ('RFQ', 'CLOSED',            'Closed',            40)
ON CONFLICT (module_name, status_code) DO NOTHING;
