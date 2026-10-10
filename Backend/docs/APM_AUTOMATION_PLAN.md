# APM Automation & Dashboards: Review and Proposed Plan

Status: **Phases 0–2 complete. Phase 1 migration applied to dev on 2026-10-09. Phases 3–7 not started.**
- No migration, no database write and no change to application code has been made.
- Phase 0 added two things: the test-document generator and the generated test documents. See section 0.

Scope: the backend (`Account_Payables/Backend`) and the frontend (`UMS/intranet-fe/src/pages/accounts-payable`).

Revision 2 (2026-10-09) adds:
- the database environment confirmation (development);
- vendor agreements (3.1a);
- the authoritative-terms rules (3.1);
- the GSTIN test strategy (4.2);
- the Phase 0 results (section 0);
- the remaining decisions (section 7).

---

## 0. Phase 0 results

### 0.1 Baseline tests (before any change)

Excluded: every test that touches the live dev DB, including the ones that use savepoint rollback:
- `test_tds_import_masters_db.py`, `test_tds_config_service_db.py`, `test_dashboard_db.py`, `test_payment_tds_tracking_db.py`
- `test_invoice_create.py`, `test_tds_determination_integration.py` (both `SessionLocal` + commit)
- `test_pr_bulk_cleanup.py`, `test_pr_reset.py`
- `manual_verify_ocr_reviewed_state.py`

| Suite | Command | Result |
|---|---|---|
| Backend (pytest) | `pytest Backend/tests --ignore=<the 9 files above>` | **1179 passed, 21 failed, 1 skipped** (25 s) |
| Frontend (vitest) | `npx vitest run` | **521 passed, 9 failed** (44 files, 4 failing) |

All 30 failures **existed before this work**; no code has been changed yet. They will be tracked separately from any regression.

**Backend failures (21):**

| Tests | Count | Cause |
|---|---|---|
| `test_process_invoice_route.py` | 5 | Get 404: the `/process-invoice` route is commented out in `invoice_process_route.py`. Stale tests. |
| `test_rfq_workflow.py` | 5 | `RFQService.send_rfq()` now requires `vendor_ids`; tests were not updated. |
| `test_rfq_email_sending.py` | 5 | Fake DB lacks `.query` / `.execute`, which the newer notification code calls. |
| `test_rfq_authorization.py` | 1 | Fake DB lacks `.query` / `.execute`, which the newer notification code calls. |
| `test_in_app_notifications.py` | 2 | Fake DB lacks `.query` / `.execute`, which the newer notification code calls. |
| `test_quotation_vendor_matcher.py` | 2 | Score expectations drifted (90 vs 95/75). |
| `test_quotation_extraction_fields.py` | 1 | Score expectations drifted. |

None of these are in the payment, TDS or dashboard code paths.

**Frontend failures (9):**

| Tests | Count | Note |
|---|---|---|
| `APDashboardPage.test.jsx`, "Requires Attention" | 5 | **These are on the page Phase 2 changes. I will diagnose them before touching the dashboard.** |
| `InvoiceTdsPanel.test.jsx` | 1 | |
| `notifications.test.js` (AP submenu wiring) | 1 | |
| `QuotationFormModal.test.jsx` | 2 | |

### 0.2 Generated documents

| Path (backend repo) | Contents |
|---|---|
| `test-documents/synthetic_invoices_v1/invoices/` | 50 documents (S01–S50). 47 are PDF, 1 is JPG (phone photo) and 1 is PNG; S50 is an intentionally corrupt PDF. |
| `test-documents/synthetic_invoices_v1/agreements/` | 3 vendor agreements: a lease (valid), an MSA (valid) and a SaaS order form (**expired**). |
| `test-documents/synthetic_invoices_v1/SCENARIOS.md` | Human-readable scenarios and expected outcomes. |
| `test-documents/synthetic_invoices_v1/scenarios.json` | Machine-readable expectations: amounts, payment-term result, TDS, the end-to-end target state, and planned payments. |
| `test-documents/synthetic_invoices_v1/vendors.json` | The vendor registry used. 11 proposed `TST-` vendors plus the existing AWS and KEKA. |
| `Backend/scripts/generate_test_invoices.py` | The generator. Deterministic (fixed seed, fixed PDF metadata and ID, verified byte-identical across runs). No DB or network access. `--vendors file.json` swaps in approved identities. |

**Coverage:**

| Dimension | Count |
|---|---|
| Invoice type | 13 PO / 37 non-PO |
| Tax | 31 intra-state (CGST+SGST) / 15 IGST / 4 GST-exempt |
| Layouts | 5 |
| Scanned / photo / PNG | 8 |
| Multi-page | 2 |
| Expected payment-term status | 33 COMPLIANT / 5 MISMATCH / 8 REVIEW_REQUIRED |
| MSME statutory deadline | 5 |
| TDS applicable | 26 |
| TDS nature needs correcting | 9 |
| Overdue as of 2026-10-09 | 12 |
| Duplicates or invalid files | 5: byte duplicate, exact vendor + number duplicate, possible duplicate, quotation (not an invoice), corrupt file |

The scenario dates span April–October 2026, so the 3/6-month reports and the forecast have data.

### 0.3 Findings from Phase 0 (I recommend fixing these, but have not changed them)

1. **GSTIN checksum bug.** `Business_Layer/utils/extraction/normalizers.py: gstin_checksum_valid` starts the mod-36 weight at **2 instead of 1**. As a result, *every real GSTIN fails the check*: AWS `07AAJCA9880A1ZL` and KEKA `36AAFCK5835K1Z6` both fail, and pass with the standard algorithm.
   - The checksum is only used as a positive OCR signal (`extraction/gstin.py:136`), so the impact is lower GSTIN-extraction confidence, not rejections.
   - It is a one-line fix plus a test.
2. **TDS mapping gaps in the purchase categories.**
   - `FIN_AUDIT`, `FIN_ACCOUNTING` and `ADMIN_FACILITIES` map to payment nature `OTHER`, which has **no TDS rule**. So audit/accounting fees and facility contracts never get TDS determined automatically, and an AP Executive has to correct the nature each time (9 of the test invoices exercise this).
   - Proposed: `FIN_*` → `PROFESSIONAL_SERVICE` and `ADMIN_FACILITIES` → `CONTRACTOR`. This is a master-data change, so it needs approval.
3. **The `RENT` payment nature has no TDS rule.** Only `RENT_LAND_BUILDING` (10%) and `RENT_PLANT_MACHINERY` (2%) do. The new `ADMIN_RENT` category should map to `RENT_LAND_BUILDING`.
4. **`BUYER_GSTIN` is empty in `.env`.** Buyer GSTIN validation therefore has nothing to compare against. The test invoices print no buyer GSTIN. Please provide the company GSTIN for the dev config.
5. **GST API configuration.** The dev `.env` points `SANDBOX_BASE_URL` at the **production** endpoint (`api.sandbox.co.in`) with a **live** key, although the code's default is `test-api.sandbox.co.in`. Every GSTIN lookup from dev is a real, billed production call (see 4.2).
6. **Backend branch.** The backend repo is on `main`, while the frontend is on `accounts_payable`.

---

## 1. Current architecture (what these changes touch)

