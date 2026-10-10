"""Email invoice intake (Phase 3b): selection rules, sender filter, one batch per email, dry run,
and the Graph client never leaking credentials. No real mailbox / DB / Textract."""
import asyncio
import datetime
import io
import zipfile

import pytest

from Backend.Business_Layer.services import invoice_email_intake_service as intake
from Backend.Business_Layer.utils import bulk_upload_files as bf
from Backend.Business_Layer.utils import graph_mail_client as gmc
from Backend.tests.test_invoice_bulk_upload import PDF, _FakeDAO, _Session, env  # noqa: F401 - env is a fixture

NOW = datetime.datetime(2026, 10, 12, 9, 0, tzinfo=datetime.timezone.utc)
START = datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc)


def _cfg(**kw):
    return intake.IntakeConfig(start=START, keywords=intake.DEFAULT_KEYWORDS.split(","), **kw)


def _msg(mid, subject, sender, received="2026-10-11T08:00:00Z", has=True):
    return {"id": mid, "internetMessageId": f"<{mid}@mail>", "subject": subject, "receivedDateTime": received,
            "hasAttachments": has, "from": {"emailAddress": {"address": sender}}}


def _att(aid, name, size=150_000, inline=False, kind="#microsoft.graph.fileAttachment"):
    return {"id": aid, "name": name, "contentType": "application/octet-stream", "size": size, "isInline": inline,
            "@odata.type": kind}


# ======================================================================
# Pure rules
# ======================================================================
def test_go_live_date_and_lookback():
    cfg = _cfg(lookback_hours=72)
    assert not intake.message_qualifies(_msg("a", "Invoice", "x@y.com", received="2026-10-09T23:59:00Z"), cfg)
    assert intake.message_qualifies(_msg("a", "Invoice", "x@y.com"), cfg)
    assert not intake.message_qualifies(_msg("a", "Invoice", "x@y.com", has=False), cfg)
    assert cfg.since(NOW) == START  # never before go-live
    assert cfg.since(NOW + datetime.timedelta(days=10)) == NOW + datetime.timedelta(days=7)


def test_vendor_email_set_reads_only_those_senders_any_subject():
    cfg = _cfg(allowed_senders=["billing@acme.example"])
    assert intake.message_qualifies(_msg("a", "October statement", "Billing@Acme.example"), cfg)
    assert not intake.message_qualifies(_msg("b", "Invoice 77", "someone@else.com"), cfg)
    assert intake.looks_like_invoice(_msg("a", "October statement", "billing@acme.example"), [_att("1", "doc.pdf")], cfg)


def test_without_vendor_email_subject_or_file_name_must_look_like_an_invoice():
    cfg = _cfg()
    pdf = [_att("1", "scan.pdf")]
    assert intake.looks_like_invoice(_msg("a", "Tax Invoice INV-77", "x@y.com"), pdf, cfg)
    assert intake.looks_like_invoice(_msg("a", "Bill for September", "x@y.com"), pdf, cfg)
    assert intake.looks_like_invoice(_msg("a", "Documents", "x@y.com"), [_att("1", "INV_2026_077.pdf")], cfg)
    assert not intake.looks_like_invoice(_msg("a", "Invitation to our investor meet", "x@y.com"), pdf, cfg)
    assert not intake.looks_like_invoice(_msg("a", "Hello", "x@y.com"), [_att("1", "brochure.pdf")], cfg)


def test_attachments_skip_inline_logos_and_non_files():
    picked = intake.usable_attachments([
        _att("1", "invoice.pdf"), _att("2", "image001.png", size=8_000), _att("3", "logo.png", inline=True),
        _att("4", "scan.jpg", size=300_000), _att("5", "fwd.eml", kind="#microsoft.graph.itemAttachment"),
        _att("6", "invoices.zip"), _att("7", "notes.docx"), _att("8", "page.tiff"),
    ])
    assert [a["name"] for a in picked] == ["invoice.pdf", "scan.jpg", "invoices.zip", "page.tiff"]


def test_sender_known_matching():
    vendors = ["billing@acme.example", "someone@gmail.com"]
    assert intake.sender_is_known("billing@acme.example", vendors)
    assert intake.sender_is_known("accounts@acme.example", vendors)  # same company domain
    assert not intake.sender_is_known("stranger@gmail.com", vendors)  # public domain: exact only
    assert not intake.sender_is_known("x@unknown.io", vendors)


def test_email_attachments_never_reject_the_whole_email():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.pdf", PDF + b"a")
    files = bf.expand_attachments([("inv.pdf", None, PDF), ("pack.zip", None, buf.getvalue()), ("bad.zip", None, b"nope")])
    assert [(f.file_name, bool(f.problem)) for f in files] == [("inv.pdf", False), ("a.pdf", False), ("bad.zip", True)]
    many = bf.expand_attachments([(f"{i}.pdf", None, PDF + bytes([i])) for i in range(27)])
    assert sum(1 for f in many if f.problem) == 2 and "upload it manually" in many[-1].problem


def test_start_date_is_required(monkeypatch):
    monkeypatch.setattr(intake, "get_env_var", lambda key, default=None: "" if key == "EMAIL_INTAKE_START_DATE" else default)
    with pytest.raises(ValueError, match="EMAIL_INTAKE_START_DATE"):
        intake.IntakeConfig.from_env()


