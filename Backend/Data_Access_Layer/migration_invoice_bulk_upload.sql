-- Bulk invoice upload tracking (APM_AUTOMATION_PLAN.md Phase 3):
--   * ap.invoice_upload_batch       one bulk upload (ZIP or several files) or one intake email
--   * ap.invoice_upload_batch_item  one file in a batch and its processing outcome
--
-- Orchestration only - invoices are still created by the single-upload operations, so no
-- existing table is altered. Same hand-applied convention as the other migration_*.sql files.
-- Additive only, safe to re-run. Rollback: migration_invoice_bulk_upload_rollback.sql.
--
-- Note: Base.metadata.create_all in main.py creates these two tables (empty, same definition)
-- the first time the backend starts with the new model. Running this file afterwards is still
-- safe - every statement is IF NOT EXISTS / guarded.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.invoice_upload_batch (
    batch_id          SERIAL       NOT NULL,
    source_type       VARCHAR(20)  NOT NULL DEFAULT 'MANUAL_UPLOAD',
    status            VARCHAR(20)  NOT NULL DEFAULT 'QUEUED',
    total_files       INTEGER      NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    source_name       VARCHAR(255),
    source_reference  VARCHAR(500),
    email_from        VARCHAR(320),
    email_subject     VARCHAR(500),
    email_received_at TIMESTAMPTZ,
    sender_known      BOOLEAN,
    uploaded_by       VARCHAR(100),
    uploaded_by_name  VARCHAR(200),
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    CONSTRAINT invoice_upload_batch_pkey PRIMARY KEY (batch_id),
    CONSTRAINT invoice_upload_batch_source_chk CHECK (source_type IN ('MANUAL_UPLOAD','EMAIL')),
    CONSTRAINT invoice_upload_batch_status_chk
        CHECK (status IN ('QUEUED','PROCESSING','COMPLETED','NEEDS_ATTENTION'))
);
CREATE INDEX IF NOT EXISTS idx_invoice_upload_batch_created ON ap.invoice_upload_batch (created_at);
CREATE INDEX IF NOT EXISTS idx_invoice_upload_batch_uploaded_by ON ap.invoice_upload_batch (uploaded_by);
-- Email intake (Phase 3b) columns - also added here in case create_all made the table first.
ALTER TABLE ap.invoice_upload_batch ADD COLUMN IF NOT EXISTS email_from VARCHAR(320);
ALTER TABLE ap.invoice_upload_batch ADD COLUMN IF NOT EXISTS email_subject VARCHAR(500);
ALTER TABLE ap.invoice_upload_batch ADD COLUMN IF NOT EXISTS email_received_at TIMESTAMPTZ;
ALTER TABLE ap.invoice_upload_batch ADD COLUMN IF NOT EXISTS sender_known BOOLEAN;
-- One batch per email message, even if two intake runners overlap.
CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_upload_batch_source_ref
    ON ap.invoice_upload_batch (source_type, source_reference) WHERE source_reference IS NOT NULL;

CREATE TABLE IF NOT EXISTS ap.invoice_upload_batch_item (
    item_id               SERIAL       NOT NULL,
    batch_id              INTEGER      NOT NULL,
    sequence_no           SMALLINT     NOT NULL,
    file_name             VARCHAR(255) NOT NULL,
    status                VARCHAR(20)  NOT NULL DEFAULT 'QUEUED',
    attempt_count         SMALLINT     NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    content_type          VARCHAR(100),
    file_size             BIGINT,
    file_sha256           VARCHAR(64),
    file_path             VARCHAR(500),
    error_code            VARCHAR(40),
    error_message         TEXT,
    extracted_data        JSONB,
    validation_result     JSONB,
    invoice_id            INTEGER,
    duplicate_of_item_id  INTEGER,
    started_at            TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ,
    CONSTRAINT invoice_upload_batch_item_pkey PRIMARY KEY (item_id),
    CONSTRAINT invoice_upload_batch_item_batch_fk
        FOREIGN KEY (batch_id) REFERENCES ap.invoice_upload_batch (batch_id),
    CONSTRAINT invoice_upload_batch_item_invoice_fk
        FOREIGN KEY (invoice_id) REFERENCES ap.invoice (invoice_id),
    CONSTRAINT invoice_upload_batch_item_duplicate_fk
        FOREIGN KEY (duplicate_of_item_id) REFERENCES ap.invoice_upload_batch_item (item_id),
    CONSTRAINT invoice_upload_batch_item_status_chk
        CHECK (status IN ('QUEUED','PROCESSING','CREATED','VENDOR_NOT_FOUND','DUPLICATE','FAILED','SKIPPED'))
);
CREATE INDEX IF NOT EXISTS idx_invoice_upload_batch_item_batch ON ap.invoice_upload_batch_item (batch_id);
CREATE INDEX IF NOT EXISTS idx_invoice_upload_batch_item_status ON ap.invoice_upload_batch_item (status);
CREATE INDEX IF NOT EXISTS idx_invoice_upload_batch_item_sha ON ap.invoice_upload_batch_item (file_sha256);
CREATE INDEX IF NOT EXISTS idx_invoice_upload_batch_item_path ON ap.invoice_upload_batch_item (file_path);

-- Email intake on/off switch (Phase 3b) - OFF until turned on from the Bulk Upload page.
INSERT INTO ap.system_configuration (config_key, config_value, data_type, description, updated_at)
VALUES ('EMAIL_INTAKE_ENABLED', 'false', 'BOOLEAN', 'Email invoice intake from the AP mailbox (on/off)', now())
ON CONFLICT (config_key) DO NOTHING;

COMMIT;
