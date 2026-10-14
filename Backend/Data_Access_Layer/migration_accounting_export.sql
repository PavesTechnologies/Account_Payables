-- Accounting export (P3): ap.accounting_export + ap.accounting_export_item - the AP vouchers (invoice
-- bookings, payments, credit / debit notes, TDS challans) Finance exported to Tally / Zoho Books / CSV,
-- so the next export defaults to "not yet exported". Ledger names live in ap.system_configuration
-- (ACCT_LEDGER_* keys, written from the export page). Additive only. Safe to re-run.
-- Rollback: migration_accounting_export_rollback.sql.
-- Note: create_all in main.py also creates these tables on the first backend start with the new models.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.accounting_export (
    export_id     SERIAL        NOT NULL,
    export_format VARCHAR(20)   NOT NULL,
    date_from     DATE          NOT NULL,
    date_to       DATE          NOT NULL,
    voucher_count INTEGER       NOT NULL DEFAULT 0,
    total_debit   NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    created_by    VARCHAR(100),
    file_name     VARCHAR(255),
    file_path     VARCHAR(500),
    CONSTRAINT accounting_export_pkey PRIMARY KEY (export_id)
);

CREATE TABLE IF NOT EXISTS ap.accounting_export_item (
    item_id        SERIAL        NOT NULL,
    export_id      INTEGER       NOT NULL,
    source_type    VARCHAR(10)   NOT NULL,
    source_id      INTEGER       NOT NULL,
    voucher_number VARCHAR(40)   NOT NULL,
    voucher_date   DATE          NOT NULL,
    amount         NUMERIC(18,2) NOT NULL,
    CONSTRAINT accounting_export_item_pkey PRIMARY KEY (item_id),
    CONSTRAINT accounting_export_item_export_fk FOREIGN KEY (export_id) REFERENCES ap.accounting_export (export_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_accounting_export_item_export ON ap.accounting_export_item (export_id);
CREATE INDEX IF NOT EXISTS idx_accounting_export_item_source ON ap.accounting_export_item (source_type, source_id);

COMMIT;