### Backend
- FastAPI app, with every router under `/apm`. SQLAlchemy 2 on PostgreSQL, all tables in schema `ap`.
- Schema changes are made with hand-written `Backend/Data_Access_Layer/migration_*.sql` files (with rollback files). `create_all` also runs at startup. There is no Alembic.
- Code is layered as `API_Layer/routes` → `Business_Layer/services` → `Data_Access_Layer/dao`.
- Every state change writes an `ap.audit_log` row and a notification.
- **Storage and OCR.** Files go to S3 through `s3_utils.upload_to_s3`. Text is extracted with AWS Textract, using async `StartExpenseAnalysis` and `StartDocumentAnalysis` with QUERIES, wrapped in retry/backoff (`invoice_extraction_fields.py`). There is also an older local OCR path (PyMuPDF and RapidOCR) that is no longer used.
- **Background work.** There is only FastAPI `BackgroundTasks` (for validate-fields), with progress kept in Redis (`ap:validation:{job}`). There is no scheduler and no Celery.
- **Authorization.** Permission codes come from the UMS JWT `permissions` claim. Each route checks its own hard-coded list (`permission_base_access.py`). Dashboard sections are filtered inside `DashboardService.capabilities()`.

### Invoice lifecycle (unchanged by this plan)
`Upload → Textract extract (Redis cache) → section corrections → validate (BG job) → create-invoice [OCR_REVIEW_PENDING] → OCR review [OCR_REVIEWED] → TDS determine → send for approval [PENDING_APPROVAL] → multi-level approve [APPROVED] → TDS verify → Mark Ready [READY_FOR_PAYMENT] → record payment(s) [PARTIALLY_PAID / PAID] → TDS tracking: deduction → deposit → filing`

### Frontend
- React 18, Vite, React Query, Tailwind, Recharts.
- Hand-built forms. AP permissions are handled through `useApPermissions` and `constants/*Permissions.js`.
- Pages: AP Dashboard (`/dashboard/summary`), Invoice upload / OCR review / list / detail, Payments ready / history plus `RecordPaymentModal`, TDS tracking plus `RecordTdsActivityModal`.
- The Reports page (`/reports`) is a placeholder.

### Database (inspected read-only, no credentials printed)
- Remote PostgreSQL server, database `accounts_payable`. **You confirmed on 2026-10-09 that it is a development database.** The configuration itself has no APP_ENV variable or hostname hint.
- Rules for this database:
  - only additive migrations;
  - test data tagged `TST-`;
  - seed and cleanup scripts are dry-run by default and reviewed before execution;
  - no deletes or overwrites of existing business data.
- Contents: 2 vendors (KEKA, AWS), 7 purchase categories (including `TEST_CAT_ONE`), 5 departments (including `TEST_DEPT`), 2 invoices (both PAID), 5 payments, **0 POs**, 0 GRNs, and 5 payment terms (Immediate / Net 15 / Net 30 / Net 45 / Net 60).
- This looks like a shared dev DB, but I am **treating it as production until you confirm otherwise.**

---

## 2. Gap analysis

| Requirement | What exists | Gap |
|---|---|---|
| **PO payment terms** | `purchase_order.payment_terms` is **free text** only. `quotation.payment_terms` is text. | No structured term on the PO, no comparison against the invoice, no due-date calculation. |
| **Invoice payment terms** | Textract query `PAYMENT_TERMS` exists. The raw text is stored only in `inbound_document.raw_extracted_data` JSON. `invoice.payment_term_id` is set by an **exact name match** ("Net 30 days" gives NULL). | No parsing, no fallback to `vendor.payment_term_id`. |
| **Due date** | `invoice.due_date` is NOT NULL and set to `extracted due date or invoice_date`. | It is never calculated from terms. The fallback to invoice_date makes forecasts and overdue figures wrong. |
| **Vendor agreement / contract** | Nothing. There is no contract model, vendor "documents" are derived only, and the NDA is a separate workflow. `vendor.payment_term_id` exists and is optional. | Agreement upload, extraction, validity, verification and audit (a new feature, 3.1a). |
| **Statutory deadlines** | Nothing. There are no MSME or Udyam fields and no TDS due-date calendar. | MSMED 45-day / 43B(h) rules, and TDS deposit and return deadlines. |
| **Exception flags** | `invoice_issue` table (VALIDATION / EXTRACTION sources). No CHECK constraint on type. | It is not exposed through any API or UI, and there is no resolve endpoint. |
| **Payment receipt automation** | Manual `RecordPaymentModal`. Receipt is uploaded after the payment is recorded. Per-invoice duplicate UTR check. | No extraction, and no duplicate UTR check across invoices. |
| **TDS challan / filing automation** | Manual deposit and filing **per invoice** (`invoice_tds_tracking`, unique per invoice_id, no challan uniqueness). | No extraction, no shared challan, no quarterly return entity. TDS deduction is not linked to the payment. |
| **Finance dashboard** | `/dashboard/summary` returns a generic KPI mix, an "Outstanding Payable" KPI, and `/payment/ready-for-payment` with due/overdue filters. | No ageing, no 30/60/90-day forecast, no due-date buckets, no exception list. |
| **Management / approver views** | Approval timestamps (`started_at`, `decided_at`, `completed_at`) and `audit_log` exist, so turnaround can be computed. | No views, and no management permissions. |
| **Reports / exports** | None. `openpyxl` and PyMuPDF are already installed. | Report endpoints, Excel and PDF export. |
| **Bulk upload** | Single file only. `create_invoice()` can be called from a service without Redis. Duplicate check is exact (vendor_id, invoice_number), backed by a unique key. | Batch entity, async worker, per-file status, fuzzy duplicates, retries. |
| **Test data** | `test-documents/` holds 1 invoice PDF and 1 TDS Excel. About 50 pytest files; some use the live DB (savepoint rollback, but `test_tds_import_masters_db.py` **really commits**). | 50 scenario invoices, test vendors, POs, cleanup tooling. |

---

## 3. Proposed design

Conventions I will follow:
- Raw SQL migration plus rollback file in `Data_Access_Layer/`.
- Status values as `VARCHAR` with a CHECK constraint, the same way `invoice_tds.determination_status` and `invoice_tds_tracking.tracking_status` work. Invoice lifecycle statuses stay in `status_master`, and **no new invoice lifecycle statuses are added.**
- Audit-log rows for every confirmation.
- Permission checks in the backend for every new endpoint.

### 3.1 Payment-term compliance

**Step 1: fix parsing and due dates first, before any forecast or overdue report is built.**
- Today `payment_term_id` is resolved by exact name, so "Net 30 days" resolves to NULL. Payment terms will be parsed into days and a basis using the existing regex extractor `Business_Layer/utils/extraction/payment_terms.py`, which reads Net N, N days, within N days, Immediate, due on receipt, and N days from delivery/GRN. The result is resolved to `payment_term` **by due_days** as well as by name.
- In `create_invoice` and the OCR review, the due date will be calculated as follows:
  - printed due date if present;
  - else **basis date + parsed term days**;
  - **never `invoice_date` while terms are available**.
- When neither terms nor a printed due date exist, the `NOT NULL` `invoice.due_date` keeps its current technical fallback. The invoice is then marked **due date unverified** (`REVIEW_REQUIRED`). Dashboards show it in a separate "due date unverified" bucket instead of counting it as due or overdue.
- **Three dates are kept apart:**
  - the contractual due date (from terms);
  - the statutory deadline (3.2);
  - the actual payment date (`payment.payment_date`, already separate).

  `invoice.due_date` holds the *effective* due date, the earlier of the first two, so existing queries and the `is_overdue` flag keep working. The underlying dates stay in their own columns.

**New table `ap.invoice_payment_term`** (1:1 with invoice; keeps `invoice` clean and holds the evidence):

