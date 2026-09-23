# Backend/tests/test_vendor_collections.py
"""Vendor-scoped retrieval: purchase orders, NDAs, GRNs and documents.

Fake-DAO style, no DB and no network - the same approach as
test_vendor_intake.py and test_nda.py. Two things are stubbed for a specific
reason:

* ``s3_utils`` is replaced in ``sys.modules`` because VendorService imports it
  lazily inside ``_presigner`` (the real module imports boto3 and reads AWS_*
  at module scope, so it cannot be imported in a test environment).
* The NDA / goods-receipt / purchase-order services are stubbed where a test
  is about the vendor-scoped wrapper rather than about their internals; the
  tests that care about delegation assert the wrapper calls straight through
  to them instead of re-implementing their queries.
"""
from __future__ import annotations

import datetime
import sys
import types
from types import SimpleNamespace

import pytest

import Backend.Business_Layer.services.vendor_service as vendor_service_module
from Backend.Business_Layer.services.vendor_service import VendorService

TODAY = datetime.date.today()
NOW = datetime.datetime(2026, 9, 22, 9, 0)


class FakeDB:
    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


class FakeVendorDAO:
    """Only the methods the vendor-scoped collections touch."""

    def __init__(self, vendor_ids=(100,)):
        self.vendor_ids = set(vendor_ids)
        self.quotation_documents = []
        self.grn_documents = []
        self.nda_documents = []
        self.invoice_documents = []
        self.calls = []

    def get_vendor_by_id(self, vendor_id):
        if vendor_id not in self.vendor_ids:
            return None
        return SimpleNamespace(vendor_id=vendor_id, vendor_name="Acme Supplies")

    def vendor_exists(self, vendor_id):
        return vendor_id in self.vendor_ids

    def get_quotation_documents(self, vendor_id):
        self.calls.append(("quotation", vendor_id))
        return [row for row in self.quotation_documents]

    def get_goods_receipt_documents(self, vendor_id):
        self.calls.append(("grn", vendor_id))
        return [row for row in self.grn_documents]

    def get_nda_documents(self, vendor_id):
        self.calls.append(("nda", vendor_id))
        return [row for row in self.nda_documents]

    def get_invoice_attachment_documents(self, vendor_id):
        self.calls.append(("invoice", vendor_id))
        return [row for row in self.invoice_documents]


@pytest.fixture
def fake_s3(monkeypatch):
    module = types.ModuleType("Backend.API_Layer.utils.s3_utils")
    calls = SimpleNamespace(presigned=[])

    def generate_presigned_url(key, expires_in=300):
        calls.presigned.append((key, expires_in))
        return f"https://private-bucket.s3.ap-south-1.amazonaws.com/{key}?X-Amz-Expires={expires_in}"

    module.generate_presigned_url = generate_presigned_url
    module.DEFAULT_PRESIGNED_URL_TTL_SECONDS = 300

    monkeypatch.setitem(sys.modules, "Backend.API_Layer.utils.s3_utils", module)
    return calls


@pytest.fixture
def env():
    service = VendorService(db=FakeDB())
    dao = FakeVendorDAO()
    service.vendor_dao = dao
    return SimpleNamespace(service=service, dao=dao)


def _stub_service(monkeypatch, module_path, class_name, method_name, result, recorder):
    """Replace one collaborator service with a stub that records its kwargs."""

    class _Stub:
        def __init__(self, db):
            pass

    def _call(self, *args, **kwargs):
        recorder.append(kwargs or args)
        return result

    setattr(_Stub, method_name, _call)

    module = types.ModuleType(module_path)
    setattr(module, class_name, _Stub)
    monkeypatch.setitem(sys.modules, module_path, module)
    return recorder


# ---------------------------------------------------------------------------
# The bug this task exists to fix: service -> DAO parameter mismatch
# ---------------------------------------------------------------------------


def test_purchase_order_service_and_dao_signatures_line_up():
    """PurchaseOrderService.list_purchase_orders used to forward its five
    arguments POSITIONALLY into a DAO whose 4th parameter is `po_number`, so
    `skip` became `po_number` and `limit` became `skip`. A default call then
    skipped the first 100 rows and GET /apm/purchase-order?vendor_id=X
    returned [] for any vendor with fewer than 100 POs."""

    import inspect

    from Backend.Business_Layer.services.purchase_order_service import PurchaseOrderService
    from Backend.Data_Access_Layer.dao.purchase_order_dao import PurchaseOrderDAO

    service_params = list(
        inspect.signature(PurchaseOrderService.list_purchase_orders).parameters
    )[1:]
    dao_params = list(inspect.signature(PurchaseOrderDAO.get_all_purchase_orders).parameters)[1:]

    # The signatures differ on purpose (the DAO also supports po_number), which
    # is exactly why the call must be made with keywords.
    assert "po_number" in dao_params
    assert "po_number" not in service_params
    for name in service_params:
        assert name in dao_params, f"service passes {name} which the DAO does not accept"


