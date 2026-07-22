# Accounts Payable — Phase 1 Schema

## Short version

This is a database schema for an **invoice automation system**, not an ERP.
It supports one flow end to end:

```
Vendor → Invoice arrives by email → OCR/Extraction → Validation →
Exception Handling → Approval (if needed) → Payment Scheduling → Paid
```

22 tables, grouped into three tiers by who owns the data:

- **System reference** (developer-seeded, locked) — `country`, `currency`, `status_master`
- **Business configuration** (seeded as suggestions, AP Executive maintains) — `tax_type`, `vendor_category`, `payment_term`, `system_configuration`
- **Transactional** (created by the pipeline as invoices flow through) — everything else

Deliberately excluded: purchase requisitions, contracts, budget control, cost
centers, GL posting, asset accounting, inventory, accounting journals,
workflow/rules engines, payment batches. Add these only when the business
actually needs them — they belong to full ERP scope, not Phase 1.

Run `ap_schema_phase1.sql` against a PostgreSQL 16+ database to create
everything, including starter seed data.

---

## Detailed explanation

### Why this shape, not a full ERP

Accounts payable automation for a small fintech is fundamentally about
*receiving and paying invoices correctly*, not managing procurement end to
end. Building purchase requisitions, budget control, or GL posting up front
adds tables and code paths that won't be used and will need to be
maintained anyway. Every table in this schema maps to a real step in the
flow above — nothing was added speculatively.

### Module 1 — Foundation Masters

| Table | Tier | Purpose |
|---|---|---|
| `country` | System reference | ISO 3166 country list. Same for every company, doesn't change. |
| `currency` | System reference | ISO 4217 currency list. Same reasoning. |
| `tax_type` | Business config | Country-specific tax definitions (GST, TDS, VAT, sales tax). Rates change yearly, so this must be editable without a code deploy. `calculation_type` distinguishes percentage-based taxes from fixed-amount ones. `is_withholding = TRUE` marks taxes deducted from the vendor (TDS-style); `FALSE` marks taxes added to the invoice (GST/VAT-style) — this flag drives how `net_amount` is calculated. |
| `vendor_category` | Business config | Reporting/UX convenience only (e.g. "Software & SaaS", "Professional Services"). **Never drives validation or payment logic** — it's optional on `vendor` and exists purely so spend-by-category reports are possible. |
| `payment_term` | Business config | "Net 30", "Net 45", etc., with `due_days` and early-payment discount terms. Business policy, changes rarely but should be editable by AP without a deploy. |
| `status_master` | System reference | Shared status codes across modules (VENDOR/INVOICE/PAYMENT/APPROVAL/PO). Status *codes* are wired into application logic — if `PAID` is renamed or deleted through an admin screen, workflows break. Only status labels should be user-editable, not the codes themselves. |
| `system_configuration` | Business config | Key-value store for business rules: `AUTO_APPROVAL_LIMIT`, `OCR_CONFIDENCE_THRESHOLD`, `DUPLICATE_INVOICE_WINDOW_DAYS`, `PO_MANDATORY`, `GRN_MANDATORY`, `PAYMENT_REMINDER_DAYS_BEFORE_DUE`, `DEFAULT_BASE_CURRENCY`. Keeps thresholds and toggles in data instead of hardcoded in application code. |

`tax_type`, `vendor_category`, and `payment_term` each carry an
`is_system_default` flag: seeded rows can be deactivated (`is_active =
FALSE`) but shouldn't be deleted, while anything the AP Executive adds
afterward is fully editable and deletable.

### Module 2 — Vendor Management

| Table | Purpose |
|---|---|
| `vendor` | Core vendor record. Required fields: `vendor_name`, `country_id`. Everything else — category, payment term, tax registration — is optional at creation and filled in as onboarding progresses. |
| `vendor_address` | One-to-many: a vendor can have a registered office, a remit-to address, and a shipping address, all different. `is_primary` marks the default. |
| `vendor_bank` | One-to-many, **versioned**. `effective_from`/`effective_to` mean a bank account change inserts a new row instead of overwriting history — critical for audit trail when a vendor switches accounts. `effective_to IS NULL` means currently active. |
| `vendor_tax` | One row per tax registration (GSTIN, VAT number, EIN). This — not `vendor_category` — is the table actually checked during tax validation. |

Note: there's no flat `address` column on `vendor` itself — `vendor_address`
is the single source of truth, since a flat column can't represent multiple
address types or history.

### Module 3 — Purchase Order & Goods Receipt (optional, minimal)

| Table | Purpose |
|---|---|
| `purchase_order` | Just `po_number`, `vendor_id`, `status_id`, optional `file_path`. Phase 1 only checks that a referenced PO exists, belongs to the right vendor, and is still `OPEN` — **no amount matching**. |
| `goods_receipt` | Same minimal shape, optionally linked to a PO. |

