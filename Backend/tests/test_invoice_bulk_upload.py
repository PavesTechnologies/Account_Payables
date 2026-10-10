"""Bulk invoice upload (Phase 3): file/ZIP intake limits, batch creation, the background worker
(same single-upload operations, concurrency limit, retry safety) and the route's permission /
error mapping. No DB, S3 or Textract - an in-memory DAO and fakes stand in for them."""
import asyncio
import datetime
import io
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from Backend.API_Layer.routes import invoice_bulk_upload_route as route
from Backend.Business_Layer.services import invoice_bulk_upload_service as svc
from Backend.Business_Layer.utils import bulk_upload_files as bf
from Backend.Business_Layer.utils.exceptions import DuplicateInvoiceError, VendorNotMatchedError
from Backend.Data_Access_Layer.dao.invoice_upload_batch_dao import InvoiceUploadBatchDAO
from Backend.Data_Access_Layer.models.invoice_upload_batch import InvoiceUploadBatch, InvoiceUploadBatchItem

PDF = b"%PDF-1.7\n invoice body"
PNG = b"\x89PNG\r\n\x1a\n image body"


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


# ======================================================================
# File / ZIP intake
# ======================================================================
def test_multiple_files_flag_bad_ones_without_rejecting_the_batch():
    files, name = bf.expand_upload([
        ("a.pdf", "application/pdf", PDF),
        ("b.png", "image/png", PNG),
        ("fake.pdf", "application/pdf", b"MZ not a pdf"),
        ("notes.docx", "application/octet-stream", b"PK.."),
        ("empty.pdf", "application/pdf", b""),
        ("big.pdf", "application/pdf", b"%PDF" + b"0" * bf.MAX_FILE_BYTES),
    ])
    assert name == "6 files"
    problems = {f.file_name: f.problem for f in files}
    assert problems["a.pdf"] is None and problems["b.png"] is None
    assert "do not match" in problems["fake.pdf"]
    assert "Unsupported" in problems["notes.docx"]
    assert "empty" in problems["empty.pdf"]
    assert "10 MB" in problems["big.pdf"]
    assert files[0].sha256 and files[0].content_type == "application/pdf"


def test_zip_is_expanded_junk_ignored_and_paths_dropped():
    payload = _zip([("Invoices/Jan/inv1.pdf", PDF), ("../../etc/inv2.PDF", PDF + b"2"),
                    ("__MACOSX/Invoices/._inv1.pdf", b"x"), ("Invoices/.DS_Store", b"x"), ("Thumbs.db", b"x")])
    files, name = bf.expand_upload([("march.zip", "application/zip", payload)])
    assert name == "march.zip"
    assert [f.file_name for f in files] == ["inv1.pdf", "inv2.PDF"]
    assert all(f.problem is None for f in files)


@pytest.mark.parametrize("parts,message", [
    ([], "at least one"),
    ([("a.zip", "application/zip", b"not a zip")], "not a valid ZIP"),
    ([("a.zip", "application/zip", b"z"), ("b.pdf", "application/pdf", PDF)], "not both"),
    ([("a.zip", "application/zip", _zip([("in.zip", b"x")]))], "inside a ZIP"),
    ([("a.zip", "application/zip", _zip([("__MACOSX/x", b""), (".hidden", b"")]))], "no invoice files"),
])
def test_request_level_rejections(parts, message):
    with pytest.raises(bf.BulkUploadRejected, match=message):
        bf.expand_upload(parts)


def test_batch_limit_is_25_for_files_and_zip_members():
    assert bf.MAX_FILES_PER_BATCH == 25
    ok, _ = bf.expand_upload([(f"{i}.pdf", None, PDF + bytes([i])) for i in range(25)])
    assert len(ok) == 25
    with pytest.raises(bf.BulkUploadRejected, match="at most 25"):
        bf.expand_upload([(f"{i}.pdf", None, PDF) for i in range(26)])
    with pytest.raises(bf.BulkUploadRejected, match="more than 25"):
        bf.expand_upload([("x.zip", None, _zip([(f"{i}.pdf", PDF) for i in range(26)]))])