def test_list_purchase_orders_forwards_skip_and_limit_by_keyword():
    """Regression guard: a vendor's first page must start at row 0."""

    from Backend.Business_Layer.services.purchase_order_service import PurchaseOrderService

    captured = {}

    class _RecordingDAO:
        def get_all_purchase_orders(self, **kwargs):
            captured.update(kwargs)
            return ["po-1", "po-2"]

    service = PurchaseOrderService.__new__(PurchaseOrderService)
    service.po_dao = _RecordingDAO()

    result = service.list_purchase_orders(vendor_id=100)

    assert result == ["po-1", "po-2"]
    assert captured["vendor_id"] == 100
    assert captured["skip"] == 0
    assert captured["limit"] == 100
    assert "po_number" not in captured


def test_list_purchase_orders_still_honours_explicit_paging():
    from Backend.Business_Layer.services.purchase_order_service import PurchaseOrderService

    captured = {}

    class _RecordingDAO:
        def get_all_purchase_orders(self, **kwargs):
            captured.update(kwargs)
            return []

    service = PurchaseOrderService.__new__(PurchaseOrderService)
    service.po_dao = _RecordingDAO()

    service.list_purchase_orders(vendor_id=100, status_id=5, search="PO-1", skip=20, limit=10)

    assert captured == {
        "vendor_id": 100, "status_id": 5, "search": "PO-1", "skip": 20, "limit": 10,
    }


# ---------------------------------------------------------------------------
# Vendor-scoped purchase orders / NDAs / GRNs
# ---------------------------------------------------------------------------


def test_vendor_purchase_orders_delegate_to_the_existing_service(env, monkeypatch):
    recorder = []
    _stub_service(
        monkeypatch, "Backend.Business_Layer.services.purchase_order_service",
        "PurchaseOrderService", "list_purchase_orders", ["po-1"], recorder,
    )

    result = env.service.list_purchase_orders_for_vendor(100, skip=5, limit=25)

    assert result == ["po-1"]
    assert recorder == [{"vendor_id": 100, "skip": 5, "limit": 25}]


def test_vendor_ndas_delegate_to_the_existing_nda_service(env, monkeypatch):
    recorder = []
    _stub_service(
        monkeypatch, "Backend.Business_Layer.services.nda_service",
        "NdaService", "list_for_vendor", ["nda-1", "nda-2"], recorder,
    )

    result = env.service.list_ndas(100)

    assert result == ["nda-1", "nda-2"]
    assert recorder == [(100,)]


def test_vendor_grns_delegate_to_the_existing_goods_receipt_service(env, monkeypatch):
    recorder = []
    _stub_service(
        monkeypatch, "Backend.Business_Layer.services.goods_receipt_service",
        "GoodsReceiptService", "list_goods_receipts", ["grn-1"], recorder,
    )

    result = env.service.list_goods_receipts(100, skip=0, limit=50)

    assert result == ["grn-1"]
    assert recorder == [{"vendor_id": 100, "po_id": None, "skip": 0, "limit": 50}]


@pytest.mark.parametrize(
    "method,module_path,class_name,inner",
    [
        ("list_purchase_orders_for_vendor",
         "Backend.Business_Layer.services.purchase_order_service",
         "PurchaseOrderService", "list_purchase_orders"),
        ("list_ndas", "Backend.Business_Layer.services.nda_service",
         "NdaService", "list_for_vendor"),
        ("list_goods_receipts", "Backend.Business_Layer.services.goods_receipt_service",
         "GoodsReceiptService", "list_goods_receipts"),
    ],
)
def test_empty_collections_return_an_empty_list_not_an_error(
    env, monkeypatch, method, module_path, class_name, inner
):
    _stub_service(monkeypatch, module_path, class_name, inner, [], [])

    assert getattr(env.service, method)(100) == []


@pytest.mark.parametrize(
    "method", ["list_purchase_orders_for_vendor", "list_ndas", "list_goods_receipts"]
)
def test_unknown_vendor_is_rejected_before_any_lookup(env, method):
    with pytest.raises(ValueError, match="Vendor not found"):
        getattr(env.service, method)(999)


# ---------------------------------------------------------------------------
# Vendor documents
# ---------------------------------------------------------------------------


