-- Rollback for migration_tds_configuration.sql. Deploy the previous code
-- version FIRST (its TaxRule model does not map the columns dropped here).
--
-- Refuses to run if any invoice_tds snapshot already references the split
-- TDS_194J_TECH variant (real business data - resolve by hand). NOTE: this
-- DROPS ap.tds_deductor and the section/deductor columns, i.e. any deductor
-- master data and section values entered through the UI are lost - export
-- them first if needed.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM ap.invoice_tds t
        JOIN ap.tax_rule r ON r.tax_rule_id = t.tds_rule_id
        WHERE r.rule_code = 'TDS_194J_TECH'
    ) THEN
        RAISE EXCEPTION 'invoice_tds rows reference TDS_194J_TECH - resolve manually before rollback';
    END IF;
END $$;

-- Move the TECHNICAL_SERVICE condition back onto TDS_194J, then drop the split variant.
UPDATE ap.tax_rule_condition c
SET tax_rule_id = src.tax_rule_id, updated_at = CURRENT_TIMESTAMP
FROM ap.tax_rule src, ap.tax_rule tech
WHERE src.rule_code = 'TDS_194J'
  AND tech.rule_code = 'TDS_194J_TECH'
  AND c.tax_rule_id = tech.tax_rule_id
  AND c.condition_type = 'PAYMENT_NATURE'
  AND c.condition_value = 'TECHNICAL_SERVICE';

DELETE FROM ap.tax_rule WHERE rule_code = 'TDS_194J_TECH';  -- cascades its tax_rate_rule rows

ALTER TABLE ap.tax_rule DROP CONSTRAINT IF EXISTS tax_rule_tds_deductor_fk;
DROP INDEX IF EXISTS ap.idx_tax_rule_tds_deductor;
DROP INDEX IF EXISTS ap.idx_tax_rule_old_section;
ALTER TABLE ap.tax_rule DROP COLUMN IF EXISTS tds_deductor_id;
ALTER TABLE ap.tax_rule DROP COLUMN IF EXISTS new_section;
ALTER TABLE ap.tax_rule DROP COLUMN IF EXISTS old_section;

DROP TABLE IF EXISTS ap.tds_deductor;

ALTER TABLE ap.invoice_tds DROP COLUMN IF EXISTS rule_snapshot;
ALTER TABLE ap.invoice_tds DROP COLUMN IF EXISTS residency_type;
ALTER TABLE ap.invoice_tds DROP COLUMN IF EXISTS threshold_type;

-- Pure lookup indexes; harmless to keep, dropped for a faithful rollback.
DROP INDEX IF EXISTS ap.idx_tax_rule_category_active;
DROP INDEX IF EXISTS ap.idx_tax_rule_condition_rule;
DROP INDEX IF EXISTS ap.idx_tax_rule_condition_type_value;
DROP INDEX IF EXISTS ap.idx_tax_rate_rule_rule;
DROP INDEX IF EXISTS ap.idx_invoice_tds_rate_rule;
DROP INDEX IF EXISTS ap.idx_invoice_tds_payment_nature;

COMMIT;