| Column | Purpose |
|---|---|
| `invoice_id` (PK/FK) | |
| `invoice_terms_text`, `invoice_term_days`, `invoice_due_date_printed` | What the invoice says |
| `po_terms_text`, `po_term_days` | PO reference (PO invoices) |
| `vendor_master_term_id`, `vendor_master_term_days` | Vendor master reference |
| `agreement_id`, `agreement_term_days`, `agreement_valid_on_invoice_date` | Agreement reference (3.1a) |
| `reference_source` | `PO` / `AGREEMENT` / `VENDOR_MASTER` / `MANUAL` / `NONE` |
| `applied_term_days`, `due_basis` (`INVOICE_DATE` / `GRN_DATE`), `basis_date` | |
| `contractual_due_date` | basis_date + applied days |
| `statutory_due_date`, `statutory_rule` | MSME limit (see 3.2) |
| `effective_due_date` | Earlier of contractual and statutory. Copied into `invoice.due_date`. |
| `due_date_verified` | False when unresolved |
| `validation_status` | `COMPLIANT` / `MISMATCH` / `REVIEW_REQUIRED` / `VERIFIED_OVERRIDE` |
| `reason_code`, `checked_at`, `verified_by`, `verified_at`, `verification_remarks` | |

- **`OVERDUE` is not stored.** It depends on time, so it is computed in queries (`effective_due_date < today AND balance > 0`). The UI shows days remaining or days overdue next to the status.
- **Status convention:** `VARCHAR` plus a CHECK constraint, like `invoice_tds.determination_status`. No new invoice lifecycle status is added.

**Which terms are authoritative.** These are the rules the 50 test scenarios were built against. The first matching rule wins:

| Invoice type | Condition | Status (reason) | Applied terms |
|---|---|---|---|
| PO | Printed PO number not matched to a PO | `REVIEW_REQUIRED` (PO_NOT_MATCHED) | none until resolved |
| PO | PO has no usable terms | `REVIEW_REQUIRED` (PO_TERMS_MISSING) | none until resolved |
| PO | Invoice terms differ from PO | `MISMATCH` (INVOICE_VS_PO) | **PO terms** (never silently overridden) |
| PO | Same, or invoice silent | `COMPLIANT` | PO terms |
| Non-PO | Invoice terms missing or ambiguous ("as agreed") and no printed due date | `REVIEW_REQUIRED` (INVOICE_TERMS_MISSING / AMBIGUOUS) | the agreement or master value is *suggested*, not applied |
| Non-PO | A valid agreement and the vendor master disagree | `MISMATCH` (VENDOR_MASTER_VS_AGREEMENT) | agreement, pending review |
| Non-PO | No valid agreement and no vendor-master term | `REVIEW_REQUIRED` (NO_AUTHORISED_TERMS) | none |
| Non-PO | Invoice differs from the authoritative reference (agreement if valid, else vendor master) | `MISMATCH` (INVOICE_VS_AGREEMENT / INVOICE_VS_VENDOR_MASTER) | the reference |
| Non-PO | Vendor has agreements but none is valid on the invoice date | `REVIEW_REQUIRED` (AGREEMENT_EXPIRED) | master value suggested |
| Non-PO | Matches the reference; a printed due date alone implies N days | `COMPLIANT` (IMPLIED_FROM_PRINTED_DUE_DATE when implied) | the reference |

- Only an agreement that is **ACTIVE (verified)** and valid on the invoice date counts as authoritative. An unverified upload is never used.
- Whether the agreement or the vendor master wins when both exist and agree is irrelevant. When they disagree, the result is always a review, never a silent choice.

**When the check runs:**
- at `create_invoice` (single and bulk);
- again on OCR-review save (terms, due date, PO or vendor changed);
- when an agreement or vendor term changes (open invoices for that vendor are re-checked);
- at Mark Ready for Payment.

Existing invoices get a backfill script (dry-run by default).

**Resolve action.**
- `POST /invoice/{id}/payment-terms/verify` accepts the applied terms (choose the source, term and due basis) and **requires remarks for MISMATCH and REVIEW_REQUIRED**.
- The result is `VERIFIED_OVERRIDE` (or `COMPLIANT` after a recheck), recorded with an audit row containing before and after values.

**Ready-for-Payment integration.** `mark_ready_for_payment` already requires APPROVED plus TDS VERIFIED. The proposal adds one more check: the payment-term status must be `COMPLIANT` or `VERIFIED_OVERRIDE` (decision D1). Approval and TDS are never bypassed.

**APIs:**
- `GET /invoice/{id}/payment-terms`
- `POST /invoice/{id}/payment-terms/recheck`
- `POST /invoice/{id}/payment-terms/verify`
- `GET /payment/term-exceptions`, a list with filters by status, reason, vendor and due window

**UI:**
- A **Payment Terms panel** on Invoice Detail: each source side by side (invoice / PO / agreement / vendor master), the applied terms, the due basis, the contractual, statutory and effective due dates, days left or overdue, the status, and a verify action.
- Badges on the Ready-for-Payment list.
- `invoice_issue` is not reused, because it has no API and is bulk-auto-resolved on OCR review, which would wipe term flags.

**PO change:** add a nullable `purchase_order.payment_term_id` and a dropdown on the PO form, keeping the free-text field (backward compatible). Existing POs fall back to parsing their text.

### 3.1a Vendor agreements and contracts (new feature)

**Should existing models be extended?** I checked and the answer is no:
- There is no `vendor_document` table. `VendorDocumentDTO` (`vendor_interface.py:247`) is assembled from quotation, GRN and invoice file references.
- `VendorNda` (`models/nda.py`) is NDA-specific: template body, sent/signed lifecycle, and no payment-term fields. Extending it would mix two workflows.

**A dedicated pair of tables is the safe additive option.** It reuses:
- the existing infrastructure: S3 `upload_to_s3` / `view_from_s3` / `download_from_s3`, `file_validation`, the Textract query helper, and the `StreamingResponse` view/download pattern;
- `audit_log`.

```
ap.vendor_agreement
  agreement_id, vendor_id (FK), agreement_type LEASE|MSA|SOW|SUBSCRIPTION|RATE_CONTRACT|OTHER,
  reference_no, title, valid_from, valid_to (NULL = open-ended), auto_renew,
  payment_term_id (FK, nullable), payment_terms_text, term_days, due_basis INVOICE_DATE|GRN_DATE,
  status DRAFT | PENDING_VERIFICATION | ACTIVE | REJECTED | SUPERSEDED,
  extracted_payload JSONB, extraction_confidence, remarks,
  uploaded_by, uploaded_at, verified_by, verified_at, verification_remarks, created/updated audit cols
  CHECK (valid_to IS NULL OR valid_to >= valid_from)
ap.vendor_agreement_document
  document_id, agreement_id (FK), file_name, s3_key, content_type, file_size, uploaded_by, uploaded_at
```

- "Expired" is **computed** (`valid_to < date`), not stored, for the same reason as OVERDUE.
- A new ACTIVE agreement of the same type for the same vendor marks the previous one SUPERSEDED.

**Workflow:**
1. **Upload** (vendor page, new "Agreements" tab). `POST /vendor/{id}/agreements/extract` runs Textract with queries for the parties, the vendor GSTIN/PAN, the effective and expiry dates, the payment-terms clause, the notice period and the agreement reference. It returns editable suggestions and writes nothing.
2. **Save draft.** `POST /vendor/{id}/agreements` stores the document and fields with status `PENDING_VERIFICATION`.
3. **Verify.** `POST /vendor-agreements/{id}/verify` or `/reject`, with remarks. **Proposed four-eyes control:** the verifier must be a different user from the uploader (decision D6). Only ACTIVE agreements are authoritative.
4. **Effect.** Activation re-runs the payment-term check for that vendor's open invoices.
5. **Expiry alerts.** Agreements expiring within 30 days appear on the Finance dashboard. There is no scheduler; the list is computed when the page is viewed.

