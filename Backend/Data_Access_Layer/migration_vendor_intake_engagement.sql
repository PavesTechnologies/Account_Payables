-- Manual migration: Vendor Intake + Pre-Screen "vendor engagement" table.
--
-- This codebase has no migration tool (Base.metadata.create_all only creates
-- missing tables and never alters existing ones), so this is applied by hand,
-- the same way as every other schema change in this project. Because
-- ap.vendor_category_mapping ALREADY EXISTS in its old shape, create_all()
-- silently leaves it alone - which is exactly why the app fails at runtime
-- with:
--     psycopg2.errors.UndefinedColumn:
--     column vendor_category_mapping.department_id does not exist
-- Applying this file is what fixes that error.
--
-- WHY A RENAME INSTEAD OF ALTERs
-- ------------------------------
-- The old ap.vendor_category_mapping linked ap.vendor -> ap.vendor_category
-- (a separate, unused vendor-category master). The new VendorEngagement shape
-- links ap.vendor -> ap.department + ap.purchase_category. The live table holds
-- 2 legacy rows (vendor 15 -> vendor_category 8 'Cloud Services', vendor 16 ->
-- vendor_category 9 'Software & SaaS'). ap.vendor_category carries no
-- department link and has no ap.purchase_category equivalent, so those rows
-- cannot be backfilled into the new shape without inventing data.
--
-- They are therefore preserved by renaming the table to
-- ap.vendor_category_mapping_legacy, and the new engagement table is created
-- fresh under the original name - per this project's rule to never blindly
-- discard existing data, and following the precedent
-- migration_approval_workflow.sql set for the old ap.invoice_approval table.
-- Nothing is deleted; the 2 rows remain readable in the _legacy table.
--
-- Safe to run more than once: the rename is guarded on the old table's shape,
-- and the CREATE is IF NOT EXISTS.

DO $$
BEGIN
    -- Old shape is identified by the vendor_category_id column, which the new
    -- shape does not have.
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'ap'
          AND table_name = 'vendor_category_mapping'
          AND column_name = 'vendor_category_id'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'ap' AND table_name = 'vendor_category_mapping_legacy'
        ) THEN
            -- Half-applied state: fail loudly rather than silently leaving the
            -- old shape in place under the live table name.
            RAISE EXCEPTION
                'ap.vendor_category_mapping_legacy already exists while ap.vendor_category_mapping is still in its old shape - resolve manually before re-running';
        END IF;

        ALTER TABLE ap.vendor_category_mapping RENAME TO vendor_category_mapping_legacy;

        ALTER TABLE ap.vendor_category_mapping_legacy
            RENAME CONSTRAINT vendor_category_mapping_pkey TO vendor_category_mapping_legacy_pkey;
        ALTER TABLE ap.vendor_category_mapping_legacy
            RENAME CONSTRAINT vendor_category_mapping_vendor_fk TO vendor_category_mapping_legacy_vendor_fk;
        ALTER TABLE ap.vendor_category_mapping_legacy
            RENAME CONSTRAINT vendor_category_mapping_category_fk TO vendor_category_mapping_legacy_category_fk;
        ALTER TABLE ap.vendor_category_mapping_legacy
            RENAME CONSTRAINT vendor_category_mapping_unique TO vendor_category_mapping_legacy_unique;

        -- ALTER TABLE ... RENAME TO renames neither the table's indexes nor its
        -- owned sequence, and both names are unique per-schema - without these
        -- the new table's SERIAL sequence and index names collide.
        ALTER SEQUENCE ap.vendor_category_mapping_vendor_category_mapping_id_seq
            RENAME TO vendor_category_mapping_legacy_id_seq;
    END IF;
END $$;

-- New engagement shape. Mirrors VendorEngagement in
-- Backend/Data_Access_Layer/models/vendor.py exactly - Backend/tests/
-- test_vendor_intake.py asserts every model column appears here, so the
-- runtime UndefinedColumn failure mode cannot silently come back.
CREATE TABLE IF NOT EXISTS ap.vendor_category_mapping (
    vendor_category_mapping_id  SERIAL        NOT NULL,
    vendor_id                   INTEGER       NOT NULL,
    department_id               BIGINT        NOT NULL,
    purchase_category_id        BIGINT        NOT NULL,
    is_primary                  BOOLEAN       NOT NULL DEFAULT false,
    pre_screen_status           VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
    created_at                  TIMESTAMP     NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMP     NOT NULL DEFAULT now(),
    business_requirement        TEXT,
    purpose_of_onboarding       TEXT,
    pre_screen_result_reason    TEXT,
    pre_screen_checked_at       TIMESTAMP,
    nda_recommended             BOOLEAN,
    nda_override                BOOLEAN,
    nda_override_reason         TEXT,
    nda_final_required          BOOLEAN,
    nda_decided_by              VARCHAR(100),
    nda_decided_at              TIMESTAMP,
    created_by                  VARCHAR(100),
    updated_by                  VARCHAR(100),

    CONSTRAINT vendor_category_mapping_pkey
        PRIMARY KEY (vendor_category_mapping_id),
    CONSTRAINT vendor_category_mapping_vendor_fk
        FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id),
    CONSTRAINT vendor_engagement_department_fk
        FOREIGN KEY (department_id) REFERENCES ap.department(id),
    CONSTRAINT vendor_engagement_purchase_category_fk
        FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id),
    -- Final protection against concurrent duplicate engagements; the service
    -- layer's pre-insert check is the friendly error, this is the guarantee.
    CONSTRAINT vendor_engagement_unique
        UNIQUE (vendor_id, department_id, purchase_category_id),
    CONSTRAINT chk_vendor_engagement_pre_screen_status
        CHECK (pre_screen_status IN ('PENDING', 'PASS', 'NEED_INFORMATION', 'FAIL'))
);

CREATE INDEX IF NOT EXISTS idx_vendor_engagement_department
    ON ap.vendor_category_mapping (department_id);
CREATE INDEX IF NOT EXISTS idx_vendor_engagement_category
    ON ap.vendor_category_mapping (purchase_category_id);

-- Verification (expect 20 columns, incl. department_id / purchase_category_id /
-- business_requirement and every pre_screen_*/nda_* column):
--   SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_schema = 'ap' AND table_name = 'vendor_category_mapping'
--   ORDER BY ordinal_position;
