-- Recurring invoice schedules (P2): rent, SaaS subscriptions, cloud bills.
--   * ap.recurring_schedule    vendor bills every period, around day N, for about Rs X
--   * ap.recurring_occurrence  one row per schedule and billing period: EXPECTED -> RECEIVED / SKIPPED
--
-- Additive only - no existing table changes. Safe to re-run.
-- Rollback: migration_recurring_schedule_rollback.sql.
-- Note: create_all in main.py also creates these tables on the first backend start with the
-- new models; running this file afterwards is still safe.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.recurring_schedule (
    schedule_id          SERIAL        NOT NULL,
    vendor_id            INTEGER       NOT NULL,
    name                 VARCHAR(200)  NOT NULL,
    frequency            VARCHAR(20)   NOT NULL DEFAULT 'MONTHLY',
    expected_day         SMALLINT      NOT NULL DEFAULT 1,
    expected_amount      NUMERIC(18,2) NOT NULL,
    tolerance_pct        NUMERIC(5,2)  NOT NULL DEFAULT 5,
    grace_days           SMALLINT      NOT NULL DEFAULT 5,
    start_date           DATE          NOT NULL,
    is_active            BOOLEAN       NOT NULL DEFAULT TRUE,
    fast_track           BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    end_date             DATE,
    agreement_id         INTEGER,
    department_id        INTEGER,
    purchase_category_id INTEGER,
    payment_nature_code  VARCHAR(50),
    match_keyword        VARCHAR(100),
    notes                TEXT,
    created_by           VARCHAR(100),
    updated_by           VARCHAR(100),
    CONSTRAINT recurring_schedule_pkey PRIMARY KEY (schedule_id),
    CONSTRAINT recurring_schedule_vendor_fk FOREIGN KEY (vendor_id) REFERENCES ap.vendor (vendor_id),
    CONSTRAINT recurring_schedule_agreement_fk FOREIGN KEY (agreement_id) REFERENCES ap.vendor_agreement (agreement_id),
    CONSTRAINT recurring_schedule_department_fk FOREIGN KEY (department_id) REFERENCES ap.department (id),
    CONSTRAINT recurring_schedule_category_fk FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category (id),
    CONSTRAINT recurring_schedule_frequency_chk CHECK (frequency IN ('MONTHLY','QUARTERLY','HALF_YEARLY','YEARLY')),
    CONSTRAINT recurring_schedule_day_chk CHECK (expected_day BETWEEN 1 AND 28),
    CONSTRAINT recurring_schedule_tolerance_chk CHECK (tolerance_pct >= 0 AND tolerance_pct <= 100)
);
CREATE INDEX IF NOT EXISTS idx_recurring_schedule_vendor ON ap.recurring_schedule (vendor_id);

CREATE TABLE IF NOT EXISTS ap.recurring_occurrence (
    occurrence_id    SERIAL        NOT NULL,
    schedule_id      INTEGER       NOT NULL,
    period_start     DATE          NOT NULL,
    expected_date    DATE          NOT NULL,
    expected_amount  NUMERIC(18,2) NOT NULL,
    status           VARCHAR(20)   NOT NULL DEFAULT 'EXPECTED',
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    invoice_id       INTEGER,
    received_amount  NUMERIC(18,2),
    variance_pct     NUMERIC(7,2),
    variance_status  VARCHAR(10),
    matched_by       VARCHAR(100),
    matched_at       TIMESTAMPTZ,
    skip_reason      VARCHAR(500),
    skipped_by       VARCHAR(100),
    CONSTRAINT recurring_occurrence_pkey PRIMARY KEY (occurrence_id),
    CONSTRAINT recurring_occurrence_schedule_fk FOREIGN KEY (schedule_id) REFERENCES ap.recurring_schedule (schedule_id),
    CONSTRAINT recurring_occurrence_invoice_fk FOREIGN KEY (invoice_id) REFERENCES ap.invoice (invoice_id),
    CONSTRAINT recurring_occurrence_status_chk CHECK (status IN ('EXPECTED','RECEIVED','SKIPPED'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_recurring_occurrence_period ON ap.recurring_occurrence (schedule_id, period_start);
CREATE UNIQUE INDEX IF NOT EXISTS uq_recurring_occurrence_invoice ON ap.recurring_occurrence (invoice_id) WHERE invoice_id IS NOT NULL;

COMMIT;
