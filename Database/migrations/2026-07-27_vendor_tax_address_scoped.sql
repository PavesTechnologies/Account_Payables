-- Migration: Scope vendor_tax to vendor_address instead of vendor directly.
--
-- Context: this project has no migration tool (no Alembic) — schema is
-- hand-maintained in Database/ap_schema.sql and applied via
-- Base.metadata.create_all() at app startup, which only creates missing
-- tables and never ALTERs existing ones. This file must be run manually
-- against the target database; ap_schema.sql has been updated to match
-- the resulting shape for any future fresh deployment.
--
-- Verified against the live database before writing this script:
--   - ap.vendor_tax currently has 0 rows, so no data backfill is required.
--   - vendor_address_id already exists (nullable) with a plain FK to
--     ap.vendor_address (no ON DELETE CASCADE) — added in an earlier,
--     partial pass at this same refactor.
--   - vendor_id exists but is NOT actually FK-constrained in the live DB.
--
-- If this is ever run against a database that already has vendor_tax rows,
-- STOP and backfill vendor_address_id manually first — this script assumes
-- the table is empty and will fail on the SET NOT NULL step otherwise.

BEGIN;

-- Drop the FK added without cascade in the earlier partial pass, so it can
-- be recreated with ON DELETE CASCADE (tax rows should die with their address).
ALTER TABLE ap.vendor_tax
    DROP CONSTRAINT IF EXISTS vendor_tax_vendor_address_id_fkey;

-- Drop legacy vendor-scoped constraints/columns.
ALTER TABLE ap.vendor_tax
    DROP CONSTRAINT IF EXISTS vendor_tax_vendor_id_fkey;

ALTER TABLE ap.vendor_tax
    DROP CONSTRAINT IF EXISTS vendor_tax_vendor_id_tax_type_id_key;

DROP INDEX IF EXISTS ap.uq_vendor_tax_per_location;
DROP INDEX IF EXISTS ap.uq_vendor_tax_single;

ALTER TABLE ap.vendor_tax
    DROP COLUMN IF EXISTS vendor_id;

ALTER TABLE ap.vendor_tax
    DROP COLUMN IF EXISTS tax_type_id;

-- vendor_address_id becomes the sole, required parent reference.
ALTER TABLE ap.vendor_tax
    ALTER COLUMN vendor_address_id SET NOT NULL;

ALTER TABLE ap.vendor_tax
    ADD CONSTRAINT vendor_tax_vendor_address_id_fkey
        FOREIGN KEY (vendor_address_id)
        REFERENCES ap.vendor_address(vendor_address_id)
        ON DELETE CASCADE;

ALTER TABLE ap.vendor_tax
    ADD CONSTRAINT vendor_tax_vendor_address_id_registration_type_key
        UNIQUE (vendor_address_id, registration_type);

CREATE INDEX IF NOT EXISTS idx_vendor_tax_address ON ap.vendor_tax(vendor_address_id);

COMMIT;
