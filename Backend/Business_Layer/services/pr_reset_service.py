# Backend/Business_Layer/services/pr_reset_service.py
"""Reset Purchase Requisition transaction data so fresh PRs can be created.

Scope: ap.purchase_requisition and the rows that hang off it through the
database's existing ON DELETE CASCADE chain - purchase_requisition_line,
quotation, rfq and rfq_vendor. Nothing else is deleted or modified.

Why this does not reuse ProcurementService.delete_purchase_requisition: that
path is DRAFT-only by business rule and deletes through the ORM session,
whose PurchaseRequisition.purchase_order relationship has no passive_deletes
- the ORM would try to NULL purchase_order.pr_id rather than refuse. The
reset instead issues one set-based DELETE on the PR headers and lets the
database's own FK rules do the rest, after proving no protected row points
at anything that would go.

Rules enforced here:
  * A PR is deleted only when NO surviving row references any of its family
    rows (purchase_order, purchase_order_line, vendor_nda,
    vendor_onboarding_request, any FK discovered in the live DB, or another
    PR's rows). Blocked PRs are reported with the reason, never forced.
  * No constraint is disabled or dropped; no TRUNCATE.
  * audit_log is untouched (it has no FK to PRs; history rows stay as-is).
  * One transaction: plan, delete, verify - any failure rolls everything back.
"""
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from Backend.Data_Access_Layer.dao.pr_reset_dao import (
    PR_FAMILY_TABLES,
    SCHEMA,
    ForeignKeyRef,
    PrResetDAO,
)

# The cascade chain the reset depends on: child table -> (column, parent).
# Verified against the live database before anything is deleted.
REQUIRED_CASCADES = {
    "purchase_requisition_line": ("pr_id", "purchase_requisition"),
    "quotation": ("pr_id", "purchase_requisition"),
    "rfq": ("pr_id", "purchase_requisition"),
    "rfq_vendor": ("rfq_id", "rfq"),
}


class PrResetError(RuntimeError):
    """The reset cannot run safely, or its post-delete verification failed."""


@dataclass
class ResetPlan:
    eligible: List[int] = field(default_factory=list)
    # pr_id -> human-readable reasons
    blocked: Dict[int, List[str]] = field(default_factory=dict)
    # table -> number of rows the cascade will remove for eligible PRs
    cascade_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class ResetResult:
    plan: ResetPlan
    executed: bool
    deleted_pr_ids: List[int] = field(default_factory=list)
    # table -> rows actually removed
    deleted_counts: Dict[str, int] = field(default_factory=dict)
    protected_tables_checked: int = 0


class PrResetService:
    def __init__(self, conn):
        self.conn = conn
        self.dao = PrResetDAO(conn)

    # =========================================================
    # Planning (read-only)
    # =========================================================

    def plan(self, pr_ids: Optional[Iterable[int]] = None) -> ResetPlan:
        fks = self.dao.foreign_keys_into_pr_family()
        self._require_cascade_chain(fks)

        candidates = self.dao.list_pr_ids(pr_ids)
        blocked: Dict[int, List[str]] = {}
        for fk in fks:
            for pr_id, count in self.dao.blocking_counts(fk, candidates).items():
                reason = (
                    f"composite FK {fk.label} - not evaluated, left in place"
                    if count < 0
                    else f"{count} row(s) via {fk.label}"
                )
                blocked.setdefault(pr_id, []).append(reason)

        eligible = [pr_id for pr_id in candidates if pr_id not in blocked]
        family = self.dao.family_row_ids(eligible)
        return ResetPlan(
            eligible=eligible,
            blocked=dict(sorted(blocked.items())),
            cascade_counts={table: len(ids) for table, ids in family.items()},
        )

    # =========================================================
    # Execution
    # =========================================================

    def execute(self, pr_ids: Optional[Iterable[int]] = None) -> ResetResult:
        """Delete every eligible PR in ONE transaction and verify the result.

        The caller passes a Connection that is NOT yet in a transaction; this
        method opens it, and commits only after verification passes.
        """

        with self.conn.begin():
            candidates = self.dao.list_pr_ids(pr_ids)
            # Lock first, then plan, so a PO/NDA/onboarding row created
            # concurrently cannot slip in between the check and the delete
            # (and if one does, the FK itself fails the DELETE -> rollback).
            self.dao.lock_prs(candidates)
            plan = self.plan(candidates)
            if not plan.eligible:
                return ResetResult(plan=plan, executed=False)

            family = self.dao.family_row_ids(plan.eligible)
            family_totals_before = {t: self.dao.row_count(SCHEMA, t) for t in PR_FAMILY_TABLES}
            protected_before = self._protected_row_counts()

            deleted = self.dao.delete_prs(plan.eligible)
            if deleted != len(plan.eligible):
                raise PrResetError(
                    f"Expected to delete {len(plan.eligible)} purchase requisition(s), deleted {deleted}"
                )

            self._verify(family, family_totals_before, protected_before)

            return ResetResult(
                plan=plan,
                executed=True,
                deleted_pr_ids=list(plan.eligible),
                deleted_counts={t: len(ids) for t, ids in family.items()},
                protected_tables_checked=len(protected_before),
            )

    # =========================================================
    # Internal helpers
    # =========================================================

    @staticmethod
    def _require_cascade_chain(fks: List[ForeignKeyRef]) -> None:
        missing = []
        for child, (column, parent) in REQUIRED_CASCADES.items():
            if not any(
                fk.schema == SCHEMA
                and fk.table == child
                and fk.columns == (column,)
                and fk.referred_table == parent
                and fk.ondelete == "CASCADE"
                for fk in fks
            ):
                missing.append(f"{SCHEMA}.{child}.{column} -> {SCHEMA}.{parent} ON DELETE CASCADE")
        if missing:
            raise PrResetError(
                "The database does not have the cascade chain the reset relies on; nothing was "
                "changed. Missing: " + "; ".join(missing)
            )

    def _protected_row_counts(self) -> Dict[str, int]:
        counts = {}
        for schema, tables in self.dao.list_tables().items():
            for table in tables:
                if schema == SCHEMA and table in PR_FAMILY_TABLES:
                    continue
                counts[f"{schema}.{table}"] = self.dao.row_count(schema, table)
        return counts

    def _verify(self, family, family_totals_before, protected_before) -> None:
        problems = []

        for table, ids in family.items():
            leftover = self.dao.count_existing(table, ids)
            if leftover:
                problems.append(f"{leftover} {table} row(s) of the deleted PRs still exist")

            # Only the targeted rows may disappear - other PRs' rows stay.
            expected = family_totals_before[table] - len(ids)
            actual = self.dao.row_count(SCHEMA, table)
            if actual != expected:
                problems.append(f"{SCHEMA}.{table} has {actual} rows, expected {expected}")

        protected_after = self._protected_row_counts()
        for name, before in protected_before.items():
            after = protected_after.get(name)
            if after != before:
                problems.append(f"protected table {name} changed from {before} to {after} rows")

        if problems:
            raise PrResetError("Verification failed, transaction rolled back: " + "; ".join(problems))
