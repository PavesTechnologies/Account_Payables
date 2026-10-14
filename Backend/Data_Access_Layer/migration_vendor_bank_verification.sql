-- Vendor bank verification and change control (P3): ap.vendor_bank_verification - penny-drop or document
-- verification of each vendor bank account, and approval by a second person. Only APPROVED accounts are
-- used by payment runs. Additive only - ap.vendor_bank is unchanged. Safe to re-run.
-- Rollback: migration_vendor_bank_verification_rollback.sql.
-- Note: create_all in main.py also creates this table on the first backend start with the new model.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.vendor_bank_verification (
    vendor_bank_id   INTEGER      NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'UNVERIFIED',
    approval_status  VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    changed_by       VARCHAR(100),
    method           VARCHAR(20),
    name_at_bank     VARCHAR(200),
    name_match_score NUMERIC(5,2),
    reference        VARCHAR(100),
    message          TEXT,
    verified_by      VARCHAR(100),
    verified_at      TIMESTAMPTZ,
    approved_by      VARCHAR(100),
    approved_at      TIMESTAMPTZ,
    approval_remarks VARCHAR(500),
    file_name        VARCHAR(255),
    file_path        VARCHAR(500),
    content_type     VARCHAR(100),
    CONSTRAINT vendor_bank_verification_pkey PRIMARY KEY (vendor_bank_id),
    CONSTRAINT vendor_bank_verification_bank_fk FOREIGN KEY (vendor_bank_id)
        REFERENCES ap.vendor_bank (vendor_bank_id) ON DELETE CASCADE,
    CONSTRAINT vendor_bank_verification_status_chk CHECK (status IN ('UNVERIFIED','VERIFIED','NAME_MISMATCH','FAILED')),
    CONSTRAINT vendor_bank_verification_approval_chk CHECK (approval_status IN ('PENDING','APPROVED','REJECTED'))
);

COMMIT;