**APIs:**
- `GET /vendor/{id}/agreements`
- `GET /vendor-agreements/{id}`
- `.../documents/{doc}/view|download`
- `PATCH /vendor-agreements/{id}` (only while DRAFT or PENDING_VERIFICATION)

**Permissions** (decision D5): reuse the vendor permissions for viewing and uploading, and add `VENDOR_AGREEMENT_VERIFY` for verification.

**Test data:** AGR-01 (lease, 15 days, valid), AGR-02 (MSA, 45 days, valid) and AGR-03 (SaaS, 30 days, **expired 2026-06-30**) are generated under `agreements/`.

### 3.2 Statutory deadlines (kept separate from contractual terms)

| Rule | What I'd implement | Needs |
|---|---|---|
| **MSMED Act s.15**: pay micro/small suppliers within the agreed term, max **45 days**, or **15 days** if there is no agreement. This links to **Income-tax s.43B(h)**, where unpaid amounts are disallowed. | `statutory_due_date`, and an "MSME at risk" flag on dashboards. | New vendor fields: `msme_registered`, `udyam_number`, `msme_category` (MICRO/SMALL/MEDIUM; only MICRO/SMALL get the deadline), shown in the vendor form. |
| **TDS deposit**: by the 7th of the following month (30 April for March deductions). | `deposit_due_date` on TDS tracking, plus "deposit due / late" KPIs. | None |
| **Quarterly TDS statement**: Q1 by 31 Jul, Q2 by 31 Oct, Q3 by 31 Jan, Q4 by 31 May. | `filing_due_date`. | None |

- Because the TDS rules are being moved to the **Income-tax Act 2025** section numbering (`old_section`/`new_section`), these dates will be **configuration rows (`system_configuration`), not hard-coded.** If the rules change, an admin can update them without a code release.
- Dashboards will label them "statutory deadline (configured)".

### 3.3 Payment receipt automation

- **`POST /payment/invoice/{id}/receipt/extract`** (multipart; permission `PAYMENT_PROCESS`):
  - Validates the file using the existing `file_validation`.
  - Runs Textract with receipt-specific QUERIES: transaction date, amount, UTR / reference / transaction ID, mode (NEFT/RTGS/IMPS/UPI/cheque), payer and beneficiary account (masked), beneficiary name, bank, status. Images and one-page PDFs use synchronous `AnalyzeDocument`; multi-page files reuse the existing async helper.
  - **Writes nothing to the DB.**
  - Returns suggested values with confidence, plus **warnings**: amount differs from the remaining balance, beneficiary name does not resemble the vendor, date is in the future, failed/pending wording, and UTR already used on *any* payment (a new cross-invoice check).
- **Frontend (`RecordPaymentModal`):**
  - A new "Upload receipt to auto-fill" step at the top. Extracted values fill the **same editable fields**, each marked "auto-filled".
  - The user reviews and submits through the existing `POST /payment/invoice/{id}/record`, then the same file is attached with the existing `POST /payment/{id}/documents`.
  - Manual entry is unchanged.
  - Uploading a receipt never records a payment by itself. All existing validations and audit rows apply.
- **Audit:** the payment's audit row records `entry_mode: RECEIPT_EXTRACTED | MANUAL` and which fields were edited after extraction.

### 3.4 TDS challan & filing automation (shared challan)

**Problem:** one challan (ITNS 281) normally pays TDS for **many invoices** for a month and section. Today `invoice_tds_tracking` stores `challan_number`, `bsr_code` and `deposit_date` **per invoice**, with no shared record and no amount check.

**Proposal (decision D4; additive, per-invoice tracking stays the system of record for status):**

```
ap.tds_challan
  challan_id, challan_serial_no, bsr_code, deposit_date, cin (computed BSR+date+serial),
  tan, assessment_year, tax_period_month, section/payment_nature_id, minor_head (200/400),
  tax_amount, surcharge, cess, interest, fee, total_amount,
  status DRAFT | CONFIRMED | CANCELLED, document (S3 via invoice_tds_document-like table), audit cols
  UNIQUE (bsr_code, deposit_date, challan_serial_no)

ap.tds_challan_allocation
  challan_id, invoice_id (→ invoice_tds_tracking), allocated_tds_amount
  UNIQUE (invoice_id) where challan CONFIRMED   -- an invoice's TDS is deposited once

ap.tds_return_filing                      -- quarterly statement acknowledgement
  filing_id, form (e.g. 26Q), financial_year, quarter, acknowledgement_no (token no.),
  filing_date, status DRAFT|CONFIRMED, document; + ap.tds_return_filing_invoice (filing_id, invoice_id)
```

**Workflow:**
1. **Upload or enter a challan** (`POST /tds/challans/extract`, then `POST /tds/challans`). Textract extracts the challan serial, BSR, deposit date, CIN, TAN, AY, minor head, section/nature, the amount breakdown, and the tax period.
2. **System-suggested allocation.** Candidates are invoices whose TDS is VERIFIED, DEDUCTED and not yet deposited, with the same section/nature and a deduction date in the challan's tax period, with each one's TDS amount pre-filled. The user ticks and adjusts.
3. **Confirm.** Checks:
   - allocations sum to `tax_amount`, with a ±₹1 tolerance (configurable);
   - every invoice is eligible;
   - the deposit date is not before any deduction date;
   - a document is attached (**evidence is required**) or a remark explains why not.

   On confirm, the **existing `record_deposit` service** runs for each allocated invoice, so per-invoice status, history, audit and current screens keep working unchanged.
4. **Filing.** The same pattern applies to the quarterly acknowledgement: extract the token/ack number and date, suggest all DEPOSITED invoices of that quarter, confirm, and call the existing `record_filing` for each.
5. **Late flags.** "Deposited after due date" and "deposit overdue" (interest exposure) appear as exceptions.
6. The single-invoice deposit and filing modals stay as they are.

**Deduction:** I propose that recording a payment **suggests** (pre-fills) the TDS deduction date as the payment date, without recording it automatically (D9).

### 3.5 Dashboards by role (backend-enforced)

The existing `/dashboard/summary` and AP Dashboard page are **kept** as the "Overview". `/accounts-payable/dashboard` gets role tabs, and only the tabs the user is entitled to are shown. The default tab is the first one the user is entitled to.

| View | Endpoint(s) | Backend gate |
|---|---|---|
| **Finance (Operational)** | `GET /dashboard/finance` | `PAYMENT_VIEW` (actions need `PAYMENT_PROCESS`; the TDS widget needs `TDS_TRACKING_VIEW`) |
| **Approver** | `GET /dashboard/approvals` | `INVOICE_APPROVE` or `INVOICE_APPROVAL_VIEW` |
| **Management (CEO)** | `GET /reports/management/*` | **new** `AP_MANAGEMENT_DASHBOARD_VIEW`, `AP_MANAGEMENT_REPORTS_VIEW`, `AP_MANAGEMENT_REPORTS_EXPORT` |
| **Procurement (CPO)** | `GET /reports/procurement/*` | **new** `AP_PROCUREMENT_REPORTS_VIEW` (D7) |
| **Reports** (placeholder page made real) | `GET /reports/{report}` and `/reports/{report}/export?format=xlsx|pdf` | per-report permission |

**Amount definitions** (one shared SQL helper, so totals agree everywhere):
- `net_payable = net_amount − tds_amount`, where `tds_amount` comes only from TDS determinations in DETERMINED/VERIFIED state.
- `paid = invoice.amount_paid`. This counts CLEARED allocations only, so partial payments are counted once.
- `reserved = SCHEDULED/SENT allocations`.
- `outstanding = net_payable − paid − reserved`. **These are the same rules as `compute_payable_amount` and `invoice_payment_summary`.**
- Due-date logic uses `effective_due_date` (from 3.1).
- Amounts are grouped **per currency**, as today, with no FX conversion.
- Forecasts are labelled **"Expected payments based on recorded invoices and due dates; not a guaranteed cash-flow forecast."** Disputed and rejected invoices are excluded, and any amount on hold is shown separately.

