# Approval Policy & CDC Work — Session Reference

This document summarizes the work done in this session for the Paves Intranet Accounts Payable (APM) backend. It covers CDC/UMS sync fixes, a full model/schema audit, cleanup, and the new **Configurable Invoice Approval Workflow** (Phase 1, backend only).

---

## 1. CDC Consumer (Kafka/Debezium) Fixes

The CDC consumer syncs UMS (MySQL) and EOS user/department/role data into AP's Postgres tables (`ap.ums_user_cache`, `ap.ums_role_cache`, `ap.eos_employee_cache`, `ap.eos_department_cache`, `ap.approver_directory`, `ap.approver_directory_role`). These caches are the **only** source of approver identity for the approval engine — UMS/EOS are never queried live.

Bugs found and fixed in `Backend/Business_Layer/services/cdc_sync_service.py`:
- **Transaction-scoping bug**: added an early `db.commit()` after `upsert_ums_user_cache` so downstream role/department upserts in the same event weren't rolled back together on unrelated failures.
- **Malformed UUID crash**: `_resolve_employee_uuid_for_user` now falls back to `user_uuid` via try/except instead of crashing on a bad EOS employee UUID.
- **Swallowed delete bug**: `process_user_role_event`'s delete branch was silently returning on a missing dependency; now raises `MissingDependencyError`.
- **System accounts**: added `SYSTEM_USER_IDS = frozenset({1, 2})` — `user_id` 1 and 2 are system accounts, not real employees, and are special-cased in `process_user_event` rather than treated as sync failures.

Data reconciliation: backfilled missing EOS employee records for 8 real users using real UMS/EOS dumps the user provided, and resynced stale `approver_directory` rows.

---

## 2. Full Model vs. Live-DB Audit

All SQLAlchemy models were audited against the actual Postgres schema (after the user manually cleaned up tables in pgAdmin) and corrected:
- `Backend/Data_Access_Layer/models/cdc.py` — `ApproverDirectory`/`ApproverDirectoryRole` gained missing `UniqueConstraint`s, `department_uuid` made nullable, `role_code` widened to `String(50)`.
- Other model files corrected for column/type/relationship mismatches found during the audit.

### Database folder cleanup
- Replaced the old `Database/migrations/` folder with a single `pg_dump`-generated `Database/schema.sql` plus a dated data snapshot (`Database/data_2026-09-15.sql`).
- Rewrote `Database/Database_README.md` to explain the new convention: no Alembic — schema changes are hand-written idempotent `DO $$...$$` SQL files, applied manually; brand-new tables are created automatically via `Base.metadata.create_all()` at app startup.
- Note: `pg_dump` on newer `psql` emits `\restrict`/`\unrestrict` lines that break older `psql`/pgAdmin — these must be stripped from generated files.

### CDC consumer folder cleanup
- Removed obsolete test/script files under `Backend/cdc_consumer/`.
- Added `Backend/cdc_consumer/README.md` documenting the pipeline (files used, what each does, how to run the consumer).

### Docker removal
- Removed `Dockerfile`, `docker-compose.yml`, `docker-compose.local-kafka.yml`, `.dockerignore` — backend and consumer are run directly via CLI in separate terminals per the user's workflow.

---

## 3. Configurable Invoice Approval Workflow (Phase 1 — Backend)

### Why
The previous approval implementation was broken: `approve_invoice()` was effectively hardcoded, only `reject_invoice()` wrote a real decision, there was no permission gate, and it was single-step only. The goal: a policy-driven, multi-level approval engine backed by real UMS/EOS-synced approver identity — **not** hardcoded to application roles. UMS permissions gate *actions* (who can call which endpoint); the resolved policy snapshot gates *who* can approve a specific invoice.

### Key architectural decision: `DEPARTMENT_APPROVER`
Per explicit instruction, this was **investigated, not assumed**. `ap.department` (bigint PK, used by PR/invoice/purchase_category) and the EOS-sourced department in `ap.approver_directory` (UUID) were confirmed to have **zero overlap** — a real gap. No reusable UMS/XMS mechanism existed for "who approves for department X," so a new AP-owned mapping table was designed instead of inventing a UMS role:

```python
class DepartmentApprover(Base):
    __tablename__ = 'department_approver'
    # department_id (FK -> ap.department.id), user_uuid, is_active
    # UNIQUE(department_id, user_uuid)
```

An earlier bridging approach (`ap.department.eos_department_uuid`) was tried first, then reverted in favor of this cleaner AP-owned mapping once confirmed the column would be all-NULL/unused.

