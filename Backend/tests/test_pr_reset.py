# Backend/tests/test_pr_reset.py
"""PR transaction-data reset (pr_reset_service.py).

Runs against a REAL database engine rather than the fake-DAO harnesses the
other procurement tests use, because what is under test is the database's own
FK behaviour: CASCADE, SET NULL, NO ACTION and transaction rollback. An
in-memory SQLite database is attached as schema ``ap`` with foreign keys
enforced; the DDL mirrors the FK names and ON DELETE rules in
Database/schema.sql (trimmed to the columns that matter).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from Backend.Business_Layer.services.pr_reset_service import (
    PrResetError,
    PrResetService,
    ResetPlan,
)

DDL = [
    "CREATE TABLE ap.vendor (vendor_id INTEGER PRIMARY KEY, name TEXT)",
    "CREATE TABLE ap.department (id INTEGER PRIMARY KEY, name TEXT)",
    "CREATE TABLE ap.audit_log (audit_id INTEGER PRIMARY KEY, table_name TEXT, record_id INTEGER)",
    """CREATE TABLE ap.purchase_requisition (
        id INTEGER PRIMARY KEY,
        pr_number TEXT,
        selected_quotation_id INTEGER,
        CONSTRAINT fk_pr_selected_quotation FOREIGN KEY (selected_quotation_id) REFERENCES quotation(id))""",
    """CREATE TABLE ap.purchase_requisition_line (
        id INTEGER PRIMARY KEY, pr_id INTEGER NOT NULL,
        CONSTRAINT fk_pr_line_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id) ON DELETE CASCADE)""",
    """CREATE TABLE ap.rfq (
        id INTEGER PRIMARY KEY, pr_id INTEGER NOT NULL,
        CONSTRAINT fk_rfq_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id) ON DELETE CASCADE)""",
    """CREATE TABLE ap.rfq_vendor (
        id INTEGER PRIMARY KEY, rfq_id INTEGER NOT NULL, vendor_id INTEGER NOT NULL,
        CONSTRAINT fk_rfq_vendor_rfq FOREIGN KEY (rfq_id) REFERENCES rfq(id) ON DELETE CASCADE,
        CONSTRAINT fk_rfq_vendor_vendor FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id))""",
    """CREATE TABLE ap.quotation (
        id INTEGER PRIMARY KEY, pr_id INTEGER NOT NULL, rfq_id INTEGER, vendor_id INTEGER NOT NULL,
        CONSTRAINT fk_quotation_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id) ON DELETE CASCADE,
        CONSTRAINT fk_quotation_rfq FOREIGN KEY (rfq_id) REFERENCES rfq(id) ON DELETE SET NULL,
        CONSTRAINT fk_quotation_vendor FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id))""",
    """CREATE TABLE ap.purchase_order (
        id INTEGER PRIMARY KEY, pr_id INTEGER NOT NULL, quotation_id INTEGER,
        CONSTRAINT fk_po_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id),
        CONSTRAINT fk_po_quotation FOREIGN KEY (quotation_id) REFERENCES quotation(id))""",
    """CREATE TABLE ap.purchase_order_line (
        id INTEGER PRIMARY KEY, po_id INTEGER NOT NULL, pr_line_id INTEGER,
        CONSTRAINT fk_po_line_po FOREIGN KEY (po_id) REFERENCES purchase_order(id) ON DELETE CASCADE,
        CONSTRAINT fk_po_line_pr_line FOREIGN KEY (pr_line_id) REFERENCES purchase_requisition_line(id))""",
    """CREATE TABLE ap.vendor_nda (
        id INTEGER PRIMARY KEY, pr_id INTEGER,
        CONSTRAINT fk_vendor_nda_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id))""",
    """CREATE TABLE ap.vendor_onboarding_request (
        id INTEGER PRIMARY KEY, pr_id INTEGER NOT NULL,
        CONSTRAINT fk_vor_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id))""",
]


def _make_engine(ddl=DDL):
    engine = create_engine("sqlite://", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("ATTACH DATABASE ':memory:' AS ap")
        cur.close()

    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
    return engine


def _seed_pr(conn, pr_id, *, with_quotation=True):
    """A PR with the full family: line, rfq, rfq_vendor, quotation (selected)."""

    base = pr_id * 10
    conn.execute(text("INSERT INTO ap.purchase_requisition (id, pr_number) VALUES (:id, :n)"),
                 {"id": pr_id, "n": f"PR-{pr_id:06d}"})
    conn.execute(text("INSERT INTO ap.purchase_requisition_line (id, pr_id) VALUES (:id, :pr)"),
                 {"id": base + 1, "pr": pr_id})
    conn.execute(text("INSERT INTO ap.rfq (id, pr_id) VALUES (:id, :pr)"), {"id": base + 2, "pr": pr_id})
    conn.execute(text("INSERT INTO ap.rfq_vendor (id, rfq_id, vendor_id) VALUES (:id, :rfq, 1)"),
                 {"id": base + 3, "rfq": base + 2})
    if with_quotation:
        conn.execute(text("INSERT INTO ap.quotation (id, pr_id, rfq_id, vendor_id) VALUES (:id, :pr, :rfq, 1)"),
                     {"id": base + 4, "pr": pr_id, "rfq": base + 2})
        conn.execute(text("UPDATE ap.purchase_requisition SET selected_quotation_id = :q WHERE id = :id"),
                     {"q": base + 4, "id": pr_id})
    conn.execute(text("INSERT INTO ap.audit_log (table_name, record_id) VALUES ('purchase_requisition', :id)"),
                 {"id": pr_id})


@pytest.fixture
def engine():
    engine = _make_engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ap.vendor (vendor_id, name) VALUES (1, 'AQUA')"))
        conn.execute(text("INSERT INTO ap.department (id, name) VALUES (1, 'IT')"))
    return engine


def _count(engine, table, where="1=1", **params):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM ap.{table} WHERE {where}"), params).scalar_one()


def _run(engine, pr_ids=None):
    with engine.connect() as conn:
        return PrResetService(conn).execute(pr_ids)


def _plan(engine, pr_ids=None) -> ResetPlan:
    with engine.connect() as conn:
        return PrResetService(conn).plan(pr_ids)


FAMILY = ["purchase_requisition", "purchase_requisition_line", "rfq", "rfq_vendor", "quotation"]


# =========================================================
# Successful deletion + cascade
# =========================================================


def test_deletes_unblocked_pr_and_cascades_its_family(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)

    result = _run(engine)

    assert result.executed is True
    assert result.deleted_pr_ids == [1]
    assert result.deleted_counts == {t: 1 for t in FAMILY}
    for table in FAMILY:
        assert _count(engine, table) == 0, table


def test_protected_tables_are_untouched(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)

    _run(engine)

    # Audit history of the deleted PR is preserved as-is; masters are untouched.
    assert _count(engine, "audit_log", "table_name = 'purchase_requisition' AND record_id = 1") == 1
    assert _count(engine, "vendor") == 1
    assert _count(engine, "department") == 1


def test_only_targeted_prs_are_deleted(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)

    result = _run(engine, pr_ids=[1])

    assert result.deleted_pr_ids == [1]
    assert _count(engine, "purchase_requisition", "id = 2") == 1
    for table in ["purchase_requisition_line", "rfq", "rfq_vendor", "quotation"]:
        assert _count(engine, table) == 1, table


def test_dry_run_plan_changes_nothing(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)

    plan = _plan(engine)

    assert plan.eligible == [1]
    assert plan.cascade_counts == {t: 1 for t in FAMILY}
    for table in FAMILY:
        assert _count(engine, table) == 1, table


def test_nothing_eligible_is_a_no_op(engine):
    result = _run(engine)
    assert result.executed is False
    assert result.deleted_pr_ids == []


# =========================================================
# Blockers
# =========================================================


@pytest.mark.parametrize(
    "blocker_sql, expected_fk",
    [
        ("INSERT INTO ap.purchase_order (id, pr_id) VALUES (900, 1)", "purchase_order.pr_id"),
        ("INSERT INTO ap.vendor_nda (id, pr_id) VALUES (900, 1)", "vendor_nda.pr_id"),
        ("INSERT INTO ap.vendor_onboarding_request (id, pr_id) VALUES (900, 1)",
         "vendor_onboarding_request.pr_id"),
    ],
)
def test_direct_dependency_blocks_pr(engine, blocker_sql, expected_fk):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        conn.execute(text(blocker_sql))

    result = _run(engine)

    assert result.deleted_pr_ids == [2]
    assert list(result.plan.blocked) == [1]
    assert any(expected_fk in reason for reason in result.plan.blocked[1])
    # The blocked PR and its whole family are still there, and so is the dependency.
    for table in FAMILY:
        assert _count(engine, table) == 1, table
    assert _count(engine, expected_fk.split(".")[0], "id = 900") == 1


def test_po_referencing_a_quotation_blocks_that_quotations_pr(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        # PO raised for PR 2 but pointing at PR 1's quotation.
        conn.execute(text("INSERT INTO ap.purchase_order (id, pr_id, quotation_id) VALUES (900, 2, 14)"))

    plan = _plan(engine)

    assert plan.eligible == []
    assert any("purchase_order.quotation_id" in r for r in plan.blocked[1])
    assert any("purchase_order.pr_id" in r for r in plan.blocked[2])


def test_po_line_referencing_a_pr_line_blocks_that_pr(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        conn.execute(text("INSERT INTO ap.purchase_order (id, pr_id) VALUES (900, 2)"))
        conn.execute(text("INSERT INTO ap.purchase_order_line (id, po_id, pr_line_id) VALUES (901, 900, 11)"))

    plan = _plan(engine)

    assert 1 in plan.blocked
    assert any("purchase_order_line.pr_line_id" in r for r in plan.blocked[1])


def test_set_null_from_another_prs_quotation_blocks(engine):
    """Deleting PR 1's rfq would SET NULL on PR 2's quotation - a modification
    of data that survives, so PR 1 is blocked rather than silently altering it."""

    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        conn.execute(text("UPDATE ap.quotation SET rfq_id = 12 WHERE id = 24"))

    result = _run(engine)

    assert 1 in result.plan.blocked
    assert any("quotation.rfq_id" in r and "SET NULL" in r for r in result.plan.blocked[1])
    assert result.deleted_pr_ids == [2]
    assert _count(engine, "rfq", "id = 12") == 1


def test_cross_pr_selected_quotation_blocks(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2, with_quotation=False)
        conn.execute(text("UPDATE ap.purchase_requisition SET selected_quotation_id = 14 WHERE id = 2"))

    plan = _plan(engine)

    assert 1 in plan.blocked
    assert any("purchase_requisition.selected_quotation_id" in r for r in plan.blocked[1])
    assert plan.eligible == [2]


def test_fk_discovered_only_in_the_database_blocks():
    """A constraint that exists in the DB but in no ORM model is still honoured."""

    engine = _make_engine(DDL + [
        """CREATE TABLE ap.custom_ref (
            id INTEGER PRIMARY KEY, rfq_vendor_id INTEGER,
            CONSTRAINT fk_custom_rfq_vendor FOREIGN KEY (rfq_vendor_id) REFERENCES rfq_vendor(id) ON DELETE CASCADE)""",
    ])
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ap.vendor (vendor_id, name) VALUES (1, 'AQUA')"))
        _seed_pr(conn, 1)
        conn.execute(text("INSERT INTO ap.custom_ref (id, rfq_vendor_id) VALUES (1, 13)"))

    result = _run(engine)

    assert result.executed is False
    assert any("custom_ref.rfq_vendor_id" in r for r in result.plan.blocked[1])
    assert _count(engine, "custom_ref") == 1
    assert _count(engine, "purchase_requisition") == 1


def test_missing_cascade_chain_aborts_before_anything_changes():
    ddl = [
        s.replace("REFERENCES rfq(id) ON DELETE CASCADE", "REFERENCES rfq(id)")
        if "fk_rfq_vendor_rfq" in s else s
        for s in DDL
    ]
    engine = _make_engine(ddl)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ap.vendor (vendor_id, name) VALUES (1, 'AQUA')"))
        _seed_pr(conn, 1)

    with pytest.raises(PrResetError, match="rfq_vendor.rfq_id"):
        _run(engine)

    assert _count(engine, "purchase_requisition") == 1


# =========================================================
# Rollback
# =========================================================


def test_verification_failure_rolls_back_everything(engine, monkeypatch):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)

    def _fail(self, *args, **kwargs):
        raise PrResetError("forced verification failure")

    monkeypatch.setattr(PrResetService, "_verify", _fail)

    with pytest.raises(PrResetError, match="forced"):
        _run(engine)

    for table in FAMILY:
        assert _count(engine, table) == 2, table


def test_database_error_mid_delete_rolls_back_everything(engine, monkeypatch):
    """If planning ever missed a blocker, the FK itself fails the DELETE and
    the whole batch - including otherwise-eligible PRs - is rolled back."""

    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        conn.execute(text("INSERT INTO ap.purchase_order (id, pr_id) VALUES (900, 1)"))

    real_plan = PrResetService.plan

    def _plan_missing_blockers(self, pr_ids=None):
        plan = real_plan(self, pr_ids)
        return ResetPlan(eligible=sorted(set(plan.eligible) | set(plan.blocked)), blocked={},
                         cascade_counts=plan.cascade_counts)

    monkeypatch.setattr(PrResetService, "plan", _plan_missing_blockers)

    with pytest.raises(IntegrityError):
        _run(engine)

    assert _count(engine, "purchase_requisition") == 2
    assert _count(engine, "purchase_order") == 1
