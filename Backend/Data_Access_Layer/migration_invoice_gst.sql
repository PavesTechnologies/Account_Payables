-- GST input tax credit register (P2): one ap.invoice_gst row per purchase invoice - CGST / SGST / IGST
-- split, ITC eligibility, e-invoice IRN check, GSTR-3B claim period and the 180-day reversal rule.
--
-- Additive only - no existing table changes. Safe to re-run.
-- Rollback: migration_invoice_gst_rollback.sql.
-- Rows for existing invoices are filled by POST /apm/gst/itc/sync (or the next upload / review).
-- Note: create_all in main.py also creates this table on the first backend start with the new model.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.invoice_gst (
    invoice_id          INTEGER       NOT NULL,
    taxable_value       NUMERIC(18,2) NOT NULL DEFAULT 0,
    cgst                NUMERIC(18,2) NOT NULL DEFAULT 0,
    sgst                NUMERIC(18,2) NOT NULL DEFAULT 0,
    igst                NUMERIC(18,2) NOT NULL DEFAULT 0,
    cess                NUMERIC(18,2) NOT NULL DEFAULT 0,
    itc_eligibility     VARCHAR(20)   NOT NULL DEFAULT 'ELIGIBLE',
    itc_status          VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
    irn_status          VARCHAR(20)   NOT NULL DEFAULT 'UNKNOWN',
    reverse_charge      BOOLEAN       NOT NULL DEFAULT FALSE,
    eligibility_locked  BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    supplier_gstin      VARCHAR(15),
    supply_type         VARCHAR(10),
    place_of_supply     VARCHAR(2),
    eligibility_reason  TEXT,
    eligibility_set_by  VARCHAR(100),
    einvoice_applicable BOOLEAN,
    irn                 VARCHAR(64),
    ack_no              VARCHAR(30),
    claim_period        DATE,
    claimed_at          TIMESTAMPTZ,
    claimed_by          VARCHAR(100),
    reversal_due_date   DATE,
    reversal_period     DATE,
    reversed_at         TIMESTAMPTZ,
    reversed_by         VARCHAR(100),
    reclaim_period      DATE,
    reclaimed_at        TIMESTAMPTZ,
    CONSTRAINT invoice_gst_pkey PRIMARY KEY (invoice_id),
    CONSTRAINT invoice_gst_invoice_fk FOREIGN KEY (invoice_id) REFERENCES ap.invoice (invoice_id) ON DELETE CASCADE,
    CONSTRAINT invoice_gst_eligibility_chk CHECK (itc_eligibility IN ('ELIGIBLE','REVIEW','BLOCKED','NOT_CLAIMABLE')),
    CONSTRAINT invoice_gst_status_chk CHECK (itc_status IN ('PENDING','CLAIMED','REVERSED','NOT_CLAIMABLE')),
    CONSTRAINT invoice_gst_irn_chk CHECK (irn_status IN ('PRESENT','MISSING','NOT_REQUIRED','UNKNOWN'))
);
CREATE INDEX IF NOT EXISTS idx_invoice_gst_claim_period ON ap.invoice_gst (claim_period);
CREATE INDEX IF NOT EXISTS idx_invoice_gst_supplier ON ap.invoice_gst (supplier_gstin);

COMMIT;
