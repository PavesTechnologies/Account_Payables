-- ============================================================================
-- ACCOUNTS PAYABLE (AP) — PHASE 1 SCHEMA
-- PostgreSQL 16+
-- Version: Final — email-intake invoice automation for a  Accounts Payable Module
-- ============================================================================
-- This is an Invoice Automation System, not an ERP. Scope is intentionally
-- limited to: Vendor -> Invoice arrives -> OCR/Extraction -> Validation ->
-- Exception Handling -> Approval (if needed) -> Payment Scheduling -> Paid.
--
-- Out of scope by design (add only if the business genuinely needs it):
--   Purchase requisitions, contracts, budget control, cost centers,
--   GL posting, asset accounting, inventory, accounting journals,
--   workflow/rules engines, payment batches/bank files.
--
-- Three-tier data ownership model used throughout:
--   SYSTEM REFERENCE   - developer-seeded, not user-editable (country,
--                         currency, status_master)
--   BUSINESS CONFIG     - seeded as suggestions, AP Executive maintains
--                         (tax_type, vendor_category, payment_term,
--                         system_configuration)
--   TRANSACTIONAL       - created by the automation pipeline (vendor,
--                         invoice, payment, approval, issue, etc.)
--
-- Changes in this version (per architecture review):
--   1. payment / payment_invoice split — one payment can now settle
--      multiple invoices, and partial payments are representable.
--   2. system_configuration table added — business rules (auto-approval
--      limit, OCR confidence threshold, PO/GRN mandatory flags, reminder
--      days) live in data, not code.
--   3. invoice_issue.severity added — INFO/WARNING/ERROR to prioritize
--      exceptions instead of treating all issues as equally urgent.
--   4. vendor_bank versioned with effective_from/effective_to — bank
--      account changes are never destructive updates, always a new row.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS ap;
SET search_path TO ap;

-- ============================================================================
-- MODULE 1: FOUNDATION MASTERS
-- ============================================================================