**Finance Executive (what to do today):**
- **Action cards with counts and amounts:**
  - Ready for payment (due ≤ 7 days / later)
  - **Overdue**, with ageing buckets 1–15 / 16–30 / 31–60 / 60+
  - Partially paid balance
  - Approved but not yet marked ready
  - Payment-term exceptions
  - TDS: verification pending, deposit due this month / overdue, filing due this quarter
  - Receipts missing on recorded payments
- **Upcoming payments:** next month, month+2 and month+3, as a bar chart plus a table of top invoices per month.
- **Recently paid:** date, UTR, amount, receipt present.
- **Reports:** last 3 / 6 months or a custom range, exportable.

**Approver:**
- My pending approvals, oldest first, with the age of each.
- Pending by department.
- High-value invoices (threshold configurable).
- My average turnaround and the team's turnaround per level (from `started_at` / `decided_at`).
- Returned-for-review and disputed invoices.

**Management, CEO (read-only, organisation level):**
- Total outstanding liability.
- Expected payments in the next 30 / 60 / 90 days.
- Monthly AP spend (invoice value) versus paid.
- On-time payment %: paid ≤ effective due date.
- Overdue total, and **high-value exceptions**.
- MSME 45-day exposure.
- Spend by department, category and vendor.
- **Vendor concentration:** top-10 vendors' share of outstanding.
- **Process efficiency:** median cycle time, upload → approved → paid, plus approval bottlenecks by level and department.
- Compliance: payment-term mismatches and TDS late or overdue.
- Filters: date range, department, vendor, status.

**Procurement, CPO:**
- PR → PO → GRN → invoice funnel.
- PO value against invoiced value.
- Spend by category and vendor.
- Non-PO spend share (a purchasing-compliance indicator).
- PO/invoice term mismatches.
- Quotation-versus-PO savings, where quotations exist.

(There are 0 POs in the DB today, so this view only becomes meaningful with data.)

**Management is read-only.** The management endpoints return aggregates, plus drill-down lists limited to invoice number, vendor, amount and dates. They expose no actions. Vendor bank details are never included.

**Reports (both Excel and PDF):**
- AP liabilities
- Ageing
- Expected payments
- Payments made (with UTR)
- Payment performance
- Spend analysis
- Vendor exposure
- Compliance exceptions
- TDS register (deducted / deposited / filed, with challans)
- Process efficiency

How they are produced:
- **Excel:** `openpyxl` (already installed).
- **PDF:** PyMuPDF (already installed, and already used for NDA PDFs), as simple branded tables. **No new dependencies.**
- Exports are generated in the backend and are permission-checked, so the server enforces what each user can export.

### 3.6 Bulk invoice upload

```
ap.invoice_upload_batch       batch_id, uploaded_by, file_count, status QUEUED|PROCESSING|COMPLETED|COMPLETED_WITH_ERRORS, counts, created/finished_at
ap.invoice_upload_batch_item  item_id, batch_id, file_name, file_sha256, s3_key, size,
                              status QUEUED|EXTRACTING|VALIDATING|CREATED|DUPLICATE|POSSIBLE_DUPLICATE|NEEDS_ATTENTION|FAILED,
                              error_code, error_message, attempts, extracted_payload JSONB, validation_summary JSONB,
                              invoice_id, inbound_document_id, timestamps
```

**Flow:**
1. **`POST /invoice-extract/bulk`** (permission `INVOICE_CREATE`):
   - validates each file (type and size), computes SHA-256, uploads to S3 and creates the items;
   - returns `batch_id` **immediately**;
   - rejects a file whose hash matches another file in the same batch or an existing document, marking it `DUPLICATE`.
2. **Worker** (FastAPI `BackgroundTasks`, the same mechanism as validate-fields):
   - Processes items with **concurrency 2**, using an asyncio semaphore. The DB pool is 3 + 2 overflow and Textract is the bottleneck.
   - For each item it runs the existing extraction, the existing validators and the existing `create_invoice()`, so the invoice lands in **OCR_REVIEW_PENDING** in the **existing OCR review queue**. Payment-term compliance (3.1) runs inside `create_invoice`.
   - Nothing is auto-approved, and the full lifecycle still applies.
3. **Resilience:**
   - Each item is retried up to 3 times on Textract throttling or timeouts (on top of the existing backoff).
   - Non-retryable errors (corrupt file, OCR failure) → `FAILED`, with the reason recorded.
   - **Startup recovery:** on app start, items left in QUEUED or EXTRACTING are re-queued, so a restart does not lose a batch.
   - `extracted_payload` is stored in the DB, not only in Redis (whose TTL is 4h). A `NEEDS_ATTENTION` item can then be opened in the existing single-upload correction screen later.
4. **Duplicates:**
   - Exact match (vendor + invoice number, the existing unique key) → `DUPLICATE`, not created.
   - **Possible duplicate** (same vendor and same amount within ±7 days with a different number, or the same normalised number such as `INV-001` vs `INV001`) → created, but flagged on the batch item and the invoice for the reviewer (D10).
5. **Vendor not found / GSTIN problems** → `NEEDS_ATTENTION`, with a link to resolve it through the existing flow.
6. **UI:** a new "Bulk Upload" tab on the Invoice Upload page:
   - multi-select drag & drop;
   - batch progress page: polling every 3s, a per-file status table, retry for failed items, open the created invoice, resolve needs-attention items;
   - "My batches" history.

   The single-file upload stays as it is.

**Limits:**
- **25 files per batch**, 10 MB each, 100 MB per batch (configurable).
- At about 30–60 s per document and concurrency 2, 25 files take roughly 8–12 minutes.

**ZIP: not recommended.** Multi-select already covers the use case, and ZIP adds zip-bomb and path-traversal risk, plus nested and unsupported file handling, for little benefit.

**Cost note:** each page is billed for Textract AnalyzeExpense plus Queries, the same as a single upload today.

### 3.7 Permissions

- New codes must be **created in UMS** (`permissions` and `permission_group` tables) and assigned to roles:
  - `AP_MANAGEMENT_DASHBOARD_VIEW`, `AP_MANAGEMENT_REPORTS_VIEW`, `AP_MANAGEMENT_REPORTS_EXPORT`
  - `AP_PROCUREMENT_REPORTS_VIEW`
  - optionally `INVOICE_PAYMENT_TERM_VERIFY` (or reuse `PAYMENT_PROCESS`, D5)
- The AP backend and frontend then reference these codes.
- No Admin bypass is added.

---

## 4. Test-data strategy (50 synthetic invoices)

### 4.1 Documents (done in Phase 0, no DB impact)

The set is under `test-documents/synthetic_invoices_v1/`. Section 0.2 lists the files and coverage, and `SCENARIOS.md` has the expected outcome of each invoice.

Every page carries the footer "SYNTHETIC TEST DOCUMENT - NOT A TAX INVOICE". Invoice numbers start with `TST`, and new vendor names start with `[TEST]`. Bank details are masked or marked synthetic, and contact addresses use `example.invalid`.

**Layouts and quality:**
- 5 layouts: classic GST invoice, modern SaaS, landlord letter (Times), utility bill, and typewriter-style small vendor (Courier).
- 6 rasterised scans: skew of ±3°, noise, blur, JPEG quality 35–55, 110–150 DPI.
- 1 perspective phone photo (JPG) and 1 PNG.
- 2 two-page invoices.
- Invalid inputs: 1 quotation (not an invoice) and 1 unreadable PDF.