def test_oversized_zip_member_is_flagged_not_read_fully():
    payload = _zip([("huge.pdf", b"%PDF" + b"0" * (bf.MAX_FILE_BYTES + 50)), ("ok.pdf", PDF)])
    files, _ = bf.expand_upload([("x.zip", None, payload)])
    assert "10 MB" in files[0].problem and files[0].size == bf.MAX_FILE_BYTES + 1
    assert files[1].problem is None


# ======================================================================
# In-memory DAO (the real DAO's derived-status logic is reused as-is)
# ======================================================================
class _Store:
    def __init__(self):
        self.batches, self.items, self.inbound = {}, {}, {}


class _FakeDAO:
    store = _Store()

    def __init__(self, db=None):
        self.s = _FakeDAO.store

    def add_batch(self, batch):
        batch.batch_id = len(self.s.batches) + 1
        batch.created_at = datetime.datetime.now(datetime.timezone.utc)
        batch.status = batch.status or "QUEUED"
        self.s.batches[batch.batch_id] = batch
        return batch

    def add_item(self, item):
        item.item_id = len(self.s.items) + 1
        self.s.items[item.item_id] = item
        return item

    def get_batch(self, batch_id):
        return self.s.batches.get(batch_id)

    def get_item(self, item_id):
        return self.s.items.get(item_id)

    def items_for_batch(self, batch_id):
        return sorted((i for i in self.s.items.values() if i.batch_id == batch_id), key=lambda i: i.sequence_no)

    def queued_item_ids(self, batch_id):
        return [i.item_id for i in self.items_for_batch(batch_id) if i.status == "QUEUED"]

    def status_counts(self, batch_ids):
        out = {}
        for i in self.s.items.values():
            if i.batch_id in batch_ids:
                out.setdefault(i.batch_id, {}).setdefault(i.status, 0)
                out[i.batch_id][i.status] += 1
        return out

    refresh_batch_status = InvoiceUploadBatchDAO.refresh_batch_status

    def list_batches(self, uploaded_by, status, offset, limit, source_type=None):
        rows = [b for b in self.s.batches.values() if (not uploaded_by or b.uploaded_by == uploaded_by)
                and (not source_type or b.source_type == source_type)]
        return rows[offset:offset + limit], len(rows)

    def mark_batch_started(self, batch_id):
        b = self.s.batches[batch_id]
        if b.started_at is None:
            b.started_at, b.status = datetime.datetime.now(datetime.timezone.utc), "PROCESSING"

    def claim_item(self, item_id):
        item = self.s.items[item_id]
        if item.status != "QUEUED":
            return False
        item.status, item.attempt_count = "PROCESSING", (item.attempt_count or 0) + 1
        item.started_at, item.error_code, item.error_message = datetime.datetime.now(datetime.timezone.utc), None, None
        return True

    def requeue_item(self, item_id, from_statuses, stale_before):
        item = self.s.items[item_id]
        stale = item.status == "PROCESSING" and stale_before and item.started_at < stale_before
        if item.status in from_statuses or stale:
            item.status = "QUEUED"
            return True
        return False

    def set_item_status(self, item_id, from_statuses, status):
        item = self.s.items[item_id]
        if item.status in from_statuses:
            item.status = status
            return True
        return False

    def created_item_with_sha(self, sha):
        return next((i for i in self.s.items.values() if i.file_sha256 == sha and i.status == "CREATED"), None)

    def invoice_for_file_path(self, path):
        return self.s.inbound.get(path)

    def batch_for_source(self, source_type, reference):
        return next((b for b in self.s.batches.values() if b.source_type == source_type and b.source_reference == reference), None)

    def vendor_emails(self):
        return ["billing@acme.example", "accounts@vendorco.in", "someone@gmail.com"]

    def invoice_numbers(self, ids):
        return {i: (f"INV-{i}", 7) for i in ids}


class _Session:
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass
    def refresh(self, obj): pass


class _Extracted:
    def __init__(self, data):
        self.data = data

    @classmethod
    def model_validate(cls, data):
        return cls(data)

    def model_dump(self, mode=None):
        return dict(self.data)


class _Calls:
    def __init__(self):
        self.extract, self.create, self.validate, self.uploads = [], [], [], []
        self.vendor_known, self.duplicate_of, self.extract_fails, self.s3_fails = True, None, set(), set()
        self.active = self.peak = 0


