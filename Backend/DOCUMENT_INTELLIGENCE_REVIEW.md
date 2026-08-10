# Document Intelligence Layer — Review & Fixes (2026-08-10)

## Summary

The Document Intelligence layer (`Business_Layer/utils/extraction/*`,
`field_extractors.py`, `validators.py`, `confidence.py`,
`vendor_matcher.py`) was reviewed against the invoice-field-mismapping
problem statement (Invoice Number↔PO Number, Vendor↔Buyer, GSTIN↔Buyer
GSTIN, Invoice Date↔Due Date, Total↔Tax).

**Finding: this is not a naive label-nearest-value extractor.** It
already implements a full anchor + geometry + candidate-ranking
engine, and the exact confusions in the problem statement are each
handled by dedicated, deliberate logic. No redesign was needed or
performed — the OCR pipeline, `DocumentResult`, `ExtractedInvoice`,
API routes, and overall architecture are unchanged, per scope. Four
concrete, real bugs/gaps were found and fixed within the existing
design; everything else was left as-is.

## Pipeline stages already implemented

| Required stage | Implemented in | Notes |
|---|---|---|
| OCR Normalization / Reading Order Reconstruction | `extraction/geometry.py: cluster_words_into_lines` | Vertical-band clustering, mirrors `ocr_provider.words_to_text` |
| Layout Analysis / Region Detection | `geometry.py: looks_like_table_row/header`, `nearest_section` | Table-row detection, section boundary scanning (Buyer/Ship To/Seller) |
| Geometry Analysis | `geometry.py: extract_right_of_anchor/below/nearest_words` | Same-line / below / nearest-neighbor relations |
| Anchor Detection / Label Normalization | `extraction/anchors.py` | One synonym list per field, regex-based, negative lookarounds to avoid cross-field bleed (e.g. bare "Date" excludes PO/dispatch/due/order/ship date) |
| Candidate Generation | Each `extraction/*.py` extractor's `collect_candidates` | Never stops at first match — collects every plausible candidate first |
| Entity Classification (Buyer vs Seller vs Ship-To) | `geometry.py: nearest_section`, `base.py: context_polarity` | Upward section scan that stops at table boundaries; symmetric hard filter in GSTIN extractors |
| Candidate Ranking | `extraction/base.py: score_candidate/rank_candidates`, `extraction/scoring.py` | One shared point system for every field |
| Financial Summary / Tax Parsing | `extraction/amounts.py` | Bottom-half-of-page bonus + table-row/multi-tax-label penalties to separate summary lines from per-item tax cells |
| Semantic / Business Rule / Arithmetic Validation | `validators.py` | GSTIN format, date ordering, tax-regime exclusivity, total reconciliation |
| Field Confidence Calculation | `extraction/scoring.py: confidence_from_score`, `confidence.py` | Per-candidate score → 0–98 confidence, then weighted composite across OCR/extraction/validation/vendor |
| Field Metadata Generation | `FieldExtractionMeta` (value, confidence, matched_anchor, page, method) | Populated by every extractor via `BaseFieldExtractor.extract` |

**Not implemented, and intentionally out of scope for this pass:**
Line Item Parsing and per-line-item arithmetic cross-validation
(summing table rows to corroborate `subtotal`). `required_output` has
no line-item field, so this would be new surface area, not a fix —
worth a separate task if line-item-level accuracy checks are wanted.

## Per-field strategy (as implemented)

