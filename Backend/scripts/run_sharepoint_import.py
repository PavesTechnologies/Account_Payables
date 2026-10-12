# Backend/scripts/run_sharepoint_import.py
"""Daily SharePoint pickup of bulk-import sheets (see sharepoint_import_service.py). Runs outside
the API process; a Postgres advisory lock stops two runs overlapping.
Requires migration_bulk_import.sql (and migration_tds_challan.sql for TDS sheets).

Run from the Account_Payables project root:

    python -m Backend.scripts.run_sharepoint_import             # dry run: list sheets + documents found
    python -m Backend.scripts.run_sharepoint_import --execute   # import (schedule once a day)

Local testing without SharePoint (same layout, checks and auto-recording, under a local folder):

    python -m Backend.scripts.run_sharepoint_import --local                  # dry run on Backend/local_imports
    python -m Backend.scripts.run_sharepoint_import --local --execute
    python -m Backend.scripts.run_sharepoint_import --local D:/ap-test --execute

On/off: "SharePoint import" switch on the AP Automation page (AP_AUTOMATION_MANAGE), stored as
BULK_IMPORT_SHAREPOINT_ENABLED, OFF by default. While it is off --execute does nothing; a dry run
still works, to test the SharePoint connection.

.env: SHAREPOINT_SITE (required), SHAREPOINT_LIBRARY (default Documents), SHAREPOINT_ROOT_FOLDER
(default "AP Imports"), plus the existing TENANT_ID / CLIENT_ID / CLIENT_SECRET.

Windows Task Scheduler (daily), action:
    Program:   <project>\\ap\\Scripts\\python.exe
    Arguments: -m Backend.scripts.run_sharepoint_import --execute
    Start in:  <project>   (the Account_Payables folder)
"""
import argparse
import asyncio
import json
import logging


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import payment / TDS sheets from SharePoint.")
    parser.add_argument("--execute", action="store_true", help="Import and record (default: dry run).")
    parser.add_argument("--local", nargs="?", const="", default=None, metavar="FOLDER",
                        help="Read a local folder instead of SharePoint (default Backend/local_imports or LOCAL_IMPORT_FOLDER).")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Registers every model WITHOUT importing Backend.main (that would run create_all).
    from Backend.Data_Access_Layer import models  # noqa: F401
    from Backend.Business_Layer.services import sharepoint_import_service as pickup

    client = None
    if args.local is not None:
        from Backend.Business_Layer.utils.local_drive_client import LocalDriveClient
        client = LocalDriveClient(args.local or None)
        for folder in pickup.FOLDERS.values():
            client.ensure_folder(f"{folder}/Inbox")
        print(json.dumps({"source": "local folder", "folder": str(client.root)}))
    try:
        report = asyncio.run(pickup.run_locked(args.execute, client=client))
    except Exception as exc:
        logging.exception("SharePoint import failed")
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    if report is None:
        print(json.dumps({"status": "skipped", "reason": "another import run is in progress"}))
    elif report.disabled:
        print(json.dumps({"status": "disabled", "reason": "SharePoint import is switched off (AP Automation page)"}))
    else:
        print(json.dumps({"status": "ok", "mode": "execute" if args.execute else "dry-run",
                          "sheets": report.sheets, "errors": report.errors}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
