# TDS Configuration — Backend API & Import Reference

Status: implemented, live-DB migrated, not yet committed. Response examples below were
captured from the running backend (not hand-written).

- Base path: `/apm/tds/config` (config) and `/apm/invoice/{invoice_id}/tds` (per-invoice)
- Auth: `Authorization: Bearer <UMS JWT>`; permissions come from the token's `permissions` claim
- No response envelope — endpoints return the object/array directly (same as the rest of AP)
- Decimals are JSON **strings** (`"1.0000"`), dates `"YYYY-MM-DD"`, timestamps ISO without timezone

---

## 1. Permissions

| Permission | Grants |
|---|---|
| `TDS_CONFIG_VIEW` | read rules, natures, deductors, metadata |
| `TDS_CONFIG_CREATE` | create rule / nature / deductor (+ read) |
| `TDS_CONFIG_EDIT` | update + activate/deactivate (+ read) |
| `TDS_CONFIG_DELETE` | delete (+ read) |
| `TDS_CONFIG_IMPORT` | Excel validate + import (+ read). An import that would **create** payment natures/deductors also needs `TDS_CONFIG_CREATE` (else 403, nothing written) |
| `INVOICE_TDS_VIEW` / `_DETERMINE` / `_EDIT` / `_VERIFY` | per-invoice TDS; also allowed to **read** `/payment-natures` (for the invoice "Correct Payment Nature" dropdown) |

Missing token → `401`; wrong permission → `403`. Permissions must be registered in UMS
(this repo only reads them).

---

