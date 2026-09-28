# Backend/Data_Access_Layer/dao/pr_bulk_cleanup_dao.py
"""SQL for the admin bulk Purchase Requisition cleanup (see
pr_bulk_cleanup_service.py).

Plain SQLAlchemy Core against a Connection; never commits - the service owns
the transaction. Reuses PrResetDAO's schema-discovery and counting helpers.
Foreign keys are REFLECTED from the live database so a constraint that exists
there but not in the ORM models is still honoured.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from sqlalchemy import bindparam, inspect, text

from Backend.Data_Access_Layer.dao.pr_reset_dao import SCHEMA, PrResetDAO


@dataclass(frozen=True)
class CleanupTable:
    """A table the cleanup removes rows from, and how its rows are owned.

    A row belongs to the cleanup when ``owner_column`` points at a row of
    ``owner_table`` that belongs to it; the root has no owner.
    """

    name: str
    pk: str
    owner_table: Optional[str] = None
    owner_column: Optional[str] = None


# Every table the cleanup may remove rows from, parents before children.
# Rows leave purchase_requisition_line / quotation / rfq / rfq_vendor /
# purchase_order_line / goods_receipt_line only through the database's
# existing ON DELETE CASCADE; the others are deleted explicitly.
CLEANUP_TABLES = (
    CleanupTable("purchase_requisition", "id"),
    CleanupTable("purchase_requisition_line", "id", "purchase_requisition", "pr_id"),
    CleanupTable("quotation", "id", "purchase_requisition", "pr_id"),
    CleanupTable("rfq", "id", "purchase_requisition", "pr_id"),
    CleanupTable("rfq_vendor", "id", "rfq", "rfq_id"),
    CleanupTable("purchase_order", "id", "purchase_requisition", "pr_id"),
    CleanupTable("purchase_order_line", "id", "purchase_order", "po_id"),
    CleanupTable("goods_receipt", "grn_id", "purchase_order", "po_id"),
    CleanupTable("goods_receipt_line", "grn_line_id", "goods_receipt", "grn_id"),
    CleanupTable("vendor_nda", "nda_id", "purchase_requisition", "pr_id"),
    CleanupTable("vendor_onboarding_request", "id", "purchase_requisition", "pr_id"),
)
CLEANUP_TABLE_BY_NAME = {t.name: t for t in CLEANUP_TABLES}

# Explicit deletes, in execution order. Everything else in CLEANUP_TABLES goes
# through CASCADE from one of these. GRNs block their PO (NO ACTION) and POs
# block their PR, quotation and PR lines (NO ACTION), so they go first.
DIRECT_DELETE_ORDER = (
    "goods_receipt",
    "purchase_order",
    "vendor_nda",
    "vendor_onboarding_request",
    "purchase_requisition",
)

# References that have NO database FK (ORM-only joins), so the database would
# not stop a delete from orphaning them: (table, column, referred table).
SOFT_REFERENCES = (
    ("invoice", "po_id", "purchase_order"),
    ("invoice_line", "po_line_id", "purchase_order_line"),
    ("goods_receipt_line", "po_line_id", "purchase_order_line"),
)


@dataclass(frozen=True)
class Reference:
    """A (reflected or soft) reference into a cleanup table."""

    schema: str
    table: str
    columns: tuple
    referred_table: str
    referred_columns: tuple
    ondelete: str  # CASCADE / SET NULL / RESTRICT / NO ACTION / SOFT (no FK)

    @property
    def label(self) -> str:
        return (
            f"{self.schema}.{self.table}.{', '.join(self.columns)} -> "
            f"{SCHEMA}.{self.referred_table}.{', '.join(self.referred_columns)} "
            f"(ON DELETE {self.ondelete})"
        )


def _ids_param(name: str):
    return bindparam(name, expanding=True)


class PrBulkCleanupDAO(PrResetDAO):

    # =====================================================
    # Concurrency guard
    # =====================================================

    def lock_for_cleanup(self, lock_timeout: str = "10s") -> None:
        """Block concurrent writers for the rest of the transaction
        (PostgreSQL only - SQLite serialises writers on its own).

        EXCLUSIVE on the tables deleted from directly still allows reads, but
        stops new rows AND new FK references to their rows (FK checks need a
        ROW SHARE lock, which conflicts). SHARE on the soft-reference tables
        stops an invoice being linked to a PO mid-cleanup. Must run before any
        query so the REPEATABLE READ snapshot is taken after the locks.
        """

        if self.conn.dialect.name != "postgresql":
            return
        self.conn.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout}'"))
        exclusive = ", ".join(f"{SCHEMA}.{t}" for t in DIRECT_DELETE_ORDER)
        share = ", ".join(sorted({f"{SCHEMA}.{t}" for t, _, _ in SOFT_REFERENCES}))
        self.conn.execute(text(f"LOCK TABLE {exclusive} IN EXCLUSIVE MODE"))
        self.conn.execute(text(f"LOCK TABLE {share} IN SHARE MODE"))

    # =====================================================
    # Scope
    # =====================================================

    def collect_row_ids(self, pr_ids: List[int]) -> Dict[str, Set[int]]:
        """Ids of every cleanup-table row owned, directly or transitively, by
        ``pr_ids``. Nothing outside this set is ever deleted."""

        result: Dict[str, Set[int]] = {"purchase_requisition": set(pr_ids)}
        for table in CLEANUP_TABLES[1:]:
            owner_ids = result[table.owner_table]
            if not owner_ids:
                result[table.name] = set()
                continue
            stmt = text(
                f"SELECT {table.pk} FROM {SCHEMA}.{table.name} WHERE {table.owner_column} IN :ids"
            ).bindparams(_ids_param("ids"))
            result[table.name] = {row[0] for row in self.conn.execute(stmt, {"ids": list(owner_ids)})}
        return result

    # =====================================================
    # Reference discovery
    # =====================================================

    def references_into_cleanup_tables(self) -> List[Reference]:
        """Every FK in any user schema that targets a cleanup table, plus the
        known soft references whose table and column exist."""

        insp = inspect(self.conn)
        refs: List[Reference] = []
        for schema in self.user_schemas():
            for (_, table), fks in insp.get_multi_foreign_keys(schema=schema).items():
                for fk in fks:
                    referred_schema = fk.get("referred_schema") or schema
                    if referred_schema != SCHEMA or fk["referred_table"] not in CLEANUP_TABLE_BY_NAME:
                        continue
                    refs.append(
                        Reference(
                            schema=schema,
                            table=table,
                            columns=tuple(fk["constrained_columns"]),
                            referred_table=fk["referred_table"],
                            referred_columns=tuple(fk["referred_columns"]),
                            ondelete=((fk.get("options") or {}).get("ondelete") or "NO ACTION").upper(),
                        )
                    )

        for table, column, referred in SOFT_REFERENCES:
            if not insp.has_table(table, schema=SCHEMA):
                continue
            if column not in {c["name"] for c in insp.get_columns(table, schema=SCHEMA)}:
                continue
            refs.append(
                Reference(
                    schema=SCHEMA,
                    table=table,
                    columns=(column,),
                    referred_table=referred,
                    referred_columns=(CLEANUP_TABLE_BY_NAME[referred].pk,),
                    ondelete="SOFT",
                )
            )
        return refs

    def surviving_reference_count(self, ref: Reference, row_ids: Dict[str, Set[int]]) -> int:
        """How many rows that will SURVIVE the cleanup point at a row that
        will be deleted, through ``ref``.

        A referencing row survives when it is not itself in the cleanup set.
        Any such row blocks the cleanup whatever the ON DELETE rule: CASCADE
        would delete data outside the scope, SET NULL would modify it, and
        NO ACTION / RESTRICT / no-FK would leave it dangling or fail.
        Returns -1 for a composite FK, which is never guessed at.
        """

        target_ids = row_ids.get(ref.referred_table) or set()
        if not target_ids:
            return 0
        if len(ref.columns) != 1:
            return -1

        referred_pk = CLEANUP_TABLE_BY_NAME[ref.referred_table].pk
        conditions = [f"t.{referred_pk} IN :target_ids"]
        params = {"target_ids": list(target_ids)}
        bind = [_ids_param("target_ids")]

        own = CLEANUP_TABLE_BY_NAME.get(ref.table) if ref.schema == SCHEMA else None
        if own is not None and row_ids.get(own.name):
            conditions.append(f"r.{own.pk} NOT IN :own_ids")
            params["own_ids"] = list(row_ids[own.name])
            bind.append(_ids_param("own_ids"))

        stmt = text(
            f"SELECT COUNT(*) FROM {ref.schema}.{ref.table} r "
            f"JOIN {SCHEMA}.{ref.referred_table} t ON r.{ref.columns[0]} = t.{ref.referred_columns[0]} "
            f"WHERE {' AND '.join(conditions)}"
        ).bindparams(*bind)
        return self.conn.execute(stmt, params).scalar_one()

    # =====================================================
    # Delete / verify
    # =====================================================

    def delete_rows(self, table_name: str, ids: Set[int]) -> int:
        """Delete exactly ``ids`` from one cleanup table; CASCADE children go
        with them through the existing FK rules."""

        if not ids:
            return 0
        table = CLEANUP_TABLE_BY_NAME[table_name]
        stmt = text(f"DELETE FROM {SCHEMA}.{table.name} WHERE {table.pk} IN :ids").bindparams(
            _ids_param("ids")
        )
        return self.conn.execute(stmt, {"ids": list(ids)}).rowcount

    def count_remaining(self, table_name: str, ids: Set[int]) -> int:
        if not ids:
            return 0
        table = CLEANUP_TABLE_BY_NAME[table_name]
        stmt = text(f"SELECT COUNT(*) FROM {SCHEMA}.{table.name} WHERE {table.pk} IN :ids").bindparams(
            _ids_param("ids")
        )
        return self.conn.execute(stmt, {"ids": list(ids)}).scalar_one()
