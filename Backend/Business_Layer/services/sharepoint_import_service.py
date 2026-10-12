# Backend/Business_Layer/services/sharepoint_import_service.py
"""Daily pickup of bulk-import sheets from a SharePoint document library (6.7).

Library layout (folders are created on first run):
    <SHAREPOINT_ROOT_FOLDER>/Payments/Inbox        sheet(s) + receipts (loose and / or ZIP)
    <SHAREPOINT_ROOT_FOLDER>/TDS Challans/Inbox    sheet(s) + challans
    <SHAREPOINT_ROOT_FOLDER>/TDS Filings/Inbox     sheet(s) + acknowledgements
    .../<type>/Processed/<yyyy-mm-dd>/             processed sheet, its documents and "<sheet> - results.xlsx"

Each .xlsx in an Inbox becomes one bulk-import job (auto_record): rows whose document confirms the
sheet are recorded through the existing services, everything else waits for review in the app
(Payments > Bulk import). A file version is imported once (unique SharePoint item id + eTag).
The switch BULK_IMPORT_SHAREPOINT_ENABLED (AP Automation page, AP_AUTOMATION_MANAGE) is OFF by
default; while it is off an --execute run does nothing.
"""
import datetime
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from Backend.Business_Layer.services import bulk_import_service as importer
from Backend.Business_Layer.utils import bulk_import_workbook as wbk
from Backend.Business_Layer.utils.graph_drive_client import GraphDriveClient
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.bulk_import import (
    KIND_PAYMENTS,
    KIND_TDS_CHALLANS,
    KIND_TDS_FILINGS,
    SOURCE_SHAREPOINT,
    BulkImportJob,
)
from Backend.Data_Access_Layer.models.master import SystemConfiguration
from Backend.Data_Access_Layer.utils.database import SessionLocal

logger = logging.getLogger(__name__)

FOLDERS = {KIND_PAYMENTS: "Payments", KIND_TDS_CHALLANS: "TDS Challans", KIND_TDS_FILINGS: "TDS Filings"}
KEY_ENABLED = "BULK_IMPORT_SHAREPOINT_ENABLED"
KEY_LAST_RUN = "BULK_IMPORT_SHAREPOINT_LAST_RUN"
ACTOR = "SHAREPOINT_IMPORT"
_LOCK_KEY = 0x41504D49  # "APMI"


# ======================================================================
# Switch / last run (same pattern as the mailbox switch)
# ======================================================================
class SharePointImportSettings:
    def __init__(self, db):
        self.db = db
        self.dao = MasterDAO(db)

    def is_enabled(self) -> bool:
        row = self.dao.get_system_config_by_key(KEY_ENABLED)
        return row is not None and (row.config_value or "").strip().lower() == "true"

    def _upsert(self, key, value, data_type, description, by):
        row = self.dao.get_system_config_by_key(key)
        if row is None:
            row = SystemConfiguration(config_key=key, config_value=value, data_type=data_type, description=description)
            self.db.add(row)
        row.config_value, row.updated_by = value, (by or "")[:100] or None
        row.updated_at = datetime.datetime.now()

    def set_enabled(self, enabled: bool, user_id: str, user_name: Optional[str] = None) -> Dict[str, Any]:
        before = self.is_enabled()
        self._upsert(KEY_ENABLED, "true" if enabled else "false", "BOOLEAN",
                     "Daily pickup of payment / TDS sheets from SharePoint (on/off)", user_name or user_id)
        if before != enabled:
            self.db.add(AuditLog(table_name="system_configuration", record_id=0,
                                 action="SHAREPOINT_IMPORT_ENABLED" if enabled else "SHAREPOINT_IMPORT_DISABLED",
                                 changed_by=str(user_id), old_values={KEY_ENABLED: before}, new_values={KEY_ENABLED: enabled}))
        self.db.commit()
        return self.status()

    def record_run(self, summary: Dict[str, Any]) -> None:
        value = json.dumps({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), **summary},
                           separators=(",", ":"))[:255]
        self._upsert(KEY_LAST_RUN, value, "JSON", "Last SharePoint import run", ACTOR)

    def status(self) -> Dict[str, Any]:
        from Backend.config.env_loader import get_env_var

        enabled_row = self.dao.get_system_config_by_key(KEY_ENABLED)
        last_row = self.dao.get_system_config_by_key(KEY_LAST_RUN)
        try:
            last = json.loads(last_row.config_value) if last_row else None
        except ValueError:
            last = None
        return {
            "enabled": self.is_enabled(),
            "configured": bool(get_env_var("SHAREPOINT_SITE", "")),
            "site": get_env_var("SHAREPOINT_SITE", "") or None,
            "library": get_env_var("SHAREPOINT_LIBRARY", "Documents") or "Documents",
            "root_folder": get_env_var("SHAREPOINT_ROOT_FOLDER", "AP Imports") or "AP Imports",
            "folders": [f"{v}/Inbox" for v in FOLDERS.values()],
            "updated_by": enabled_row.updated_by if enabled_row else None,
            "updated_at": enabled_row.updated_at if enabled_row else None,
            "last_run": last,
        }