@pytest.fixture
def env(monkeypatch):
    _FakeDAO.store = _Store()
    calls = _Calls()

    async def fake_extract(s3_key, filename=None):
        calls.extract.append(s3_key)
        calls.active += 1
        calls.peak = max(calls.peak, calls.active)
        await asyncio.sleep(0.01)
        calls.active -= 1
        if filename in calls.extract_fails:
            raise RuntimeError("Textract job failed")
        return _Extracted({"vendor": {"name": "Acme", "gstin": "29ABCDE1234F1Z5"},
                           "reference": {"invoice_number": f"N-{filename}"}})

    def fake_upload(filename, content, content_type=None, prefix="invoices/", key=None):
        if filename in calls.s3_fails:
            raise RuntimeError("S3 down")
        calls.uploads.append(prefix)
        return {"filepath": f"{prefix}{filename}"}

    class FakeIntake:
        def __init__(self, db):
            pass

        def validate_invoice(self, extracted, file_path, job_id=None):
            calls.validate.append(file_path)
            return SimpleNamespace(model_dump=lambda mode=None: {"is_valid": False, "issues": ["Buyer GSTIN mismatch"]})

        def create_invoice(self, extracted, file_path, created_by):
            if not calls.vendor_known:
                raise VendorNotMatchedError("Vendor could not be matched for GSTIN '29ABCDE1234F1Z5'.")
            if calls.duplicate_of:
                raise DuplicateInvoiceError(f"Invoice 'N' already exists for vendor 7 (invoice_id={calls.duplicate_of}).")
            calls.create.append((file_path, created_by))
            invoice_id = 100 + len(calls.create)
            _FakeDAO.store.inbound[file_path] = invoice_id
            return {"invoice_id": invoice_id}

    monkeypatch.setattr(svc, "InvoiceUploadBatchDAO", _FakeDAO)
    monkeypatch.setattr(svc, "SessionLocal", _Session)
    monkeypatch.setattr(svc, "extract_invoice_from_s3", fake_extract)
    monkeypatch.setattr(svc, "upload_to_s3", fake_upload)
    monkeypatch.setattr(svc, "InvoiceExtractionService", FakeIntake)
    monkeypatch.setattr(svc, "ExtractedInvoiceResponse", _Extracted)
    monkeypatch.setattr(svc, "_semaphores", __import__("weakref").WeakKeyDictionary())
    return calls


def _batch(names, contents=None):
    contents = contents or [PDF + n.encode() for n in names]
    files, source = bf.expand_upload(list(zip(names, [None] * len(names), contents)))
    return svc.InvoiceBulkUploadService(_Session()).create_batch(files, source, "u1", "Asha")


def _items(batch_id):
    return {i.file_name: i for i in _FakeDAO.store.items.values() if i.batch_id == batch_id}


# ======================================================================
# Batch creation
# ======================================================================
def test_create_batch_records_every_file_and_uploads_only_good_ones(env):
    env.s3_fails = {"c.pdf"}
    batch_id = _batch(["a.pdf", "a-copy.pdf", "bad.pdf", "c.pdf", "d.pdf"],
                      [PDF + b"A", PDF + b"A", b"junk", PDF + b"C", PDF + b"D"])
    items = _items(batch_id)
    assert items["a.pdf"].status == "QUEUED" and items["a.pdf"].file_path == f"invoices/bulk/{batch_id}/a.pdf"
    assert items["a-copy.pdf"].status == "DUPLICATE" and items["a-copy.pdf"].duplicate_of_item_id == items["a.pdf"].item_id
    assert items["bad.pdf"].status == "FAILED" and items["bad.pdf"].error_code == "INVALID_FILE"
    assert items["c.pdf"].status == "FAILED" and items["c.pdf"].error_code == "UPLOAD_FAILED"
    assert env.uploads == [f"invoices/bulk/{batch_id}/"] * 2
    batch = _FakeDAO.store.batches[batch_id]
    assert batch.total_files == 5 and batch.status == "QUEUED" and batch.uploaded_by_name == "Asha"


def test_same_file_already_created_in_an_earlier_batch_is_a_duplicate(env):
    first = _batch(["a.pdf"])
    asyncio.run(svc.process_batch(first, "u1"))
    second = _batch(["renamed.pdf"], [PDF + b"a.pdf"])
    item = _items(second)["renamed.pdf"]
    assert item.status == "DUPLICATE" and item.invoice_id == 101 and f"batch #{first}" in item.error_message
    assert len(env.extract) == 1  # never sent to Textract again


