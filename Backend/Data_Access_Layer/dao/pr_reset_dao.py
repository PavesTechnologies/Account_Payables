# Backend/Data_Access_Layer/dao/pr_reset_dao.py
"""SQL for the PR transaction-data reset (see pr_reset_service.py).

Everything here is plain SQLAlchemy Core against a Connection and never
commits - the service owns the transaction. Foreign keys are REFLECTED from
the live database rather than read from the ORM models, so a constraint that
exists in the database but not in the models is still honoured.
"""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import bindparam, inspect, text

SCHEMA = "ap"

# The PR "family": the only tables the reset may remove rows from. Rows leave
# them solely through the database's own ON DELETE CASCADE chain rooted at
# ap.purchase_requisition - nothing is deleted from them directly.
PR_FAMILY_TABLES = (
    "purchase_requisition",
    "purchase_requisition_line",
    "quotation",
    "rfq",
    "rfq_vendor",
)

# SQL expression yielding the owning PR id of a row of each family table,
# given the row's alias. rfq_vendor has no pr_id of its own - it belongs to a
# PR through its rfq.
_OWNER_SQL = {
    "purchase_requisition": "{a}.id",
    "purchase_requisition_line": "{a}.pr_id",
    "quotation": "{a}.pr_id",
    "rfq": "{a}.pr_id",
    "rfq_vendor": f"(SELECT o.pr_id FROM {SCHEMA}.rfq o WHERE o.id = {{a}}.rfq_id)",
}

_SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast"}


@dataclass(frozen=True)
class ForeignKeyRef:
    """One FK constraint whose target is a PR-family table."""

    name: Optional[str]
    schema: str
    table: str
    columns: tuple
    referred_table: str
    referred_columns: tuple
    ondelete: str  # CASCADE / SET NULL / SET DEFAULT / RESTRICT / NO ACTION

    @property
    def is_internal(self) -> bool:
        return self.schema == SCHEMA and self.table in PR_FAMILY_TABLES

    @property
    def label(self) -> str:
        cols = ", ".join(self.columns)
        ref_cols = ", ".join(self.referred_columns)
        return (
            f"{self.schema}.{self.table}.{cols} -> {SCHEMA}.{self.referred_table}.{ref_cols} "
            f"(ON DELETE {self.ondelete})"
        )


def _owner(table: str, alias: str) -> str:
    return _OWNER_SQL[table].format(a=alias)


def _qualified(schema: str, table: str) -> str:
    return f"{schema}.{table}"