### Schema (schema `ap`)
- **`approval_policy`** — admin-defined template: `name` (unique), `department_id` (nullable), `purchase_category_id` (nullable), `min_amount`/`max_amount`, `is_active`, **`is_default`** (see §5 below).
- **`approval_policy_level`** — ordered levels per policy: `level_number`, `approver_type` (`DEPARTMENT_APPROVER` | `ROLE` | `USER`), `role_code`/`user_uuid` as applicable, `approval_rule` (`ANY_ONE` | `ALL`).
- **`invoice_approval`** — one runtime instance per invoice send-for-approval: `status` (`PENDING`|`IN_PROGRESS`|`APPROVED`|`REJECTED`|`CANCELLED`), links to the policy used.
- **`invoice_approval_step`** — one row per level, frozen at creation time.
- **`invoice_approval_step_approver`** — one row per resolved approver per step, frozen at creation time.
- **`department_approver`** — AP-owned department→approver mapping (see above).

**Critical design property**: `invoice_approval`/`invoice_approval_step`/`invoice_approval_step_approver` are a **frozen runtime snapshot** — created once at `send_for_approval` time and never re-derived from the policy, UMS, or EOS afterward. Later changes to a policy or to someone's UMS role/CDC record do not retroactively change who can approve an invoice already in flight.

### Matching logic
`ApprovalPolicyService.match_policy(department_id, purchase_category_id, amount)`:
1. Look up active policies scoped to the exact `department_id` + `purchase_category_id`.
2. Filter by amount range containment.
3. If more than one matches, raise (ambiguity is rejected **at policy-write time**, not resolved by priority at match time — `create_policy`/`update_policy`/`set_policy_status` validate no active overlapping scoped policy exists).
4. If none match, fall back to the single active **default** policy (see §5).
5. If nothing at all applies, raise `"No applicable approval policy found for this invoice."`

### Quorum rules
- **`ANY_ONE`**: the first approval completes the level; other pending approvers on that step are marked `SKIPPED`.
- **`ALL`**: every assigned approver on the step must approve before the level completes.
- **Reject**: unconditional and immediate under either rule — it kills the whole approval run regardless of quorum state.

### Security
- The acting user is always resolved server-side from the JWT (`user_id`/`sub` → `ap.ums_user_cache` → `user_uuid`) — **never** trusted from the request body.
- Approve/reject requires **both**: the UMS permission for the action, **and** being a resolved, currently-eligible approver on the active step.

### New/changed backend files
- `Backend/Data_Access_Layer/models/approval.py` — `ApprovalPolicy`, `ApprovalPolicyLevel`, `InvoiceApproval`, `InvoiceApprovalStep`, `InvoiceApprovalStepApprover`, `DepartmentApprover`.
- `Backend/Data_Access_Layer/models/purchase.py` — `Department` (bridging column added then removed after confirmation it was unused).
- `Backend/Data_Access_Layer/models/invoice.py` — `Invoice.department_id`/`purchase_category_id` + relationships.
- DAOs: `approval_policy_dao.py`, `approver_directory_dao.py` (new, read-only CDC-directory lookups), `department_approver_dao.py` (new), `invoice_approval_dao.py` (rewritten).
- Services: `approval_policy_service.py`, `approver_resolver_service.py`, `department_approver_service.py` (new), `invoice_approval_service.py` (rewritten), `invoice_process_service.py` (extended — see §4).
- Interfaces: `approval_policy_interface.py`, `invoice_process_interface.py` (extended).
- Routes: `approval_policy_route.py` — policy CRUD, approver/role lookups, department-approver mapping CRUD, all gated on `APPROVAL_POLICY_MANAGE`.
- Migrations (hand-written, applied live): `migration_approval_workflow.sql`, `migration_approval_policy_default.sql`.

### UMS Permissions (recommended, grounded in real UMS RBAC inspection)
Real UMS chain: `User → user_role → Role → role_permission_group → Permission_Group → permission_group_mapping → Permissions`. `permission_code` is free-text (no enum); groups/roles are created dynamically via UMS admin API — nothing pre-existed for AP's new codes, so these were proposed fresh after confirming no collision:
- `APPROVAL_POLICY_MANAGE` — create/edit/activate approval policies and department-approver mappings (admin only).
- `INVOICE_SEND_FOR_APPROVAL` — trigger `send_for_approval` on an invoice.
- `INVOICE_APPROVE` / `INVOICE_REJECT` — act on an approval step.
- `INVOICE_APPROVAL_VIEW` — read-only visibility into approval status/history.

---

## 4. Department & Purchase Category Wiring on Invoices

Per explicit instruction: *"if its non po the upload invoice form should ask for department and category must."*