# ======================================================================
# Worker
# ======================================================================
def test_worker_runs_the_single_upload_operations_and_creates_for_review(env):
    batch_id = _batch(["a.pdf", "b.pdf"])
    asyncio.run(svc.process_batch(batch_id, "u1"))
    items = _items(batch_id)
    assert {i.status for i in items.values()} == {"CREATED"}
    assert items["a.pdf"].invoice_id and items["a.pdf"].attempt_count == 1
    # validation ran and its issues are kept, but - like "Save for Manual Review" - did not block create
    assert items["a.pdf"].validation_result["issues"] == ["Buyer GSTIN mismatch"]
    assert env.create[0][1] == "u1"
    assert _FakeDAO.store.batches[batch_id].status == "COMPLETED"
    detail = svc.InvoiceBulkUploadService(_Session()).batch_detail(batch_id)
    assert detail["counts"]["created"] == 2 and detail["items"][0]["invoice_number"].startswith("INV-")
    assert detail["items"][0]["is_valid"] is False


def test_concurrency_is_limited(env, monkeypatch):
    monkeypatch.setattr(svc, "CONCURRENCY", 2)
    batch_id = _batch([f"{i}.pdf" for i in range(7)])
    asyncio.run(svc.process_batch(batch_id, "u1"))
    assert env.peak == 2 and len(env.create) == 7


def test_vendor_not_found_then_retry_reuses_extraction(env):
    env.vendor_known = False
    batch_id = _batch(["a.pdf"])
    asyncio.run(svc.process_batch(batch_id, "u1"))
    item = _items(batch_id)["a.pdf"]
    assert item.status == "VENDOR_NOT_FOUND" and "Onboard the vendor" in item.error_message
    assert item.extracted_data["vendor"]["gstin"] == "29ABCDE1234F1Z5"
    assert _FakeDAO.store.batches[batch_id].status == "NEEDS_ATTENTION"

    env.vendor_known = True  # vendor onboarded
    service = svc.InvoiceBulkUploadService(_Session())
    ids = service.retry_batch(batch_id)
    asyncio.run(svc.process_batch(batch_id, "u2", ids))
    assert item.status == "CREATED" and item.attempt_count == 2
    assert len(env.extract) == 1  # Textract not called again
    assert env.create[-1][1] == "u2"
    assert _FakeDAO.store.batches[batch_id].status == "COMPLETED"


def test_extraction_failure_is_retryable(env):
    env.extract_fails = {"a.pdf"}
    batch_id = _batch(["a.pdf"])
    asyncio.run(svc.process_batch(batch_id, "u1"))
    item = _items(batch_id)["a.pdf"]
    assert item.status == "FAILED" and item.error_code == "EXTRACTION_FAILED" and "Textract" in item.error_message
    service = svc.InvoiceBulkUploadService(_Session())
    assert service.batch_detail(batch_id)["items"][0]["can_retry"] is True
    env.extract_fails = set()
    service.retry_item(item.item_id)
    asyncio.run(svc.process_batch(batch_id, "u1", [item.item_id]))
    assert item.status == "CREATED"


def test_duplicate_invoice_number_links_the_existing_invoice(env):
    env.duplicate_of = 55
    batch_id = _batch(["a.pdf"])
    asyncio.run(svc.process_batch(batch_id, "u1"))
    item = _items(batch_id)["a.pdf"]
    assert item.status == "DUPLICATE" and item.error_code == "DUPLICATE_INVOICE" and item.invoice_id == 55
    with pytest.raises(ValueError, match="Duplicates are not retried"):
        svc.InvoiceBulkUploadService(_Session()).retry_item(item.item_id)


def test_retry_after_crash_finds_the_invoice_instead_of_creating_again(env):
    batch_id = _batch(["a.pdf"])
    item = _items(batch_id)["a.pdf"]
    # previous worker: create_invoice committed, then the process died with the item PROCESSING
    _FakeDAO.store.inbound[item.file_path] = 77
    item.status, item.started_at = "PROCESSING", datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    service = svc.InvoiceBulkUploadService(_Session())
    assert service.batch_detail(batch_id)["items"][0]["stalled"] is True
    asyncio.run(svc.process_batch(batch_id, "u1", service.retry_batch(batch_id)))
    assert item.status == "CREATED" and item.invoice_id == 77
    assert env.create == [] and env.extract == []


