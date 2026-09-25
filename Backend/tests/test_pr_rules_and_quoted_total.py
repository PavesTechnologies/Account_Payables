# Backend/tests/test_pr_rules_and_quoted_total.py
"""Purchase-requisition business rules and the quoted-total -> PO value chain.

Reuses the existing fake-DAO harnesses rather than building a third one:
``Workflow`` from test_pr_approval_workflow.py for PR create/update rules, and
``Workflow`` from test_rfq_workflow.py for the quotation -> vendor selection ->
PO path (it is the harness that already wires up a PurchaseOrder DAO). The
project already imports across test modules this way - see
test_rfq_authorization.py importing from test_procurement_authorization.py.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from Backend.Business_Layer.services.procurement_service import (
    PR_EDITABLE_STATUS_CODES,
    REQUIRED_BY_IN_PAST_MESSAGE,
    ProcurementService,
)
from Backend.tests.test_pr_approval_workflow import Workflow as PrWorkflow
from Backend.tests.test_rfq_workflow import Workflow as RfqWorkflow

TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
TOMORROW = TODAY + datetime.timedelta(days=1)


@pytest.fixture
def pr_wf():
    return PrWorkflow()


@pytest.fixture
def rfq_wf(monkeypatch):
    import Backend.Business_Layer.services.rfq_service as rfq_service_module

    monkeypatch.setattr(
        rfq_service_module, "send_email",
        lambda **kwargs: SimpleNamespace(
            success=True, sent_at=datetime.datetime.now(datetime.timezone.utc), error=None
        ),
    )
    return RfqWorkflow()


def _create_payload(required_by=None, **overrides):
    defaults = dict(
        department_id=10,
        purchase_category_id=20,
        priority="NORMAL",
        required_by=required_by,
        delivery_location=None,
        justification=None,
        lines=[
            SimpleNamespace(
                item_name="Office Chairs", description=None, quantity=Decimal("10"),
                uom="EA", estimated_unit_price=5000, estimated_amount=50000,
            )
        ],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _update_payload(**overrides):
    defaults = dict(
        department_id=None, purchase_category_id=None, priority=None,
        required_by=None, delivery_location=None, justification=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# 1. Required By Date may be today or later, never in the past
# ---------------------------------------------------------------------------


def test_required_by_today_is_allowed_on_create(pr_wf):
    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(required_by=TODAY), user_id="requester1"
    )

    assert pr.required_by == TODAY


def test_required_by_future_is_allowed_on_create(pr_wf):
    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(required_by=TOMORROW), user_id="requester1"
    )

    assert pr.required_by == TOMORROW


def test_required_by_in_the_past_is_rejected_on_create(pr_wf):
    with pytest.raises(ValueError) as excinfo:
        pr_wf.procurement_service.create_purchase_requisition(
            _create_payload(required_by=YESTERDAY), user_id="requester1"
        )

    assert str(excinfo.value) == "Required By Date cannot be earlier than today."


def test_required_by_is_optional_on_create(pr_wf):
    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(required_by=None), user_id="requester1"
    )

    assert pr.required_by is None


def test_required_by_today_is_allowed_on_update(pr_wf):
    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(), user_id="requester1"
    )

    updated = pr_wf.procurement_service.update_purchase_requisition(
        pr.id, _update_payload(required_by=TODAY), "requester1"
    )

    assert updated.required_by == TODAY


def test_required_by_future_is_allowed_on_update(pr_wf):
    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(), user_id="requester1"
    )

    updated = pr_wf.procurement_service.update_purchase_requisition(
        pr.id, _update_payload(required_by=TOMORROW), "requester1"
    )

    assert updated.required_by == TOMORROW


def test_required_by_in_the_past_is_rejected_on_update(pr_wf):
    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(required_by=TOMORROW), user_id="requester1"
    )

    with pytest.raises(ValueError) as excinfo:
        pr_wf.procurement_service.update_purchase_requisition(
            pr.id, _update_payload(required_by=YESTERDAY), "requester1"
        )

    assert str(excinfo.value) == REQUIRED_BY_IN_PAST_MESSAGE
    # The stored value is untouched by the rejected update.
    assert pr_wf.procurement_dao.get_purchase_requisition_by_id(pr.id).required_by == TOMORROW


def test_an_update_that_omits_required_by_keeps_the_existing_date(pr_wf):
    """An existing PR whose required_by has since fallen into the past must
    still be editable for its other fields - the validation only applies to a
    date the caller actually supplies."""

    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(required_by=TOMORROW), user_id="requester1"
    )
    pr.required_by = YESTERDAY

    updated = pr_wf.procurement_service.update_purchase_requisition(
        pr.id, _update_payload(justification="Still needed"), "requester1"
    )

    assert updated.required_by == YESTERDAY
    assert updated.justification == "Still needed"


def test_required_by_is_compared_as_a_date_not_a_timestamp(pr_wf):
    """A same-day value must pass no matter what time component rides along,
    so a date-only business field never fails on a clock difference."""

    end_of_today = datetime.datetime.combine(TODAY, datetime.time(23, 59, 59))
    start_of_today = datetime.datetime.combine(TODAY, datetime.time(0, 0, 0))

    for value in (start_of_today, end_of_today):
        ProcurementService._validate_required_by(value)

    with pytest.raises(ValueError, match="cannot be earlier than today"):
        ProcurementService._validate_required_by(
            datetime.datetime.combine(YESTERDAY, datetime.time(23, 59, 59))
        )


def test_required_by_validation_is_the_same_rule_in_both_operations(pr_wf):
    """Guards against the two paths drifting apart."""

    import inspect

    source = inspect.getsource(ProcurementService)

    assert source.count("self._validate_required_by(") == 2
    assert "_validate_required_by" in inspect.getsource(
        ProcurementService.create_purchase_requisition
    )
    assert "_validate_required_by" in inspect.getsource(
        ProcurementService.update_purchase_requisition
    )


# ---------------------------------------------------------------------------
# 2. A CANCELLED PR is updateable and stays CANCELLED
# ---------------------------------------------------------------------------


def _cancelled_pr(pr_wf):
    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(required_by=TOMORROW), user_id="requester1"
    )
    cancelled = pr_wf.procurement_service.cancel_purchase_requisition(pr.id)
    assert cancelled.status.status_code == "CANCELLED"
    return cancelled


def test_cancelled_pr_can_be_updated(pr_wf):
    pr = _cancelled_pr(pr_wf)

    updated = pr_wf.procurement_service.update_purchase_requisition(
        pr.id,
        _update_payload(
            priority="HIGH", justification="Reinstating the request",
            delivery_location="Block B", required_by=TOMORROW,
        ),
        "requester1",
    )

    assert updated.priority == "HIGH"
    assert updated.justification == "Reinstating the request"
    assert updated.delivery_location == "Block B"
    assert updated.required_by == TOMORROW


def test_updating_a_cancelled_pr_does_not_change_its_status(pr_wf):
    pr = _cancelled_pr(pr_wf)

    updated = pr_wf.procurement_service.update_purchase_requisition(
        pr.id, _update_payload(priority="URGENT"), "requester1"
    )

    assert updated.status.status_code == "CANCELLED"
    assert pr_wf.procurement_dao.get_purchase_requisition_by_id(pr.id).status.status_code == "CANCELLED"


def test_field_validation_still_applies_to_a_cancelled_pr(pr_wf):
    """Only the status restriction was lifted - every other rule stands."""

    pr = _cancelled_pr(pr_wf)

    with pytest.raises(ValueError, match="cannot be earlier than today"):
        pr_wf.procurement_service.update_purchase_requisition(
            pr.id, _update_payload(required_by=YESTERDAY), "requester1"
        )

    with pytest.raises(ValueError):
        pr_wf.procurement_service.update_purchase_requisition(
            pr.id, _update_payload(priority="NOT_A_PRIORITY"), "requester1"
        )


def test_cancelled_pr_transitions_are_unchanged(pr_wf):
    """Editing a CANCELLED PR must not reopen the status graph: CANCELLED is
    still terminal."""

    from Backend.Business_Layer.services.procurement_service import PR_TRANSITIONS

    assert PR_TRANSITIONS["CANCELLED"] == set()

    pr = _cancelled_pr(pr_wf)
    pr_wf.procurement_service.update_purchase_requisition(
        pr.id, _update_payload(priority="HIGH"), "requester1"
    )

    with pytest.raises(ValueError, match="cannot move from CANCELLED"):
        pr_wf.procurement_service.submit_purchase_requisition(pr.id, user_id="requester1")


@pytest.mark.parametrize(
    "status_code", ["PENDING_APPROVAL", "APPROVED", "VENDOR_SELECTION", "PO_GENERATED", "REJECTED"]
)
def test_other_statuses_remain_blocked_from_update(pr_wf, status_code):
    """Only CANCELLED was added to the editable set."""

    assert status_code not in PR_EDITABLE_STATUS_CODES

    pr = pr_wf.procurement_service.create_purchase_requisition(
        _create_payload(), user_id="requester1"
    )
    pr.status_id = pr_wf.registry.get_by_module_code("PURCHASE_REQUISITION", status_code).status_id
    pr_wf.registry.attach(pr)

    with pytest.raises(ValueError, match="cannot be updated"):
        pr_wf.procurement_service.update_purchase_requisition(
            pr.id, _update_payload(priority="HIGH"), "requester1"
        )


def test_editable_statuses_are_exactly_draft_returned_and_cancelled():
    assert PR_EDITABLE_STATUS_CODES == {"DRAFT", "RETURNED", "CANCELLED"}


# ---------------------------------------------------------------------------
# 3. Quotation total_amount is the grand total, and drives the PO value
# ---------------------------------------------------------------------------


QUOTED_TOTAL = Decimal("275000")


def _pr_with_selected_quotation(rfq_wf, total_amount=QUOTED_TOTAL):
    pr = rfq_wf.create_approved_pr()
    quotation = rfq_wf.procurement_service.create_quotation(
        pr_id=pr.id, vendor_id=1, file_url="quotations/q1.pdf",
        quotation_number="QT-1", quotation_date=TODAY, valid_until=TOMORROW,
        total_amount=total_amount, user_id="buyer1",
    )
    rfq_wf.procurement_service.select_vendor(pr.id, quotation.id, reason="Best price", user_id="buyer1")
    return pr, quotation


def test_quotation_header_has_no_subtotal_discount_or_tax_fields():
    """total_amount alone represents the overall/grand total quoted amount -
    no extra quotation header money fields were introduced."""

    from Backend.Data_Access_Layer.models.purchase import Quotation

    columns = set(Quotation.__table__.columns.keys())

    assert "total_amount" in columns
    for invented in ("subtotal", "discount_amount", "tax_amount", "other_charges", "grand_total"):
        assert invented not in columns, f"quotation gained a {invented} column"


def test_vendor_selection_uses_the_quotation_total_amount(rfq_wf):
    pr, quotation = _pr_with_selected_quotation(rfq_wf)

    assert quotation.total_amount == QUOTED_TOTAL
    assert pr.selected_quotation_id == quotation.id
    assert pr.selected_vendor_id == quotation.vendor_id


def test_purchase_order_value_comes_from_the_selected_quotation(rfq_wf):
    pr, quotation = _pr_with_selected_quotation(rfq_wf)
    estimated_before = pr.estimated_total

    purchase_order = rfq_wf.procurement_service.generate_purchase_order(pr.id, "buyer1")

    assert purchase_order.total_amount == QUOTED_TOTAL
    assert purchase_order.subtotal == QUOTED_TOTAL
    assert purchase_order.quotation_id == quotation.id
    # ...and NOT the requester's estimate, which was a different number.
    assert QUOTED_TOTAL != estimated_before
    assert purchase_order.total_amount != estimated_before


def test_generating_a_purchase_order_does_not_overwrite_the_pr_estimate(rfq_wf):
    pr, _ = _pr_with_selected_quotation(rfq_wf)
    estimated_before = pr.estimated_total

    rfq_wf.procurement_service.generate_purchase_order(pr.id, "buyer1")

    assert pr.estimated_total == estimated_before
    stored = rfq_wf.procurement_dao.get_purchase_requisition_by_id(pr.id)
    assert stored.estimated_total == estimated_before


@pytest.mark.parametrize("quoted", [Decimal("1"), Decimal("250000.55"), Decimal("999999.99")])
def test_any_quoted_total_flows_through_to_the_purchase_order(rfq_wf, quoted):
    pr, _ = _pr_with_selected_quotation(rfq_wf, total_amount=quoted)

    purchase_order = rfq_wf.procurement_service.generate_purchase_order(pr.id, "buyer1")

    assert purchase_order.total_amount == quoted


def test_a_quotation_without_a_total_falls_back_to_the_pr_estimate(rfq_wf):
    """total_amount is nullable, so a legacy quotation that never captured one
    must not produce a zero-value PO."""

    pr, _ = _pr_with_selected_quotation(rfq_wf, total_amount=None)
    estimated = pr.estimated_total

    purchase_order = rfq_wf.procurement_service.generate_purchase_order(pr.id, "buyer1")

    assert purchase_order.total_amount == estimated


def test_purchase_order_lines_still_come_from_the_pr_lines(rfq_wf):
    """There is no quotation_line table, so the existing PO design - lines
    derived from the PR lines - is unchanged; only the header value moved to
    the quoted total."""

    from Backend.Data_Access_Layer.models import purchase as purchase_models

    assert not hasattr(purchase_models, "QuotationLine")

    pr, _ = _pr_with_selected_quotation(rfq_wf)
    purchase_order = rfq_wf.procurement_service.generate_purchase_order(pr.id, "buyer1")

    lines = [line for line in rfq_wf.po_dao.lines if line.po_id == purchase_order.po_id]
    pr_lines = rfq_wf.procurement_dao.get_lines_by_pr_id(pr.id)

    assert len(lines) == len(pr_lines) == 1
    assert lines[0].item_name == pr_lines[0].item_name
    assert lines[0].pr_line_id == pr_lines[0].id


# ---------------------------------------------------------------------------
# GET /apm/vendor/{vendor_id}/purchase-orders serialization
#
# The wrapper responses are CONSTRUCTED IN THE ROUTE from SQLAlchemy objects.
# FastAPI only applies from_attributes to a top-level response_model, so a
# nested DTO without ConfigDict(from_attributes=True) rejected the ORM
# instance with "Input should be a valid dictionary or instance of
# PurchaseOrderDTO".
# ---------------------------------------------------------------------------


def _orm_purchase_order():
    import decimal

    from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder

    return PurchaseOrder(
        po_id=1, po_number="PO-000059", pr_id=1, vendor_id=100,
        po_date=datetime.date(2026, 9, 1), subtotal=decimal.Decimal("275000"),
        tax_amount=decimal.Decimal("0"), total_amount=decimal.Decimal("275000"),
        status_id=1, created_by="buyer1",
        created_at=datetime.datetime(2026, 9, 1), updated_at=datetime.datetime(2026, 9, 1),
    )


def _orm_goods_receipt():
    from Backend.Data_Access_Layer.models.purchase_order import GoodsReceipt

    return GoodsReceipt(
        grn_id=3, vendor_id=100, created_at=datetime.datetime(2026, 9, 5), po_id=1,
        file_path="grn/2026/09/grn-3.pdf", created_by="storekeeper1",
        grn_number="GRN-000012", receipt_date=datetime.date(2026, 9, 5),
    )


@pytest.mark.parametrize(
    "dto_name,module",
    [
        ("InvoiceSummaryDTO", "purchase_order_interface"),
        ("GoodsReceiptSummaryDTO", "purchase_order_interface"),
        ("PurchaseOrderLineDTO", "purchase_order_interface"),
        ("PurchaseOrderDTO", "purchase_order_interface"),
        ("PurchaseOrderSummaryDTO", "goods_receipt_interface"),
        ("InvoiceSummaryDTO", "goods_receipt_interface"),
        ("GoodsReceiptLineDTO", "goods_receipt_interface"),
        ("GoodsReceiptDTO", "goods_receipt_interface"),
    ],
)
def test_nested_dtos_declare_orm_serialization(dto_name, module):
    import importlib

    interface = importlib.import_module(f"Backend.API_Layer.interface.{module}")
    dto = getattr(interface, dto_name)

    assert dto.model_config.get("from_attributes") is True, (
        f"{module}.{dto_name} cannot be built from a SQLAlchemy instance"
    )


def test_vendor_purchase_order_response_accepts_orm_objects():
    from Backend.API_Layer.interface.vendor_interface import VendorPurchaseOrderListResponse

    response = VendorPurchaseOrderListResponse(
        vendor_id=100, count=1, items=[_orm_purchase_order()]
    )

    assert response.count == 1
    assert response.items[0].po_number == "PO-000059"
    assert response.items[0].total_amount == 275000
    assert response.items[0].purchase_order_line == []


def test_vendor_goods_receipt_response_accepts_orm_objects():
    from Backend.API_Layer.interface.vendor_interface import VendorGoodsReceiptListResponse

    response = VendorGoodsReceiptListResponse(
        vendor_id=100, count=1, items=[_orm_goods_receipt()]
    )

    assert response.count == 1
    assert response.items[0].grn_number == "GRN-000012"
    assert response.items[0].file_path == "grn/2026/09/grn-3.pdf"


def test_vendor_purchase_orders_endpoint_serializes_end_to_end(monkeypatch):
    """Exercises the real route through FastAPI, which is where the 500 was
    raised - a DTO-level check alone would not prove the endpoint works."""

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.middleware.base import BaseHTTPMiddleware

    from Backend.API_Layer.routes import vendor_route

    class _FakeAuthAndDBMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "officer-1"}
            request.state.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
            return await call_next(request)

    class _FakeService:
        def __init__(self, db):
            pass

        def list_purchase_orders_for_vendor(self, vendor_id, skip=0, limit=100):
            return [_orm_purchase_order()]

    monkeypatch.setattr(vendor_route, "VendorService", _FakeService)

    app = FastAPI()
    app.add_middleware(_FakeAuthAndDBMiddleware)
    app.include_router(vendor_route.router, prefix="/apm/vendor")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/apm/vendor/100/purchase-orders?skip=0&limit=100")

    assert response.status_code == 200
    body = response.json()
    assert body["vendor_id"] == 100
    assert body["count"] == 1
    assert body["items"][0]["po_number"] == "PO-000059"


def test_existing_purchase_order_list_endpoint_still_serializes():
    """GET /apm/purchase-order keeps returning ORM rows through a top-level
    response_model - that path was never broken and must stay working."""

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from Backend.API_Layer.interface.purchase_order_interface import PurchaseOrderDTO

    app = FastAPI()

    @app.get("/purchase-order", response_model=list[PurchaseOrderDTO])
    def _list():
        return [_orm_purchase_order()]

    response = TestClient(app, raise_server_exceptions=False).get("/purchase-order")

    assert response.status_code == 200
    assert response.json()[0]["po_number"] == "PO-000059"
