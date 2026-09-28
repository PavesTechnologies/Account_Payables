# Backend/tests/test_pr_bulk_cleanup.py
"""Admin bulk PR cleanup (pr_bulk_cleanup_service.py +
DELETE /procurement/admin/purchase-requisitions).

Like test_pr_reset.py, runs against a REAL database engine because what is
under test is the database's own FK behaviour: CASCADE, NO ACTION, SET NULL
and transaction rollback. An in-memory SQLite database is attached as schema
``ap`` with foreign keys enforced; the DDL mirrors the FK names, ON DELETE
rules and FK-less soft references in Database/schema.sql (trimmed to the
columns that matter).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import procurement_admin_route
from Backend.Business_Layer.services.pr_bulk_cleanup_service import (
    PrBulkCleanupService,
    PrCleanupBlockedError,
    PrCleanupError,
    PrCleanupNotFoundError,
)

DDL = [
    "CREATE TABLE ap.vendor (vendor_id INTEGER PRIMARY KEY, name TEXT)",
    """CREATE TABLE ap.vendor_bank (
        vendor_bank_id INTEGER PRIMARY KEY, vendor_id INTEGER NOT NULL,
        CONSTRAINT vendor_bank_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id) ON DELETE CASCADE)""",
    "CREATE TABLE ap.unit_of_measure (id INTEGER PRIMARY KEY, code TEXT)",
    "CREATE TABLE ap.audit_log (audit_log_id INTEGER PRIMARY KEY, table_name TEXT, record_id INTEGER)",
    """CREATE TABLE ap.purchase_requisition (
        id INTEGER PRIMARY KEY, pr_number TEXT, selected_quotation_id INTEGER,
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
        id INTEGER PRIMARY KEY, pr_id INTEGER NOT NULL, quotation_id INTEGER, vendor_id INTEGER NOT NULL,
        CONSTRAINT fk_po_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id),
        CONSTRAINT fk_po_quotation FOREIGN KEY (quotation_id) REFERENCES quotation(id),
        CONSTRAINT fk_po_vendor FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id))""",
    """CREATE TABLE ap.purchase_order_line (
        id INTEGER PRIMARY KEY, po_id INTEGER NOT NULL, pr_line_id INTEGER,
        CONSTRAINT fk_po_line_po FOREIGN KEY (po_id) REFERENCES purchase_order(id) ON DELETE CASCADE,
        CONSTRAINT fk_po_line_pr_line FOREIGN KEY (pr_line_id) REFERENCES purchase_requisition_line(id))""",
    """CREATE TABLE ap.goods_receipt (
        grn_id INTEGER PRIMARY KEY, po_id INTEGER, vendor_id INTEGER NOT NULL,
        CONSTRAINT fk_goods_receipt_po FOREIGN KEY (po_id) REFERENCES purchase_order(id),
        CONSTRAINT goods_receipt_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id))""",
    # po_line_id: no FK in the real schema (ORM-only join).
    """CREATE TABLE ap.goods_receipt_line (
        grn_line_id INTEGER PRIMARY KEY, grn_id INTEGER NOT NULL, po_line_id INTEGER,
        CONSTRAINT goods_receipt_line_grn_id_fkey FOREIGN KEY (grn_id) REFERENCES goods_receipt(grn_id) ON DELETE CASCADE)""",
    # po_id: no FK in the real schema (ORM-only join).
    """CREATE TABLE ap.invoice (
        invoice_id INTEGER PRIMARY KEY, vendor_id INTEGER NOT NULL, po_id INTEGER, grn_id INTEGER,
        CONSTRAINT invoice_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id),
        CONSTRAINT invoice_grn_id_fkey FOREIGN KEY (grn_id) REFERENCES goods_receipt(grn_id))""",
    # po_line_id: no FK in the real schema (ORM-only join).
    """CREATE TABLE ap.invoice_line (
        invoice_line_id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL, po_line_id INTEGER,
        CONSTRAINT invoice_line_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES invoice(invoice_id) ON DELETE CASCADE)""",
    """CREATE TABLE ap.payment (
        payment_id INTEGER PRIMARY KEY, vendor_id INTEGER NOT NULL,
        CONSTRAINT payment_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id))""",
    """CREATE TABLE ap.payment_invoice (
        id INTEGER PRIMARY KEY, payment_id INTEGER NOT NULL, invoice_id INTEGER NOT NULL,
        CONSTRAINT payment_invoice_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES payment(payment_id) ON DELETE CASCADE,
        CONSTRAINT payment_invoice_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES invoice(invoice_id))""",
    """CREATE TABLE ap.vendor_nda (
        nda_id INTEGER PRIMARY KEY, pr_id INTEGER, vendor_id INTEGER NOT NULL,
        CONSTRAINT fk_vendor_nda_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id),
        CONSTRAINT fk_vendor_nda_vendor FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id))""",
    """CREATE TABLE ap.vendor_onboarding_request (
        id INTEGER PRIMARY KEY, pr_id INTEGER NOT NULL, vendor_id INTEGER,
        CONSTRAINT fk_vor_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id),
        CONSTRAINT fk_vor_vendor FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id))""",
]

SCOPE_TABLES = [
    "purchase_requisition", "purchase_requisition_line", "quotation", "rfq", "rfq_vendor",
    "purchase_order", "purchase_order_line", "goods_receipt", "goods_receipt_line",
    "vendor_nda", "vendor_onboarding_request",
]


def _make_engine(ddl=DDL):
    # check_same_thread=False: TestClient runs the route in a worker thread.
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("ATTACH DATABASE ':memory:' AS ap")
        cur.close()

    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
        conn.execute(text("INSERT INTO ap.vendor (vendor_id, name) VALUES (1, 'AQUA')"))
        conn.execute(text("INSERT INTO ap.vendor_bank (vendor_bank_id, vendor_id) VALUES (1, 1)"))
        conn.execute(text("INSERT INTO ap.unit_of_measure (id, code) VALUES (1, 'EA')"))
    return engine


def _seed_pr(conn, pr_id, *, with_po=True):
    """A PR with its whole transactional family. Ids are pr_id*100 + offset.

    PO -> quotation, PO line -> PR line and PR -> selected quotation are all
    NO ACTION references INSIDE the scope, so the delete order matters.
    """

    b = pr_id * 100
    ex = lambda sql, **p: conn.execute(text(sql), p)  # noqa: E731
    ex("INSERT INTO ap.purchase_requisition (id, pr_number) VALUES (:id, :n)", id=pr_id, n=f"PR-{pr_id:06d}")
    ex("INSERT INTO ap.purchase_requisition_line (id, pr_id) VALUES (:id, :pr)", id=b + 1, pr=pr_id)
    ex("INSERT INTO ap.rfq (id, pr_id) VALUES (:id, :pr)", id=b + 2, pr=pr_id)
    ex("INSERT INTO ap.rfq_vendor (id, rfq_id, vendor_id) VALUES (:id, :rfq, 1)", id=b + 3, rfq=b + 2)
    ex("INSERT INTO ap.quotation (id, pr_id, rfq_id, vendor_id) VALUES (:id, :pr, :rfq, 1)",
       id=b + 4, pr=pr_id, rfq=b + 2)
    ex("UPDATE ap.purchase_requisition SET selected_quotation_id = :q WHERE id = :id", q=b + 4, id=pr_id)
    ex("INSERT INTO ap.vendor_nda (nda_id, pr_id, vendor_id) VALUES (:id, :pr, 1)", id=b + 5, pr=pr_id)
    ex("INSERT INTO ap.vendor_onboarding_request (id, pr_id, vendor_id) VALUES (:id, :pr, 1)", id=b + 6, pr=pr_id)
    if with_po:
        ex("INSERT INTO ap.purchase_order (id, pr_id, quotation_id, vendor_id) VALUES (:id, :pr, :q, 1)",
           id=b + 7, pr=pr_id, q=b + 4)
        ex("INSERT INTO ap.purchase_order_line (id, po_id, pr_line_id) VALUES (:id, :po, :prl)",
           id=b + 8, po=b + 7, prl=b + 1)
        ex("INSERT INTO ap.goods_receipt (grn_id, po_id, vendor_id) VALUES (:id, :po, 1)", id=b + 9, po=b + 7)
        ex("INSERT INTO ap.goods_receipt_line (grn_line_id, grn_id, po_line_id) VALUES (:id, :grn, :pol)",
           id=b + 10, grn=b + 9, pol=b + 8)
    ex("INSERT INTO ap.audit_log (table_name, record_id) VALUES ('purchase_requisition', :id)", id=pr_id)


def _seed_unrelated(conn):
    """AP data not traceable to any PR - must survive every cleanup."""

    for sql in [
        "INSERT INTO ap.vendor_nda (nda_id, pr_id, vendor_id) VALUES (9001, NULL, 1)",
        "INSERT INTO ap.goods_receipt (grn_id, po_id, vendor_id) VALUES (9002, NULL, 1)",
        "INSERT INTO ap.goods_receipt_line (grn_line_id, grn_id, po_line_id) VALUES (9003, 9002, NULL)",
        "INSERT INTO ap.invoice (invoice_id, vendor_id, po_id, grn_id) VALUES (9004, 1, NULL, 9002)",
        "INSERT INTO ap.invoice_line (invoice_line_id, invoice_id, po_line_id) VALUES (9005, 9004, NULL)",
        "INSERT INTO ap.payment (payment_id, vendor_id) VALUES (9006, 1)",
        "INSERT INTO ap.payment_invoice (id, payment_id, invoice_id) VALUES (9007, 9006, 9004)",
        "INSERT INTO ap.audit_log (table_name, record_id) VALUES ('invoice', 9004)",
    ]:
        conn.execute(text(sql))


@pytest.fixture
def engine():
    return _make_engine()


def _count(engine, table, where="1=1", **params):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM ap.{table} WHERE {where}"), params).scalar_one()


def _counts(engine):
    return {t: _count(engine, t) for t in SCOPE_TABLES}


def _run(engine):
    with Session(engine) as db:
        return PrBulkCleanupService(db).delete_all_purchase_requisitions()


def _run_ids(engine, pr_ids):
    with Session(engine) as db:
        return PrBulkCleanupService(db).delete_purchase_requisitions(pr_ids)


def _run_one(engine, pr_id):
    with Session(engine) as db:
        return PrBulkCleanupService(db).delete_purchase_requisition(pr_id)


_SEEDED_PKS = {"goods_receipt": "grn_id", "goods_receipt_line": "grn_line_id", "vendor_nda": "nda_id"}


def _family(engine, pr_id):
    """Row counts of every scope table restricted to one PR's seeded ids
    (_seed_pr numbers them pr_id*100 + offset)."""

    counts = {"purchase_requisition": _count(engine, "purchase_requisition", "id = :id", id=pr_id)}
    for table in SCOPE_TABLES[1:]:
        pk = _SEEDED_PKS.get(table, "id")
        counts[table] = _count(engine, table, f"{pk} BETWEEN :lo AND :hi", lo=pr_id * 100, hi=pr_id * 100 + 99)
    return counts


# =========================================================
# Successful deletion
# =========================================================


def test_deletes_all_prs_and_every_dependent_row(engine):
    with engine.begin() as conn:
        for pr_id in (1, 2, 3):
            _seed_pr(conn, pr_id)

    result = _run(engine)

    assert result.deleted_counts == {t: 3 for t in SCOPE_TABLES}
    assert _counts(engine) == {t: 0 for t in SCOPE_TABLES}


def test_cascade_removes_lines_quotations_rfqs_and_rfq_vendors(engine):
    """Only the headers, POs, GRNs, NDAs and onboarding requests are deleted
    directly; the rest must go through the existing ON DELETE CASCADE."""

    with engine.begin() as conn:
        _seed_pr(conn, 1, with_po=False)

    result = _run(engine)

    for table in ["purchase_requisition_line", "quotation", "rfq", "rfq_vendor"]:
        assert result.deleted_counts[table] == 1, table
        assert _count(engine, table) == 0, table


def test_purchase_order_children_are_removed_before_the_po(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)

    result = _run(engine)

    for table in ["purchase_order", "purchase_order_line", "goods_receipt", "goods_receipt_line"]:
        assert result.deleted_counts[table] == 1, table
        assert _count(engine, table) == 0, table


def test_pr_linked_nda_and_onboarding_requests_are_deleted(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1, with_po=False)

    result = _run(engine)

    assert result.deleted_counts["vendor_nda"] == 1
    assert result.deleted_counts["vendor_onboarding_request"] == 1
    assert _count(engine, "vendor_nda") == 0
    assert _count(engine, "vendor_onboarding_request") == 0


def test_unrelated_ap_data_is_untouched(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_unrelated(conn)

    _run(engine)

    assert _count(engine, "vendor_nda", "nda_id = 9001") == 1
    assert _count(engine, "goods_receipt", "grn_id = 9002") == 1
    assert _count(engine, "goods_receipt_line", "grn_line_id = 9003") == 1
    for table in ["invoice", "invoice_line", "payment", "payment_invoice"]:
        assert _count(engine, table) == 1, table
    for table in ["vendor", "vendor_bank", "unit_of_measure"]:
        assert _count(engine, table) == 1, table
    # Audit history is preserved, including the deleted PR's own entries.
    assert _count(engine, "audit_log") == 2


def test_unrelated_purchase_order_is_untouched():
    """purchase_order.pr_id is NOT NULL in the real schema, so every PO is
    PR-linked today; this proves the delete is still scoped to the captured
    PR ids if that constraint is ever relaxed."""

    engine = _make_engine([
        s.replace("pr_id INTEGER NOT NULL, quotation_id", "pr_id INTEGER, quotation_id") for s in DDL
    ])
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        conn.execute(text("INSERT INTO ap.purchase_order (id, pr_id, vendor_id) VALUES (9100, NULL, 1)"))
        conn.execute(text("INSERT INTO ap.purchase_order_line (id, po_id) VALUES (9101, 9100)"))

    result = _run(engine)

    assert result.deleted_counts["purchase_order"] == 1
    assert _count(engine, "purchase_order", "id = 9100") == 1
    assert _count(engine, "purchase_order_line", "id = 9101") == 1


def test_foreign_key_constraints_are_unchanged(engine):
    def _fks():
        with engine.connect() as conn:
            insp = inspect(conn)
            return {
                (table, fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"],
                 (fk.get("options") or {}).get("ondelete"))
                for table in insp.get_table_names(schema="ap")
                for fk in insp.get_foreign_keys(table, schema="ap")
            }

    with engine.begin() as conn:
        _seed_pr(conn, 1)
    before = _fks()

    _run(engine)

    assert _fks() == before


# =========================================================
# No data / idempotency
# =========================================================


def test_no_prs_returns_zero_counts_and_changes_nothing(engine):
    with engine.begin() as conn:
        _seed_unrelated(conn)

    result = _run(engine)

    assert result.purchase_requisitions == 0
    assert result.deleted_counts == {t: 0 for t in SCOPE_TABLES}
    assert _count(engine, "vendor_nda") == 1
    assert _count(engine, "invoice") == 1


def test_repeated_execution_is_safe(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_unrelated(conn)

    first = _run(engine)
    second = _run(engine)

    assert first.purchase_requisitions == 1
    assert second.deleted_counts == {t: 0 for t in SCOPE_TABLES}
    assert _count(engine, "invoice") == 1


# =========================================================
# Blockers - nothing outside the scope may be deleted or orphaned
# =========================================================


@pytest.mark.parametrize(
    "blocker_sql, expected_ref",
    [
        # Soft reference (no FK): the DB alone would let the PO go and orphan the invoice.
        ("INSERT INTO ap.invoice (invoice_id, vendor_id, po_id) VALUES (900, 1, 107)", "invoice.po_id"),
        ("INSERT INTO ap.invoice (invoice_id, vendor_id, grn_id) VALUES (900, 1, 109)", "invoice.grn_id"),
        ("INSERT INTO ap.invoice (invoice_id, vendor_id) VALUES (900, 1); "
         "INSERT INTO ap.invoice_line (invoice_line_id, invoice_id, po_line_id) VALUES (901, 900, 108)",
         "invoice_line.po_line_id"),
        # An unrelated GRN's line pointing at a PR-linked PO line.
        ("INSERT INTO ap.goods_receipt (grn_id, po_id, vendor_id) VALUES (900, NULL, 1); "
         "INSERT INTO ap.goods_receipt_line (grn_line_id, grn_id, po_line_id) VALUES (901, 900, 108)",
         "goods_receipt_line.po_line_id"),
    ],
)
def test_reference_from_outside_the_scope_blocks_everything(engine, blocker_sql, expected_ref):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        for stmt in blocker_sql.split("; "):
            conn.execute(text(stmt))
    before = _counts(engine)

    with pytest.raises(PrCleanupBlockedError) as exc_info:
        _run(engine)

    assert expected_ref in str(exc_info.value)
    assert _counts(engine) == before
    assert _count(engine, expected_ref.split(".")[0]) >= 1


def test_fk_discovered_only_in_the_database_blocks():
    """A constraint in the DB but in no ORM model or known list is still honoured -
    here a CASCADE that would silently delete out-of-scope rows."""

    engine = _make_engine(DDL + [
        """CREATE TABLE ap.custom_ref (
            id INTEGER PRIMARY KEY, po_line_id INTEGER,
            CONSTRAINT fk_custom_po_line FOREIGN KEY (po_line_id) REFERENCES purchase_order_line(id) ON DELETE CASCADE)""",
    ])
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        conn.execute(text("INSERT INTO ap.custom_ref (id, po_line_id) VALUES (1, 108)"))

    with pytest.raises(PrCleanupBlockedError, match="custom_ref.po_line_id"):
        _run(engine)

    assert _count(engine, "custom_ref") == 1
    assert _count(engine, "purchase_requisition") == 1


def test_missing_cascade_chain_aborts_before_anything_changes():
    engine = _make_engine([
        s.replace("REFERENCES purchase_order(id) ON DELETE CASCADE", "REFERENCES purchase_order(id)")
        for s in DDL
    ])
    with engine.begin() as conn:
        _seed_pr(conn, 1)
    before = _counts(engine)

    with pytest.raises(PrCleanupError, match="purchase_order_line.po_id"):
        _run(engine)

    assert _counts(engine) == before


# =========================================================
# Rollback
# =========================================================


def test_verification_failure_rolls_back_everything(engine, monkeypatch):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
    before = _counts(engine)

    def _fail(self, *args, **kwargs):
        raise PrCleanupError("forced verification failure")

    monkeypatch.setattr(PrBulkCleanupService, "_verify", _fail)

    with pytest.raises(PrCleanupError, match="forced"):
        _run(engine)

    assert _counts(engine) == before


def test_database_error_on_the_last_delete_rolls_back_the_earlier_ones(monkeypatch):
    """If the blocker check ever missed something, the FK itself fails the
    final PR delete - and the GRN / PO / NDA / onboarding deletes that already
    ran in the same transaction are rolled back with it."""

    engine = _make_engine(DDL + [
        """CREATE TABLE ap.custom_ref (
            id INTEGER PRIMARY KEY, pr_id INTEGER,
            CONSTRAINT fk_custom_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id))""",
    ])
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        conn.execute(text("INSERT INTO ap.custom_ref (id, pr_id) VALUES (1, 2)"))
    before = _counts(engine)

    monkeypatch.setattr(
        PrBulkCleanupService, "_require_no_surviving_references", staticmethod(lambda *a, **k: None)
    )

    with pytest.raises(IntegrityError):
        _run(engine)

    assert _counts(engine) == before


# =========================================================
# Route, end to end on a real session
# =========================================================


def _client(engine, permissions=("PR_ADMIN_PURGE",)):
    class _AuthAndRealDB(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "admin-1", "permissions": list(permissions)}
            db = Session(engine)
            request.state.db = db
            try:
                return await call_next(request)
            finally:
                db.close()

    app = FastAPI()
    app.add_middleware(_AuthAndRealDB)
    app.include_router(procurement_admin_route.router, prefix="/apm/procurement/admin")
    return TestClient(app)


URL = "/apm/procurement/admin/purchase-requisitions"
DELETE_ALL = {"delete_all": True}


def _delete(engine, path=URL, json=DELETE_ALL, **kwargs):
    return _client(engine, **kwargs).request("DELETE", path, json=json)


def test_route_deletes_everything_and_reports_counts(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        _seed_unrelated(conn)

    response = _delete(engine)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "All Purchase Requisition data deleted successfully."
    assert body["deleted_counts"] == {
        "purchase_requisitions": 2, "purchase_orders": 2, "purchase_requisition_lines": 2,
        "quotations": 2, "rfqs": 2, "vendor_nda": 2, "vendor_onboarding_requests": 2,
        "rfq_vendors": 2, "purchase_order_lines": 2, "goods_receipts": 2, "goods_receipt_lines": 2,
    }
    assert _count(engine, "purchase_requisition") == 0
    assert _count(engine, "invoice") == 1

    again = _delete(engine)
    assert again.status_code == 200
    assert again.json()["message"] == "No Purchase Requisition records found."
    assert set(again.json()["deleted_counts"].values()) == {0}


def test_route_returns_409_and_deletes_nothing_when_blocked(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        conn.execute(text("INSERT INTO ap.invoice (invoice_id, vendor_id, po_id) VALUES (900, 1, 107)"))
    before = _counts(engine)

    response = _delete(engine)

    assert response.status_code == 409
    assert "invoice (1)" in response.json()["detail"]
    assert "Nothing was deleted" in response.json()["detail"]
    assert _counts(engine) == before


def test_route_returns_clean_500_and_deletes_nothing_on_failure(engine, monkeypatch):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
    before = _counts(engine)

    def _boom(self, *args, **kwargs):
        raise IntegrityError("DELETE FROM ap.purchase_requisition ...", {}, Exception("fk violation"))

    monkeypatch.setattr(PrBulkCleanupService, "_verify", _boom)

    response = _delete(engine)

    assert response.status_code == 500
    assert response.json() == {"detail": "Purchase Requisition cleanup failed. No data was deleted."}
    assert _counts(engine) == before


def test_route_forbidden_without_admin_permission_deletes_nothing(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)

    response = _delete(engine, permissions=("PR_VIEW", "PR_DELETE", "PR_CREATE"))

    assert response.status_code == 403
    assert _count(engine, "purchase_requisition") == 1


# =========================================================
# Individual delete (service)
# =========================================================

FULL_FAMILY = {t: 1 for t in SCOPE_TABLES}
NO_PO_FAMILY = {**FULL_FAMILY, "purchase_order": 0, "purchase_order_line": 0,
                "goods_receipt": 0, "goods_receipt_line": 0}
EMPTY_FAMILY = {t: 0 for t in SCOPE_TABLES}
FINANCIAL_AND_MASTER = ["invoice", "invoice_line", "payment", "payment_invoice",
                        "vendor", "vendor_bank", "unit_of_measure", "audit_log"]


def _snapshot(engine, tables=FINANCIAL_AND_MASTER):
    return {t: _count(engine, t) for t in tables}


def test_individual_deletes_only_that_pr_and_its_po_grn_nda_onboarding(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        _seed_unrelated(conn)
    unrelated_before = _snapshot(engine)

    result = _run_one(engine, 1)

    assert result.deleted_counts == FULL_FAMILY
    assert _family(engine, 1) == EMPTY_FAMILY
    assert _family(engine, 2) == FULL_FAMILY
    assert _count(engine, "vendor_nda", "nda_id = 9001") == 1
    assert _count(engine, "goods_receipt", "grn_id = 9002") == 1
    assert _snapshot(engine) == unrelated_before


def test_individual_pr_without_po(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1, with_po=False)
        _seed_pr(conn, 2)

    result = _run_one(engine, 1)

    assert result.deleted_counts == NO_PO_FAMILY
    assert _family(engine, 2) == FULL_FAMILY


def test_individual_missing_pr_is_not_found_and_changes_nothing(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
    before = _counts(engine)

    with pytest.raises(PrCleanupNotFoundError) as exc_info:
        _run_one(engine, 999)

    assert exc_info.value.missing_ids == [999]
    assert _counts(engine) == before


def test_individual_invoice_linked_pr_is_blocked(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        conn.execute(text("INSERT INTO ap.invoice (invoice_id, vendor_id, grn_id) VALUES (900, 1, 109)"))
    before = _counts(engine)

    with pytest.raises(PrCleanupBlockedError, match="invoice.grn_id"):
        _run_one(engine, 1)

    assert _counts(engine) == before
    # The other PR is not linked to the invoice and can still be deleted on its own.
    assert _run_one(engine, 2).purchase_requisitions == 1


def test_individual_blocked_by_another_prs_reference(engine):
    """PR 2's PO points at PR 1's quotation: deleting PR 1 alone would leave a
    surviving row dangling, so it is blocked; deleting both together is fine."""

    with engine.begin() as conn:
        _seed_pr(conn, 1, with_po=False)
        _seed_pr(conn, 2)
        conn.execute(text("UPDATE ap.purchase_order SET quotation_id = 104 WHERE id = 207"))
    before = _counts(engine)

    with pytest.raises(PrCleanupBlockedError, match="purchase_order.quotation_id"):
        _run_one(engine, 1)
    assert _counts(engine) == before

    assert _run_ids(engine, [1, 2]).purchase_requisitions == 2


def test_individual_rollback_on_failure(engine, monkeypatch):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
    before = _counts(engine)

    def _fail(self, *args, **kwargs):
        raise PrCleanupError("forced verification failure")

    monkeypatch.setattr(PrBulkCleanupService, "_verify", _fail)

    with pytest.raises(PrCleanupError, match="forced"):
        _run_one(engine, 1)

    assert _counts(engine) == before


# =========================================================
# Bulk delete of selected PRs (service)
# =========================================================


def test_bulk_deletes_exactly_the_selected_prs_with_mixed_dependencies(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        _seed_pr(conn, 3, with_po=False)
        _seed_unrelated(conn)
    unrelated_before = _snapshot(engine)

    result = _run_ids(engine, [3, 1])

    assert result.deleted_counts == {t: FULL_FAMILY[t] + NO_PO_FAMILY[t] for t in SCOPE_TABLES}
    assert _family(engine, 1) == EMPTY_FAMILY
    assert _family(engine, 3) == EMPTY_FAMILY
    assert _family(engine, 2) == FULL_FAMILY
    assert _snapshot(engine) == unrelated_before


def test_bulk_one_blocked_pr_deletes_none(engine):
    with engine.begin() as conn:
        for pr_id in (1, 2, 3):
            _seed_pr(conn, pr_id)
        conn.execute(text("INSERT INTO ap.invoice (invoice_id, vendor_id, po_id) VALUES (900, 1, 207)"))
    before = _counts(engine)

    with pytest.raises(PrCleanupBlockedError, match="invoice.po_id"):
        _run_ids(engine, [1, 2, 3])

    assert _counts(engine) == before


def test_bulk_missing_pr_deletes_none(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
    before = _counts(engine)

    with pytest.raises(PrCleanupNotFoundError) as exc_info:
        _run_ids(engine, [1, 998, 2, 999])

    assert exc_info.value.missing_ids == [998, 999]
    assert _counts(engine) == before


def test_bulk_database_error_mid_batch_rolls_back_everything(monkeypatch):
    engine = _make_engine(DDL + [
        """CREATE TABLE ap.custom_ref (
            id INTEGER PRIMARY KEY, pr_id INTEGER,
            CONSTRAINT fk_custom_pr FOREIGN KEY (pr_id) REFERENCES purchase_requisition(id))""",
    ])
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        conn.execute(text("INSERT INTO ap.custom_ref (id, pr_id) VALUES (1, 2)"))
    before = _counts(engine)
    monkeypatch.setattr(
        PrBulkCleanupService, "_require_no_surviving_references", staticmethod(lambda *a, **k: None)
    )

    with pytest.raises(IntegrityError):
        _run_ids(engine, [1, 2])

    assert _counts(engine) == before


def test_bulk_empty_list_is_rejected(engine):
    with pytest.raises(ValueError):
        _run_ids(engine, [])


# =========================================================
# Individual + bulk routes, end to end on a real session
# =========================================================


def test_route_individual_delete(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)

    response = _delete(engine, f"{URL}/1", json=None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "Purchase Requisition deleted successfully."
    assert body["deleted_counts"] == {
        "purchase_requisitions": 1, "purchase_orders": 1, "purchase_requisition_lines": 1,
        "quotations": 1, "rfqs": 1, "vendor_nda": 1, "vendor_onboarding_requests": 1,
        "rfq_vendors": 1, "purchase_order_lines": 1, "goods_receipts": 1, "goods_receipt_lines": 1,
    }
    assert _family(engine, 1) == EMPTY_FAMILY
    assert _family(engine, 2) == FULL_FAMILY


def test_route_individual_404(engine):
    response = _delete(engine, f"{URL}/42", json=None)
    assert response.status_code == 404
    assert "42" in response.json()["detail"]


def test_route_individual_409_when_invoice_linked(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        conn.execute(text("INSERT INTO ap.invoice (invoice_id, vendor_id) VALUES (900, 1)"))
        conn.execute(text(
            "INSERT INTO ap.invoice_line (invoice_line_id, invoice_id, po_line_id) VALUES (901, 900, 108)"
        ))
    before = _counts(engine)

    response = _delete(engine, f"{URL}/1", json=None)

    assert response.status_code == 409
    assert "invoice_line (1)" in response.json()["detail"]
    assert _counts(engine) == before


def test_route_individual_500_is_generic(engine, monkeypatch):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
    before = _counts(engine)

    def _boom(self, *args, **kwargs):
        raise IntegrityError("DELETE FROM ap.purchase_requisition ...", {}, Exception("fk violation"))

    monkeypatch.setattr(PrBulkCleanupService, "_verify", _boom)

    response = _delete(engine, f"{URL}/1", json=None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Purchase Requisition cleanup failed. No data was deleted."}
    assert _counts(engine) == before


def test_route_individual_forbidden_without_permission(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)

    response = _delete(engine, f"{URL}/1", json=None, permissions=("PR_DELETE",))

    assert response.status_code == 403
    assert _count(engine, "purchase_requisition") == 1


def test_route_bulk_delete_selected(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        _seed_pr(conn, 3, with_po=False)

    response = _delete(engine, json={"pr_ids": [1, 3]})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "Purchase Requisitions deleted successfully."
    assert body["requested_pr_count"] == 2
    assert body["deleted_counts"] == {
        "purchase_requisitions": 2, "purchase_orders": 1, "purchase_requisition_lines": 2,
        "quotations": 2, "rfqs": 2, "vendor_nda": 2, "vendor_onboarding_requests": 2,
        "rfq_vendors": 2, "purchase_order_lines": 1, "goods_receipts": 1, "goods_receipt_lines": 1,
    }
    assert _family(engine, 2) == FULL_FAMILY


def test_route_bulk_404_when_any_pr_missing(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
    before = _counts(engine)

    response = _delete(engine, json={"pr_ids": [1, 77]})

    assert response.status_code == 404
    assert "77" in response.json()["detail"]
    assert _counts(engine) == before


def test_route_bulk_409_when_any_pr_blocked(engine):
    with engine.begin() as conn:
        _seed_pr(conn, 1)
        _seed_pr(conn, 2)
        conn.execute(text("INSERT INTO ap.invoice (invoice_id, vendor_id, po_id) VALUES (900, 1, 207)"))
    before = _counts(engine)

    response = _delete(engine, json={"pr_ids": [1, 2]})

    assert response.status_code == 409
    assert _counts(engine) == before


@pytest.mark.parametrize(
    "body",
    [None, {}, {"pr_ids": []}, {"pr_ids": None}, {"pr_ids": [1, 1]}, {"pr_ids": [0]}, {"pr_ids": ["x"]},
     {"pr_ids": [1], "delete_all": True}, {"delete_all": False}],
    ids=["no_body", "empty_body", "empty_list", "null_list", "duplicates", "non_positive", "non_integer",
         "ids_and_delete_all", "delete_all_false"],
)
def test_route_bulk_rejects_invalid_requests_and_never_deletes_all(engine, body):
    with engine.begin() as conn:
        _seed_pr(conn, 1)

    response = _delete(engine, json=body)

    assert response.status_code == 422
    assert _count(engine, "purchase_requisition") == 1