In `invoice_process_service.py`, a new `_resolve_approval_context(invoice, db)` step runs during `apply_ocr_review` (after the PO_MANDATORY check, before auto-approval):
- **PO invoices**: `department_id`/`purchase_category_id` are **auto-derived from the linked PR** — any client-supplied values are overwritten.
- **NON_PO invoices**: both fields are **hard-required** and validated (department/category must exist, be active, and the category must belong to the selected department) — a 422 is raised otherwise.

`InvoiceOCRReviewRequest` (API interface) gained optional `department_id`/`purchase_category_id` fields to carry this input in from the frontend.

---

## 5. Default (Catch-All) Fallback Policy

Per explicit instruction: *"add one default policy which is applicable if no matching policy... like user in ums with role superadmin anyone can approval and it editable."*

- `ApprovalPolicy.is_default: bool` — a default policy has **no** department, category, or amount range (enforced: rejected with `"cannot have a department..."` if any are set).
- At most **one active** default policy may exist at a time (enforced on create and on reactivation via `set_policy_status`).
- `match_policy()` uses it only when no scoped policy matches (see §3 matching logic).
- Fully admin-editable via the same `ApprovalPolicy` CRUD — not hardcoded.
- A real default policy was created in the live database via the app's own service layer:
  - `id=2`, `name="Default Policy"`, `is_default=True`
  - Level 1: `approver_type=ROLE`, `role_code=Super_Admin`, `approval_rule=ANY_ONE`

---

## 6. Testing

No DB test fixtures exist in this project — all service tests use in-memory fake DAOs (matching the existing `test_pr_approval_workflow.py`/`test_procurement_authorization.py` conventions), and route tests use a bare FastAPI app with a fake auth/db middleware.

New/updated test files:
- `test_invoice_approval_workflow.py` — end-to-end scenarios (matching, overlap rejection, ANY_ONE/ALL, snapshot immutability).
- `test_approval_policy_service.py` — CRUD/validation, including 12 dedicated default-policy tests.
- `test_approver_resolver_service.py`
- `test_department_approver_service.py` (new, 10 tests)
- `test_approval_policy_authorization.py` — permission-gating matrix, including department-approver routes.
- `test_invoice_status_and_persistence.py` — fixture updates for the new department/category wiring.
- `test_cdc_event_parsing.py`, `test_cdc_retry_service.py`, `test_cdc_sync_service.py` — CDC pipeline coverage.

**Final state**: 465 passed, 17 pre-existing/unrelated failures (RFQ/quotation-matcher/invoice-create test files, confirmed via `git status` to have zero diffs — not caused by this work), 1 skipped.

---

## 7. Frontend Work (Not Yet Implemented — Prompts Only)

This session did not touch the `intranet-fe` repo directly. Two ready-to-hand-off prompts were prepared for a frontend session, covering:
1. **Upload/OCR-review form**: require Department + Purchase Category when `invoice_type === "NON_PO"`, filtered/cascading from Department; hide both for `PO` (backend derives and overwrites them); surface the backend's 422 validation messages.
2. **Admin Approval Policy builder**: add an `is_default` toggle that hides department/category/amount fields when on; badge default policies in the policy list; surface the "an active default policy already exists" 422 clearly.

Both prompts instruct the frontend session to reuse existing conventions (`expense-management/approval-engine` module, `apLookupService`/`useApLookups`, `useDepartments`/`usePurchaseCategories` hooks) rather than build new patterns.

---

## 8. Invoice Lifecycle (for reference)

Status flow (`status_master`, module `INVOICE`):

```
OCR_REVIEW_PENDING -> PENDING_APPROVAL -> APPROVED / REJECTED -> PARTIALLY_PAID -> PAID
```

- `OCR_FAILED` / `DISPUTED` are branches, not sequential steps.
- `DRAFT` exists in `status_master` but is unused by any current code path.
- `apply_ocr_review()` is simultaneously "save corrections" and "confirm review" — there is no separate draft-save state; every call ends at `PENDING_APPROVAL`. The frontend likely lacks a distinct "confirm/send to approval" button for this — noted as a Phase 2 gap, not a backend bug.
- Invoices at or below `AUTO_APPROVAL_LIMIT` with no open `InvoiceIssue` rows skip the approval engine entirely via `_maybe_auto_approve()`, going straight to `APPROVED` with no `invoice_approval` record.
- `invoice.status_id` stays at `PENDING_APPROVAL` for the entire approval-in-progress period — the fine-grained "in progress" state lives only in `invoice_approval.status`.

---

*Generated as a session reference summary — reflects backend work completed as of 2026-09-17.*
