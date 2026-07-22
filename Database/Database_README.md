# Accounts Payable (AP) Database Design

## Version
- **Version:** 1.0
- **Database:** PostgreSQL 16+
- **Application:** Accounts Payable (AP) Module
- **Architecture:** Modular Monolith (Python FastAPI backend)
- **Schema file:** `ap_schema.sql`

---

## Overview

The AP module automates the complete lifecycle of vendor invoice processing —
from invoice receipt to payment — matching the flow:

```
Vendor → Invoice Received → Invoice Validation → Approval → Payment → Audit & Reporting
```

The database is designed to be:
- Scalable
- Easy to maintain
- Multi-country ready
- Suitable for small and medium businesses
- Extendable for future ERP capabilities

All tables live under the `ap` Postgres schema (`CREATE SCHEMA ap`).

---

## Getting Started

```bash
psql -U postgres -d your_database -f ap_schema.sql
```

This creates the `ap` schema, all tables, indexes, and seed reference data
(countries, currencies, vendor categories, payment terms, status values,
sample tax types for India and Germany).

Set your app's default schema search path so FastAPI/SQLAlchemy models
resolve without prefixing:

```python
# example: SQLAlchemy engine option
engine = create_engine(DATABASE_URL, connect_args={"options": "-csearch_path=ap"})
```

---

## Database Modules

| Module | Purpose |
|---|---|
| Foundation Masters | Common reference data (country, currency, tax, categories, terms, status) |
| Vendor Management | Vendor master, addresses, bank accounts, tax registrations |
| Purchase Order | PO, PO lines, goods receipt |
| Invoice Management | Invoice header/lines, attachments, validation, exceptions |
| Approval | Approval workflow rules and invoice approval history |
| Payment | Payment records against invoices |
| Audit | System-wide audit trail |

---

## Table Reference

### Foundation Masters

| Table | Key Columns | Notes |
|---|---|---|
| `country` | `country_id`, `country_name`, `country_code` | ISO alpha-2 code, drives all country-specific data |
| `currency` | `currency_id`, `currency_code`, `symbol`, `decimal_places` | ISO 4217 |
| `tax_type` | `tax_type_id`, `country_id` (FK), `tax_code`, `rate_percent`, `is_withholding`, `effective_from/to` | Effective-dated so rate changes don't break historical invoices |
| `vendor_category` | `vendor_category_id`, `category_name` | Drives approval routing rules |
| `payment_term` | `payment_term_id`, `term_name`, `due_days`, `discount_percent` | Net 30, Net 45, etc. |
| `status_master` | `status_id`, `module_name`, `status_code`, `status_name` | One shared status table for vendor/invoice/PO/approval/payment states |

### Vendor Management

| Table | Key Columns | Notes |
|---|---|---|
| `vendor` | `vendor_id`, `vendor_name`, `country_id` (FK), `vendor_category_id` (FK), `address`, `phone_number`, `status_id` (FK) | Core vendor master |
| `vendor_address` | `vendor_address_id`, `vendor_id` (FK), `address_type`, `country_id` (FK) | Supports multiple addresses per vendor (registered / remit-to / shipping) |
| `vendor_bank` | `vendor_bank_id`, `vendor_id` (FK), `iban`, `swift_code`, `routing_number`, `ifsc_code` | One row per bank account; country-specific fields kept nullable side by side rather than EAV, since the set of formats is small and known |
| `vendor_tax` | `vendor_tax_id`, `vendor_id` (FK), `tax_type_id` (FK), `registration_number` | Stores GSTIN / VAT number / EIN etc., one row per tax type per vendor |

### Purchase Order

| Table | Key Columns | Notes |
|---|---|---|
| `purchase_order` | `po_id`, `po_number`, `vendor_id` (FK), `total_amount`, `status_id` (FK) | |
| `purchase_order_line` | `po_line_id`, `po_id` (FK), `quantity`, `unit_price`, `line_amount` | |
| `goods_receipt` | `grn_id`, `po_id` (FK), `po_line_id` (FK), `received_quantity` | Needed for 3-way match (PO + GRN + Invoice) |

### Invoice Management

| Table | Key Columns | Notes |
|---|---|---|
| `invoice` | `invoice_id`, `vendor_id` (FK), `po_id` (FK, nullable), `invoice_type` (`PO`/`NON_PO`), `total_amount`, `amount_paid`, `status_id` (FK) | Header table; `po_id` is NULL for Non-PO invoices |
| `invoice_line` | `invoice_line_id`, `invoice_id` (FK), `tax_type_id` (FK), `line_amount`, `tax_amount` | |
| `invoice_attachment` | `invoice_attachment_id`, `invoice_id` (FK), `file_path` | Uploaded invoice files (original scan/PDF) |
| `invoice_validation` | `invoice_validation_id`, `invoice_id` (FK), `validation_type`, `result` (`PASS`/`FAIL`) | One row per validation check (vendor, duplicate, tax, PO, format) |
| `invoice_exception` | `invoice_exception_id`, `invoice_id` (FK), `exception_type`, `status_id` (FK) | Flags requiring manual review |