def _load_documents(env):
    # (quotation_id, quotation_number, po_number, file_url, quotation_date)
    env.dao.quotation_documents = [
        (7, "QT-000059", "PO-000059", "quotations/2026/09/qt-59.pdf", datetime.date(2026, 9, 1)),
    ]
    env.dao.grn_documents = [
        (3, "GRN-000012", "grn/2026/09/grn-12.pdf", datetime.date(2026, 9, 5)),
    ]
    env.dao.nda_documents = [
        (
            11,
            "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf",
            "ap/nda/signed/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf",
            NOW,
        ),
    ]
    env.dao.invoice_documents = [
        (21, "INV-9001", "original-invoice.pdf", "invoices/2026/08/abc_invoice.pdf", NOW),
    ]


def test_documents_aggregate_every_general_source(env, fake_s3):
    _load_documents(env)

    documents = env.service.list_documents(100)

    by_type = {d["document_type"]: d for d in documents}
    # NDA / NDA_SIGNED are absent by design - see the NDA exclusion tests below.
    assert sorted(by_type) == ["GOODS_RECEIPT", "INVOICE_ATTACHMENT", "QUOTATION"]
    assert by_type["QUOTATION"]["source_id"] == 7
    # The PO the quotation backs is the reference when one was raised.
    assert by_type["QUOTATION"]["reference"] == "PO-000059"
    assert by_type["GOODS_RECEIPT"]["reference"] == "GRN-000012"
    assert by_type["INVOICE_ATTACHMENT"]["reference"] == "INV-9001"
    # The attachment's own stored filename wins over the key's last segment.
    assert by_type["INVOICE_ATTACHMENT"]["file_name"] == "original-invoice.pdf"


# ---------------------------------------------------------------------------
# NDA documents belong to the NDA tab, not to /documents
#
# The NDA workflow owns its files and serves them with the status, scope,
# validity and sent/signed dates that make them meaningful. /documents is the
# general inventory and must not repeat them.
# ---------------------------------------------------------------------------


def test_generated_nda_is_excluded_from_documents(env, fake_s3):
    _load_documents(env)

    documents = env.service.list_documents(100)

    assert all(d["document_type"] != "NDA" for d in documents)
    assert all(d["file_name"] != "NDA-PR-000059-ZTL1149-v1.0.pdf" for d in documents)
    # The generated NDA's key is never even signed for this endpoint.
    assert not any("/nda/generated/" in key for key, _ttl in fake_s3.presigned)


def test_signed_nda_is_excluded_from_documents(env, fake_s3):
    _load_documents(env)

    documents = env.service.list_documents(100)

    assert all(d["document_type"] != "NDA_SIGNED" for d in documents)
    assert not any("/nda/signed/" in key for key, _ttl in fake_s3.presigned)


def test_a_vendor_whose_only_files_are_ndas_has_no_documents(env, fake_s3):
    env.dao.nda_documents = [
        (11, "ap/nda/generated/2026/x.pdf", "ap/nda/signed/2026/x.pdf", NOW),
    ]

    # An empty list, not an error - the vendor simply has no general documents.
    assert env.service.list_documents(100) == []


def test_an_nda_without_a_signed_copy_is_still_fully_excluded(env, fake_s3):
    env.dao.nda_documents = [(11, "ap/nda/generated/2026/x.pdf", None, NOW)]

    assert env.service.list_documents(100) == []


def test_normal_vendor_documents_survive_the_nda_exclusion(env, fake_s3):
    """The exclusion is targeted: everything that is not an NDA file stays."""

    _load_documents(env)

    documents = env.service.list_documents(100)

    assert len(documents) == 3
    assert {d["document_type"] for d in documents} == {
        "QUOTATION", "GOODS_RECEIPT", "INVOICE_ATTACHMENT",
    }
    assert all(d["url"].startswith("https://") for d in documents)


def test_po_and_grn_documents_remain_included(env, fake_s3):
    """The procurement-side file (the quotation the PO was raised from) and the
    GRN file are exactly what /documents is for - the NDA change must not touch
    them."""

    env.dao.quotation_documents = [
        (7, "QT-000059", "PO-000059", "quotations/2026/09/qt-59.pdf", datetime.date(2026, 9, 1)),
    ]
    env.dao.grn_documents = [
        (3, "GRN-000012", "grn/2026/09/grn-12.pdf", datetime.date(2026, 9, 5)),
    ]
    env.dao.nda_documents = [
        (11, "ap/nda/generated/2026/x.pdf", "ap/nda/signed/2026/x.pdf", NOW),
    ]

    documents = env.service.list_documents(100)

    by_type = {d["document_type"]: d for d in documents}
    assert sorted(by_type) == ["GOODS_RECEIPT", "QUOTATION"]
    assert by_type["QUOTATION"]["reference"] == "PO-000059"
    assert by_type["GOODS_RECEIPT"]["reference"] == "GRN-000012"


