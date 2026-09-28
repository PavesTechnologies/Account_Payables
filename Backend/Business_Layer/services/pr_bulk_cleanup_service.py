# Backend/Business_Layer/services/pr_bulk_cleanup_service.py
"""Admin PR cleanup: permanently delete Purchase Requisitions - all of them,
a chosen batch, or a single one - and the transactional rows that exist only
because of them. All three share one engine (_execute), so dependency
discovery, delete order, financial protection, locking, rollback and
verification are identical.

Scope - captured once, then every delete is limited to it:
  purchase_requisition (all rows, or the requested ids)
    +- purchase_requisition_line, quotation, rfq -> rfq_vendor   (CASCADE)
    +- purchase_order -> purchase_order_line                     (explicit; line CASCADE)
    |    +- goods_receipt -> goods_receipt_line                  (explicit; line CASCADE)
    +- vendor_nda, vendor_onboarding_request                     (explicit)

Differs from pr_reset_service.py (the CLI reset), which skips any PR that has
a PO / NDA / onboarding request. Here those rows are in scope and deleted
first, because the task is to remove the PR data entirely.

Safety rules:
  * If ANY row outside the scope references a row inside it - through a
    reflected FK or a known FK-less column such as invoice.po_id, or from a
    PR that is not being deleted - nothing is deleted and
    PrCleanupBlockedError is raised.
  * A requested PR id that does not exist fails the whole request
    (PrCleanupNotFoundError) before anything is deleted. Invoices and payments are
    financial records and are never deleted by this operation.
  * No TRUNCATE / DROP, no constraint disabled, no ORM or ad-hoc CASCADE: only
    the database's existing ON DELETE CASCADE rules remove child rows.
  * One transaction (REPEATABLE READ on PostgreSQL, with the affected tables
    locked against writers): lock, plan, delete, verify, commit. Any failure
    rolls everything back. audit_log history is left as-is.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from Backend.Business_Layer.services.pr_reset_service import (
    REQUIRED_CASCADES as PR_RESET_REQUIRED_CASCADES,
)
from Backend.Data_Access_Layer.dao.pr_bulk_cleanup_dao import (
    CLEANUP_TABLE_BY_NAME,
    CLEANUP_TABLES,
    DIRECT_DELETE_ORDER,
    PrBulkCleanupDAO,
    Reference,
)
from Backend.Data_Access_Layer.dao.pr_reset_dao import SCHEMA

logger = logging.getLogger(__name__)

# child table -> (column, parent): the CASCADE rules the cleanup relies on to
# remove rows it never deletes directly. Verified before anything is deleted.
REQUIRED_CASCADES = {
    **PR_RESET_REQUIRED_CASCADES,
    "purchase_order_line": ("po_id", "purchase_order"),
    "goods_receipt_line": ("grn_id", "goods_receipt"),
}


class PrCleanupError(RuntimeError):
    """The cleanup cannot run safely, or its post-delete verification failed."""


class PrCleanupBlockedError(PrCleanupError):
    """Rows outside the cleanup scope reference rows inside it."""

    def __init__(self, blockers: Dict[Reference, int]):
        self.blockers = blockers
        super().__init__(
            "Cleanup blocked by references from outside its scope: "
            + "; ".join(
                f"{ref.label}: {'composite FK, not evaluated' if n < 0 else f'{n} row(s)'}"
                for ref, n in blockers.items()
            )
        )

    @property
    def blocking_tables(self) -> Dict[str, int]:
        """Referencing table -> row count (composite FKs count as 0)."""

        tables: Dict[str, int] = {}
        for ref, n in self.blockers.items():
            tables[ref.table] = tables.get(ref.table, 0) + max(n, 0)
        return tables


class PrCleanupNotFoundError(PrCleanupError):
    """One or more requested purchase requisitions do not exist."""

    def __init__(self, missing_ids: List[int]):
        self.missing_ids = missing_ids
        super().__init__(f"Purchase requisition(s) not found: {missing_ids}")


@dataclass
class CleanupResult:
    # cleanup table -> rows removed
    deleted_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def purchase_requisitions(self) -> int:
        return self.deleted_counts.get("purchase_requisition", 0)


class PrBulkCleanupService:
    def __init__(self, db: Session):
        self.db = db

    def delete_all_purchase_requisitions(self) -> CleanupResult:
        """Delete every PR and its data."""

        return self._execute(None)

    def delete_purchase_requisitions(self, pr_ids: Iterable[int]) -> CleanupResult:
        """Delete exactly the given PRs and their data - all or none."""

        ids = sorted(set(pr_ids))
        if not ids:
            raise ValueError("At least one purchase requisition id is required")
        return self._execute(ids)

    def delete_purchase_requisition(self, pr_id: int) -> CleanupResult:
        return self.delete_purchase_requisitions([pr_id])

    # =========================================================
    # Internal helpers
    # =========================================================

    def _execute(self, pr_ids: Optional[List[int]]) -> CleanupResult:
        """Run the cleanup in ONE transaction on ``self.db`` and commit only
        after verification passes; roll back and re-raise on any error.
        ``pr_ids`` None means every PR."""

        try:
            dao = PrBulkCleanupDAO(self._open_connection())
            result = self._run(dao, pr_ids)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning(
                "PR cleanup: %s - transaction rolled back, nothing was deleted", type(exc).__name__
            )
            raise
        return result

    def _open_connection(self):
        # REPEATABLE READ keeps every count in this transaction on one
        # snapshot, so unrelated concurrent activity can't fail verification.
        # The isolation level can only be set before the transaction starts.
        if self.db.get_bind().dialect.name == "postgresql":
            if not self.db.in_transaction():
                return self.db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            logger.warning("PR cleanup: session already in a transaction; running at its isolation level")
        return self.db.connection()

    def _run(self, dao: PrBulkCleanupDAO, requested: Optional[List[int]]) -> CleanupResult:
        dao.lock_for_cleanup()

        pr_ids = dao.list_pr_ids(requested)
        if requested is not None:
            missing = sorted(set(requested) - set(pr_ids))
            if missing:
                raise PrCleanupNotFoundError(missing)
        logger.info("PR cleanup: %d purchase requisition(s) identified", len(pr_ids))
        if not pr_ids:
            return CleanupResult(deleted_counts={t.name: 0 for t in CLEANUP_TABLES})

        refs = dao.references_into_cleanup_tables()
        self._require_cascade_chain(refs)

        row_ids = dao.collect_row_ids(pr_ids)
        planned = {table: len(ids) for table, ids in row_ids.items()}
        logger.info("PR cleanup: rows in scope %s", planned)

        self._require_no_surviving_references(dao, refs, row_ids)

        totals_before = {t.name: dao.row_count(SCHEMA, t.name) for t in CLEANUP_TABLES}
        protected_before = self._protected_row_counts(dao)
        fks_before = self._fk_snapshot(refs)

        logger.info("PR cleanup: deletion started")
        for table in DIRECT_DELETE_ORDER:
            expected = len(row_ids[table])
            deleted = dao.delete_rows(table, row_ids[table])
            if deleted != expected:
                raise PrCleanupError(f"Expected to delete {expected} {table} row(s), deleted {deleted}")

        self._verify(
            dao, row_ids, totals_before, protected_before, fks_before, expect_empty=requested is None
        )
        logger.info("PR cleanup: deletion completed and verified, deleted %s", planned)
        return CleanupResult(deleted_counts=planned)

    @staticmethod
    def _require_cascade_chain(refs: List[Reference]) -> None:
        missing = []
        for child, (column, parent) in REQUIRED_CASCADES.items():
            if not any(
                ref.schema == SCHEMA
                and ref.table == child
                and ref.columns == (column,)
                and ref.referred_table == parent
                and ref.ondelete == "CASCADE"
                for ref in refs
            ):
                missing.append(f"{SCHEMA}.{child}.{column} -> {SCHEMA}.{parent} ON DELETE CASCADE")
        if missing:
            raise PrCleanupError(
                "The database does not have the cascade chain the cleanup relies on; nothing was "
                "changed. Missing: " + "; ".join(missing)
            )

    @staticmethod
    def _require_no_surviving_references(
        dao: PrBulkCleanupDAO, refs: List[Reference], row_ids: Dict[str, Set[int]]
    ) -> None:
        blockers = {}
        for ref in refs:
            count = dao.surviving_reference_count(ref, row_ids)
            if count:
                blockers[ref] = count
        if blockers:
            raise PrCleanupBlockedError(blockers)

    @staticmethod
    def _protected_row_counts(dao: PrBulkCleanupDAO) -> Dict[str, int]:
        counts = {}
        for schema, tables in dao.list_tables().items():
            for table in tables:
                if schema == SCHEMA and table in CLEANUP_TABLE_BY_NAME:
                    continue
                counts[f"{schema}.{table}"] = dao.row_count(schema, table)
        return counts

    @staticmethod
    def _fk_snapshot(refs: List[Reference]) -> Set[Reference]:
        return {ref for ref in refs if ref.ondelete != "SOFT"}

    def _verify(self, dao, row_ids, totals_before, protected_before, fks_before, *, expect_empty) -> None:
        problems = []

        # Delete-all must leave the table empty; a targeted delete must leave
        # every other PR in place (checked by the per-table totals below).
        remaining_prs = dao.row_count(SCHEMA, "purchase_requisition")
        if expect_empty and remaining_prs:
            problems.append(f"{remaining_prs} purchase_requisition row(s) remain")

        for table, ids in row_ids.items():
            leftover = dao.count_remaining(table, ids)
            if leftover:
                problems.append(f"{leftover} {table} row(s) in scope still exist")
            # Only in-scope rows may disappear - unrelated rows stay.
            expected = totals_before[table] - len(ids)
            actual = dao.row_count(SCHEMA, table)
            if actual != expected:
                problems.append(f"{SCHEMA}.{table} has {actual} rows, expected {expected}")

        protected_after = self._protected_row_counts(dao)
        for name, before in protected_before.items():
            after = protected_after.get(name)
            if after != before:
                problems.append(f"protected table {name} changed from {before} to {after} rows")

        if self._fk_snapshot(dao.references_into_cleanup_tables()) != fks_before:
            problems.append("foreign-key constraints into the cleanup tables changed")

        if problems:
            raise PrCleanupError("Verification failed, transaction rolled back: " + "; ".join(problems))
