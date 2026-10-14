-- Work assignment (P3): which AP Executive works which invoice.
--   * ap.work_assignment_rule  vendor / department -> AP Executive (new invoices land in their queue)
--   * ap.invoice_assignment    current owner of an invoice (RULE / CLAIM / REASSIGN)
-- Additive only - no existing table changes. Safe to re-run.
-- Rollback: migration_work_assignment_rollback.sql.
-- Note: create_all in main.py also creates these tables on the first backend start with the new models.

BEGIN;

CREATE TABLE IF NOT EXISTS ap.work_assignment_rule (
    rule_id          SERIAL       NOT NULL,
    scope            VARCHAR(20)  NOT NULL,
    assignee_user_id VARCHAR(100) NOT NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    vendor_id        INTEGER,
    department_id    INTEGER,
    created_by       VARCHAR(100),
    updated_by       VARCHAR(100),
    CONSTRAINT work_assignment_rule_pkey PRIMARY KEY (rule_id),
    CONSTRAINT work_assignment_rule_vendor_fk FOREIGN KEY (vendor_id) REFERENCES ap.vendor (vendor_id),
    CONSTRAINT work_assignment_rule_department_fk FOREIGN KEY (department_id) REFERENCES ap.department (id),
    CONSTRAINT work_assignment_rule_scope_chk CHECK (scope IN ('VENDOR','DEPARTMENT')),
    CONSTRAINT work_assignment_rule_target_chk CHECK ((scope = 'VENDOR' AND vendor_id IS NOT NULL)
                                                   OR (scope = 'DEPARTMENT' AND department_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_work_assignment_rule_vendor ON ap.work_assignment_rule (vendor_id)
    WHERE is_active AND scope = 'VENDOR';
CREATE UNIQUE INDEX IF NOT EXISTS uq_work_assignment_rule_department ON ap.work_assignment_rule (department_id)
    WHERE is_active AND scope = 'DEPARTMENT';

CREATE TABLE IF NOT EXISTS ap.invoice_assignment (
    invoice_id       INTEGER      NOT NULL,
    assignee_user_id VARCHAR(100) NOT NULL,
    source           VARCHAR(20)  NOT NULL,
    assigned_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    assigned_by      VARCHAR(100),
    rule_id          INTEGER,
    note             VARCHAR(300),
    CONSTRAINT invoice_assignment_pkey PRIMARY KEY (invoice_id),
    CONSTRAINT invoice_assignment_invoice_fk FOREIGN KEY (invoice_id) REFERENCES ap.invoice (invoice_id) ON DELETE CASCADE,
    CONSTRAINT invoice_assignment_rule_fk FOREIGN KEY (rule_id) REFERENCES ap.work_assignment_rule (rule_id),
    CONSTRAINT invoice_assignment_source_chk CHECK (source IN ('RULE','CLAIM','REASSIGN'))
);
CREATE INDEX IF NOT EXISTS idx_invoice_assignment_assignee ON ap.invoice_assignment (assignee_user_id);

COMMIT;