def test_an_nda_file_referenced_by_another_record_is_still_excluded(env, fake_s3):
    """An NDA object must not reappear via some other file-bearing row. The
    match is against the vendor's own NDA keys, so it is caught wherever the
    reference is stored - not by pattern-matching a filename."""

    nda_key = "ap/nda/signed/2026/PR-1/NDA-PR-1-v1.0.pdf"
    env.dao.nda_documents = [(11, "ap/nda/generated/2026/PR-1/NDA.pdf", nda_key, NOW)]
    # The same object, reached through a different record instead.
    env.dao.invoice_documents = [(21, "INV-9001", "NDA-PR-1-v1.0.pdf", nda_key, NOW)]
    env.dao.grn_documents = [(3, "GRN-1", "grn/2026/09/grn-1.pdf", TODAY)]

    documents = env.service.list_documents(100)

    assert [d["document_type"] for d in documents] == ["GOODS_RECEIPT"]


@pytest.mark.parametrize(
    "stored_reference",
    [
        "  ap/nda/signed/2026/x.pdf  ",  # stray whitespace
        "/ap/nda/signed/2026/x.pdf",  # leading slash
    ],
)
def test_nda_exclusion_survives_key_formatting_differences(env, fake_s3, stored_reference):
    env.dao.nda_documents = [(11, None, "ap/nda/signed/2026/x.pdf", NOW)]
    env.dao.invoice_documents = [(21, "INV-1", "x.pdf", stored_reference, NOW)]

    assert env.service.list_documents(100) == []


def test_a_non_nda_file_is_not_excluded_just_for_looking_like_one(env, fake_s3):
    """Classification comes from the NDA records, never from the path - a file
    merely named like an NDA, on a record the NDA module does not own, stays."""

    env.dao.nda_documents = [(11, "ap/nda/generated/2026/real-nda.pdf", None, NOW)]
    env.dao.invoice_documents = [
        (21, "INV-9001", "nda-summary.pdf", "invoices/2026/08/ap-nda-notes.pdf", NOW),
    ]

    documents = env.service.list_documents(100)

    assert [d["document_type"] for d in documents] == ["INVOICE_ATTACHMENT"]


def test_nda_records_are_only_read_never_written_by_the_documents_list(env, fake_s3):
    """The exclusion reads ap.vendor_nda; it must not delete or modify it."""

    class WriteIsFatalDB(FakeDB):
        def commit(self):
            raise AssertionError("list_documents must not write")

    env.service.db = WriteIsFatalDB()
    _load_documents(env)

    env.service.list_documents(100)

    # The NDA rows handed to the service are untouched.
    assert env.dao.nda_documents == [
        (
            11,
            "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf",
            "ap/nda/signed/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf",
            NOW,
        ),
    ]


def test_the_nda_endpoint_still_returns_this_vendors_nda_documents(env, monkeypatch):
    """The NDA tab remains the single source for NDA records and their files."""

    nda = SimpleNamespace(
        nda_id=11,
        vendor_id=100,
        document_key="ap/nda/generated/2026/x.pdf",
        signed_document_key="ap/nda/signed/2026/x.pdf",
        status_code="SENT",
    )
    recorder = []
    _stub_service(
        monkeypatch, "Backend.Business_Layer.services.nda_service",
        "NdaService", "list_for_vendor", [nda], recorder,
    )

    result = env.service.list_ndas(100)

    assert result == [nda]
    assert result[0].document_key == "ap/nda/generated/2026/x.pdf"
    assert result[0].signed_document_key == "ap/nda/signed/2026/x.pdf"


def test_documents_return_presigned_urls_and_never_the_object_key(env, fake_s3):
    _load_documents(env)

    documents = env.service.list_documents(100)

    for document in documents:
        assert document["url"].startswith("https://")
        assert "X-Amz-Expires" in document["url"]
        assert document["url_expires_in_seconds"] == 300
        # No raw key field is exposed on the entry.
        assert "file_path" not in document
        assert "document_key" not in document

    assert len(fake_s3.presigned) == len(documents)


def test_documents_honour_a_custom_expiry(env, fake_s3):
    _load_documents(env)

    documents = env.service.list_documents(100, expires_in=60)

    assert all(d["url_expires_in_seconds"] == 60 for d in documents)
    assert {ttl for _, ttl in fake_s3.presigned} == {60}


