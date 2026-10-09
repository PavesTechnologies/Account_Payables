-- Rollback for migration_payment_term_compliance.sql.
-- Drops ONLY what that migration added. Deploy the previous code version
-- first (the models map the vendor / purchase_order columns removed below).
-- Data in the dropped tables/columns (compliance records, agreements, MSME
-- flags, PO payment_term_id) is lost - export it first if it matters.

BEGIN;

DROP TABLE IF EXISTS ap.invoice_payment_term;
DROP TABLE IF EXISTS ap.vendor_agreement_document;
DROP TABLE IF EXISTS ap.vendor_agreement;

ALTER TABLE ap.purchase_order DROP CONSTRAINT IF EXISTS fk_po_payment_term;
ALTER TABLE ap.purchase_order DROP COLUMN IF EXISTS payment_term_id;

ALTER TABLE ap.vendor DROP CONSTRAINT IF EXISTS vendor_msme_category_chk;
ALTER TABLE ap.vendor DROP COLUMN IF EXISTS msme_category;
ALTER TABLE ap.vendor DROP COLUMN IF EXISTS udyam_number;
ALTER TABLE ap.vendor DROP COLUMN IF EXISTS msme_registered;

DELETE FROM ap.system_configuration
WHERE config_key IN ('MSME_MAX_PAYMENT_DAYS', 'MSME_DEFAULT_PAYMENT_DAYS');

COMMIT;