## 2. Endpoints

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/metadata` | any TDS_CONFIG_* | dropdown values + import columns |
| GET | `/rules` | any TDS_CONFIG_* | query: `search`, `status` (ACTIVE/INACTIVE/ALL), `payment_nature` (code), `effective_date` (YYYY-MM-DD), `deductor_id` |
| GET | `/rules/{id}` | any TDS_CONFIG_* | |
| POST | `/rules` | CREATE | 201 |
| PUT | `/rules/{id}` | EDIT | full body; never changes status |
| PATCH | `/rules/{id}/status` | EDIT | `{"is_active": bool}` |
| DELETE | `/rules/{id}` | DELETE | 409 if any invoice TDS references it → deactivate instead |
| GET | `/payment-natures` | any TDS_CONFIG_* or INVOICE_TDS_* | query: `search`, `is_active` |
| GET | `/payment-natures/{id}` | same | |
| POST | `/payment-natures` | CREATE | 201 |
| PUT | `/payment-natures/{id}` | EDIT | partial; code immutable once in use (409) |
| PATCH | `/payment-natures/{id}/status` | EDIT | |
| DELETE | `/payment-natures/{id}` | DELETE | 409 if used by rules / category mappings / invoices |
| GET | `/deductors`, `/deductors/{id}` | any TDS_CONFIG_* | query: `search`, `is_active` |
| POST / PUT / PATCH status / DELETE | `/deductors[...]` | as above | DELETE 409 if used by a rule |
| POST | `/import/validate` | IMPORT | multipart `file`; **never writes**; always 200 |
| POST | `/import` | IMPORT (+ CREATE if the file creates masters) | multipart `file`; re-validates; all-or-nothing |

Per-invoice (unchanged paths, extended responses):

| Method | Path | Permission | Body |
|---|---|---|---|
| POST | `/apm/invoice/{id}/tds/determine` | INVOICE_TDS_DETERMINE | `{"payment_nature_code": "RENT"}` (optional — omit to use purchase-category default) |
| GET | `/apm/invoice/{id}/tds` | any INVOICE_TDS_* or INVOICE_VIEW | |
| PUT | `/apm/invoice/{id}/tds` | INVOICE_TDS_EDIT | `{"payment_nature_code": "..."}` (required) |
| POST | `/apm/invoice/{id}/tds/verify` | INVOICE_TDS_VERIFY | `{"remarks": "..."}` (optional) |

---

## 3. Response shapes

### GET /metadata
```json
{
  "threshold_periods": [
    {"value": "PER_TRANSACTION", "label": "Single Transaction"},
    {"value": "AGGREGATE_PERIOD", "label": "Financial Year (Aggregate)"}
  ],
  "rate_condition_types": [
    {"condition_type": "ENTITY_TYPE", "operators": ["EQUALS","NOT_EQUALS","IN","NOT_IN"],
     "values": ["AOP","ARTIFICIAL_JURIDICAL_PERSON","BOI","COMPANY","FIRM","GOVERNMENT","HUF","INDIVIDUAL","LOCAL_AUTHORITY","TRUST"]},
    {"condition_type": "RESIDENCY_TYPE", "operators": ["EQUALS","NOT_EQUALS","IN","NOT_IN"],
     "values": ["NON_RESIDENT","RESIDENT"]}
  ],
  "rate_condition_example": "ENTITY_TYPE IN INDIVIDUAL,HUF",
  "import_columns": ["Code","Old Section","New Section","Nature of Payment","Deductor","Rate",
                     "Threshold Amount","Threshold Period","Rate Condition","Effective From","Effective To"],
  "import_file_types": [".xlsx", ".csv"]
}
```

### Rule (GET /rules → array of these; GET/POST/PUT/PATCH → one)
```json
{
  "id": 6, "code": "TDS_194C", "rule_name": "TDS - Contractor Payments",
  "description": "TDS applicable on payments to contractors/sub-contractors under Section 194C",
  "old_section": "194C", "new_section": null,
  "legal_reference": "Section 194C, Income-tax Act (FY2026-27)",
  "payment_nature": {"id": 1, "code": "CONTRACTOR", "name": "Contractor Payments", "is_active": true},
  "deductor": null,
  "rate_percent": "1.0000", "calculation_type": "PERCENTAGE", "current_rate_rule_id": 6,
  "threshold_amount": "100000.00", "threshold_period": "AGGREGATE_PERIOD",
  "threshold_period_label": "Financial Year (Aggregate)",
  "rate_condition": null,
  "conditions": [
    {"id": 6, "condition_type": "PAYMENT_NATURE", "operator": "EQUALS", "condition_value": "CONTRACTOR",
     "logical_group": 1, "sequence_no": 1}
  ],
  "rates": [
    {"id": 6, "rate_percent": "1.0000", "calculation_type": "PERCENTAGE", "fixed_amount": null,
     "effective_from": "2026-04-01", "effective_to": null, "is_active": true}
  ],
  "effective_from": "2026-04-01", "effective_to": null, "priority": 100,
  "is_active": true, "status": "ACTIVE",
  "created_by": null, "created_at": "2026-08-21T14:29:27.179090",
  "updated_by": null, "updated_at": "2026-09-30T07:12:44.875320"
}
```
- `deductor` (when set) has the same shape as `payment_nature`.
- `rate_condition` is `null` or canonical text, e.g. `"ENTITY_TYPE IN HUF,INDIVIDUAL"` (values sorted — may differ in order from what was sent).
- `rates` is history: editing the rate of a rule an invoice already used retires the old row (`is_active:false`) and adds a new one.

### Payment nature / Deductor
```json
{"id": 5, "code": "COMMISSION", "name": "Commission or Brokerage",
 "description": "Payments towards commission, brokerage or similar intermediary services",
 "is_active": true, "status": "ACTIVE",
 "created_at": "2026-09-23T07:04:38.767154", "updated_at": "2026-09-23T07:04:38.767154"}