def test_documents_query_each_source_exactly_once(env, fake_s3):
    """Four flat queries, no per-row lookups - the list must not degrade into
    N+1 as a vendor accumulates records."""

    env.dao.quotation_documents = [
        (i, f"QT-{i}", f"PO-{i}", f"quotations/qt-{i}.pdf", TODAY) for i in range(50)
    ]
    env.dao.nda_documents = [
        (i, f"ap/nda/generated/{i}.pdf", f"ap/nda/signed/{i}.pdf", NOW) for i in range(20)
    ]

    documents = env.service.list_documents(100)

    # The 40 NDA files are excluded; only the 50 quotation documents remain.
    assert len(documents) == 50
    # The NDA source is still queried exactly once - to build the exclusion
    # set, not to add rows - so the list stays at four flat queries.
    assert sorted(env.dao.calls) == [
        ("grn", 100), ("invoice", 100), ("nda", 100), ("quotation", 100),
    ]


def test_vendor_with_no_documents_returns_an_empty_list(env, fake_s3):
    assert env.service.list_documents(100) == []


def test_documents_for_an_unknown_vendor_are_rejected(env, fake_s3):
    with pytest.raises(ValueError, match="Vendor not found"):
        env.service.list_documents(999)


def test_documents_are_still_listed_when_s3_is_unavailable(env, monkeypatch):
    """No boto3 / no AWS config: the inventory is still useful, so the rows
    come back with url=None rather than the request failing."""

    _load_documents(env)
    monkeypatch.setattr(
        vendor_service_module.VendorService,
        "_presigner",
        staticmethod(lambda expires_in: ((lambda key: None), None)),
    )

    documents = env.service.list_documents(100)

    assert len(documents) == 3
    assert all(d["url"] is None for d in documents)
    assert all(d["url_expires_in_seconds"] is None for d in documents)
    # The record references are still there, so the UI can still deep-link.
    # The NDA record (11) is not among them - NDA files are never listed here,
    # whether or not a URL could be minted.
    assert {d["source_id"] for d in documents} == {7, 3, 21}


def test_a_single_unsignable_key_does_not_drop_the_other_documents(env, monkeypatch, fake_s3):
    _load_documents(env)
    module = sys.modules["Backend.API_Layer.utils.s3_utils"]
    original = module.generate_presigned_url

    def _sometimes_fails(key, expires_in=300):
        if key.startswith("grn/"):
            raise RuntimeError("Unable to generate document access URL.")
        return original(key, expires_in=expires_in)

    monkeypatch.setattr(module, "generate_presigned_url", _sometimes_fails)

    documents = env.service.list_documents(100)

    assert len(documents) == 3
    grn = next(d for d in documents if d["document_type"] == "GOODS_RECEIPT")
    assert grn["url"] is None
    assert grn["url_expires_in_seconds"] is None
    assert all(d["url"] is not None for d in documents if d["document_type"] != "GOODS_RECEIPT")


# ---------------------------------------------------------------------------
# Route wiring
# ---------------------------------------------------------------------------


def test_vendor_collection_routes_are_registered():
    from Backend.API_Layer.routes.vendor_route import router

    declared = {(tuple(sorted(r.methods)), r.path) for r in router.routes}

    for path in (
        "/{vendor_id}/purchase-orders",
        "/{vendor_id}/ndas",
        "/{vendor_id}/grns",
        "/{vendor_id}/documents",
    ):
        assert (("GET",), path) in declared, f"GET {path} is missing"


def test_existing_vendor_routes_are_untouched():
    from Backend.API_Layer.routes.vendor_route import router

    declared = {(tuple(sorted(r.methods)), r.path) for r in router.routes}

    for method, path in [
        ("POST", ""),
        ("GET", ""),
        ("GET", "/{vendor_id}"),
        ("PUT", "/{vendor_id}"),
        ("PATCH", "/{vendor_id}/status"),
        ("GET", "/{vendor_id}/addresses"),
        ("POST", "/{vendor_id}/addresses"),
        ("GET", "/{vendor_id}/banks"),
        ("POST", "/{vendor_id}/banks"),
    ]:
        assert ((method,), path) in declared, f"{method} {path} is missing"


def test_collection_routes_do_not_shadow_the_vendor_detail_route():
    from starlette.routing import Match

    from Backend.API_Layer.routes.vendor_route import router

    def _match(path):
        scope = {
            "type": "http", "method": "GET", "path": path,
            "path_params": {}, "headers": [], "query_string": b"", "root_path": "",
        }
        matched = [r for r in router.routes if r.matches(scope)[0] == Match.FULL]
        assert matched, f"no route matched {path}"
        return matched[0].name

    assert _match("/100") == "get_vendor_by_id"
    assert _match("/100/ndas") == "list_vendor_ndas"
    assert _match("/100/grns") == "list_vendor_goods_receipts"
    assert _match("/100/documents") == "list_vendor_documents"
    assert _match("/100/purchase-orders") == "list_vendor_purchase_orders"


