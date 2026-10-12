-- Bulk import of payments / TDS challans / TDS filings from Excel (APM_AUTOMATION_PLAN.md 6.7):
--   * ap.bulk_import_job   one uploaded (or SharePoint) workbook
--   * ap.bulk_import_row   one sheet row, its checks against the attached document, and the outcome
-- Tracking only - payments / challans / filings are recorded by the existing services. Additive,
-- safe to re-run. Rollback: migration_bulk_import_rollback.sql. create_all creates the tables on the
-- next backend start too; running this file afterwards is still safe.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.bulk_import_job (
    job_id            SERIAL        NOT NULL,
    kind              VARCHAR(20)   NOT NULL,
    source            VARCHAR(20)   NOT NULL DEFAULT 'MANUAL_UPLOAD',
    status            VARCHAR(20)   NOT NULL DEFAULT 'VALIDATING',
    file_name         VARCHAR(255)  NOT NULL,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    auto_record       BOOLEAN       NOT NULL DEFAULT FALSE,
    source_reference  VARCHAR(500),
    file_path         VARCHAR(500),
    error_message     TEXT,
    created_by        VARCHAR(100),
    created_by_name   VARCHAR(200),
    completed_at      TIMESTAMPTZ,
    CONSTRAINT bulk_import_job_pkey PRIMARY KEY (job_id),
    CONSTRAINT bulk_import_job_kind_chk CHECK (kind IN ('PAYMENTS','TDS_CHALLANS','TDS_FILINGS')),
    CONSTRAINT bulk_import_job_source_chk CHECK (source IN ('MANUAL_UPLOAD','SHAREPOINT')),
    CONSTRAINT bulk_import_job_status_chk
        CHECK (status IN ('VALIDATING','VALIDATED','RECORDING','COMPLETED','NEEDS_REVIEW','FAILED'))
);
CREATE INDEX IF NOT EXISTS idx_bulk_import_job_created ON ap.bulk_import_job (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bulk_import_job_source_ref
    ON ap.bulk_import_job (source, source_reference) WHERE source_reference IS NOT NULL;

CREATE TABLE IF NOT EXISTS ap.bulk_import_row (
    row_id            SERIAL        NOT NULL,
    job_id            INTEGER       NOT NULL,
    row_number        INTEGER       NOT NULL,
    status            VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
    data              JSONB         NOT NULL,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    group_key         VARCHAR(200),
    invoice_id        INTEGER,
    document_name     VARCHAR(255),
    document_path     VARCHAR(500),
    extracted         JSONB,
    messages          JSONB,
    result_reference  VARCHAR(100),
    recorded_by       VARCHAR(100),
    recorded_at       TIMESTAMPTZ,
    CONSTRAINT bulk_import_row_pkey PRIMARY KEY (row_id),
    CONSTRAINT bulk_import_row_job_fk FOREIGN KEY (job_id) REFERENCES ap.bulk_import_job (job_id),
    CONSTRAINT bulk_import_row_status_chk CHECK (status IN ('PENDING','READY','NEEDS_REVIEW','ERROR','RECORDED','SKIPPED'))
);
CREATE INDEX IF NOT EXISTS idx_bulk_import_row_job ON ap.bulk_import_row (job_id);

-- Daily SharePoint pickup switch - OFF until the Finance Manager turns it on (AP Automation page).
INSERT INTO ap.system_configuration (config_key, config_value, data_type, description, updated_at)
VALUES ('BULK_IMPORT_SHAREPOINT_ENABLED', 'false', 'BOOLEAN', 'Daily pickup of payment / TDS sheets from SharePoint (on/off)', now())
ON CONFLICT (config_key) DO NOTHING;

COMMIT;