### Approval

| Table | Key Columns | Notes |
|---|---|---|
| `approval_workflow` | `approval_workflow_id`, `min_amount`, `max_amount`, `vendor_category_id` (FK, nullable), `approval_level`, `approver_role` | Configurable rule table — amount range + optional category → required approver role |
| `invoice_approval` | `invoice_approval_id`, `invoice_id` (FK), `approval_workflow_id` (FK), `step_number`, `decision` | Actual approval history per invoice |

### Payment

| Table | Key Columns | Notes |
|---|---|---|
| `payment` | `payment_id`, `invoice_id` (FK), `vendor_id` (FK), `vendor_bank_id` (FK), `amount`, `payment_method`, `reference_number`, `status_id` (FK) | `reference_number` holds UTR / bank ref / cheque number |

### Audit

| Table | Key Columns | Notes |
|---|---|---|
| `audit_log` | `audit_log_id`, `table_name`, `record_id`, `action`, `old_values` (JSONB), `new_values` (JSONB) | Generic trail; populate via application-layer hooks or triggers |

---

## Entity Relationship (text form)

```
country ──┬── vendor ──┬── vendor_address
          │            ├── vendor_bank
          │            ├── vendor_tax
          │            ├── purchase_order ── purchase_order_line ── goods_receipt
          │            └── invoice ──┬── invoice_line
          │                          ├── invoice_attachment
currency ─┘                          ├── invoice_validation
                                      ├── invoice_exception
                                      ├── invoice_approval ── approval_workflow
                                      └── payment ── vendor_bank

status_master ── referenced by: vendor, invoice, purchase_order, invoice_approval*, payment
tax_type ── referenced by: vendor_tax, invoice_line
vendor_category ── referenced by: vendor, approval_workflow
```

*`invoice_approval.decision` uses a plain VARCHAR rather than `status_master`
since approval decisions are a fixed, small enum (`PENDING/APPROVED/REJECTED`)
that never needs runtime configuration.

---

## Multi-Country Support

Country-specific behavior is data-driven, not schema-driven:

| Country | Tax Example | How it's modeled |
|---|---|---|
| India | GST, TDS | Rows in `tax_type` with `country_id` = India |
| United States | Sales Tax | Rows in `tax_type` with `country_id` = US |
| Germany | VAT | Rows in `tax_type` with `country_id` = DE |
| UAE / Singapore | VAT / GST | Same pattern |

**Adding a new country never requires an ALTER TABLE** — just insert into
`country`, then `tax_type` rows for that country, and vendor/bank data as it
comes in. `vendor_bank` keeps common international fields (`iban`,
`swift_code`, `routing_number`, `ifsc_code`) side by side as nullable columns,
since the number of real-world bank-field shapes is small and stable; this
avoids over-engineering with EAV unless you're onboarding many more countries.

---

## Naming Standards

- **Primary keys:** `<table>_id` (e.g. `vendor_id`, `invoice_id`)
- **Foreign keys:** same name as the referenced primary key (e.g. `country_id`, `status_id`)
- **Audit columns:** `created_by`, `created_at`, `updated_by`, `updated_at` on every master/transaction table
- **Booleans:** prefixed `is_` (e.g. `is_active`, `is_primary`, `is_withholding`)
- **Money columns:** always `NUMERIC(18,2)` — never `FLOAT`/`REAL`

---

## Data Integrity

- Foreign keys enforce referential integrity between all modules
- `UNIQUE` constraints prevent duplicate invoice numbers per vendor, duplicate PO numbers, duplicate tax registrations per vendor per tax type
- Indexes added on all common lookup/filter columns (`vendor_id`, `status_id`, `due_date`, etc.)
- `tax_type` is effective-dated (`effective_from`/`effective_to`) so historical invoices keep the tax rate that applied when they were created — never recompute old invoices when rates change

--- 

## FastAPI Integration Notes

- Use SQLAlchemy 2.0 async + `asyncpg` as the driver
- Model one SQLAlchemy class per table above, in module-aligned files (e.g. `models/vendor.py`, `models/invoice.py`, `models/payment.py`) mirroring this README's module grouping
- Recommended: a `BaseAuditModel` mixin providing `created_by/created_at/updated_by/updated_at` so every model inherits it consistently
- `status_master` lookups are a good candidate for an in-memory cache (rarely changes, read very often)
 
---

## Future Enhancements

- Vendor self-service portal
- Multi-company / multi-entity support
- Multi-currency accounting with FX rate tables
- Advanced tax engine (slab-based, reverse charge)
- OCR/AI invoice extraction integration
- Payment gateway integration
- ERP / General Ledger posting
- Vendor performance & spend analytics dashboards
- Recurring invoice processing

---

## Suggested `docs/` Folder Structure

```
docs/
├── README.md               (this file)
├── ER_Diagram.png
├── Data_Dictionary.xlsx    (every table, column, type, nullable, default, description)
├── Business_Flow.pdf       (Invoice → Validation → Approval → Payment)
├── Naming_Conventions.md
└── Database_Standards.md
```
