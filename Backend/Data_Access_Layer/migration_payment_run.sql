-- Payment runs (P3): ap.payment_run + ap.payment_run_item - pay many invoices in one approved batch
-- (maker-checker), export a bank bulk-payment file, confirm UTRs. Money still moves only through the
-- existing ap.payment SCHEDULED -> SENT -> CLEARED flow. Additive only. Safe to re-run.
-- Rollback: migration_payment_run_rollback.sql.
-- Note: create_all in main.py also creates these tables on the first backend start with the new models.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.payment_run (
    run_id            SERIAL       NOT NULL,
    name              VARCHAR(150) NOT NULL,
    value_date        DATE         NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'DRAFT',
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    created_by        VARCHAR(100),
    submitted_by      VARCHAR(100),
    submitted_at      TIMESTAMPTZ,
    approved_by       VARCHAR(100),
    approved_at       TIMESTAMPTZ,
    decision_remarks  VARCHAR(500),
    file_format       VARCHAR(30),
    file_generated_at TIMESTAMPTZ,
    file_generated_by VARCHAR(100),
    sent_at           TIMESTAMPTZ,
    sent_by           VARCHAR(100),
    completed_at      TIMESTAMPTZ,
    notes             TEXT,
    CONSTRAINT payment_run_pkey PRIMARY KEY (run_id),
    CONSTRAINT payment_run_status_chk CHECK (status IN ('DRAFT','SUBMITTED','APPROVED','SENT','COMPLETED','REJECTED','CANCELLED'))
);
CREATE INDEX IF NOT EXISTS idx_payment_run_status ON ap.payment_run (status);

CREATE TABLE IF NOT EXISTS ap.payment_run_item (
    item_id        SERIAL        NOT NULL,
    run_id         INTEGER       NOT NULL,
    invoice_id     INTEGER       NOT NULL,
    vendor_id      INTEGER       NOT NULL,
    amount         NUMERIC(18,2) NOT NULL,
    status         VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
    vendor_bank_id INTEGER,
    payment_id     INTEGER,
    utr            VARCHAR(50),
    failure_reason VARCHAR(300),
    CONSTRAINT payment_run_item_pkey PRIMARY KEY (item_id),
    CONSTRAINT payment_run_item_run_fk FOREIGN KEY (run_id) REFERENCES ap.payment_run (run_id) ON DELETE CASCADE,
    CONSTRAINT payment_run_item_invoice_fk FOREIGN KEY (invoice_id) REFERENCES ap.invoice (invoice_id),
    CONSTRAINT payment_run_item_vendor_fk FOREIGN KEY (vendor_id) REFERENCES ap.vendor (vendor_id),
    CONSTRAINT payment_run_item_bank_fk FOREIGN KEY (vendor_bank_id) REFERENCES ap.vendor_bank (vendor_bank_id),
    CONSTRAINT payment_run_item_payment_fk FOREIGN KEY (payment_id) REFERENCES ap.payment (payment_id),
    CONSTRAINT payment_run_item_status_chk CHECK (status IN ('PENDING','PAID','FAILED')),
    CONSTRAINT payment_run_item_amount_chk CHECK (amount > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_run_item_invoice ON ap.payment_run_item (run_id, invoice_id);
CREATE INDEX IF NOT EXISTS idx_payment_run_item_invoice ON ap.payment_run_item (invoice_id);

COMMIT;