class PrResetDAO:
    def __init__(self, conn):
        self.conn = conn

    # =====================================================
    # Schema discovery
    # =====================================================

    def user_schemas(self) -> List[str]:
        return [s for s in inspect(self.conn).get_schema_names() if s not in _SYSTEM_SCHEMAS]

    def list_tables(self) -> Dict[str, List[str]]:
        insp = inspect(self.conn)
        return {schema: insp.get_table_names(schema=schema) for schema in self.user_schemas()}

    def foreign_keys_into_pr_family(self) -> List[ForeignKeyRef]:
        """Every FK, in any user schema, whose target is a PR-family table."""

        insp = inspect(self.conn)
        refs: List[ForeignKeyRef] = []
        for schema in self.user_schemas():
            for (_, table), fks in insp.get_multi_foreign_keys(schema=schema).items():
                for fk in fks:
                    # A same-schema FK is reported with referred_schema None
                    # by some dialects.
                    referred_schema = fk.get("referred_schema") or schema
                    if referred_schema != SCHEMA or fk["referred_table"] not in PR_FAMILY_TABLES:
                        continue
                    ondelete = ((fk.get("options") or {}).get("ondelete") or "NO ACTION").upper()
                    refs.append(
                        ForeignKeyRef(
                            name=fk.get("name"),
                            schema=schema,
                            table=table,
                            columns=tuple(fk["constrained_columns"]),
                            referred_table=fk["referred_table"],
                            referred_columns=tuple(fk["referred_columns"]),
                            ondelete=ondelete,
                        )
                    )
        return refs

    # =====================================================
    # Planning queries
    # =====================================================

    def list_pr_ids(self, pr_ids: Optional[Iterable[int]] = None) -> List[int]:
        sql = f"SELECT id FROM {SCHEMA}.purchase_requisition"
        params = {}
        stmt = text(sql + " ORDER BY id")
        if pr_ids is not None:
            stmt = text(sql + " WHERE id IN :ids ORDER BY id").bindparams(
                bindparam("ids", expanding=True)
            )
            params = {"ids": list(pr_ids)}
            if not params["ids"]:
                return []
        return [row[0] for row in self.conn.execute(stmt, params)]

    def lock_prs(self, pr_ids: List[int]) -> None:
        """Row-lock the candidate PRs for the rest of the transaction
        (PostgreSQL only - SQLite serialises writers on its own)."""

        if not pr_ids or self.conn.dialect.name != "postgresql":
            return
        stmt = text(
            f"SELECT id FROM {SCHEMA}.purchase_requisition WHERE id IN :ids FOR UPDATE"
        ).bindparams(bindparam("ids", expanding=True))
        self.conn.execute(stmt, {"ids": pr_ids}).fetchall()

    def blocking_counts(self, fk: ForeignKeyRef, pr_ids: List[int]) -> Dict[int, int]:
        """Per PR id: how many rows that would SURVIVE the delete reference
        this PR's family rows through ``fk``.

        A referencing row survives when it lives outside the PR family (every
        such row is protected data, whatever the ON DELETE rule - CASCADE
        would delete it, SET NULL would modify it, RESTRICT/NO ACTION would
        fail) or when it belongs to a DIFFERENT PR. A same-PR reference is
        removed together with its target, so it only blocks under RESTRICT,
        which PostgreSQL checks immediately rather than at statement end.
        """

        if not pr_ids:
            return {}
        if len(fk.columns) != 1:
            # Never guess at composite keys - report every candidate blocked.
            return {pr_id: -1 for pr_id in pr_ids}

        target_owner = _owner(fk.referred_table, "t")
        conditions = [f"{target_owner} IN :ids"]
        if fk.is_internal and fk.ondelete != "RESTRICT":
            conditions.append(f"{_owner(fk.table, 'r')} <> {target_owner}")

        stmt = text(
            f"SELECT {target_owner} AS pr_id, COUNT(*) AS n "
            f"FROM {_qualified(fk.schema, fk.table)} r "
            f"JOIN {SCHEMA}.{fk.referred_table} t ON r.{fk.columns[0]} = t.{fk.referred_columns[0]} "
            f"WHERE {' AND '.join(conditions)} "
            f"GROUP BY {target_owner}"
        ).bindparams(bindparam("ids", expanding=True))
        return {row[0]: row[1] for row in self.conn.execute(stmt, {"ids": pr_ids})}

    def family_row_ids(self, pr_ids: List[int]) -> Dict[str, Set[int]]:
        """Ids of every PR-family row owned by ``pr_ids`` - exactly what the
        cascade is expected to remove."""

        result: Dict[str, Set[int]] = {}
        for table in PR_FAMILY_TABLES:
            if not pr_ids:
                result[table] = set()
                continue
            stmt = text(
                f"SELECT a.id FROM {SCHEMA}.{table} a WHERE {_owner(table, 'a')} IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            result[table] = {row[0] for row in self.conn.execute(stmt, {"ids": pr_ids})}
        return result

    def count_existing(self, table: str, ids: Set[int]) -> int:
        if not ids:
            return 0
        stmt = text(f"SELECT COUNT(*) FROM {SCHEMA}.{table} WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        )
        return self.conn.execute(stmt, {"ids": list(ids)}).scalar_one()

    def row_count(self, schema: str, table: str) -> int:
        return self.conn.execute(text(f"SELECT COUNT(*) FROM {_qualified(schema, table)}")).scalar_one()

    # =====================================================
    # Delete
    # =====================================================

    def delete_prs(self, pr_ids: List[int]) -> int:
        """Delete PR headers only; lines, quotations, RFQs and RFQ vendors go
        with them through the existing ON DELETE CASCADE constraints."""

        if not pr_ids:
            return 0
        stmt = text(f"DELETE FROM {SCHEMA}.purchase_requisition WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        )
        return self.conn.execute(stmt, {"ids": pr_ids}).rowcount