def test_purchase_order_vendor_filter_endpoint_is_unchanged():
    """The task's required endpoint - GET /apm/purchase-order?vendor_id= -
    must keep existing rather than being replaced by the vendor-scoped one."""

    import inspect

    from Backend.API_Layer.routes.purchase_order_route import (
        get_all_purchase_orders,
        router,
    )

    declared = {(tuple(sorted(r.methods)), r.path) for r in router.routes}
    assert (("GET",), "") in declared
    assert "vendor_id" in inspect.signature(get_all_purchase_orders).parameters


def test_collection_responses_reuse_the_owning_modules_dtos():
    from Backend.API_Layer.interface.goods_receipt_interface import GoodsReceiptDTO
    from Backend.API_Layer.interface.nda_interface import VendorNdaDTO
    from Backend.API_Layer.interface.purchase_order_interface import PurchaseOrderDTO
    from Backend.API_Layer.interface.vendor_interface import (
        VendorGoodsReceiptListResponse,
        VendorNdaListResponse,
        VendorPurchaseOrderListResponse,
    )

    def _item_type(model):
        import typing

        return typing.get_args(model.model_fields["items"].annotation)[0]

    assert _item_type(VendorPurchaseOrderListResponse) is PurchaseOrderDTO
    assert _item_type(VendorNdaListResponse) is VendorNdaDTO
    assert _item_type(VendorGoodsReceiptListResponse) is GoodsReceiptDTO


def test_document_dto_accepts_a_service_entry_verbatim(env, fake_s3):
    from Backend.API_Layer.interface.vendor_interface import (
        VendorDocumentDTO,
        VendorDocumentListResponse,
    )

    _load_documents(env)
    documents = env.service.list_documents(100)

    items = [VendorDocumentDTO(**document) for document in documents]
    counts: dict = {}
    for document in documents:
        counts[document["document_type"]] = counts.get(document["document_type"], 0) + 1

    response = VendorDocumentListResponse(
        vendor_id=100, count=len(items), counts_by_type=counts, items=items
    )

    # Three general documents; the vendor's two NDA files are served by the
    # NDA endpoint, so they are not part of this response or its breakdown.
    assert response.count == 3
    assert response.counts_by_type == {
        "QUOTATION": 1, "GOODS_RECEIPT": 1, "INVOICE_ATTACHMENT": 1,
    }
    assert "NDA" not in response.counts_by_type
    assert "NDA_SIGNED" not in response.counts_by_type
    # The contract itself is unchanged.
    assert set(response.model_dump()) == {"vendor_id", "count", "counts_by_type", "items"}


def test_empty_collection_responses_serialize_as_empty_arrays():
    from Backend.API_Layer.interface.vendor_interface import (
        VendorDocumentListResponse,
        VendorGoodsReceiptListResponse,
        VendorNdaListResponse,
        VendorPurchaseOrderListResponse,
    )

    for model in (
        VendorPurchaseOrderListResponse,
        VendorNdaListResponse,
        VendorGoodsReceiptListResponse,
        VendorDocumentListResponse,
    ):
        payload = model(vendor_id=100, count=0).model_dump()
        assert payload["items"] == []
        assert payload["count"] == 0
        assert payload["vendor_id"] == 100


# ---------------------------------------------------------------------------
# Regression: PurchaseOrder has no file_path
#
# GET /apm/vendor/{vendor_id}/documents returned
#     type object 'PurchaseOrder' has no attribute 'file_path'
# because the aggregation queried a column that exists neither on the model
# nor in ap.purchase_order. There is no purchase_order_attachment table
# either - the only file a PO can reach in this schema is the quotation it
# was raised from (purchase_order.quotation_id -> quotation.file_url).
# ---------------------------------------------------------------------------


def test_purchase_order_model_genuinely_has_no_file_column():
    """Pins the finding this fix rests on. If a PO file column is ever added
    for real, this fails and the aggregation should be revisited."""

    from Backend.Data_Access_Layer.models.purchase_order import PurchaseOrder

    columns = set(PurchaseOrder.__table__.columns.keys())

    assert "file_path" not in columns
    assert "file_url" not in columns
    assert not hasattr(PurchaseOrder, "file_path")
    # ...and no attachment relationship either.
    relationships = set(PurchaseOrder.__mapper__.relationships.keys())
    assert not any("attach" in name or "document" in name for name in relationships)
    # The quotation link - the file reference a PO actually has - is present.
    assert "quotation" in relationships
    assert "quotation_id" in columns


