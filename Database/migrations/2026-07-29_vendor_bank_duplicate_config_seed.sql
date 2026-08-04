-- Migration: Seed the VENDOR_BANK_DUPLICATE_ACROSS_VENDORS system_configuration
-- key used by the vendor bank-account duplicate check
-- (VendorService._bank_duplicate_across_vendors_enabled).
--
-- Context: this project has no migration tool (no Alembic) — schema is
-- hand-maintained in Database/ap_schema.sql and applied via
-- Base.metadata.create_all() at app startup, which only creates missing
-- tables and never seeds/alters existing ones. ap_schema.sql has been
-- updated with this same row for any future fresh deployment; this file
-- seeds it into an already-deployed database.

BEGIN;

INSERT INTO ap.system_configuration (config_key, config_value, data_type, description)
VALUES (
    'VENDOR_BANK_DUPLICATE_ACROSS_VENDORS',
    'false',
    'BOOLEAN',
    'Whether a vendor bank account_number/IBAN must be unique across all vendors, not just within one vendor'
)
ON CONFLICT (config_key) DO NOTHING;

COMMIT;
