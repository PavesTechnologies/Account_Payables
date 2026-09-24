-- Manual migration for the TDS (India withholding-tax) determination feature,
-- Phase 1 backend foundation. This app has no migration tool - every schema
-- change here is applied by hand the same way as every other migration_*.sql
-- in this directory (see migration_nda.sql for the identical precedent).
--
-- Table creation for ap.tds_payment_nature / ap.purchase_category_tds_mapping /
-- ap.vendor_tds_profile / ap.invoice_tds is NOT included here: they are new
-- tables, modeled in Backend/Data_Access_Layer/models/tds.py and registered in
-- models/__init__.py, so Base.metadata.create_all() creates them automatically
-- the next time the app starts on an environment where they don't exist yet
-- (create_all only ever creates missing tables, never alters existing ones -
-- see migration_nda.sql's docstring). On the environment this was developed
-- against, those four tables were already created ahead of time via equivalent
-- raw SQL (same column/constraint/index shapes the models below expect) -
-- this migration's ALTER/UPDATE/INSERT statements below apply cleanly on top
-- of that. On any OTHER environment, run this file only AFTER the app has
-- started at least once (so create_all has created the four tables), or
-- adjust the CREATE TABLE ordering yourself.
--
-- Everything below is safe to re-run: ALTER ... ADD COLUMN IF NOT EXISTS,
-- ADD CONSTRAINT guarded by a DO block, UPDATE (naturally idempotent - same
-- values every time), and INSERT ... ON CONFLICT DO NOTHING.

-- ---------------------------------------------------------------
-- 1) Minimal TDS extension to the existing generic tax_rule table
--    (spec: "do not unnecessarily redesign the entire tax framework" - a TDS
--    rate is just a tax_rule row with rule_category='TDS_RATE', matched the
--    same way GST_RATE/TAX_COMPONENT rows already are in
--    InvoiceExtractionDAO.get_gst_rate_rule_for_sac). Only two things were
--    missing from that generic framework for TDS specifically:
--
--    - legal_reference: kept separate from rule_code/rule_name on purpose.
--      rule_code today literally is the old Income-tax Act, 1961 section
--      number (TDS_194C etc.) - baking that same string in as the
--      "permanent" legal identifier would silently mislabel a rule if the
--      underlying section is renumbered/replaced by a later legal framework.
--      Only this column needs to change then, not rule_code (which
--      InvoiceTds.tds_rule_id and every other FK/reference points at).
--    - threshold_amount / threshold_type: no threshold concept existed
--      anywhere in tax_rule/tax_rate_rule/tax_rule_condition before this.
--      threshold_type distinguishes a single-transaction limit from a
--      financial-year cumulative-aggregate limit (TDSDeterminationService
--      evaluates AGGREGATE_PERIOD via ap.invoice_tds.current_transaction_amount
--      summed across the vendor+payment-nature's other invoices in the same
--      1-Apr-31-Mar financial year).
--
--    Both columns are nullable and meaningless for the existing GST_RATE/
--    TAX_COMPONENT rows - this is additive only, no existing row's meaning
--    changes.
-- ---------------------------------------------------------------

ALTER TABLE ap.tax_rule ADD COLUMN IF NOT EXISTS legal_reference VARCHAR(50);
ALTER TABLE ap.tax_rule ADD COLUMN IF NOT EXISTS threshold_amount NUMERIC(18,2);
ALTER TABLE ap.tax_rule ADD COLUMN IF NOT EXISTS threshold_type VARCHAR(20);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tax_rule_threshold_type_chk'
    ) THEN
        ALTER TABLE ap.tax_rule ADD CONSTRAINT tax_rule_threshold_type_chk
            CHECK (threshold_type IS NULL OR threshold_type IN ('PER_TRANSACTION', 'AGGREGATE_PERIOD'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tax_rule_threshold_amount_chk'
    ) THEN
        ALTER TABLE ap.tax_rule ADD CONSTRAINT tax_rule_threshold_amount_chk
            CHECK (threshold_amount IS NULL OR threshold_amount >= 0);
    END IF;
END $$;

-- ---------------------------------------------------------------
-- 2) determination_status CHECK on ap.invoice_tds - the table as originally
--    created had no CHECK on this column at all. Added now, guarded, so it
--    applies cleanly whether the table was just created by create_all() (no
--    rows) or already has the one DETERMINED row from earlier ad-hoc testing.
-- ---------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'invoice_tds_determination_status_chk'
    ) THEN
        ALTER TABLE ap.invoice_tds ADD CONSTRAINT invoice_tds_determination_status_chk
            CHECK (determination_status IN ('PENDING', 'DETERMINED', 'VERIFIED'));
    END IF;
END $$;

-- ---------------------------------------------------------------
-- 3) Threshold/legal-reference defaults for the five TDS rules already
--    seeded in ap.tax_rule (rule_code TDS_194C/194J/194I/194H/194Q).
--
--    *** ILLUSTRATIVE DEFAULTS - CONFIRM WITH FINANCE/TAX BEFORE GO-LIVE ***
--    (same caveat this repo already applies to the NDA template body in
--    migration_nda.sql - these are placeholder figures reflecting a common
--    reading of each section's threshold, not a legal opinion. 194Q's real
--    applicability additionally depends on the buyer's prior-year turnover,
--    which this Phase 1 does not model.)
--
--    Every row below only ever touches TDS_RATE rules by rule_code - no
--    GST_RATE/TAX_COMPONENT row is touched.
-- ---------------------------------------------------------------

