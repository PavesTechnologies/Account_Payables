-- Credit and debit notes (P2): ap.vendor_note - a vendor's GST credit note, or our debit note on a
-- vendor, applied to one of that vendor's unpaid invoices (lowers its payable and, before TDS is
-- deducted, its TDS base). Additive only - no existing table changes. Safe to re-run.
-- Rollback: migration_vendor_note_rollback.sql.
-- Note: create_all in main.py also creates this table on the first backend start with the new model.
-- Until the table exists, payables are computed exactly as before (no notes).

BEGIN;

CREATE TABLE IF NOT EXISTS ap.vendor_note (
    note_id              SERIAL        NOT NULL,
    note_type            VARCHAR(20)   NOT NULL,
    vendor_id            INTEGER       NOT NULL,
    note_number          VARCHAR(60)   NOT NULL,
    note_date            DATE          NOT NULL,
    reason               TEXT          NOT NULL,
    taxable_value        NUMERIC(18,2) NOT NULL,
    cgst                 NUMERIC(18,2) NOT NULL DEFAULT 0,
    sgst                 NUMERIC(18,2) NOT NULL DEFAULT 0,
    igst                 NUMERIC(18,2) NOT NULL DEFAULT 0,
    total_amount         NUMERIC(18,2) NOT NULL,
    status               VARCHAR(20)   NOT NULL DEFAULT 'OPEN',
    tds_adjusted         NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    reference_invoice_id INTEGER,
    applied_invoice_id   INTEGER,
    tds_note             VARCHAR(300),
    itc_period           DATE,
    file_name            VARCHAR(255),
    file_path            VARCHAR(500),
    content_type         VARCHAR(100),
    created_by           VARCHAR(100),
    applied_by           VARCHAR(100),
    applied_at           TIMESTAMPTZ,
    cancelled_by         VARCHAR(100),
    cancel_reason        VARCHAR(500),
    CONSTRAINT vendor_note_pkey PRIMARY KEY (note_id),
    CONSTRAINT vendor_note_vendor_fk FOREIGN KEY (vendor_id) REFERENCES ap.vendor (vendor_id),
    CONSTRAINT vendor_note_reference_fk FOREIGN KEY (reference_invoice_id) REFERENCES ap.invoice (invoice_id),
    CONSTRAINT vendor_note_applied_fk FOREIGN KEY (applied_invoice_id) REFERENCES ap.invoice (invoice_id),
    CONSTRAINT vendor_note_type_chk CHECK (note_type IN ('CREDIT_NOTE','DEBIT_NOTE')),
    CONSTRAINT vendor_note_status_chk CHECK (status IN ('OPEN','APPLIED','CANCELLED')),
    CONSTRAINT vendor_note_amount_chk CHECK (total_amount > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_note_number ON ap.vendor_note (vendor_id, note_type, note_number);
CREATE INDEX IF NOT EXISTS idx_vendor_note_applied ON ap.vendor_note (applied_invoice_id);

COMMIT;