# ======================================================================
# Run (fake Graph + the bulk pipeline fakes)
# ======================================================================
class _FakeGraph:
    def __init__(self, messages, attachments):
        self.messages, self.atts, self.downloads, self.since = messages, attachments, [], None

    def messages_since(self, since):
        self.since = since
        return iter(self.messages)

    def attachments(self, mid):
        return self.atts.get(mid, [])

    def attachment_bytes(self, mid, aid):
        self.downloads.append((mid, aid))
        return PDF + f"{mid}{aid}".encode()


@pytest.fixture
def graph(env, monkeypatch):
    monkeypatch.setattr(intake, "SessionLocal", _Session)
    monkeypatch.setattr(intake, "InvoiceUploadBatchDAO", _FakeDAO)
    return _FakeGraph(
        [_msg("m1", "Tax invoice INV-1", "billing@acme.example"),
         _msg("m2", "Lunch on Friday?", "colleague@paves.example"),
         _msg("m3", "Invoice", "stranger@unknown.io"),
         _msg("m4", "Invoice from old times", "billing@acme.example", received="2026-09-01T00:00:00Z")],
        {"m1": [_att("a1", "INV-1.pdf"), _att("a2", "image001.png", size=5_000)],
         "m2": [_att("b1", "menu.pdf")],
         "m3": [_att("c1", "inv.pdf")]},
    )


def test_dry_run_lists_without_storing(graph, env):
    report = asyncio.run(intake.run_once(False, client=graph, config=_cfg(), now=NOW))
    assert [i["subject"] for i in report.imported] == ["Tax invoice INV-1", "Invoice"]
    assert report.skipped == 2 and graph.downloads == [] and _FakeDAO.store.batches == {}
    assert graph.since == "2026-10-10T00:00:00Z"


def test_execute_creates_one_batch_per_email_through_the_bulk_pipeline(graph, env):
    report = asyncio.run(intake.run_once(True, client=graph, config=_cfg(), now=NOW))
    assert len(report.imported) == 2
    batches = sorted(_FakeDAO.store.batches.values(), key=lambda b: b.batch_id)
    acme, stranger = batches
    assert acme.source_type == "EMAIL" and acme.source_reference == "<m1@mail>" and acme.email_from == "billing@acme.example"
    assert acme.sender_known is True and stranger.sender_known is False
    assert acme.uploaded_by == "EMAIL_INTAKE" and acme.total_files == 1  # the tiny signature png is ignored
    assert graph.downloads == [("m1", "a1"), ("m3", "c1")]
    assert {i.status for i in _FakeDAO.store.items.values()} == {"CREATED"}
    assert all(created_by == "EMAIL_INTAKE" for _, created_by in env.create)

    # next run: nothing is imported twice
    again = asyncio.run(intake.run_once(True, client=graph, config=_cfg(), now=NOW))
    assert again.imported == [] and again.already_imported == 2 and len(_FakeDAO.store.batches) == 2


def test_vendor_email_filter_in_a_run(graph, env):
    report = asyncio.run(intake.run_once(True, client=graph, config=_cfg(allowed_senders=["billing@acme.example"]), now=NOW))
    assert [i["subject"] for i in report.imported] == ["Tax invoice INV-1"]


# ======================================================================
# Graph client hygiene
# ======================================================================
class _Resp:
    def __init__(self, status, body=None, headers=None, content=b""):
        self.status_code, self._body, self.headers, self.content = status, body or {}, headers or {"content-type": "application/json"}, content

    def json(self):
        return self._body


class _Http:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, data=None, timeout=None):
        self.calls.append(("POST", url))
        return self.responses.pop(0)

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append(("GET", url))
        return self.responses.pop(0)


def _client(monkeypatch, responses):
    env_values = {"TENANT_ID": "tenant-x", "CLIENT_ID": "client-x", "CLIENT_SECRET": "super-secret-value", "MAIL_ADDRESS": "box@paves.example"}
    monkeypatch.setattr(gmc, "get_env_var", lambda key, default=None: env_values.get(key, default))
    return gmc.GraphMailClient(session=_Http(responses))


def test_graph_errors_never_contain_the_secret(monkeypatch):
    client = _client(monkeypatch, [_Resp(401, {"error": "invalid_client", "error_description": "secret super-secret-value bad"})])
    with pytest.raises(gmc.GraphMailError) as err:
        list(client.messages_since("2026-10-10T00:00:00Z"))
    assert "super-secret-value" not in str(err.value) and "invalid_client" in str(err.value)


def test_graph_paging_and_read_only(monkeypatch):
    client = _client(monkeypatch, [
        _Resp(200, {"access_token": "tok", "expires_in": 3600}),
        _Resp(200, {"value": [{"id": "1"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/next"}),
        _Resp(200, {"value": [{"id": "2"}]}),
    ])
    assert [m["id"] for m in client.messages_since("2026-10-10T00:00:00Z")] == ["1", "2"]
    methods = [m for m, _ in client.http.calls]
    assert methods == ["POST", "GET", "GET"]  # only the token request is a POST; mail is only read