-- SYSTEM REFERENCE — seeded once, not exposed for editing.
CREATE TABLE country (
    country_id      SERIAL PRIMARY KEY,
    country_name    VARCHAR(100) NOT NULL,
    country_code    CHAR(2) NOT NULL UNIQUE,       -- ISO 3166-1 alpha-2
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- SYSTEM REFERENCE — seeded once, not exposed for editing.
CREATE TABLE currency (
    currency_id     SERIAL PRIMARY KEY,
    currency_name   VARCHAR(50) NOT NULL,
    currency_code   CHAR(3) NOT NULL UNIQUE,       -- ISO 4217
    symbol          VARCHAR(10) NOT NULL,
    decimal_places  SMALLINT NOT NULL DEFAULT 2,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- BUSINESS CONFIG — AP Executive maintains; rates change yearly.
CREATE TABLE tax_type (
    tax_type_id       SERIAL PRIMARY KEY,
    country_id        INT NOT NULL REFERENCES country(country_id),
    tax_name          VARCHAR(100) NOT NULL,        -- 'GST 18%', 'TDS Section 194C'
    tax_code          VARCHAR(30) NOT NULL,
    calculation_type  VARCHAR(20) NOT NULL DEFAULT 'PERCENTAGE', -- 'PERCENTAGE' or 'FIXED'
    rate_percent      NUMERIC(6,3),                  -- used when calculation_type = PERCENTAGE
    fixed_amount      NUMERIC(18,2),                 -- used when calculation_type = FIXED
    is_withholding    BOOLEAN NOT NULL DEFAULT FALSE, -- TRUE = deducted from vendor (TDS-style)
                                                        -- FALSE = added to invoice (GST/VAT-style)
    effective_from    DATE NOT NULL,
    effective_to      DATE,
    is_system_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_by        VARCHAR(100),
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by        VARCHAR(100),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (country_id, tax_code, effective_from),
    CHECK (
        (calculation_type = 'PERCENTAGE' AND rate_percent IS NOT NULL) OR
        (calculation_type = 'FIXED' AND fixed_amount IS NOT NULL)
    )
);

-- -- BUSINESS CONFIG — reporting/UX convenience only. Never drives validation
-- -- or payment calculation logic. Optional on vendor.
-- CREATE TABLE vendor_category (
--     vendor_category_id SERIAL PRIMARY KEY,
--     category_name      VARCHAR(100) NOT NULL UNIQUE,
--     description         VARCHAR(255),
--     is_system_default    BOOLEAN NOT NULL DEFAULT FALSE,
--     is_active             BOOLEAN NOT NULL DEFAULT TRUE,
--     created_by             VARCHAR(100),
--     created_at               TIMESTAMP NOT NULL DEFAULT NOW(),
--     updated_by                 VARCHAR(100),
--     updated_at                   TIMESTAMP NOT NULL DEFAULT NOW()
-- );

-- BUSINESS CONFIG — AP Executive maintains (business policy, not a constant).
CREATE TABLE payment_term (
    payment_term_id   SERIAL PRIMARY KEY,
    term_name          VARCHAR(50) NOT NULL UNIQUE,  -- 'Net 30', 'Immediate'
    due_days            SMALLINT NOT NULL DEFAULT 0,
    discount_percent      NUMERIC(5,2) NOT NULL DEFAULT 0,
    discount_days           SMALLINT NOT NULL DEFAULT 0,
    is_system_default         BOOLEAN NOT NULL DEFAULT FALSE,
    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
    created_by                    VARCHAR(100),
    created_at                       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by                         VARCHAR(100),
    updated_at                           TIMESTAMP NOT NULL DEFAULT NOW()
);

-- SYSTEM REFERENCE — codes are wired into application logic. Label text may
-- be editable via admin UI; status_code/module_name/row lifecycle stay
-- dev-controlled.
CREATE TABLE status_master (
    status_id       SERIAL PRIMARY KEY,
    module_name     VARCHAR(50) NOT NULL,           -- 'VENDOR','INVOICE','APPROVAL','PAYMENT','PO'
    status_code     VARCHAR(30) NOT NULL,
    status_name     VARCHAR(100) NOT NULL,
    display_order   SMALLINT NOT NULL DEFAULT 0,
    UNIQUE (module_name, status_code)
);

-- BUSINESS CONFIG — business rules as data, not hardcoded in application
-- code. E.g. AUTO_APPROVAL_LIMIT, OCR_CONFIDENCE_THRESHOLD, PO_MANDATORY,
-- GRN_MANDATORY, PAYMENT_REMINDER_DAYS, DUPLICATE_INVOICE_WINDOW_DAYS.
CREATE TABLE system_configuration (
    config_key    VARCHAR(100) PRIMARY KEY,
    config_value  VARCHAR(255) NOT NULL,
    data_type     VARCHAR(20) NOT NULL DEFAULT 'STRING', -- 'STRING','NUMBER','BOOLEAN'
    description   VARCHAR(255),
    updated_by    VARCHAR(100),
    updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- MODULE 2: VENDOR MANAGEMENT
-- ============================================================================

-- Required at creation: vendor_name, country_id. At least one vendor_address
-- and one active vendor_bank row must exist before a vendor can be paid.
CREATE TABLE vendor (
    vendor_id           SERIAL PRIMARY KEY,
    vendor_name         VARCHAR(200) NOT NULL,
    vendor_code         VARCHAR(30) UNIQUE,
    country_id          INT NOT NULL REFERENCES country(country_id),
    -- vendor_category_id  INT REFERENCES vendor_category(vendor_category_id), -- OPTIONAL
    payment_term_id     INT REFERENCES payment_term(payment_term_id),        -- OPTIONAL
    currency_id         INT REFERENCES currency(currency_id),
    phone_number        VARCHAR(30),
    email               VARCHAR(150),                -- expected sender for inbound invoice emails
    status_id           INT REFERENCES status_master(status_id),
    created_by          VARCHAR(100),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by          VARCHAR(100),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vendor_country ON vendor(country_id);
CREATE INDEX idx_vendor_status ON vendor(status_id);
CREATE INDEX idx_vendor_email ON vendor(email);

CREATE TABLE vendor_address (
    vendor_address_id SERIAL PRIMARY KEY,
    vendor_id          INT NOT NULL REFERENCES vendor(vendor_id) ON DELETE CASCADE,
    address_type       VARCHAR(30) NOT NULL DEFAULT 'REGISTERED', -- REGISTERED, REMIT_TO, SHIPPING
    address_line1      VARCHAR(200) NOT NULL,
    address_line2      VARCHAR(200),
    city               VARCHAR(100) NOT NULL,
    state              VARCHAR(100),
    postal_code        VARCHAR(20),
    country_id         INT NOT NULL REFERENCES country(country_id),
    is_primary         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vendor_address_vendor ON vendor_address(vendor_id);

-- Versioned: bank account changes insert a new row rather than overwriting
-- history. effective_to = NULL means currently active.
CREATE TABLE vendor_bank (
    vendor_bank_id      SERIAL PRIMARY KEY,
    vendor_id           INT NOT NULL REFERENCES vendor(vendor_id) ON DELETE CASCADE,
    bank_name           VARCHAR(150) NOT NULL,
    account_holder_name VARCHAR(150) NOT NULL,
    account_number      VARCHAR(50),
    iban                VARCHAR(50),                 -- EU/international
    swift_code          VARCHAR(20),
    routing_number      VARCHAR(20),                 -- US ABA routing
    ifsc_code           VARCHAR(20),                 -- India
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    effective_from      DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to        DATE,                        -- NULL = currently active
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vendor_bank_vendor ON vendor_bank(vendor_id);
CREATE INDEX idx_vendor_bank_active ON vendor_bank(vendor_id, effective_to);

-- Authoritative source for tax validation (not vendor_category).
CREATE TABLE vendor_tax (
    vendor_tax_id       SERIAL PRIMARY KEY,
    vendor_id           INT NOT NULL REFERENCES vendor(vendor_id) ON DELETE CASCADE,
    tax_type_id         INT NOT NULL REFERENCES tax_type(tax_type_id),
    registration_number VARCHAR(50) NOT NULL,
    is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at         TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (vendor_id, tax_type_id)
);

-- ============================================================================
-- MODULE 3: PURCHASE ORDER & GOODS RECEIPT (optional, minimal — Phase 1)
-- ============================================================================
-- Existence + status check only, no amount matching in Phase 1.

CREATE TABLE purchase_order (
    po_id        SERIAL PRIMARY KEY,
    po_number    VARCHAR(50) NOT NULL UNIQUE,
    vendor_id    INT NOT NULL REFERENCES vendor(vendor_id),
    file_path    VARCHAR(500),
    status_id    INT REFERENCES status_master(status_id), -- OPEN/CLOSED/CANCELLED
    created_by   VARCHAR(100),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_po_vendor ON purchase_order(vendor_id);

CREATE TABLE goods_receipt (
    grn_id      SERIAL PRIMARY KEY,
    po_id       INT REFERENCES purchase_order(po_id),
    vendor_id   INT NOT NULL REFERENCES vendor(vendor_id),
    file_path   VARCHAR(500),
    created_by  VARCHAR(100),
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_grn_vendor ON goods_receipt(vendor_id);
CREATE INDEX idx_grn_po ON goods_receipt(po_id);

-- ============================================================================
-- MODULE 4: INBOUND DOCUMENT — the email-intake front door
-- ============================================================================

CREATE TABLE inbound_document (
    inbound_document_id SERIAL PRIMARY KEY,
    source_type          VARCHAR(20) NOT NULL DEFAULT 'EMAIL', -- 'EMAIL','UPLOAD'
    email_from           VARCHAR(200),
    email_subject        VARCHAR(255),
    email_message_id     VARCHAR(255),                -- de-dup re-sent emails
    received_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    file_name            VARCHAR(255) NOT NULL,
    file_path            VARCHAR(500) NOT NULL,
    extraction_status    VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING/EXTRACTED/FAILED
    extraction_confidence NUMERIC(5,2),
    raw_extracted_data   JSONB,                        -- parser output pre-validation
    vendor_id            INT REFERENCES vendor(vendor_id),
    invoice_id           INT,                           -- FK added after invoice table exists
    created_at           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_inbound_document_status ON inbound_document(extraction_status);
CREATE INDEX idx_inbound_document_message_id ON inbound_document(email_message_id);
CREATE INDEX idx_inbound_document_raw_data ON inbound_document USING GIN (raw_extracted_data);

-- ============================================================================
-- MODULE 5: INVOICE MANAGEMENT
-- ============================================================================

CREATE TABLE invoice (
    invoice_id          SERIAL PRIMARY KEY,
    invoice_number      VARCHAR(50) NOT NULL,          -- vendor's own invoice number
    vendor_id           INT NOT NULL REFERENCES vendor(vendor_id),
    inbound_document_id INT REFERENCES inbound_document(inbound_document_id),
    invoice_type        VARCHAR(20) NOT NULL DEFAULT 'NON_PO', -- 'PO' or 'NON_PO'
    po_id               INT REFERENCES purchase_order(po_id),
    grn_id              INT REFERENCES goods_receipt(grn_id),
    invoice_date        DATE NOT NULL,
    due_date            DATE NOT NULL,
    payment_term_id     INT REFERENCES payment_term(payment_term_id),
    currency_id         INT NOT NULL REFERENCES currency(currency_id),
    gross_amount        NUMERIC(18,2) NOT NULL,         -- subtotal before discount/tax
    discount_amount     NUMERIC(18,2) NOT NULL DEFAULT 0,
    tax_amount          NUMERIC(18,2) NOT NULL DEFAULT 0,
    net_amount          NUMERIC(18,2) NOT NULL,          -- gross - discount + tax = payable amount
    amount_paid         NUMERIC(18,2) NOT NULL DEFAULT 0, -- kept in sync via payment_invoice allocations
    status_id           INT REFERENCES status_master(status_id),
    created_by          VARCHAR(100),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by          VARCHAR(100),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (vendor_id, invoice_number)
);

CREATE INDEX idx_invoice_vendor ON invoice(vendor_id);
CREATE INDEX idx_invoice_status ON invoice(status_id);
CREATE INDEX idx_invoice_due_date ON invoice(due_date);
CREATE INDEX idx_invoice_po ON invoice(po_id);

ALTER TABLE inbound_document
    ADD CONSTRAINT fk_inbound_document_invoice
    FOREIGN KEY (invoice_id) REFERENCES invoice(invoice_id);

CREATE TABLE invoice_line (
    invoice_line_id SERIAL PRIMARY KEY,
    invoice_id      INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    line_number     SMALLINT NOT NULL,
    description     VARCHAR(255) NOT NULL,
    quantity        NUMERIC(18,4) NOT NULL DEFAULT 1,
    unit_price      NUMERIC(18,4) NOT NULL,
    line_amount     NUMERIC(18,2) NOT NULL,
    tax_type_id     INT REFERENCES tax_type(tax_type_id),
    tax_amount      NUMERIC(18,2) NOT NULL DEFAULT 0,
    UNIQUE (invoice_id, line_number)
);

CREATE TABLE invoice_attachment (
    invoice_attachment_id SERIAL PRIMARY KEY,
    invoice_id       INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    file_name        VARCHAR(255) NOT NULL,
    file_path        VARCHAR(500) NOT NULL,
    uploaded_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Single table for both automated validation failures and manual exceptions.
-- severity lets the exception queue be triaged instead of treating every
-- issue as equally urgent.
CREATE TABLE invoice_issue (
    invoice_issue_id SERIAL PRIMARY KEY,
    invoice_id       INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    issue_source     VARCHAR(20) NOT NULL,   -- 'VALIDATION' or 'MANUAL'
    issue_type       VARCHAR(50) NOT NULL,   -- 'DUPLICATE','TAX_MISMATCH','VENDOR_NOT_FOUND',
                                              -- 'PO_MISMATCH','GSTIN_MISMATCH','FORMAT','LOW_OCR_CONFIDENCE'
    severity         VARCHAR(10) NOT NULL DEFAULT 'ERROR', -- 'INFO','WARNING','ERROR'
    result           VARCHAR(10),            -- 'PASS'/'FAIL', null for manual exceptions
    description      VARCHAR(255),
    status_id        INT REFERENCES status_master(status_id),
    resolved_by      VARCHAR(100),
    resolved_at      TIMESTAMP,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    CHECK (severity IN ('INFO','WARNING','ERROR'))
);

CREATE INDEX idx_invoice_issue_invoice ON invoice_issue(invoice_id);
CREATE INDEX idx_invoice_issue_severity ON invoice_issue(severity);

-- ============================================================================
-- MODULE 6: APPROVAL (exceptions only — no workflow/rules-engine table)
-- ============================================================================

CREATE TABLE invoice_approval (
    invoice_approval_id SERIAL PRIMARY KEY,
    invoice_id       INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    invoice_issue_id INT REFERENCES invoice_issue(invoice_issue_id),
    approver_name    VARCHAR(150) NOT NULL,
    decision         VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING/APPROVED/REJECTED
    comments         VARCHAR(500),
    decided_at       TIMESTAMP,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_invoice_approval_invoice ON invoice_approval(invoice_id);

-- ============================================================================
-- MODULE 7: PAYMENT
-- ============================================================================
-- payment = one outgoing transaction (one NEFT/wire/cheque run).
-- payment_invoice = which invoice(s) that transaction settles, and how much
-- of each. This supports one payment covering multiple invoices, and a
-- single invoice being paid across multiple partial payments.

CREATE TABLE payment (
    payment_id       SERIAL PRIMARY KEY,
    vendor_id        INT NOT NULL REFERENCES vendor(vendor_id),
    vendor_bank_id   INT REFERENCES vendor_bank(vendor_bank_id),
    scheduled_date   DATE NOT NULL,           -- when scheduled to run (may capture discount)
    payment_date     DATE,                    -- when it actually executed
    total_amount     NUMERIC(18,2) NOT NULL,  -- sum of payment_invoice.allocated_amount
    currency_id      INT NOT NULL REFERENCES currency(currency_id),
    payment_method   VARCHAR(30) NOT NULL,    -- 'ACH','WIRE','NEFT','RTGS','CHEQUE'
    reference_number VARCHAR(100),
    status_id        INT REFERENCES status_master(status_id),
    created_by       VARCHAR(100),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by       VARCHAR(100),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_payment_vendor ON payment(vendor_id);
CREATE INDEX idx_payment_scheduled_date ON payment(scheduled_date);

CREATE TABLE payment_invoice (
    payment_invoice_id SERIAL PRIMARY KEY,
    payment_id         INT NOT NULL REFERENCES payment(payment_id) ON DELETE CASCADE,
    invoice_id         INT NOT NULL REFERENCES invoice(invoice_id),
    allocated_amount   NUMERIC(18,2) NOT NULL,  -- how much of this payment applies to this invoice
    created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (payment_id, invoice_id)
);

CREATE INDEX idx_payment_invoice_payment ON payment_invoice(payment_id);
CREATE INDEX idx_payment_invoice_invoice ON payment_invoice(invoice_id);

-- ============================================================================
-- MODULE 8: AUDIT
-- ============================================================================

CREATE TABLE audit_log (
    audit_log_id BIGSERIAL PRIMARY KEY,
    table_name   VARCHAR(50) NOT NULL,
    record_id    INT NOT NULL,
    action       VARCHAR(20) NOT NULL,        -- INSERT/UPDATE/DELETE
    changed_by   VARCHAR(100),
    changed_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    old_values   JSONB,
    new_values   JSONB
);

CREATE INDEX idx_audit_table_record ON audit_log(table_name, record_id);
CREATE INDEX idx_audit_new_values ON audit_log USING GIN (new_values);

-- ============================================================================
-- SEED DATA
-- ============================================================================

INSERT INTO currency (currency_name, currency_code, symbol) VALUES
('Indian Rupee','INR','₹'), ('US Dollar','USD','$'), ('Euro','EUR','€');

INSERT INTO country (country_name, country_code) VALUES
('India','IN'), ('United States','US'), ('Germany','DE'),
('United Arab Emirates','AE'), ('Singapore','SG');

-- INSERT INTO vendor_category (category_name, description, is_system_default) VALUES
-- ('Software & SaaS','Software subscriptions and SaaS tools', TRUE),
-- ('Professional Services','Consulting, legal, audit', TRUE),
-- ('IT Hardware','Computers, servers, networking equipment', TRUE),
-- ('Marketing','Advertising and marketing services', TRUE),
-- ('Utilities','Electricity, water, internet', TRUE),
-- ('Others','Uncategorized vendors', TRUE);

INSERT INTO payment_term (term_name, due_days, discount_percent, discount_days, is_system_default) VALUES
('Immediate', 0, 0, 0, TRUE),
('Net 15', 15, 0, 0, TRUE),
('Net 30', 30, 2, 10, TRUE),
('Net 45', 45, 0, 0, TRUE),
('Net 60', 60, 0, 0, TRUE);

INSERT INTO status_master (module_name, status_code, status_name, display_order) VALUES
('VENDOR','PENDING','Pending Approval',1), ('VENDOR','ACTIVE','Active',2),
('VENDOR','INACTIVE','Inactive',3), ('VENDOR','BLOCKED','Blocked',4),
('INVOICE','DRAFT','Draft',1), ('INVOICE','PENDING_APPROVAL','Pending Approval',2),
('INVOICE','APPROVED','Approved',3), ('INVOICE','REJECTED','Rejected',4),
('INVOICE','PARTIALLY_PAID','Partially Paid',5), ('INVOICE','PAID','Paid',6),
('INVOICE','DISPUTED','Disputed',7),
('PO','OPEN','Open',1), ('PO','CLOSED','Closed',2), ('PO','CANCELLED','Cancelled',3),
('APPROVAL','PENDING','Pending',1), ('APPROVAL','APPROVED','Approved',2), ('APPROVAL','REJECTED','Rejected',3),
('PAYMENT','SCHEDULED','Scheduled',1), ('PAYMENT','SENT','Sent',2),
('PAYMENT','CLEARED','Cleared',3), ('PAYMENT','FAILED','Failed',4);

INSERT INTO tax_type (country_id, tax_name, tax_code, calculation_type, rate_percent, is_withholding, effective_from, is_system_default)
SELECT country_id, 'GST 18%', 'GST18', 'PERCENTAGE', 18.000, FALSE, '2024-01-01', TRUE FROM country WHERE country_code = 'IN';

INSERT INTO tax_type (country_id, tax_name, tax_code, calculation_type, rate_percent, is_withholding, effective_from, is_system_default)
SELECT country_id, 'TDS Section 194J', 'TDS194J', 'PERCENTAGE', 10.000, TRUE, '2024-01-01', TRUE FROM country WHERE country_code = 'IN';

INSERT INTO tax_type (country_id, tax_name, tax_code, calculation_type, rate_percent, is_withholding, effective_from, is_system_default)
SELECT country_id, 'Standard VAT', 'VAT-STD', 'PERCENTAGE', 19.000, FALSE, '2024-01-01', TRUE FROM country WHERE country_code = 'DE';

INSERT INTO tax_type (country_id, tax_name, tax_code, calculation_type, rate_percent, is_withholding, effective_from, is_system_default)
SELECT country_id, 'Sales Tax', 'SALES-TX', 'PERCENTAGE', 8.250, FALSE, '2024-01-01', TRUE FROM country WHERE country_code = 'US';

INSERT INTO system_configuration (config_key, config_value, data_type, description) VALUES
('AUTO_APPROVAL_LIMIT', '5000', 'NUMBER', 'Invoices at or below this amount (in base currency) skip manual approval if no other issues are raised'),
('OCR_CONFIDENCE_THRESHOLD', '85', 'NUMBER', 'Minimum extraction_confidence (%) before an invoice is auto-promoted; below this, flagged for manual review'),
('DUPLICATE_INVOICE_WINDOW_DAYS', '90', 'NUMBER', 'Lookback window for duplicate invoice_number + vendor_id detection'),
('PO_MANDATORY', 'FALSE', 'BOOLEAN', 'Whether every invoice must reference a PO'),
('GRN_MANDATORY', 'FALSE', 'BOOLEAN', 'Whether goods-based invoices require a matching GRN'),
('PAYMENT_REMINDER_DAYS_BEFORE_DUE', '3', 'NUMBER', 'Days before due_date to notify AP Executive of an unscheduled invoice'),
('DEFAULT_BASE_CURRENCY', 'INR', 'STRING', 'Company base currency for reporting and threshold comparisons');