def test_an_item_is_never_processed_twice_concurrently(env):
    batch_id = _batch(["a.pdf"])
    item_id = _items(batch_id)["a.pdf"].item_id

    async def both():
        await asyncio.gather(svc.process_item(item_id, "u1"), svc.process_item(item_id, "u1"))
    asyncio.run(both())
    assert len(env.extract) == 1 and len(env.create) == 1


def test_in_progress_and_created_items_cannot_be_retried_and_skip_rules(env):
    env.vendor_known = False
    batch_id = _batch(["a.pdf", "b.pdf"])
    service = svc.InvoiceBulkUploadService(_Session())
    a = _items(batch_id)["a.pdf"]
    a.status, a.started_at = "PROCESSING", datetime.datetime.now(datetime.timezone.utc)
    with pytest.raises(ValueError, match="still being processed"):
        service.retry_item(a.item_id)
    b = _items(batch_id)["b.pdf"]
    asyncio.run(svc.process_batch(batch_id, "u1", [b.item_id]))
    assert service.skip_item(b.item_id).status == "SKIPPED"
    with pytest.raises(ValueError, match="skipped"):
        service.retry_item(b.item_id)
    with pytest.raises(ValueError, match="Only files that need attention"):
        service.skip_item(a.item_id)


def test_claim_is_a_conditional_update():
    captured = []

    class _Db:
        def execute(self, stmt):
            captured.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(rowcount=0)
    assert InvoiceUploadBatchDAO(_Db()).claim_item(5) is False
    assert "status = 'QUEUED'" in captured[0] and "attempt_count" in captured[0]


# ======================================================================
# Route
# ======================================================================
def _client(permissions):
    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = {"user_id": "u1", "name": "Asha", "permissions": permissions}
            request.state.db = _Session()
            return await call_next(request)
    app = FastAPI()
    app.add_middleware(_Auth)
    app.include_router(route.router, prefix="/invoice-bulk-upload")
    return TestClient(app)


def test_route_requires_bulk_upload_permission(env):
    client = _client(["INVOICE_CREATE"])
    assert client.get("/invoice-bulk-upload/batches").status_code == 403
    assert client.post("/invoice-bulk-upload", files=[("files", ("a.pdf", PDF, "application/pdf"))]).status_code == 403


def test_route_upload_queues_background_processing(env, monkeypatch):
    started = []

    async def fake_process(batch_id, actor, item_ids=None):
        started.append((batch_id, actor, item_ids))
    monkeypatch.setattr(route.worker, "process_batch", fake_process)
    client = _client(["INVOICE_BULK_UPLOAD"])
    res = client.post("/invoice-bulk-upload", files=[("files", ("a.pdf", PDF, "application/pdf")),
                                                     ("files", ("b.pdf", PDF + b"b", "application/pdf"))])
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["total_files"] == 2 and body["counts"]["queued"] == 2 and len(body["items"]) == 2
    assert started == [(body["batch_id"], "u1", None)]
    assert client.get(f"/invoice-bulk-upload/batches/{body['batch_id']}").json()["batch_id"] == body["batch_id"]
    assert client.get("/invoice-bulk-upload/batches").json()["total"] == 1
    assert client.get("/invoice-bulk-upload/batches/999").status_code == 404
    assert client.get("/invoice-bulk-upload/limits").json()["max_files"] == 25


def test_route_rejects_bad_requests(env):
    client = _client(["INVOICE_BULK_UPLOAD"])
    too_many = [("files", (f"{i}.pdf", PDF, "application/pdf")) for i in range(26)]
    res = client.post("/invoice-bulk-upload", files=too_many)
    assert res.status_code == 400 and "at most 25" in res.json()["detail"]
    res = client.post("/invoice-bulk-upload", files=[("files", ("x.zip", b"nope", "application/zip"))])
    assert res.status_code == 400
    assert client.post("/invoice-bulk-upload/items/999/retry").status_code == 404