```

### DELETE (any)
```json
{"id": 6, "message": "TDS rule deleted successfully"}
```

---

## 4. Request bodies

### POST / PUT /rules
```json
{
  "code": "1023",
  "old_section": "194C",
  "new_section": "393(1) Table 6(i).D(a)",
  "payment_nature_id": 1,              // or "payment_nature_code": "CONTRACTOR"
  "deductor_id": 3,                    // or "deductor_code": "SPECIFIED_PERSON"; optional
  "rate": "1",                         // key is "rate" (NOT "rate_percent"); 0–100, max 4 dp
  "threshold_amount": "100000",        // optional; >= 0, max 2 dp
  "threshold_period": "AGGREGATE_PERIOD", // or the label; required iff threshold_amount set
  "rate_condition": "ENTITY_TYPE IN INDIVIDUAL,HUF", // optional; null/"" = applies to all vendors
  "effective_from": "2026-04-01",
  "effective_to": null,                // optional; must be >= effective_from
  "rule_name": null, "description": null, "legal_reference": null, "priority": null  // optional
}
```
- `code`: letters, digits, `_ - . /`; stored upper-case; must be unique across **all** tax rules.
- `old_section` ≤ 20 chars (upper-cased); `new_section` ≤ 100 chars (casing kept).
- `rule_name` defaults to `"TDS <old_section> - <nature name> (<rate condition>)"` on create; never auto-changed on update.

### POST /payment-natures, /deductors
```json
{"code": "ROYALTY", "name": "Royalty", "description": "optional", "is_active": true}
```
PUT takes the same fields, all optional. PATCH `/status`: `{"is_active": false}`.

### Rate Condition grammar
`<TYPE> <OPERATOR> <VALUE[,VALUE...]>` joined by ` AND `.
Types/values: see `/metadata`. `EQUALS`/`NOT_EQUALS` take one value; `IN`/`NOT_IN` a list.
Only vendor facts the engine can evaluate are allowed (entity type from PAN, residency).
Variants that depend on *what* is paid (plant vs land rent, royalty vs fees, insurance vs other
commission) are modelled as **separate payment natures**, not rate conditions.

---

## 5. Errors

| Status | `detail` | When |
|---|---|---|
| 401 | `{"success": false, "message": "..."}` | no/invalid token (JWT middleware) |
| 403 | `"You do not have permission to access this resource"` | missing permission |
| 404 | string | id not found |
| 409 | string, e.g. `"TDS rule with code 'TDS_194C' already exists"` | duplicate code, conflicting variant, delete/recode of in-use record |
| 422 | **string**, e.g. `"Rate: Rate must be between 0 and 100"` (multiple joined with `; `) | business validation |
| 422 | **array** (FastAPI), e.g. `[{"type":"missing","loc":["body","rate"],"msg":"Field required",...}]` | malformed body / wrong types |
| 422 | **object** = full import report | `/import` with row errors |

---

## 6. Excel import

### Template (sheet 1, header row, exact names, this order)

| Code | Old Section | New Section | Nature of Payment | Deductor | Rate | Threshold Amount | Threshold Period | Rate Condition | Effective From | Effective To |
|---|---|---|---|---|---|---|---|---|---|---|
| 1023 | 194C | 393(1) Table 6(i).D(a) | CONTRACTOR | SPECIFIED_PERSON | 1 | 100000 | Financial Year (Aggregate) | ENTITY_TYPE IN INDIVIDUAL,HUF | 2026-04-01 | |
| 1024 | 194C | 393(1) Table 6(i).D(b) | CONTRACTOR | SPECIFIED_PERSON | 2 | 100000 | Financial Year (Aggregate) | ENTITY_TYPE NOT_IN INDIVIDUAL,HUF | 2026-04-01 | |
| 1008 | 194I | 393(1) Table 2(ii).D(a) | RENT_PLANT_MACHINERY | SPECIFIED_PERSON | 2 | 50000 | Single Transaction | | 2026-04-01 | |
| 1028 | 194J | 393(1) Table 6(iii).D(b) | DIRECTOR_REMUNERATION | COMPANY | 10 | | | | 2026-04-01 | |

Full populated file (15 rules under the Income-tax Act 2025, plus "Create First" and "Notes"
sheets): `test-documents/TDS_Rules_Import_IT_Act_2025.xlsx`.

Cell rules:
- Required: Code, Old Section, Nature of Payment, Rate, Effective From.
- Nature of Payment / Deductor: an existing **code or name** (case- and whitespace-insensitive), or a
  new name, which the import **creates**: code generated by the backend (`"Director Remuneration"`
  -> `DIRECTOR_REMUNERATION`, `"Specified Person*"` -> `SPECIFIED_PERSON`), description null, active.
  Errors instead of creating: the value matches an **inactive** record ("exists but is inactive.
  Activate it before importing." — never reactivated); it matches several records, or its generated
  code belongs to a different record (ambiguous — no fuzzy matching); two spellings in one file
  generate the same code; no letters/digits; generated code > 50 chars.
- Rate: `2`, `2%`, `0.1`. Threshold Amount: `50000`, `50,000`, blank = no threshold.
- Threshold Period: `Single Transaction` / `Financial Year (Aggregate)` (or the codes).
- Dates: Excel date cells, `YYYY-MM-DD`, `DD-MM-YYYY`, `DD/MM/YYYY`, `DD.MM.YYYY`, `DD-Mon-YYYY`.
- `.xlsx` or UTF-8 `.csv`; max 5 MB / 5000 rows; blank rows skipped; only sheet 1 is read.

### Behaviour
- Matching key = **Code**. Row outcome: `NEW` (code not found), `UPDATED` (found, a field differs),
  `UNCHANGED` (found, identical — re-uploading the same file is a no-op), `ERROR`.
- Updates keep the rule's status and name (sheet has no such columns).
- Conflict check: two active variants with the same Old Section + Nature + Deductor + Rate
  Condition and overlapping dates are rejected (within the file and against existing rules).
- Masters: `/import/validate` lists what would be created and writes nothing; `/import` creates them
  first, then the rules, in ONE transaction (any row/DB error rolls back masters too).
- `/import/validate`: always 200, check `valid`. `/import`: 200 on success; 422 with the report
  as `detail` if any row errors — **nothing written**. File-level problems (type, header, empty):
  422 with string `detail` from both.

### Report
```json
{
  "valid": false, "imported": false,
  "total_rows": 1, "valid_rows": 0, "error_rows": 1,
  "new_rows": 0, "updated_rows": 0, "unchanged_rows": 0,
  "errors": [{"row": 2, "field": "Rate", "message": "Rate must be numeric"}],
  "rows": [{"row": 2, "code": "X2", "status": "ERROR", "existing_rule_id": null, "changed_fields": []}],
  "import_batch_id": null,
  "new_payment_natures": [{"name": "Director Remuneration", "code": "DIRECTOR_REMUNERATION", "row_numbers": [2]}],
  "new_deductors": [{"name": "Specified Person*", "code": "SPECIFIED_PERSON", "row_numbers": [3, 4]}],
  "new_payment_nature_count": 1,
  "new_deductor_count": 1
}
```
`new_*`: on validate = would be created; on a successful import = were created; existing masters
matched by name/code never appear. 403 (`{"detail": "This file would create 1 payment nature(s) and
1 deductor(s) - TDS_CONFIG_CREATE permission is required to import it"}`) when a valid file needs
new masters and the caller lacks TDS_CONFIG_CREATE.

`row` = spreadsheet row number (header = row 1). `field` = column name. `changed_fields`
(UPDATED rows) = column names that changed. `import_batch_id` set on successful import.

---

## 7. Per-invoice TDS response (GET/POST/PUT /apm/invoice/{id}/tds...)

Existing fields plus: `threshold_type`, `residency_type`, `rule_snapshot`, and
`tds_rule.old_section` / `tds_rule.new_section`. `rule_snapshot` is `null` for invoices
determined before this release, otherwise:
```json
{
  "tax_rule_id": 11, "rule_code": "1024", "rule_name": "...", "old_section": "194C",
  "new_section": "393(1) Table 6(i).D(b)", "legal_reference": null,
  "deductor": {"id": 3, "code": "SPECIFIED_PERSON", "name": "Specified Person"},
  "rate_condition": "ENTITY_TYPE NOT_IN HUF,INDIVIDUAL",
  "rule_effective_from": "2026-04-01", "rule_effective_to": null,
  "threshold_amount": "100000.00", "threshold_type": "AGGREGATE_PERIOD",
  "tax_rate_rule_id": 12, "configured_rate_percent": "2.0000", "calculation_type": "PERCENTAGE",
  "fixed_amount": null, "rate_effective_from": "2026-04-01", "rate_effective_to": null,
  "rate_basis": "STANDARD",   // STANDARD | LOWER_DEDUCTION_CERTIFICATE | PAN_NOT_AVAILABLE_206AA | FIXED
  "variants_considered": ["1023", "1024"],
  "vendor_facts": {"entity_type": "COMPANY", "residency_type": "RESIDENT", "pan_status": "VALID",
                   "tds_exemption_flag": false, "lower_deduction_available": false},
  "lower_deduction_certificate": {"certificate_number": "...", "certificate_rate": "1.5", "valid_from": "...", "valid_to": "..."}  // only when applied
}
```

Workflow rules enforced server-side (422 with a message):
- Send for approval requires a complete determination (determined, has a payment nature, and
  if a rule matched it has a rate). "No rule for this nature" (e.g. INTEREST) counts as complete.
- Determine / correct payment nature is refused once the invoice is PENDING_APPROVAL or later.
- Mark ready for payment requires TDS `VERIFIED`. Verify refuses incomplete determinations.
- A VERIFIED snapshot is never recalculated.

---

## 8. Implementation summary

Data model (reuses the generic tax engine — no TDS-specific rule tables):
- `ap.tax_rule` (rule_category `TDS_RATE`, tax_type TDS) = one rule **variant**; new columns
  `old_section`, `new_section`, `tds_deductor_id`.
- `ap.tax_rule_condition` = `PAYMENT_NATURE EQUALS <code>` + rate-condition rows (AND within a group).
- `ap.tax_rate_rule` = effective-dated rate.
- New `ap.tds_deductor`; existing `ap.tds_payment_nature`; `ap.invoice_tds` gained
  `threshold_type`, `residency_type`, `rule_snapshot`.
- Determination: candidates = active in-effect rules for the payment nature on the invoice
  date → rate conditions evaluated against the vendor TDS profile → lowest priority, then most
  specific, then lowest id wins.

Backend files:
- Migrations: `Backend/Data_Access_Layer/migration_tds_configuration.sql` (+ `_rollback.sql`),
  `migration_tds_new_section_length.sql`
- `Data_Access_Layer/dao/tds_config_dao.py`, `dao/tds_dao.py`, `models/tds.py`, `models/master.py`
- `Business_Layer/services/tds_config_service.py`, `tds_config_import_service.py`,
  `tds_determination_service.py`; `Business_Layer/utils/tds_rate_condition.py`
- Gates: `invoice_approval_service.py` (send for approval), `payment_service.py` (ready for payment)
- `API_Layer/routes/tds_config_route.py`, `API_Layer/interface/tds_config_interface.py`, `tds_interface.py`
- Tests: `test_tds_config_service_db.py`, `test_tds_config_route_authorization.py`,
  `test_tds_rate_condition.py`, `test_tds_determination_variants.py`

Known limitations:
- One threshold per rule (no "per contract OR per year"); periods are single transaction or
  financial-year aggregate only (no monthly).
- Deductor is descriptive, not a calculation input.
- The import never edits an existing payment nature/deductor (no rename, description or reactivation).