| Field | Extractor | Disambiguation strategy |
|---|---|---|
| `invoice_number` / `po_number` | `identifiers.py` | Separate anchor lists, no whole-document fallback (a missing anchor yields `None`, never a guessed number); date/GSTIN-shaped tokens and label fragments ("Date", "No") are skipped mid-line so a neighboring field's label sharing the anchor's line can't be picked up |
| `invoice_date` / `due_date` | `dates.py` | Separate anchor lists; `due_date` has no fallback to `invoice_date` |
| `gstin` (vendor) / `buyer_gstin` | `gstin.py` | Every GSTIN-shaped token in the doc is a candidate; buyer/ship-to context is a **hard filter**, not just a penalty — a GSTIN confirmed near "Bill To" can never win as the vendor's own, and vice versa |
| `vendor_name` | `vendor.py` | Merges labelled candidates ("Vendor:", "Seller:", "From:") with a page-1 heuristic scorer (company suffix, top-of-page position, near the vendor's own GSTIN, title/upper case) against a blocklist (boilerplate labels, addresses, bank details, contact lines) |
| `subtotal` / `cgst` / `sgst` / `igst` / `cess` / `total` | `amounts.py` | Bottom-half-of-page bonus and table-row penalty keep the tax-summary line from losing to a per-item tax column; `total`'s anchor excludes "Subtotal" via negative lookbehind |
| `payment_terms` | `payment_terms.py` | Structured term pattern (Net N, COD, Immediate, ...) preferred; raw label text only trusted from a specific anchor (see Fix 2 below) |
| `currency` | `currency.py` | Symbol/code proximity to the grand-total line wins over a stray line-item figure; GSTIN presence now provides a safe last-resort INR default (Fix 4) |

## Bugs fixed in this pass

1. **`validators.py` — `cess` omitted from total reconciliation.**
   `validate_totals` checked `total ≈ subtotal + cgst + sgst + igst`,
   silently ignoring `cess`. Any invoice with cess raised a false
   "Total does not match subtotal + taxes" error. Fixed: `cess` added
   to the signature and the reconciliation sum.

2. **`extraction/payment_terms.py` — bare "Terms" anchor produced
   garbage.** `PAYMENT_TERMS_ANCHORS` includes `\bterms\b` to catch
   labels like "Terms: Net 30", but when no structured term matched,
   the extractor fell back to raw right-of-anchor text for *any*
   anchor hit — including a "Terms and Conditions" section heading,
   yielding values like `"And Conditions"`. Fixed: the raw-text
   fallback is now gated on the anchor being a specific one
   (`payment terms` / `credit days`); the bare `terms` anchor only
   ever contributes a candidate when it matches the structured term
   pattern.

3. **`confidence.py` — optional-field absence penalized like a miss.**
   `_extraction_confidence` averaged every field's confidence
   equally, so a correctly-empty optional field (`due_date`,
   `buyer_gstin`, `po_number`, `cess`, `payment_terms`, `currency` —
   all legitimately absent on plenty of valid invoices) contributed a
   0.0 alongside genuinely required fields, dragging down
   `overall_confidence` for a perfectly correct extraction. Fixed:
   these fields are now excluded from the average when the extractor
   found nothing for them; a real miss on a required field still
   lowers confidence as before.

4. **`extraction/currency.py` — no default for GST invoices.**
   Invoices frequently don't print an explicit ₹/INR symbol or code
   anywhere. Since a GSTIN can only exist on an Indian-domestic
   invoice, its presence is now a safe last-resort signal: a fallback
   `INR` candidate is added, scored just above the minimum accept
   threshold so it only wins when no explicit currency token exists
   anywhere in the document (verified: an explicit `USD`/`₹`/etc.
   token still always outranks it).

All four fixes were verified with targeted scenarios (synthetic
`DocumentResult`/`Page` fixtures) exercising both the fix and a
regression case for the previously-working behavior; see the
project's test setup for where to place these as permanent unit tests
(none currently exist for this layer — `Backend/requirements.txt` has
no `pytest` test directory yet).

## Suggested next steps (not implemented, for prioritization)

- Add a `tests/` suite under `Business_Layer/utils/extraction/` — this
  layer currently has zero automated tests, so regressions in anchor
  wording or scoring constants are only caught in production.
- Line-item table parsing + subtotal cross-check, if line-item-level
  data becomes a requirement.
- `vendor_matcher.py` is an explicit placeholder (mock directory) —
  wire it to `vendor_service`/`vendor_dao` when vendor master
  persistence is ready (already called out in that file's own
  docstring; not part of this pass's scope).

## Round 2 — tax semantics, cross-field reconciliation, anchor coverage (2026-08-10)

A deeper pass targeted business-field-assignment correctness rather
than anchor/geometry mechanics. Every item below was reproduced against
the actual code before fixing, and locked in by the new regression
suite at `Backend/tests/` (20 tests, `pytest Backend/tests/`).

**Bugs fixed:**

1. **Tax rate returned as tax amount.** `CGST 9% Rs.225.00` returned
   `9` (the rate), not `225.00`. `amounts.py` now uses
   `normalizers.iter_amount_matches`, which skips any digit run
   immediately followed by `%`.
2. **`AMOUNT_PATTERN` couldn't match a value glued to a currency
   prefix** (`Rs.225.00` with no space) — its lookbehind treated a
   preceding `.` the same as a preceding digit. Narrowed to `(?<!\d)`;
   blast radius is contained because `AMOUNT_PATTERN` is only ever
   scanned right of a financial anchor (Subtotal/CGST/SGST/IGST/CESS/
   Total family) in `amounts.py`.
3. **"Total GST" / "Line Total" / "Tax Total" / "Total Discount"
   beat the real Grand Total.** The generic bare-`total` anchor now
   excludes all of these via negative lookaround; explicit anchors
   ("Grand Total", "Invoice Total", "Total Payable", "Gross Worth", ...)
   also get a scoring bonus over the weak generic pattern.
4. **No multi-tax-slab aggregation.** An invoice printing two CGST
   summary lines (e.g. 14% and 2.5% slabs) now sums them instead of
   picking one winner. Scoped to CGST/SGST/IGST/CESS only, restricted
   to non-table, bottom-of-page occurrences to avoid summing in a
   stray per-item tax cell, and backward-compatible with the common
   single-slab case (verified by test).
5. **`buyer_gstin` could pick the Ship-To/consignee's GSTIN over the
   actual buyer's** — both contributed the same scoring bonus. A
   Ship-To association is now a weaker (but still valid) signal than
   an actual Buyer/Bill-To heading, found via the new regression test
   for this exact scenario.
6. **No total-vs-taxes arithmetic reconciliation during ranking.**
   Added a bounded post-extraction step (`registry.py:_reconcile_total`):
   if the independently-chosen `total` doesn't reconcile with
   `subtotal + cgst + sgst + igst + cess`, and `GrandTotalExtractor`
   has a ranked alternate that does, the alternate is used instead.
   Never fabricates a value — if nothing reconciles, the original
   pick is kept and `validators.py` still flags the mismatch as before.
7. **Anchor coverage gaps**: `BUYER_MARKERS` was missing
   "Customer"/"Client"/"Issued To"; `VENDOR_LINE_BLOCKLIST` was missing
   "Issued To"/"Billing & Shipping Address"; `SUBTOTAL_ANCHORS` was
   missing "Net Value"/"Net Charges"/"Amount Before Tax"; payment-terms
   free-text sentences ("Payment is due within 7 days from the date of
   invoice") had no anchor at all.

**Explicitly not implemented (flagged, not silently skipped):**

- **Multi-line vendor-name reconstruction.** A company name split
  across two lines (e.g. "Manan Trading" / "Private Limited") is still
  scored as two independent line candidates, not merged into one. This
  is real remaining work, deliberately deferred — it needs a distinct
  "does this line look like a continuation of the previous one"
  heuristic that doesn't yet exist, and rushing it risked merging
  unrelated adjacent lines (e.g. an address line) into the vendor name,
  which is a worse failure mode than the current single-line result.
- **Round-off/discount/freight as first-class reconciliation inputs.**
  `ExtractedInvoice`/`FieldExtractionMeta` are frozen per scope, so
  there's no schema slot to carry them; an invoice with these
  adjustments still extracts every field correctly but may report a
  `validators.py` total-mismatch (see
  `test_discount_and_round_off_extraction_still_correct_though_unreconciled`).
  Solving this properly needs either a schema change (out of scope) or
  a heuristic adjustment-line detector living entirely inside
  validation — worth a dedicated follow-up.
- **Full `FOUND/CONFIRMED_ABSENT/UNCERTAIN` field-completeness state
  machine.** Same schema constraint — `FieldExtractionMeta` has no slot
  for a tri-state completeness flag. The closest existing equivalent
  (null vs. non-null value, plus `validators.py` errors for anything
  that fails a business rule) was kept rather than bolted on.

**New files:**

- `Backend/tests/conftest.py` — puts the project root on `sys.path` so
  `Backend.*` absolute imports resolve under pytest.
- `Backend/tests/invoice_builder.py` — synthetic `DocumentResult`
  builder for tests (plain text lines → word/line geometry).
- `Backend/tests/test_document_intelligence_regression.py` — 20 tests
  covering CGST+SGST vs IGST regimes, multi-slab tax aggregation,
  cess-in-total, Total-GST/Line-Total traps, multi-GSTIN role
  separation (including the ship-to-vs-buyer case), multi-date role
  separation, payment-terms (labelled, free-text, and false-positive
  rejection), PO-vs-POS, vendor-name blocklist headings, currency
  fallback/override, arithmetic reconciliation, and the discount/
  round-off known-limitation case.
