-- Shared TDS challan and quarterly return filing (APM_AUTOMATION_PLAN.md 3.4 / D4, Phase 5):
--   * ap.tds_challan                 one challan (ITNS 281) - usually many invoices' TDS
--   * ap.tds_challan_allocation      which invoices a challan pays, and how much of each
--   * ap.tds_return_filing           one quarterly statement (26Q / 27Q / 24Q / 27EQ) acknowledgement
--   * ap.tds_return_filing_invoice   which invoices that statement covers
--
-- Additive only - per-invoice status stays in ap.invoice_tds_tracking, which is updated through the
-- existing deposit / filing service when a challan or filing is confirmed. Safe to re-run.
-- Rollback: migration_tds_challan_rollback.sql.
-- Note: create_all in main.py creates these tables (empty, same definition) on the first backend
-- start with the new models; running this file afterwards is still safe.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.tds_challan (
    challan_id         SERIAL        NOT NULL,
    challan_serial_no  VARCHAR(5)    NOT NULL,
    bsr_code           VARCHAR(7)    NOT NULL,
    deposit_date       DATE          NOT NULL,
    cin                VARCHAR(25)   NOT NULL,
    tax_amount         NUMERIC(18,2) NOT NULL,
    total_amount       NUMERIC(18,2) NOT NULL,
    status             VARCHAR(20)   NOT NULL DEFAULT 'CONFIRMED',
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    surcharge          NUMERIC(18,2) NOT NULL DEFAULT 0,
    cess               NUMERIC(18,2) NOT NULL DEFAULT 0,
    interest           NUMERIC(18,2) NOT NULL DEFAULT 0,
    fee                NUMERIC(18,2) NOT NULL DEFAULT 0,
    tan                VARCHAR(10),
    assessment_year    VARCHAR(9),
    minor_head         VARCHAR(3),
    section_code       VARCHAR(20),
    tax_period         DATE,
    file_name          VARCHAR(255),
    file_path          VARCHAR(500),
    content_type       VARCHAR(100),
    remarks            TEXT,
    source             VARCHAR(20),
    created_by         VARCHAR(100),
    CONSTRAINT tds_challan_pkey PRIMARY KEY (challan_id),
    CONSTRAINT tds_challan_status_chk CHECK (status IN ('CONFIRMED')),
    CONSTRAINT tds_challan_bsr_chk CHECK (bsr_code ~ '^[0-9]{7}$'),
    CONSTRAINT tds_challan_serial_chk CHECK (challan_serial_no ~ '^[0-9]{1,5}$'),
    CONSTRAINT tds_challan_amounts_chk CHECK (tax_amount >= 0 AND total_amount >= 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tds_challan_identity ON ap.tds_challan (bsr_code, deposit_date, challan_serial_no);
CREATE INDEX IF NOT EXISTS idx_tds_challan_deposit_date ON ap.tds_challan (deposit_date);

CREATE TABLE IF NOT EXISTS ap.tds_challan_allocation (
    allocation_id         SERIAL        NOT NULL,
    challan_id            INTEGER       NOT NULL,
    invoice_id            INTEGER       NOT NULL,
    allocated_tds_amount  NUMERIC(18,2) NOT NULL,
    is_active             BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT tds_challan_allocation_pkey PRIMARY KEY (allocation_id),
    CONSTRAINT tds_challan_allocation_challan_fk FOREIGN KEY (challan_id) REFERENCES ap.tds_challan (challan_id),
    CONSTRAINT tds_challan_allocation_invoice_fk FOREIGN KEY (invoice_id) REFERENCES ap.invoice (invoice_id),
    CONSTRAINT tds_challan_allocation_amount_chk CHECK (allocated_tds_amount > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tds_challan_allocation_invoice ON ap.tds_challan_allocation (invoice_id) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_tds_challan_allocation_challan ON ap.tds_challan_allocation (challan_id);

CREATE TABLE IF NOT EXISTS ap.tds_return_filing (
    filing_id           SERIAL       NOT NULL,
    form_type           VARCHAR(5)   NOT NULL,
    financial_year      VARCHAR(7)   NOT NULL,
    quarter             SMALLINT     NOT NULL,
    acknowledgement_no  VARCHAR(30)  NOT NULL,
    filing_date         DATE         NOT NULL,
    status              VARCHAR(20)  NOT NULL DEFAULT 'CONFIRMED',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    tan                 VARCHAR(10),
    is_revision         BOOLEAN      NOT NULL DEFAULT FALSE,
    file_name           VARCHAR(255),
    file_path           VARCHAR(500),
    content_type        VARCHAR(100),
    remarks             TEXT,
    source              VARCHAR(20),
    created_by          VARCHAR(100),
    CONSTRAINT tds_return_filing_pkey PRIMARY KEY (filing_id),
    CONSTRAINT tds_return_filing_form_chk CHECK (form_type IN ('26Q','27Q','24Q','27EQ')),
    CONSTRAINT tds_return_filing_quarter_chk CHECK (quarter BETWEEN 1 AND 4),
    CONSTRAINT tds_return_filing_status_chk CHECK (status IN ('CONFIRMED'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tds_return_filing_ack ON ap.tds_return_filing (acknowledgement_no);
CREATE INDEX IF NOT EXISTS idx_tds_return_filing_period ON ap.tds_return_filing (financial_year, quarter);

CREATE TABLE IF NOT EXISTS ap.tds_return_filing_invoice (
    id          SERIAL   NOT NULL,
    filing_id   INTEGER  NOT NULL,
    invoice_id  INTEGER  NOT NULL,
    CONSTRAINT tds_return_filing_invoice_pkey PRIMARY KEY (id),
    CONSTRAINT tds_return_filing_invoice_filing_fk FOREIGN KEY (filing_id) REFERENCES ap.tds_return_filing (filing_id),
    CONSTRAINT tds_return_filing_invoice_invoice_fk FOREIGN KEY (invoice_id) REFERENCES ap.invoice (invoice_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tds_return_filing_invoice ON ap.tds_return_filing_invoice (filing_id, invoice_id);
CREATE INDEX IF NOT EXISTS idx_tds_return_filing_invoice_invoice ON ap.tds_return_filing_invoice (invoice_id);

-- Allowed difference between a challan's tax amount and the TDS of the invoices it covers (rupees).
INSERT INTO ap.system_configuration (config_key, config_value, data_type, description, updated_at)
VALUES ('TDS_CHALLAN_TOLERANCE', '1', 'NUMBER', 'Allowed difference between challan tax amount and allocated invoice TDS (INR)', now())
ON CONFLICT (config_key) DO NOTHING;

COMMIT;