def test_document_aggregation_never_touches_a_purchase_order_file_column():
    """The DAO must not reference PurchaseOrder.file_path in any form - that
    attribute access is what raised the 500."""

    import inspect

    from Backend.Data_Access_Layer.dao import vendor_dao as vendor_dao_module

    source = inspect.getsource(vendor_dao_module)

    assert "PurchaseOrder.file_path" not in source
    assert not hasattr(vendor_dao_module.VendorDAO, "get_purchase_order_documents")
    assert hasattr(vendor_dao_module.VendorDAO, "get_quotation_documents")


def test_quotation_document_query_builds_against_the_real_models():
    """Exercises the real DAO method with a recording session. Every column
    expression is resolved on the real models here, so a non-existent
    attribute raises exactly as it did at request time - this is what would
    have caught the original bug without a database."""

    from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO

    captured = {}

    class _RecordingQuery:
        def __init__(self, *entities):
            captured["entities"] = entities

        def outerjoin(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def group_by(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

    dao = VendorDAO(db=SimpleNamespace(query=lambda *e: _RecordingQuery(*e)))

    assert dao.get_quotation_documents(100) == []
    # Five selected expressions, in the order the service unpacks them.
    assert len(captured["entities"]) == 5


def test_documents_endpoint_works_with_the_real_dao_wired_up(fake_s3):
    """Over the real VendorDAO query builders (fake session, no DB): proves
    /documents no longer explodes on PurchaseOrder.file_path."""

    from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO

    class _EmptyQuery:
        def __getattr__(self, _name):
            return lambda *a, **k: self

        def all(self):
            return []

        def first(self):
            return SimpleNamespace(vendor_id=100, vendor_name="Acme Supplies")

    session = SimpleNamespace(query=lambda *e: _EmptyQuery())
    service = VendorService(db=session)
    service.vendor_dao = VendorDAO(db=session)

    assert service.list_documents(100) == []


# ---------------------------------------------------------------------------
# POs with and without an attachment
# ---------------------------------------------------------------------------


def test_purchase_order_with_an_attachment_is_returned(env, fake_s3):
    env.dao.quotation_documents = [
        (7, "QT-000059", "PO-000059", "quotations/2026/09/qt-59.pdf", datetime.date(2026, 9, 1)),
    ]

    documents = env.service.list_documents(100)

    assert len(documents) == 1
    entry = documents[0]
    assert entry["document_type"] == "QUOTATION"
    assert entry["source_id"] == 7
    assert entry["reference"] == "PO-000059"
    assert entry["file_name"] == "qt-59.pdf"
    assert entry["url"].startswith("https://")


def test_purchase_order_without_an_attachment_is_skipped_not_failed(env, fake_s3):
    """A row with no usable file reference is skipped; the rest of the
    inventory still comes back."""

    env.dao.quotation_documents = [
        (7, "QT-000059", "PO-000059", None, datetime.date(2026, 9, 1)),
        (8, "QT-000060", "PO-000060", "", datetime.date(2026, 9, 2)),
        (9, "QT-000061", "PO-000061", "quotations/qt-61.pdf", datetime.date(2026, 9, 3)),
    ]
    env.dao.grn_documents = [(3, "GRN-1", "grn/grn-1.pdf", TODAY)]

    documents = env.service.list_documents(100)

    assert [d["source_id"] for d in documents if d["document_type"] == "QUOTATION"] == [9]
    assert any(d["document_type"] == "GOODS_RECEIPT" for d in documents)
    assert len(documents) == 2


def test_a_quotation_with_no_purchase_order_yet_falls_back_to_its_own_number(env, fake_s3):
    env.dao.quotation_documents = [
        (7, "QT-000059", None, "quotations/qt-59.pdf", datetime.date(2026, 9, 1)),
    ]

    documents = env.service.list_documents(100)

    assert documents[0]["reference"] == "QT-000059"


def test_vendor_with_only_unattached_purchase_orders_returns_an_empty_list(env, fake_s3):
    env.dao.quotation_documents = [
        (7, "QT-1", "PO-1", None, TODAY),
        (8, "QT-2", "PO-2", None, TODAY),
    ]

    assert env.service.list_documents(100) == []


def test_one_malformed_row_does_not_fail_the_whole_request(env, fake_s3):
    """A single bad document must never turn /documents into a 500: the row
    is dropped and the rest survive."""

    env.dao.quotation_documents = [(7, "QT-1", "PO-1", "quotations/qt-1.pdf", TODAY)]
    env.dao.grn_documents = [(3, "GRN-1", "grn/grn-1.pdf", TODAY)]

    def _explode_on_grn(document_type, source_id, reference, file_path, document_date, sign, ttl):
        if document_type == "GOODS_RECEIPT":
            raise RuntimeError("corrupt row")
        return {
            "document_type": document_type, "source_id": source_id, "reference": reference,
            "file_name": "x.pdf", "url": "https://x", "url_expires_in_seconds": 300,
            "document_date": document_date,
        }

    env.service._document_entry = staticmethod(_explode_on_grn)

    documents = env.service.list_documents(100)

    assert [d["document_type"] for d in documents] == ["QUOTATION"]


def test_quotation_documents_are_counted_under_their_own_type(env, fake_s3):
    env.dao.quotation_documents = [
        (7, "QT-1", "PO-1", "quotations/qt-1.pdf", TODAY),
        (8, "QT-2", None, "quotations/qt-2.pdf", TODAY),
    ]

    documents = env.service.list_documents(100)

    counts: dict = {}
    for document in documents:
        counts[document["document_type"]] = counts.get(document["document_type"], 0) + 1

    assert counts == {"QUOTATION": 2}
    # The phantom type is gone for good.
    assert "PURCHASE_ORDER" not in counts


def test_response_contract_is_unchanged(env, fake_s3):
    """{vendor_id, count, items, counts_by_type} - same envelope as before."""

    from Backend.API_Layer.interface.vendor_interface import (
        VendorDocumentDTO,
        VendorDocumentListResponse,
    )

    env.dao.quotation_documents = [(7, "QT-1", "PO-1", "quotations/qt-1.pdf", TODAY)]
    env.dao.grn_documents = [(3, "GRN-1", "grn/grn-1.pdf", TODAY)]

    documents = env.service.list_documents(100)
    counts: dict = {}
    for document in documents:
        counts[document["document_type"]] = counts.get(document["document_type"], 0) + 1

    payload = VendorDocumentListResponse(
        vendor_id=100,
        count=len(documents),
        counts_by_type=counts,
        items=[VendorDocumentDTO(**d) for d in documents],
    ).model_dump()

    assert sorted(payload) == ["count", "counts_by_type", "items", "vendor_id"]
    assert payload["count"] == 2
    assert payload["counts_by_type"] == {"QUOTATION": 1, "GOODS_RECEIPT": 1}
    assert sorted(payload["items"][0]) == [
        "document_date", "document_type", "file_name", "reference",
        "source_id", "url", "url_expires_in_seconds",
    ]


def test_every_vendor_document_query_compiles_to_real_sql():
    """The strongest guard against the class of bug that caused this: each
    document query is built AND compiled against the real mapped models, so
    any column that does not exist fails here rather than at request time.

    Uses an unbound Session - enough to construct and compile a statement,
    no database required.
    """

    from sqlalchemy.dialects import postgresql
    from sqlalchemy.orm import Session

    from Backend.Data_Access_Layer.dao.vendor_dao import VendorDAO

    compiled = []

    class _CapturingSession(Session):
        def query(self, *entities, **kwargs):
            query = super().query(*entities, **kwargs)
            return _CapturingQuery(query)

    class _CapturingQuery:
        def __init__(self, query):
            self._query = query

        def __getattr__(self, name):
            attribute = getattr(self._query, name)

            def _wrap(*args, **kwargs):
                result = attribute(*args, **kwargs)
                return _CapturingQuery(result) if hasattr(result, "statement") else result

            return _wrap if callable(attribute) else attribute

        def all(self):
            compiled.append(
                str(self._query.statement.compile(dialect=postgresql.dialect()))
            )
            return []

    dao = VendorDAO(db=_CapturingSession())

    assert dao.get_quotation_documents(100) == []
    assert dao.get_goods_receipt_documents(100) == []
    assert dao.get_nda_documents(100) == []
    assert dao.get_invoice_attachment_documents(100) == []

    assert len(compiled) == 4
    sql = " ".join(compiled)
    # No phantom PO file column anywhere in the generated SQL.
    assert "purchase_order.file_path" not in sql
    assert "purchase_order.file_url" not in sql
    # The PO is reached only through the quotation it backs.
    assert "LEFT OUTER JOIN ap.purchase_order ON ap.purchase_order.quotation_id" in compiled[0]
    # Grouped, so a quotation with several POs yields one row, not one per PO.
    assert "GROUP BY" in compiled[0]
    # The sources that must keep working untouched.
    assert "ap.goods_receipt" in compiled[1]
    assert "ap.vendor_nda" in compiled[2]
    assert "ap.invoice_attachment" in compiled[3]
    assert "JOIN ap.invoice" in compiled[3]
