-- GSTR-2B reconciliation (P3): ap.gstr2b_import + ap.gstr2b_entry - each supplier's filed invoices /
-- notes for a return period, matched against the books (MATCHED / MISMATCH / NOT_IN_BOOKS). Once a
-- period's GSTR-2B is imported, only matched invoices are claimable in GSTR-3B. Additive only. Safe to re-run.
-- Rollback: migration_gstr2b_rollback.sql.
-- Note: create_all in main.py also creates these tables on the first backend start with the new models.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.gstr2b_import (
    import_id     SERIAL       NOT NULL,
    return_period DATE         NOT NULL,
    uploaded_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_current    BOOLEAN      NOT NULL DEFAULT TRUE,
    file_name     VARCHAR(255),
    file_path     VARCHAR(500),
    source_format VARCHAR(10),
    buyer_gstin   VARCHAR(15),
    generated_on  DATE,
    uploaded_by   VARCHAR(100),
    CONSTRAINT gstr2b_import_pkey PRIMARY KEY (import_id)
);
CREATE INDEX IF NOT EXISTS idx_gstr2b_import_period ON ap.gstr2b_import (return_period);

CREATE TABLE IF NOT EXISTS ap.gstr2b_entry (
    entry_id               SERIAL        NOT NULL,
    import_id              INTEGER       NOT NULL,
    supplier_gstin         VARCHAR(15)   NOT NULL,
    doc_type               VARCHAR(5)    NOT NULL,
    doc_number             VARCHAR(60)   NOT NULL,
    taxable_value          NUMERIC(18,2) NOT NULL DEFAULT 0,
    igst                   NUMERIC(18,2) NOT NULL DEFAULT 0,
    cgst                   NUMERIC(18,2) NOT NULL DEFAULT 0,
    sgst                   NUMERIC(18,2) NOT NULL DEFAULT 0,
    cess                   NUMERIC(18,2) NOT NULL DEFAULT 0,
    match_status           VARCHAR(20)   NOT NULL,
    supplier_name          VARCHAR(200),
    doc_date               DATE,
    itc_available          BOOLEAN,
    itc_unavailable_reason VARCHAR(200),
    supplier_filed_on      DATE,
    matched_invoice_id     INTEGER,
    tax_difference         NUMERIC(18,2),
    note                   VARCHAR(300),
    CONSTRAINT gstr2b_entry_pkey PRIMARY KEY (entry_id),
    CONSTRAINT gstr2b_entry_import_fk FOREIGN KEY (import_id) REFERENCES ap.gstr2b_import (import_id) ON DELETE CASCADE,
    CONSTRAINT gstr2b_entry_invoice_fk FOREIGN KEY (matched_invoice_id) REFERENCES ap.invoice (invoice_id),
    CONSTRAINT gstr2b_entry_status_chk CHECK (match_status IN ('MATCHED','MISMATCH','NOT_IN_BOOKS'))
);
CREATE INDEX IF NOT EXISTS idx_gstr2b_entry_import ON ap.gstr2b_entry (import_id);
CREATE INDEX IF NOT EXISTS idx_gstr2b_entry_invoice ON ap.gstr2b_entry (matched_invoice_id);

COMMIT;