I did not include a password-protected PDF. PyMuPDF can create one, but nothing in the current upload path handles encryption, so it would only test the generic failure path that S50 already covers. Say if you want one added.

**Expectations are tied to real rules:**
- TDS expectations use the **active TDS_RATE rules read from the dev DB** (FY 2026-27 under the Income-tax Act 2025 numbering), the engine's taxable base (gross − discount), and its aggregate logic.
- Payment-term expectations use the rule table in 3.1.
- The generator encodes both, so a rule change shows up as a diff in `scenarios.json`.

### 4.2 GSTIN test strategy (no invented real GSTINs, no validation bypass)

**How GST validation works today:**
- **Vendor creation and update** call the live GST search (`vendor_service.py:68`), and any failure blocks the vendor.
- **Auto-onboarding** from an invoice requires a verified, Active GST response (`vendor_auto_onboarding.py:305`).
- **Invoice validation** matches the invoice GSTIN against the vendor master (`validate_vendor`), with no API call.
- **The TDS compliance check** calls the API and only warns.

I will not change any of this.

**Strategy by layer:**

| Layer | What is used | Why it is safe |
|---|---|---|
| **Automated tests** (unit and service) | Monkeypatch `search_gstin` / `call_gst_search` with recorded-shape fixtures (Active, Cancelled, Suspended, HTTP error, timeout, malformed). This is the existing pattern in `test_tds_determination_service.py`. | No network; every branch of the real validation code still runs. |
| **Generated documents (now)** | **Placeholder GSTINs that are format-valid but carry a deliberately wrong mod-36 check digit** (verified with the standard algorithm). Each one is flagged `PLACEHOLDER_CHECKSUM_INVALID` in `vendors.json`, and its PAN is synthetic too (`TST…`). | A wrong check digit means the number **cannot be a registered GSTIN**, so no real business is impersonated. These vendors **cannot be onboarded**, because the real GST check rejects them. That is intended. |
| **Dev end-to-end run** | **Approved test identities** go into `vendors.json`, and the documents are regenerated with `--vendors`, giving the same scenarios with new identifiers. Vendors are then onboarded through the **normal flow, with GST validation unchanged**. | The validation path is exactly the production path. |

**Where approved test identities can come from (decision D2):**
1. **Sandbox test environment credentials (`key_test_…`)** pointed at `test-api.sandbox.co.in`, which is already the code's default base URL.
   - **This is the option I recommend.** It also stops dev from making billed calls to the production API with a live key (finding 0.3-5).
   - **Caveat:** I can't confirm which GSTINs the test environment answers for without credentials. If it only returns canned responses for documented test GSTINs, we use exactly those.
2. **GSTINs Finance approves for testing**, such as the company's own registrations. These are real registrations used with permission, never invented ones.
3. If neither is available, the dev end-to-end run is limited to the existing AWS and KEKA vendors (13 scenarios). The other 37 are checked at document and extraction level only, where they are expected to land in `NEEDS_ATTENTION` / `VENDOR_NOT_FOUND`.

**Not proposed:** skipping GST validation for `TST-` vendors, a hidden dev stub inside the application, or inventing checksum-valid GSTINs.

**Keeping test data separate from real vendors:**
- `vendor_code` `TST-001…`, names prefixed `[TEST]`, emails `@example.invalid`;
- `created_by` set to a dedicated test user;
- S3 keys under a `test-data/` prefix;
- invoice and PO numbers prefixed `TST`;
- seed and cleanup scripts **dry-run by default**. Cleanup selects strictly by these tags and refuses to touch a row that lacks them.

### 4.3 Master data for the end-to-end run (proposed; Phase 7, needs approval)

**Test vendors:** the 11 `TST-` vendors in `vendors.json`:
- entity types company, firm and individual, covering the 194C 1% and 2% variants;
- vendor-master payment terms Net 15/30/45/60;
- 2 MSME (one MICRO, one SMALL).

**New purchase categories:**

| Category | Department | TDS nature |
|---|---|---|
| `ADMIN_RENT` | ADMIN | RENT_LAND_BUILDING |
| `PROF_CONSULTING` | FIN | PROFESSIONAL_SERVICE |
| `IT_SERVICES` | IT | TECHNICAL_SERVICE |
| `ADMIN_UTILITIES` | ADMIN | OTHER |

**Mapping fixes for existing categories (finding 0.3-2):** `FIN_AUDIT` and `FIN_ACCOUNTING` → PROFESSIONAL_SERVICE, `ADMIN_FACILITIES` → CONTRACTOR.
- Without the fix, 9 scenarios need a manual nature correction. That is also a valid test case, so either choice works.

**POs and agreements:**
- 12 POs (`TST-PO-0001`…`0012`), with PRs and GRNs where needed, created **through the existing services**. The PO list in `scenarios.json` gives terms, GRN dates and amounts.
- 3 agreements, loaded once 3.1a exists.

**Setup:** `BUYER_GSTIN` configured in dev (finding 0.3-4).

### 4.4 End-to-end run (Phase 7)

1. Bulk-upload all 50 documents.
2. Compare each one automatically with `scenarios.json`: intake result, duplicate flags, payment-term status and reason, effective due date, TDS nature, section and amount.
3. Drive each invoice to its `e2e_target` (approve, verify TDS, mark ready, record the planned payments), so the dashboards and reports have known expected totals.
4. Report a pass/fail table and list every mismatch.

---

## 5. Testing plan

1. **Baseline first:**
   - Done in Phase 0 (section 0.1). The same exclusion list is used for every later run, so results stay comparable.
   - Run `npx vitest run` in the frontend.
   - Record the failures that already exist **before** any change.
2. **New unit tests (fake DAOs / monkeypatched Textract and Redis, following the existing patterns):**
   - Term parsing.
   - PO and non-PO compliance matrix.
   - Due-basis and statutory calculations, including March and the TDS-deposit edge case and month-end and leap-year dates.
   - Ready-for-payment gate.
   - Receipt and challan extraction mapping, warnings, and failure paths.
   - Challan allocation sum and eligibility.
   - Bulk worker state machine, retries, startup recovery, duplicates.
   - Dashboard math: partial payments, TDS, reserved amounts, overdue buckets.
   - Report and export content.
   - Permission gating (403s) for every new endpoint.
3. **DB tests** use the existing savepoint/rollback `db` fixture only.
4. **Frontend tests** for the auto-fill modal, the bulk progress page and the dashboard tabs by permission.
5. The final report lists **existing failures separately from regressions.**

---

## 6. Phasing (each phase is a reviewable commit set, reported as it completes)

| Phase | Scope | DB changes | Status |
|---|---|---|---|
| **0** | Baseline tests; 50 synthetic documents + 3 agreements; scenario documentation | none | **Done** |
| **1** | Payment-term parsing and due-date fix; `invoice_payment_term` compliance; **vendor agreements (3.1a)**; statutory config; MSME vendor fields; PO `payment_term_id`; Ready-for-Payment gate; backfill script (dry-run); GSTIN checksum fix | `migration_payment_term_compliance.sql` (+ rollback) — applied to dev 2026-10-09 | **Done** — see 6.1 |
| **2** | Finance Executive dashboard; Reports page with Excel/PDF export (diagnose the 5 failing `APDashboardPage` tests first) | none | **Done** — see 6.2 |
| **3** | Bulk invoice upload | additive (batch tables) | |
| **4** | Payment receipt extraction and auto-fill | none expected | |
| **5** | TDS challan/filing extraction; shared challan and quarterly filing model | additive | |
| **6** | Approver dashboard; Management (CEO) view; Procurement (CPO) view if in scope | none expected | |
| **7** | Seed `TST-` master data (dry-run first, then on approval); E2E run with the 50 documents; results report | tagged test rows only | |