If 2-way or 3-way amount matching becomes a requirement later, add
`total_amount`/line-item tables — that's an additive change, not a redesign.

### Module 4 — Inbound Document (the email-intake front door)

`inbound_document` captures the raw email/attachment and OCR output
*before* it becomes a clean invoice: `email_from`, `email_subject`,
`email_message_id` (for de-duplicating re-sent emails), `raw_extracted_data`
(JSONB — whatever the parser pulled out), `extraction_confidence`. Once
validation succeeds, the row links to the `invoice` it produced. This
separation matters because extraction is unreliable — you need somewhere to
inspect what the parser actually saw when something goes wrong, without
polluting the clean `invoice` table with partially-parsed data.

### Module 5 — Invoice Management

| Table | Purpose |
|---|---|
| `invoice` | Core invoice record. `gross_amount`, `discount_amount`, `tax_amount`, `net_amount` (the actual payable amount) instead of a flat subtotal/total split — makes early-payment discounts and tax visible as separate line items in reporting. `invoice_type` ('PO' or 'NON_PO') plus optional `po_id`/`grn_id` links. `amount_paid` is kept in sync via `payment_invoice` allocations (see Module 7). |
| `invoice_line` | Line-item detail, each optionally tagged with its own `tax_type_id` for line-level tax calculation. |
| `invoice_attachment` | Supporting documents beyond the invoice itself — receipts, contracts, correspondence. |
| `invoice_issue` | **Single table for both automated validation failures and manually-raised exceptions** — no separate validation/exception/mismatch/review tables. `issue_source` distinguishes automated (`VALIDATION`) from human-flagged (`MANUAL`). `severity` (`INFO`/`WARNING`/`ERROR`) lets the exception queue be triaged — e.g. a GST mismatch is `ERROR`, a missing payment term is `WARNING`, low OCR confidence is `INFO`. |

### Module 6 — Approval

`invoice_approval` only gets a row when an `invoice_issue` routes an
invoice to a human — the fully-automated path never touches this table.
There's intentionally no `approval_workflow`/rules-engine table configuring
amount thresholds or approver roles: for a small company, hardcoding "who
reviews exceptions" in application logic (or the `system_configuration`
table, e.g. `AUTO_APPROVAL_LIMIT`) is simpler than building a workflow
engine nobody needs yet.

### Module 7 — Payment

This is the one part reshaped from earlier versions of the schema, based on
architecture review: a single payment run frequently covers **multiple
invoices** (e.g. one NEFT transfer settling three separate invoices from
the same vendor), and a single invoice can be paid in installments.

| Table | Purpose |
|---|---|
| `payment` | One outgoing transaction: `total_amount`, `scheduled_date` (chosen to capture early-payment discounts where possible), `payment_date` (when it actually executed), `payment_method`, `reference_number`. |
| `payment_invoice` | Junction table: which invoice(s) a payment settles, and how much of each (`allocated_amount`). `sum(allocated_amount)` per payment should equal `payment.total_amount`; `sum(allocated_amount)` per invoice accumulates into `invoice.amount_paid`. |

### Module 8 — Audit

`audit_log` is a single generic table (`table_name`, `record_id`, `action`,
`old_values`/`new_values` as JSONB) covering every table in the schema
rather than a per-table audit trail. Finance and compliance will ask for
this — it's cheap to include from day one and expensive to retrofit later.

---

## Example end-to-end flow

1. Email from a known vendor arrives → `inbound_document` row created, OCR
   populates `raw_extracted_data`, `extraction_confidence = 96.5`
2. Vendor matched by email/GSTIN → `vendor_id` resolved; GSTIN cross-checked
   against `vendor_tax`
3. If invoice references a PO → `invoice_type = 'PO'`, `purchase_order`
   existence/status checked (no amount match in Phase 1)
4. Tax validated: invoice's stated tax compared against the vendor's
   registered `tax_type` via `vendor_tax` — `vendor_category` is never part
   of this check, only ever a suggestion
5. All checks pass → `invoice` row created with `net_amount` calculated;
   `due_date` derived from `payment_term_id`
6. If a check fails → `invoice_issue` logged with a `severity`, routed to
   `invoice_approval` if it needs a human
7. Clean invoice(s) scheduled → `payment` created (possibly settling
   several invoices at once via `payment_invoice`), `scheduled_date` chosen
   to capture any early-payment discount
8. AP Executive notified for review/confirmation before the payment
   executes

## What's intentionally deferred to a later phase

- PO/GRN amount matching (2-way/3-way match)
- Multi-step approval workflow with configurable rules/thresholds beyond
  `system_configuration`
- Payment batching/bank file generation for high transaction volumes
- Multi-currency conversion/FX rate tracking beyond storing `currency_id`
- GL posting / accounting journal integration