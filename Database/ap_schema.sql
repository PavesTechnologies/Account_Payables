-- ============================================================================
-- ACCOUNTS PAYABLE (AP) MODULE — DATABASE SCHEMA
-- PostgreSQL 16+
-- Version: 1.0
-- ============================================================================
-- Modules: Foundation Masters | Vendor Management | Invoice Management
--          Purchase Order | Approval | Payment | Audit
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS ap;
SET search_path TO ap;

-- ============================================================================
-- MODULE 1: FOUNDATION MASTERS
-- ============================================================================

CREATE TABLE country (
    country_id      SERIAL PRIMARY KEY,
    country_name    VARCHAR(100) NOT NULL,
    country_code    CHAR(2) NOT NULL UNIQUE,      -- ISO 3166-1 alpha-2, e.g. 'IN','US','DE'
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      VARCHAR(100),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by      VARCHAR(100),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE currency (
    currency_id     SERIAL PRIMARY KEY,
    currency_name   VARCHAR(50) NOT NULL,
    currency_code   CHAR(3) NOT NULL UNIQUE,      -- ISO 4217, e.g. 'INR','USD','EUR'
    symbol          VARCHAR(10) NOT NULL,
    decimal_places  SMALLINT NOT NULL DEFAULT 2,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      VARCHAR(100),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by      VARCHAR(100),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Country-specific tax definitions (GST, TDS, VAT, Sales Tax...)
CREATE TABLE tax_type (
    tax_type_id     SERIAL PRIMARY KEY,
    country_id      INT NOT NULL REFERENCES country(country_id),
    tax_name        VARCHAR(100) NOT NULL,        -- e.g. 'GST 18%', 'TDS Section 194C', 'Sales Tax'
    tax_code        VARCHAR(30) NOT NULL,          -- e.g. 'GST18', 'TDS194C'
    rate_percent    NUMERIC(6,3) NOT NULL,
    is_withholding  BOOLEAN NOT NULL DEFAULT FALSE, -- true for TDS-style withholding tax
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      VARCHAR(100),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by      VARCHAR(100),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (country_id, tax_code, effective_from)
);

CREATE TABLE vendor_category (
    vendor_category_id SERIAL PRIMARY KEY,
    category_name      VARCHAR(100) NOT NULL UNIQUE, -- 'Software & SaaS', 'IT Hardware', etc.
    description         VARCHAR(255),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_by           VARCHAR(100),
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by           VARCHAR(100),
    updated_at           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE payment_term (
    payment_term_id SERIAL PRIMARY KEY,
    term_name       VARCHAR(50) NOT NULL UNIQUE,   -- 'Net 30', 'Net 45', 'Immediate'
    due_days        SMALLINT NOT NULL DEFAULT 0,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    discount_days    SMALLINT NOT NULL DEFAULT 0,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_by       VARCHAR(100),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by       VARCHAR(100),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Shared status values across modules (vendor, invoice, PO, payment, approval)
CREATE TABLE status_master (
    status_id       SERIAL PRIMARY KEY,
    module_name     VARCHAR(50) NOT NULL,          -- 'VENDOR','INVOICE','PAYMENT','APPROVAL','PO'
    status_code     VARCHAR(30) NOT NULL,          -- 'PENDING','APPROVED','PAID', etc.
    status_name     VARCHAR(100) NOT NULL,
    display_order   SMALLINT NOT NULL DEFAULT 0,
    UNIQUE (module_name, status_code)
);

-- ============================================================================
-- MODULE 2: VENDOR MANAGEMENT
-- ============================================================================

CREATE TABLE vendor (
    vendor_id           SERIAL PRIMARY KEY,
    vendor_name         VARCHAR(200) NOT NULL,
    vendor_code         VARCHAR(30) UNIQUE,        -- internal short code, optional
    country_id          INT NOT NULL REFERENCES country(country_id),
    vendor_category_id  INT REFERENCES vendor_category(vendor_category_id),
    payment_term_id     INT REFERENCES payment_term(payment_term_id),
    currency_id         INT REFERENCES currency(currency_id),  -- default billing currency
    address             VARCHAR(255),
    phone_number        VARCHAR(30),
    email                VARCHAR(150),
    status_id            INT REFERENCES status_master(status_id),
    created_by           VARCHAR(100),
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by           VARCHAR(100),
    updated_at           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vendor_country ON vendor(country_id);
CREATE INDEX idx_vendor_status ON vendor(status_id);

-- A vendor can have more than one address (registered / remit-to / shipping)
CREATE TABLE vendor_address (
    vendor_address_id SERIAL PRIMARY KEY,
    vendor_id          INT NOT NULL REFERENCES vendor(vendor_id) ON DELETE CASCADE,
    address_type       VARCHAR(30) NOT NULL DEFAULT 'REGISTERED', -- REGISTERED, REMIT_TO, SHIPPING
    address_line1      VARCHAR(200) NOT NULL,
    address_line2      VARCHAR(200),
    city                VARCHAR(100) NOT NULL,
    state               VARCHAR(100),
    postal_code         VARCHAR(20),
    country_id          INT NOT NULL REFERENCES country(country_id),
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    created_by          VARCHAR(100),
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by           VARCHAR(100),
    updated_at           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vendor_address_vendor ON vendor_address(vendor_id);

-- A vendor can have more than one bank account; fields cover common global formats
CREATE TABLE vendor_bank (
    vendor_bank_id      SERIAL PRIMARY KEY,
    vendor_id           INT NOT NULL REFERENCES vendor(vendor_id) ON DELETE CASCADE,
    bank_name            VARCHAR(150) NOT NULL,
    account_holder_name  VARCHAR(150) NOT NULL,
    account_number       VARCHAR(50),
    iban                 VARCHAR(50),               -- for EU/international vendors
    swift_code           VARCHAR(20),
    routing_number        VARCHAR(20),              -- US ABA routing
    ifsc_code             VARCHAR(20),              -- India
    is_primary            BOOLEAN NOT NULL DEFAULT FALSE,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_by            VARCHAR(100),
    created_at             TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by             VARCHAR(100),
    updated_at             TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vendor_bank_vendor ON vendor_bank(vendor_id);

-- Vendor's tax registrations (GSTIN, VAT number, EIN...), one row per tax type
CREATE TABLE vendor_tax (
    vendor_tax_id       SERIAL PRIMARY KEY,
    vendor_id            INT NOT NULL REFERENCES vendor(vendor_id) ON DELETE CASCADE,
    tax_type_id          INT NOT NULL REFERENCES tax_type(tax_type_id),
    registration_number  VARCHAR(50) NOT NULL,       -- the GSTIN / VAT / EIN value itself
    is_verified          BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at           TIMESTAMP,
    created_by            VARCHAR(100),
    created_at             TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by             VARCHAR(100),
    updated_at             TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (vendor_id, tax_type_id)
);

-- ============================================================================
-- MODULE 3: PURCHASE ORDER (referenced by invoice before Invoice Management,
-- since invoice.po_id points here)
-- ============================================================================

CREATE TABLE purchase_order (
    po_id           SERIAL PRIMARY KEY,
    po_number       VARCHAR(50) NOT NULL UNIQUE,
    vendor_id        INT NOT NULL REFERENCES vendor(vendor_id),
    po_date          DATE NOT NULL,
    currency_id      INT REFERENCES currency(currency_id),
    total_amount     NUMERIC(18,2) NOT NULL DEFAULT 0,
    status_id        INT REFERENCES status_master(status_id),
    created_by       VARCHAR(100),
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by        VARCHAR(100),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_po_vendor ON purchase_order(vendor_id);

CREATE TABLE purchase_order_line (
    po_line_id      SERIAL PRIMARY KEY,
    po_id            INT NOT NULL REFERENCES purchase_order(po_id) ON DELETE CASCADE,
    line_number      SMALLINT NOT NULL,
    description       VARCHAR(255) NOT NULL,
    quantity           NUMERIC(18,4) NOT NULL DEFAULT 1,
    unit_price         NUMERIC(18,4) NOT NULL,
    line_amount        NUMERIC(18,2) NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (po_id, line_number)
);

CREATE TABLE goods_receipt (
    grn_id           SERIAL PRIMARY KEY,
    po_id             INT NOT NULL REFERENCES purchase_order(po_id),
    po_line_id        INT REFERENCES purchase_order_line(po_line_id),
    received_quantity  NUMERIC(18,4) NOT NULL,
    received_date       DATE NOT NULL,
    received_by         VARCHAR(100),
    created_at            TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_grn_po ON goods_receipt(po_id);

-- ============================================================================
-- MODULE 4: INVOICE MANAGEMENT
-- ============================================================================

CREATE TABLE invoice (
    invoice_id          SERIAL PRIMARY KEY,
    invoice_number       VARCHAR(50) NOT NULL,       -- vendor's invoice number
    vendor_id             INT NOT NULL REFERENCES vendor(vendor_id),
    po_id                 INT REFERENCES purchase_order(po_id),  -- NULL for Non-PO invoices
    invoice_type          VARCHAR(20) NOT NULL DEFAULT 'NON_PO', -- 'PO' or 'NON_PO'
    invoice_date           DATE NOT NULL,
    due_date               DATE NOT NULL,
    payment_term_id        INT REFERENCES payment_term(payment_term_id),
    currency_id             INT NOT NULL REFERENCES currency(currency_id),
    subtotal_amount          NUMERIC(18,2) NOT NULL,
    tax_amount                NUMERIC(18,2) NOT NULL DEFAULT 0,
    total_amount               NUMERIC(18,2) NOT NULL,
    amount_paid                 NUMERIC(18,2) NOT NULL DEFAULT 0,
    status_id                    INT REFERENCES status_master(status_id),
    created_by                    VARCHAR(100),
    created_at                     TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by                     VARCHAR(100),
    updated_at                     TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (vendor_id, invoice_number)
);

CREATE INDEX idx_invoice_vendor ON invoice(vendor_id);
CREATE INDEX idx_invoice_status ON invoice(status_id);
CREATE INDEX idx_invoice_due_date ON invoice(due_date);

CREATE TABLE invoice_line (
    invoice_line_id  SERIAL PRIMARY KEY,
    invoice_id        INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    line_number        SMALLINT NOT NULL,
    description         VARCHAR(255) NOT NULL,
    quantity             NUMERIC(18,4) NOT NULL DEFAULT 1,
    unit_price           NUMERIC(18,4) NOT NULL,
    line_amount          NUMERIC(18,2) NOT NULL,
    tax_type_id           INT REFERENCES tax_type(tax_type_id),
    tax_amount             NUMERIC(18,2) NOT NULL DEFAULT 0,
    UNIQUE (invoice_id, line_number)
);

CREATE TABLE invoice_attachment (
    invoice_attachment_id SERIAL PRIMARY KEY,
    invoice_id              INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    file_name                 VARCHAR(255) NOT NULL,
    file_path                  VARCHAR(500) NOT NULL,
    uploaded_by                 VARCHAR(100),
    uploaded_at                   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE invoice_validation (
    invoice_validation_id SERIAL PRIMARY KEY,
    invoice_id              INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    validation_type           VARCHAR(30) NOT NULL,   -- 'VENDOR','DUPLICATE','TAX','PO','FORMAT'
    result                     VARCHAR(10) NOT NULL,   -- 'PASS' / 'FAIL'
    remarks                     VARCHAR(255),
    validated_at                 TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_invoice_validation_invoice ON invoice_validation(invoice_id);

CREATE TABLE invoice_exception (
    invoice_exception_id SERIAL PRIMARY KEY,
    invoice_id              INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    exception_type            VARCHAR(50) NOT NULL,   -- 'DUPLICATE','TAX_MISMATCH','PO_NOT_FOUND'...
    description                VARCHAR(255),
    status_id                    INT REFERENCES status_master(status_id),
    resolved_by                   VARCHAR(100),
    resolved_at                     TIMESTAMP,
    created_at                       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_invoice_exception_invoice ON invoice_exception(invoice_id);

-- ============================================================================
-- MODULE 5: APPROVAL
-- ============================================================================

-- Configurable rules: which invoices need which approval level
CREATE TABLE approval_workflow (
    approval_workflow_id SERIAL PRIMARY KEY,
    workflow_name           VARCHAR(100) NOT NULL,
    min_amount                NUMERIC(18,2) NOT NULL DEFAULT 0,
    max_amount                 NUMERIC(18,2),          -- NULL = no upper bound
    vendor_category_id          INT REFERENCES vendor_category(vendor_category_id), -- NULL = applies to all
    approval_level                SMALLINT NOT NULL DEFAULT 1,
    approver_role                  VARCHAR(50) NOT NULL, -- 'Finance Manager','AP Executive', etc.
    is_active                        BOOLEAN NOT NULL DEFAULT TRUE,
    created_by                        VARCHAR(100),
    created_at                          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by                          VARCHAR(100),
    updated_at                          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE invoice_approval (
    invoice_approval_id SERIAL PRIMARY KEY,
    invoice_id             INT NOT NULL REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    approval_workflow_id     INT REFERENCES approval_workflow(approval_workflow_id),
    step_number                SMALLINT NOT NULL,
    approver_name                VARCHAR(150) NOT NULL,
    decision                      VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING/APPROVED/REJECTED
    comments                       VARCHAR(500),
    decided_at                      TIMESTAMP,
    created_at                        TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (invoice_id, step_number)
);

CREATE INDEX idx_invoice_approval_invoice ON invoice_approval(invoice_id);

-- ============================================================================
-- MODULE 6: PAYMENT
-- ============================================================================

CREATE TABLE payment (
    payment_id       SERIAL PRIMARY KEY,
    invoice_id         INT NOT NULL REFERENCES invoice(invoice_id),
    vendor_id           INT NOT NULL REFERENCES vendor(vendor_id),
    vendor_bank_id       INT REFERENCES vendor_bank(vendor_bank_id),
    payment_date          DATE NOT NULL,
    amount                 NUMERIC(18,2) NOT NULL,
    currency_id             INT NOT NULL REFERENCES currency(currency_id),
    payment_method            VARCHAR(30) NOT NULL,   -- 'ACH','WIRE','NEFT','RTGS','CHEQUE'
    reference_number            VARCHAR(100),          -- UTR / bank reference / cheque number
    status_id                     INT REFERENCES status_master(status_id),
    created_by                     VARCHAR(100),
    created_at                       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by                       VARCHAR(100),
    updated_at                       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_payment_invoice ON payment(invoice_id);
CREATE INDEX idx_payment_vendor ON payment(vendor_id);

-- ============================================================================
-- MODULE 7: AUDIT
-- ============================================================================

CREATE TABLE audit_log (
    audit_log_id    BIGSERIAL PRIMARY KEY,
    table_name        VARCHAR(50) NOT NULL,
    record_id          INT NOT NULL,
    action              VARCHAR(20) NOT NULL,          -- INSERT / UPDATE / DELETE
    changed_by            VARCHAR(100),
    changed_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    old_values                JSONB,
    new_values                JSONB
);

CREATE INDEX idx_audit_table_record ON audit_log(table_name, record_id);
CREATE INDEX idx_audit_new_values ON audit_log USING GIN (new_values);

-- ============================================================================
-- SEED DATA (starter reference values — extend as needed)
-- ============================================================================

INSERT INTO currency (currency_name, currency_code, symbol) VALUES
('Indian Rupee','INR','₹'),
('US Dollar','USD','$'),
('Euro','EUR','€');

INSERT INTO country (country_name, country_code) VALUES
('India','IN'),
('United States','US'),
('Germany','DE'),
('United Arab Emirates','AE'),
('Singapore','SG');

INSERT INTO vendor_category (category_name, description) VALUES
('Software & SaaS','Software subscriptions and SaaS tools'),
('Rent & Lease','Office and equipment rent'),
('Food & Catering','Catering and food services'),
('Office Supplies','Stationery and office consumables'),
('IT Hardware','Computers, servers, networking equipment'),
('Professional Services','Consulting, legal, audit'),
('Marketing','Advertising and marketing services'),
('Utilities','Electricity, water, internet'),
('General Goods','Miscellaneous goods'),
('Banking Services','Bank charges and financial services'),
('Travel','Travel and accommodation'),
('Others','Uncategorized vendors');

INSERT INTO payment_term (term_name, due_days) VALUES
('Immediate', 0),
('Net 7', 7),
('Net 15', 15),
('Net 30', 30),
('Net 45', 45),
('Net 60', 60);

INSERT INTO status_master (module_name, status_code, status_name, display_order) VALUES
('VENDOR','PENDING','Pending Approval',1),
('VENDOR','ACTIVE','Active',2),
('VENDOR','INACTIVE','Inactive',3),
('VENDOR','BLOCKED','Blocked',4),
('INVOICE','DRAFT','Draft',1),
('INVOICE','PENDING_APPROVAL','Pending Approval',2),
('INVOICE','APPROVED','Approved',3),
('INVOICE','REJECTED','Rejected',4),
('INVOICE','PARTIALLY_PAID','Partially Paid',5),
('INVOICE','PAID','Paid',6),
('INVOICE','DISPUTED','Disputed',7),
('PO','OPEN','Open',1),
('PO','CLOSED','Closed',2),
('PO','CANCELLED','Cancelled',3),
('APPROVAL','PENDING','Pending',1),
('APPROVAL','APPROVED','Approved',2),
('APPROVAL','REJECTED','Rejected',3),
('PAYMENT','SCHEDULED','Scheduled',1),
('PAYMENT','SENT','Sent',2),
('PAYMENT','CLEARED','Cleared',3),
('PAYMENT','FAILED','Failed',4);

-- Example: India-specific tax types (requires country row above to exist)
INSERT INTO tax_type (country_id, tax_name, tax_code, rate_percent, is_withholding, effective_from)
SELECT country_id, 'GST 18%', 'GST18', 18.000, FALSE, '2024-01-01' FROM country WHERE country_code = 'IN';

INSERT INTO tax_type (country_id, tax_name, tax_code, rate_percent, is_withholding, effective_from)
SELECT country_id, 'TDS Section 194C', 'TDS194C', 2.000, TRUE, '2024-01-01' FROM country WHERE country_code = 'IN';

INSERT INTO tax_type (country_id, tax_name, tax_code, rate_percent, is_withholding, effective_from)
SELECT country_id, 'Standard VAT', 'VAT-STD', 19.000, FALSE, '2024-01-01' FROM country WHERE country_code = 'DE';