### 6.1 Phase 1 implementation notes

- **Endpoints.** The agreement routes live under `/apm/vendor-agreements/...` instead of `/vendor/{id}/agreements`, so they cannot collide with the existing `/vendor/{vendor_id}` routes:
  - `GET /vendor-agreements/vendor/{vendor_id}`
  - `POST /vendor-agreements/vendor/{vendor_id}/extract`
  - `POST /vendor-agreements/vendor/{vendor_id}` (multipart)
  - `GET|PATCH /vendor-agreements/{id}`
  - `POST /vendor-agreements/{id}/verify|reject`
  - `GET /vendor-agreements/{id}/documents/{doc}/view|download`
  - `GET /vendor-agreements/expiring`
  - Invoice terms: `GET /invoice/{id}/payment-terms`, `POST .../recheck`, `POST .../verify`
  - `GET /payment-terms/exceptions`, `GET /payment-terms/metadata`
- **PO terms gap fixed.** PO generation (`procurement_service`) never copied the selected quotation's payment terms. It now copies the text and resolves `payment_term_id`. Without this, every PO invoice would have been REVIEW_REQUIRED.
- **MSME fields** are editable on the vendor Edit page and shown on vendor Overview. The onboarding request flow is unchanged.
- **Payment-terms parser.** Ranges and alternatives ("30 or 45 days", "30/60", "EOM", "as agreed") are always ambiguous, so they are flagged for review and never guessed.
- **Incident (2026-10-09).** Importing `Backend.main` during development ran `create_all` against the dev DB. It created the three new, empty tables (`vendor_agreement`, `vendor_agreement_document`, `invoice_payment_term`). No existing table, column or row was touched. Recommended fix: drop those three empty tables, then apply the reviewed migration.

### 6.2 Phase 2 implementation notes

- **Endpoints.**
  - `GET /apm/dashboard/finance` requires PAYMENT_VIEW or PAYMENT_PROCESS. The TDS block is included only for users holding a TDS permission.
  - `GET /apm/reports` lists only the reports the caller may run.
  - `GET /apm/reports/{key}?from_date&to_date&vendor_id&department_id&months&format=json|xlsx|pdf`.
- **Reports and their permissions:**
  - `outstanding_payables`, `ageing`, `expected_payments`, `payments_made`: payment permissions.
  - `tds_register`: TDS permissions.
  - `payment_term_exceptions`: term or payment permissions.

  Running a report the caller may not run returns 403.
- **One row model** (`APReportingService.invoice_figures`) feeds the dashboard and every export, so the totals always agree. A partly paid invoice is counted once, net of TDS, payments made and scheduled payments.
- **Ageing** covers approved and ready-for-payment invoices. The **upcoming** view splits approved amounts from those still in review or approval. Invoices without a verified due date get their own bucket, and disputed invoices are shown as on hold. The forecast label states that it is not a guaranteed cash-flow forecast.
- **Statutory TDS calendar** (`statutory_calendar.py`): deposit by the 7th (30 April for March deductions); quarterly statement due 31 Jul / 31 Oct / 31 Jan / 31 May. Both can be overridden with `TDS_DEPOSIT_DUE_DAY` / `TDS_MARCH_DEPOSIT_DUE_DAY`.
- **Frontend.**
  - The dashboard now has **Finance** (default for payment users) and **Overview** (the existing summary) tabs.
  - The Reports page has period presets (last 3 / 6 months, financial year, custom) plus Excel and PDF export.
  - Reports is now in the sidebar.
  - The 5 stale `APDashboardPage` tests (written for the old notification-based "Requires Attention") were rewritten for the new page.
- **Known limitation:** PDF and Excel amounts use international digit grouping (1,132,800.00); the screens use Indian grouping (11,32,800.00).

### 6.3 Role dashboards (one point of view per person)

The generic "all statuses" Overview is replaced by role views. `GET /apm/dashboard/views` lists the ones the caller may open, and `GET /apm/dashboard/view/{key}` returns one; each view is permission-checked server-side.

| View | Granted by | Shows |
|---|---|---|
| Management (CEO / Chief Product Officer) | `AP_MANAGEMENT_DASHBOARD_VIEW` | total liability, 30/60/90-day outflow, overdue %, on-time %, days to pay, FY spend, vendor concentration, spend by department, process efficiency (median cycle times, approval bottlenecks), compliance and high-value exceptions. Read-only. |
| Finance | `PAYMENT_VIEW` / `PAYMENT_PROCESS` | as in 6.2 |
| Approvals | `INVOICE_APPROVE` / `REJECT` / `SEND_BACK` | my queue (oldest first, high-value flag), oldest wait, my decisions per month, my turnaround, waiting by department |
| My work (AP Executive) | `INVOICE_CREATE` / `OCR_REVIEW` / `SEND_FOR_APPROVAL` / `TDS_DETERMINE` | to review, returned, TDS to determine, ready to send, intake trend (all vs mine), oldest items with their next step, payment-term issues to fix at review |

**Fallback:** users holding none of these (e.g. procurement-only) keep the generic AP Overview.

**Management access:**
- The AP menu, Dashboard and Reports also open with any `AP_MANAGEMENT_*` permission, with no AP role needed.
- `AP_MANAGEMENT_REPORTS_VIEW` reads every report and the summary.
- Excel/PDF export additionally needs `AP_MANAGEMENT_REPORTS_EXPORT`; this is enforced in the backend.

**High-value threshold:** `HIGH_VALUE_INVOICE_THRESHOLD` in system_configuration (default 1,00,000).

**Database rules:**
- Every migration is a reviewed SQL file with a rollback file, and is **applied only after your go-ahead for that phase**.
- Seed and cleanup scripts print a dry-run first.
- Nothing deletes or overwrites existing business data.

---

### 6.4 Phase 3 implementation notes (bulk upload)

Decisions (2026-10-10): **ZIP or several files**, **25 per batch**, invoices **saved straight to OCR review**, new permission **`INVOICE_BULK_UPLOAD`**, email intake next (3b).

**Principle:** the single upload stays the source of truth. The worker calls, per file, exactly what the Invoice Upload page drives: `upload_to_s3` → `extract_invoice_from_s3` → `InvoiceExtractionService.validate_invoice` → `create_invoice`, and (like "Save for Manual Review") creates whatever the validation result. Bulk adds only batch tracking, a concurrency limit and retry safety. Review, approval, payment terms, TDS and payment are untouched.

