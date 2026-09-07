# Backend/tests/test_procurement_authorization.py
"""Authorization tests for the Procurement APIs.

Follows the project's existing route-test convention (see test_new_routes.py):
a minimal FastAPI app with a fake auth/db middleware, and the
ProcurementService monkeypatched so these tests only verify the
permission_based_access dependency wiring - not business logic (that's
covered by test_pr_approval_workflow.py / test_rfq_workflow.py / etc).

Covers:
- the three UMS personas (PR Creator, PR Approver, Procurement Officer)
  against the full Procurement endpoint matrix
- 401 when there is no authenticated user
- 403 when the required permission is missing
- normalization: case-insensitivity, permissions as a bare string,
  whitespace, duplicates, and permissions missing entirely from the JWT
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.middleware.permission_base_access import permission_based_access
from Backend.API_Layer.routes import procurement_route


PR_CREATOR_PERMISSIONS = [
    "PR_VIEW",
    "PR_CREATE",
    "PR_EDIT",
    "PR_DELETE",
    "PR_SUBMIT",
    "PR_TRACK",
]

PR_APPROVER_PERMISSIONS = [
    "PR_VIEW",
    "PR_TRACK",
    "PR_APPROVAL_VIEW",
    "PR_APPROVE",
    "PR_REJECT",
]

PROCUREMENT_OFFICER_PERMISSIONS = [
    "PR_VIEW",
    "PR_TRACK",
    "QUOTATION_VIEW",
    "QUOTATION_CREATE",
    "QUOTATION_UPDATE",
    "QUOTATION_DELETE",
    "VENDOR_SELECTION_VIEW",
    "VENDOR_SELECT",
    "PO_VIEW",
    "PO_CREATE",
]


def _make_middleware(user):
    class _FakeAuthAndDBMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if user is not None:
                request.state.user = user
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    return _FakeAuthAndDBMiddleware


def _make_client(user):
    app = FastAPI()
    app.add_middleware(_make_middleware(user))
    app.include_router(procurement_route.router)
    return TestClient(app)


def _user(permissions):
    return {"user_id": "test-user", "permissions": permissions}


def _fake_pr():
    return SimpleNamespace(
        id=1,
        po_id=1,
        pr_number="PR-0001",
        department_id=1,
        purchase_category_id=1,
        status_id=1,
        priority="NORMAL",
        estimated_total=0,
        created_by="test-user",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        required_by=None,
        delivery_location=None,
        justification=None,
        selected_vendor_id=None,
        selected_quotation_id=None,
        approved_by=None,
        approved_at=None,
        approval_comment=None,
        sourcing_type=None,
        selection_reason=None,
        purchase_requisition_line=[],
        quotation=[],
    )


def _stub_service(monkeypatch, method_name, return_value=None):
    from Backend.Business_Layer.services import procurement_service

    def _stub(self, *args, **kwargs):
        return return_value if return_value is not None else _fake_pr()

    monkeypatch.setattr(procurement_service.ProcurementService, method_name, _stub)


# ---------------------------------------------------------------------------
# 401 / 403 / normalization
# ---------------------------------------------------------------------------


def test_no_authenticated_user_returns_401():
    client = _make_client(None)
    response = client.get("/purchase-requisitions")
    assert response.status_code == 401


def test_missing_permission_returns_403(monkeypatch):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    client = _make_client(_user(["QUOTATION_VIEW"]))
    response = client.get("/purchase-requisitions")
    assert response.status_code == 403


def test_permissions_missing_from_jwt_returns_403():
    client = _make_client({"user_id": "test-user"})
    response = client.get("/purchase-requisitions")
    assert response.status_code == 403


def test_correct_permission_is_allowed(monkeypatch):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    client = _make_client(_user(["PR_VIEW"]))
    response = client.get("/purchase-requisitions")
    assert response.status_code == 200


def test_case_insensitive_permission_is_allowed(monkeypatch):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    client = _make_client(_user(["pr_view"]))
    response = client.get("/purchase-requisitions")
    assert response.status_code == 200


def test_permissions_as_bare_string_is_allowed(monkeypatch):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    client = _make_client(_user("PR_VIEW"))
    response = client.get("/purchase-requisitions")
    assert response.status_code == 200


def test_whitespace_and_duplicate_permissions_are_allowed(monkeypatch):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    client = _make_client(_user([" PR_VIEW ", "PR_VIEW", "pr_view"]))
    response = client.get("/purchase-requisitions")
    assert response.status_code == 200


def test_malformed_permission_entries_are_ignored_safely(monkeypatch):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    client = _make_client(_user([None, 123, "", "   ", "PR_VIEW"]))
    response = client.get("/purchase-requisitions")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# PR Creator
# ---------------------------------------------------------------------------


@pytest.fixture
def pr_creator_client():
    return _make_client(_user(PR_CREATOR_PERMISSIONS))


def test_pr_creator_can_create_pr(monkeypatch, pr_creator_client):
    _stub_service(monkeypatch, "create_purchase_requisition")
    response = pr_creator_client.post(
        "/purchase-requisitions",
        json={"department_id": 1, "purchase_category_id": 1},
    )
    assert response.status_code == 200


def test_pr_creator_can_edit_pr(monkeypatch, pr_creator_client):
    _stub_service(monkeypatch, "update_purchase_requisition")
    response = pr_creator_client.put("/purchase-requisitions/1", json={})
    assert response.status_code == 200


def test_pr_creator_can_delete_pr(monkeypatch, pr_creator_client):
    _stub_service(monkeypatch, "delete_purchase_requisition")
    response = pr_creator_client.delete("/purchase-requisitions/1")
    assert response.status_code == 200


def test_pr_creator_can_submit_pr(monkeypatch, pr_creator_client):
    _stub_service(monkeypatch, "submit_purchase_requisition")
    response = pr_creator_client.post("/purchase-requisitions/1/submit")
    assert response.status_code == 200


def test_pr_creator_can_view_and_track_pr(monkeypatch, pr_creator_client):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    response = pr_creator_client.get("/purchase-requisitions")
    assert response.status_code == 200


def test_pr_creator_cannot_approve(pr_creator_client):
    response = pr_creator_client.post("/purchase-requisitions/1/approve", json={})
    assert response.status_code == 403


def test_pr_creator_cannot_reject(pr_creator_client):
    response = pr_creator_client.post("/purchase-requisitions/1/reject", json={"comment": "no"})
    assert response.status_code == 403


def test_pr_creator_cannot_create_quotation(pr_creator_client):
    response = pr_creator_client.post(
        "/purchase-requisitions/1/quotations",
        data={"vendor_id": "1"},
        files={"file": ("q.pdf", b"data", "application/pdf")},
    )
    assert response.status_code == 403


def test_pr_creator_cannot_select_vendor(pr_creator_client):
    response = pr_creator_client.post(
        "/purchase-requisitions/1/select-vendor", json={"quotation_id": 1}
    )
    assert response.status_code == 403


def test_pr_creator_cannot_generate_po(pr_creator_client):
    response = pr_creator_client.post("/purchase-requisitions/1/generate-po")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PR Approver
# ---------------------------------------------------------------------------


@pytest.fixture
def pr_approver_client():
    return _make_client(_user(PR_APPROVER_PERMISSIONS))


def test_pr_approver_can_view_pr(monkeypatch, pr_approver_client):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    response = pr_approver_client.get("/purchase-requisitions")
    assert response.status_code == 200


def test_pr_approver_can_view_approval_queue(monkeypatch, pr_approver_client):
    _stub_service(monkeypatch, "list_pending_approval", return_value=[])
    response = pr_approver_client.get("/purchase-requisitions/pending-approval")
    assert response.status_code == 200


def test_pr_approver_can_approve(monkeypatch, pr_approver_client):
    _stub_service(monkeypatch, "approve_purchase_requisition")
    response = pr_approver_client.post("/purchase-requisitions/1/approve", json={})
    assert response.status_code == 200


def test_pr_approver_can_reject(monkeypatch, pr_approver_client):
    _stub_service(monkeypatch, "reject_purchase_requisition")
    response = pr_approver_client.post(
        "/purchase-requisitions/1/reject", json={"comment": "no"}
    )
    assert response.status_code == 200


def test_pr_approver_cannot_create_pr(pr_approver_client):
    response = pr_approver_client.post(
        "/purchase-requisitions",
        json={"department_id": 1, "purchase_category_id": 1},
    )
    assert response.status_code == 403


def test_pr_approver_cannot_edit_pr(pr_approver_client):
    response = pr_approver_client.put("/purchase-requisitions/1", json={})
    assert response.status_code == 403


def test_pr_approver_cannot_create_quotation(pr_approver_client):
    response = pr_approver_client.post(
        "/purchase-requisitions/1/quotations",
        data={"vendor_id": "1"},
        files={"file": ("q.pdf", b"data", "application/pdf")},
    )
    assert response.status_code == 403


def test_pr_approver_cannot_select_vendor(pr_approver_client):
    response = pr_approver_client.post(
        "/purchase-requisitions/1/select-vendor", json={"quotation_id": 1}
    )
    assert response.status_code == 403


def test_pr_approver_cannot_generate_po(pr_approver_client):
    response = pr_approver_client.post("/purchase-requisitions/1/generate-po")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Procurement Officer
# ---------------------------------------------------------------------------


@pytest.fixture
def procurement_officer_client():
    return _make_client(_user(PROCUREMENT_OFFICER_PERMISSIONS))


def test_procurement_officer_can_view_track_pr(monkeypatch, procurement_officer_client):
    _stub_service(monkeypatch, "list_purchase_requisitions", return_value=[])
    response = procurement_officer_client.get("/purchase-requisitions")
    assert response.status_code == 200


def test_procurement_officer_can_view_quotations(monkeypatch, procurement_officer_client):
    _stub_service(monkeypatch, "list_quotations", return_value=[])
    response = procurement_officer_client.get("/purchase-requisitions/1/quotations")
    assert response.status_code == 200


def test_procurement_officer_can_create_quotation(monkeypatch, procurement_officer_client):
    _stub_service(monkeypatch, "create_quotation")
    response = procurement_officer_client.post(
        "/purchase-requisitions/1/quotations",
        data={"vendor_id": "1"},
        files={"file": ("q.pdf", b"data", "application/pdf")},
    )
    assert response.status_code == 200


def test_procurement_officer_can_delete_quotation(monkeypatch, procurement_officer_client):
    _stub_service(monkeypatch, "delete_quotation")
    response = procurement_officer_client.delete("/quotations/1")
    assert response.status_code == 200


def test_procurement_officer_can_select_vendor(monkeypatch, procurement_officer_client):
    _stub_service(monkeypatch, "select_vendor")
    response = procurement_officer_client.post(
        "/purchase-requisitions/1/select-vendor", json={"quotation_id": 1}
    )
    assert response.status_code == 200


def test_procurement_officer_can_generate_po(monkeypatch, procurement_officer_client):
    _stub_service(monkeypatch, "generate_purchase_order")
    response = procurement_officer_client.post("/purchase-requisitions/1/generate-po")
    assert response.status_code == 200


def test_procurement_officer_cannot_approve_pr(procurement_officer_client):
    response = procurement_officer_client.post("/purchase-requisitions/1/approve", json={})
    assert response.status_code == 403


def test_procurement_officer_cannot_reject_pr(procurement_officer_client):
    response = procurement_officer_client.post(
        "/purchase-requisitions/1/reject", json={"comment": "no"}
    )
    assert response.status_code == 403


def test_procurement_officer_cannot_create_pr(procurement_officer_client):
    response = procurement_officer_client.post(
        "/purchase-requisitions",
        json={"department_id": 1, "purchase_category_id": 1},
    )
    assert response.status_code == 403


def test_procurement_officer_cannot_edit_pr(procurement_officer_client):
    response = procurement_officer_client.put("/purchase-requisitions/1", json={})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# permission_based_access: ANY vs ALL semantics
# ---------------------------------------------------------------------------


def _any_all_client(user, require_all: bool):
    app = FastAPI()
    app.add_middleware(_make_middleware(user))

    @app.get(
        "/probe",
        dependencies=[
            Depends(permission_based_access(["PR_EDIT", "PR_SUBMIT"], require_all=require_all))
        ],
    )
    def probe():
        return {"ok": True}

    return TestClient(app)


def test_any_semantics_allows_with_only_one_of_the_required_permissions():
    client = _any_all_client(_user(["PR_EDIT"]), require_all=False)
    assert client.get("/probe").status_code == 200


def test_all_semantics_rejects_with_only_one_of_the_required_permissions():
    client = _any_all_client(_user(["PR_EDIT"]), require_all=True)
    assert client.get("/probe").status_code == 403


def test_all_semantics_allows_with_every_required_permission():
    client = _any_all_client(_user(["PR_EDIT", "PR_SUBMIT"]), require_all=True)
    assert client.get("/probe").status_code == 200