UPDATE ap.tax_rule SET
    legal_reference = 'Section 194C, Income-tax Act (FY2026-27)',
    threshold_type = 'AGGREGATE_PERIOD',
    threshold_amount = 100000.00
WHERE rule_code = 'TDS_194C';

UPDATE ap.tax_rule SET
    legal_reference = 'Section 194J, Income-tax Act (FY2026-27)',
    threshold_type = 'AGGREGATE_PERIOD',
    threshold_amount = 30000.00
WHERE rule_code = 'TDS_194J';

UPDATE ap.tax_rule SET
    legal_reference = 'Section 194I, Income-tax Act (FY2026-27)',
    threshold_type = 'AGGREGATE_PERIOD',
    threshold_amount = 240000.00
WHERE rule_code = 'TDS_194I';

UPDATE ap.tax_rule SET
    legal_reference = 'Section 194H, Income-tax Act (FY2026-27)',
    threshold_type = 'AGGREGATE_PERIOD',
    threshold_amount = 15000.00
WHERE rule_code = 'TDS_194H';

UPDATE ap.tax_rule SET
    legal_reference = 'Section 194Q, Income-tax Act (FY2026-27)',
    threshold_type = 'AGGREGATE_PERIOD',
    threshold_amount = 5000000.00
WHERE rule_code = 'TDS_194Q';

-- ---------------------------------------------------------------
-- 4) Seed data for ap.tds_payment_nature / ap.purchase_category_tds_mapping -
--    repeated here (ON CONFLICT DO NOTHING) for repeatability on any OTHER
--    environment; on the environment this was developed against these rows
--    already exist from earlier ad-hoc testing and are left untouched.
-- ---------------------------------------------------------------

INSERT INTO ap.tds_payment_nature (code, name, description) VALUES
    ('CONTRACTOR', 'Contractor Payments', 'Payments made for contract or work execution services'),
    ('PROFESSIONAL_SERVICE', 'Professional Services', 'Payments for professional services such as legal, accounting, consulting or similar services'),
    ('TECHNICAL_SERVICE', 'Technical Services', 'Payments for technical, specialized or technical consultancy services'),
    ('RENT', 'Rent', 'Payments towards rent of land, building, equipment or other applicable assets'),
    ('COMMISSION', 'Commission or Brokerage', 'Payments towards commission, brokerage or similar intermediary services'),
    ('PURCHASE_OF_GOODS', 'Purchase of Goods', 'Payments towards purchase of goods where TDS may apply'),
    ('INTEREST', 'Interest', 'Interest payments other than specified exempt categories'),
    ('OTHER', 'Other', 'Other payment natures requiring manual tax review')
ON CONFLICT (code) DO NOTHING;

-- Purchase-category -> suggested payment-nature defaults. Left as a
-- best-effort mapping for whatever purchase_category rows exist on this
-- environment (matched by code where recognized, OTHER otherwise) - these
-- are suggestions an AP Executive can always override per invoice
-- (TDSDeterminationService.update_inputs), never a legal determination.
INSERT INTO ap.purchase_category_tds_mapping (purchase_category_id, tds_payment_nature_id, is_default)
SELECT
    pc.id,
    tpn.id,
    TRUE
FROM ap.purchase_category pc
JOIN ap.tds_payment_nature tpn
    ON tpn.code = CASE pc.code
        WHEN 'IT_TECH'       THEN 'TECHNICAL_SERVICE'
        WHEN 'SOFTWARE_SAAS' THEN 'PROFESSIONAL_SERVICE'
        WHEN 'IT_SUPPORT'    THEN 'TECHNICAL_SERVICE'
        WHEN 'IT_HARDWARE'   THEN 'PURCHASE_OF_GOODS'
        WHEN 'PROF_SERV'     THEN 'PROFESSIONAL_SERVICE'
        WHEN 'FAC_ADMIN'     THEN 'CONTRACTOR'
        WHEN 'TRAVEL_LOG'    THEN 'OTHER'
        WHEN 'MARKETING'     THEN 'PROFESSIONAL_SERVICE'
        WHEN 'HR_SERV'       THEN 'PROFESSIONAL_SERVICE'
        WHEN 'FIN_SERV'      THEN 'PROFESSIONAL_SERVICE'
        ELSE 'OTHER'
    END
ON CONFLICT (purchase_category_id, tds_payment_nature_id) DO NOTHING;

-- Verification:
--   SELECT rule_code, legal_reference, threshold_type, threshold_amount
--   FROM ap.tax_rule WHERE rule_category = 'TDS_RATE' ORDER BY rule_code;   -- expect 5 rows, all populated
--
--   SELECT conname FROM pg_constraint
--   WHERE conname IN ('tax_rule_threshold_type_chk', 'tax_rule_threshold_amount_chk',
--                      'invoice_tds_determination_status_chk');              -- expect 3 rows
--
--   SELECT code, name FROM ap.tds_payment_nature ORDER BY id;                -- expect 8 rows
--
--   SELECT pc.code, tpn.code FROM ap.purchase_category_tds_mapping m
--   JOIN ap.purchase_category pc ON pc.id = m.purchase_category_id
--   JOIN ap.tds_payment_nature tpn ON tpn.id = m.tds_payment_nature_id
--   ORDER BY pc.code;