- **Only change to existing code:** `create_invoice` raises `VendorNotMatchedError`, a new `FieldExtractionError` subclass, for an unmatched vendor (the single route still returns the same 400).
- **Tables** (`migration_invoice_bulk_upload.sql` + rollback, additive): `invoice_upload_batch`, `invoice_upload_batch_item`. `create_all` creates them (empty) on the next backend start; the migration is idempotent.
- **API** `/invoice-bulk-upload` (all `INVOICE_BULK_UPLOAD`): `POST` (files or one ZIP, 202), `GET /batches`, `GET /batches/{id}`, `POST /batches/{id}/retry`, `POST /items/{id}/retry|skip`, `GET /limits`.
- **Item results:** CREATED · VENDOR_NOT_FOUND · DUPLICATE (same file SHA-256 in the batch / already created, or existing vendor + invoice number) · FAILED (invalid file, upload, extraction, create) · SKIPPED.
- **Retry safety:** atomic QUEUED→PROCESSING claim; Textract output stored on the item so retries do not re-extract; a retry first looks for an invoice already created from the same S3 object (crash between commit and status update); `PROCESSING` older than 15 min shows as *stalled* and is retryable. Startup auto-recovery was **not** added (it would mean DB work at import time); "Retry" resumes a batch instead.
- **Concurrency:** 2 files per backend process (`BULK_UPLOAD_CONCURRENCY`).
- **ZIP safety:** one ZIP only, no nested ZIPs, no password-protected ZIPs, ≤ 25 invoice files, every member read with a hard 10 MB cap (header sizes not trusted), folder paths dropped, OS clutter ignored; PDF/image signature checked.
- **Not done (deviation from 3.6):** "possible duplicate" fuzzy flagging (D10) - the single upload has no such check, so bulk does not either; reviewers still see exact duplicates.
- **UI:** "Bulk Upload" button on Invoice Management and the single-upload page; `/invoices/bulk-upload` (drop zone + batch history) and `/invoices/bulk-upload/:id` (live progress, per-file result, retry / skip / onboard vendor / open invoice).
- **Tests:** `test_invoice_bulk_upload.py` (23), `InvoiceBulkUpload.test.jsx` (6).

### 6.5 Phase 3b and Step A implementation notes (2026-10-10)

**Email intake (3b):** `Backend/scripts/run_email_intake.py` (dry run by default, `--execute`, `--loop`), Graph read-only client `graph_mail_client.py`, `invoice_email_intake_service.py`. One batch per email (unique `source_reference`), go-live `EMAIL_INTAKE_START_DATE` required, `VENDOR_EMAIL` = only those senders, otherwise invoice-like subject / file name + "unknown sender" flag. Advisory lock against overlapping runners.
- **Switch:** `EMAIL_INTAKE_ENABLED` in `system_configuration` (OFF by default, seeded by the migration), toggled on the Bulk Upload page by `EMAIL_INTAKE_MANAGE` (audited); `GET/PUT /email-intake/status`. Runner records `EMAIL_INTAKE_LAST_RUN`.
- **`READ_MAIL_ACCESS`** now guards `/intake/graph-token`, `/intake/mails`, `/intake/send-mail` (in-process `send_mail` used by notifications unaffected).

**Step A - review workbench:** `/invoices/review-workbench` ("Review & Send"), API `/invoice-review` (`GET /workbench?stage=to_review|reviewed`, `POST /bulk-review`, `POST /bulk-send`, max 25).
- NON_PO coding suggestion: vendor's primary `vendor_category_mapping` → vendor's last coded NON_PO invoice (active + category belongs to department); PO: from the PR.
- Readiness (re-checked on the server): validation passed on upload (bulk/email only - single uploads are reviewed on their own), no open issues, coding, approval policy matches; TDS for the reviewed stage.
- Bulk action per invoice: `apply_ocr_review` → `auto_determine_tds` (only if not determined) → `send_for_approval`; independent results SENT / REVIEWED / SKIPPED / FAILED. Sending needs `INVOICE_SEND_FOR_APPROVAL`, else review only.
- TDS is now determined automatically after every OCR review (single review route too; never overwrites DETERMINED / VERIFIED).
- Fix: review queue items carry `invoice_type` / department / category, so the review modal shows the NON_PO fields.

**Next - Step B (approved 2026-10-10):** PO auto-link + configurable 2/3-way match tolerances; matched PO invoices auto-reviewed and sent for approval; below a configured amount auto-approved (Finance still verifies before payment); switch and settings managed by `AP_AUTOMATION_MANAGE` (Finance Manager); touchless-rate KPI.

## 7. Decisions needed

Answered so far:
- **Database:** dev; additive migrations and `TST-` data allowed after review.
- **GSTINs:** use valid, approved identities and keep validation intact; strategy in 4.2.
- **Vendor agreements:** in scope; design in 3.1a.
- **Fix parsing and due dates first:** this is Phase 1.

**Still open (my recommendation in bold):**

| # | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | **Ready-for-Payment blocking rule.** Should an unresolved payment-term status (MISMATCH / REVIEW_REQUIRED) block "Mark Ready for Payment"? | (a) block until verified or overridden with remarks, (b) warn only | **(a) block**, with a verify/override action that requires remarks and is fully audited. Approval and TDS controls are unchanged. |
| **D2** | **GST test identities** | (1) Sandbox `key_test` credentials for dev, (2) Finance-approved GSTINs, (3) limit the E2E run to AWS and KEKA | **(1)**, and move dev off the production GST endpoint and live key. |
| **D3** | **MSME fields** on vendor: `msme_registered`, `udyam_number`, `msme_category` (MICRO/SMALL/MEDIUM), `msme_verified_at` | add now / later | **Add in Phase 1.** Apply the 45-day limit (15 days when nothing is agreed) to MICRO/SMALL only, as a **separate statutory date that caps the effective due date**, plus an "MSME at risk" flag (43B(h)). The limits are configuration, not code. |
| **D4** | **Shared TDS challan design (3.4):** `tds_challan` + allocations to invoices, and `tds_return_filing` per quarter, confirmed via the existing per-invoice deposit and filing services | approve / revise | **Approve.** Sum check ±₹1, evidence required, per-invoice screens unchanged. |
| **D5** | **Permissions.** New codes: `AP_MANAGEMENT_DASHBOARD_VIEW`, `AP_MANAGEMENT_REPORTS_VIEW`, `AP_MANAGEMENT_REPORTS_EXPORT`, `AP_PROCUREMENT_REPORTS_VIEW`, `VENDOR_AGREEMENT_VERIFY`, and `INVOICE_PAYMENT_TERM_VERIFY` (or reuse `PAYMENT_PROCESS`) | who creates them in UMS; which roles get them | You (or the UMS admin) create them in UMS. I add the backend checks and the frontend gating. **Use a new `INVOICE_PAYMENT_TERM_VERIFY`** so payment-term overrides are separable from payment processing. |
| **D6** | **Four-eyes control** on agreement verification and payment-term overrides | require a different user / allow the same user | **Different user** for agreement verification. For a term override, the same user is allowed but remarks are mandatory. |
| **D7** | **CPO dashboard scope** | (a) build the CPO view in Phase 6 with the CEO view, (b) defer, (c) include it as a tab in the Management view | **(c)**, a Procurement tab in Management, gated by `AP_PROCUREMENT_REPORTS_VIEW`. The DB has 0 POs today, so it will only become meaningful once procurement data exists. Please confirm CPO means Chief Procurement Officer. |
| **D8** | **TDS category mapping fixes** (finding 0.3-2) and the 4 new purchase categories | apply in Phase 7 seed / leave as-is | **Apply** (master data, reviewed migration). |
| **D9** | **TDS deduction at payment** | pre-fill the deduction date from the payment date / record it automatically | **Pre-fill only.** |
| **D10** | **Possible duplicates in bulk upload** | create and flag / hold out of the review queue | **Create and flag.** Exact duplicates are always rejected. |
| **D11** | **Bulk limits** | 25 files per batch, 10 MB each, no ZIP | **As stated.** |
| **D12** | **Exports** | Excel via openpyxl, PDF via PyMuPDF (no new dependencies) | **As stated.** |
| **D13** | **Currency** | per-currency totals, no FX conversion | **As stated.** |
| **D14** | **Git** | the backend repo is on `main`, the frontend on `accounts_payable` | Create `accounts_payable` (or the name you prefer) in the backend and commit per phase. Phase 0 files are **not committed yet**. |
| **D15** | **Company GSTIN** for `BUYER_GSTIN` in the dev config | provide | Needed for buyer validation in the E2E run. |