# ======================================================================
# Pickup
# ======================================================================
@dataclass
class PickupReport:
    disabled: bool = False
    sheets: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def referenced_documents(kind: str, content: bytes) -> List[str]:
    try:
        rows = wbk.parse_workbook(kind, content)
    except wbk.WorkbookRejected:
        return []
    column = wbk.DOCUMENT_COLUMN[kind]
    return sorted({wbk.file_name_of(r.data.get(column)).lower() for r in rows if r.data.get(column)})


async def run_once(execute: bool, client: Optional[GraphDriveClient] = None, today: Optional[datetime.date] = None) -> PickupReport:
    client = client or GraphDriveClient()
    today = today or datetime.date.today()
    report = PickupReport()
    for kind, folder in FOLDERS.items():
        try:
            inbox = client.children(f"{folder}/Inbox")
        except Exception as exc:
            report.errors.append(f"{folder}: {exc}")
            continue
        by_name = {i["name"].lower(): i for i in inbox}
        zips = [i for i in inbox if i["name"].lower().endswith(".zip")]
        for sheet in (i for i in inbox if i["name"].lower().endswith(".xlsx")):
            entry = {"type": kind, "sheet": sheet["name"], "modified_by": ((sheet.get("lastModifiedBy") or {}).get("user") or {}).get("displayName")}
            try:
                book = client.download(sheet["id"])
                names = referenced_documents(kind, book)
                docs_items = [by_name[n] for n in names if n in by_name]
                if len(docs_items) < len(names):
                    docs_items += zips  # missing ones may be inside a ZIP
                entry["documents"] = [d["name"] for d in docs_items]
                if not execute:
                    report.sheets.append(entry)
                    continue
                entry.update(await _import(kind, folder, sheet, book, docs_items, client, today))
            except Exception as exc:
                logger.exception("SharePoint import of %s failed", sheet.get("name"))
                entry["error"] = str(exc)[:300]
                report.errors.append(f"{sheet.get('name')}: {exc}")
            report.sheets.append(entry)
    return report


async def _import(kind, folder, sheet, book, docs_items, client, today) -> Dict[str, Any]:
    reference = f"{sheet['id']}:{sheet.get('eTag') or sheet.get('lastModifiedDateTime')}"[:500]
    db = SessionLocal()
    try:
        if db.query(BulkImportJob).filter(BulkImportJob.source == SOURCE_SHAREPOINT,
                                          BulkImportJob.source_reference == reference).first():
            return {"skipped": "already imported"}
        documents = [(d["name"], None, client.download(d["id"])) for d in docs_items]
        modified_by = ((sheet.get("lastModifiedBy") or {}).get("user") or {}).get("displayName")
        origin = "Local folder" if str(sheet["id"]).startswith("local:") else f"SharePoint ({modified_by or 'unknown'})"
        try:
            job_id = importer.BulkImportService(db).create_job(
                kind, (sheet["name"], book), documents, ACTOR, origin,
                source=SOURCE_SHAREPOINT, source_reference=reference, auto_record=True)
        except IntegrityError:
            db.rollback()
            return {"skipped": "already imported"}
        except ValueError as exc:  # unreadable / wrong sheet: leave a result note, move it out of the Inbox
            db.rollback()
            processed = client.ensure_folder(f"{folder}/Processed/{today.isoformat()}")
            client.upload(processed, f"{sheet['name'].rsplit('.', 1)[0]} - NOT IMPORTED.txt", str(exc).encode())
            client.move(sheet["id"], processed)
            return {"rejected": str(exc)[:300]}
    finally:
        db.close()

    await importer.validate_job(job_id, ACTOR)

    db = SessionLocal()
    try:
        service = importer.BulkImportService(db)
        detail = service.job_detail(job_id)
        name, results = service.results_workbook(job_id)
    finally:
        db.close()
    processed = client.ensure_folder(f"{folder}/Processed/{today.isoformat()}")
    client.upload(processed, name, results)
    client.move(sheet["id"], processed)
    for d in docs_items:
        try:
            client.move(d["id"], processed)
        except Exception:
            logger.warning("Could not move %s to Processed", d.get("name"))
    return {"job_id": job_id, "status": detail["status"], "counts": detail["counts"]}


def try_lock(db) -> bool:
    return bool(db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}).scalar())


def unlock(db) -> None:
    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})


async def run_locked(execute: bool, client=None) -> Optional[PickupReport]:
    """client: a GraphDriveClient (default) or LocalDriveClient (local testing, `--local`)."""
    lock_db = SessionLocal()
    try:
        if not try_lock(lock_db):
            return None
        try:
            settings = SharePointImportSettings(lock_db)
            if execute and not settings.is_enabled():
                return PickupReport(disabled=True)
            try:
                report = await run_once(execute, client=client)
            except Exception as exc:
                if execute:
                    settings.record_run({"status": "error", "error": str(exc)[:120]})
                    lock_db.commit()
                raise
            if execute:
                imported = [s for s in report.sheets if s.get("job_id")]
                settings.record_run({"status": "ok", "sheets": len(imported),
                                     "recorded": sum((s.get("counts") or {}).get("recorded", 0) for s in imported),
                                     "review": sum((s.get("counts") or {}).get("needs_review", 0) + (s.get("counts") or {}).get("error", 0) for s in imported),
                                     "errors": len(report.errors)})
                lock_db.commit()
            return report
        finally:
            unlock(lock_db)
            lock_db.commit()
    finally:
        lock_db.close()
