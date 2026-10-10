# Backend/scripts/run_email_intake.py
"""Email invoice intake runner (see invoice_email_intake_service.py). Runs OUTSIDE the API
process, so several API workers never read the mailbox twice; a Postgres advisory lock also stops
two runners overlapping. Requires migration_invoice_bulk_upload.sql.

Run from the Account_Payables project root:

    python -m Backend.scripts.run_email_intake                      # dry run: list what would be imported
    python -m Backend.scripts.run_email_intake --execute            # import once (Task Scheduler / cron)
    python -m Backend.scripts.run_email_intake --execute --loop     # keep running every N minutes

On/off: the "Mailbox intake" switch on the Bulk Upload page (EMAIL_INTAKE_MANAGE permission,
stored as EMAIL_INTAKE_ENABLED in ap.system_configuration, OFF by default). While it is off an
--execute run does nothing; a dry run still works, to test the mailbox connection.

.env:
    EMAIL_INTAKE_START_DATE         required - go-live date; older mail is never imported
    VENDOR_EMAIL                    optional - comma-separated senders; when set ONLY their mail is read
    EMAIL_INTAKE_INTERVAL_MINUTES   --loop interval, default 15 (e.g. 30)
    EMAIL_INTAKE_LOOKBACK_HOURS     how far back each run looks, default 72
    EMAIL_INTAKE_SUBJECT_KEYWORDS   default "invoice,inv,bill,tax invoice,e-invoice,gst invoice"
    (TENANT_ID / CLIENT_ID / CLIENT_SECRET / MAIL_ADDRESS - the existing Graph app settings)

Windows Task Scheduler (every 15 minutes), action:
    Program:   <project>\\ap\\Scripts\\python.exe
    Arguments: -m Backend.scripts.run_email_intake --execute
    Start in:  <project>   (the Account_Payables folder)

The report is printed as JSON. Credentials and tokens are never printed.
"""
import argparse
import asyncio
import json
import logging
import time


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import invoices from the intake mailbox.")
    parser.add_argument("--execute", action="store_true", help="Create batches / invoices (default: dry run).")
    parser.add_argument("--loop", action="store_true", help="Keep running every --interval-minutes.")
    parser.add_argument("--interval-minutes", type=int, default=None, help="Loop interval (default EMAIL_INTAKE_INTERVAL_MINUTES or 15).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Imported here so --help works without a configured .env. Registers every model (mappers)
    # WITHOUT importing Backend.main - that would run create_all.
    from Backend.Data_Access_Layer import models  # noqa: F401
    from Backend.Business_Layer.services import invoice_email_intake_service as intake
    from Backend.config.env_loader import get_env_var

    interval = args.interval_minutes or int(get_env_var("EMAIL_INTAKE_INTERVAL_MINUTES", "15"))
    while True:
        started = time.time()
        try:
            report = asyncio.run(intake.run_locked(args.execute))
            if report is None:
                print(json.dumps({"status": "skipped", "reason": "another intake run is in progress"}))
            elif report.disabled:
                print(json.dumps({"status": "disabled", "reason": "Email intake is switched off (Bulk Upload page > Mailbox intake)"}))
            else:
                print(json.dumps({"status": "ok", "mode": "execute" if args.execute else "dry-run",
                                  "examined": report.examined, "already_imported": report.already_imported,
                                  "skipped": report.skipped, "imported": report.imported,
                                  "automation_rechecked": report.automation_rechecked,
                                  "errors": report.errors}, indent=2, default=str))
        except Exception as exc:  # keep the loop alive; a single bad run must not stop intake
            logging.exception("Email intake run failed")
            print(json.dumps({"status": "error", "error": str(exc)}))
            if not args.loop:
                return 1
        if not args.loop:
            return 0
        time.sleep(max(60, interval * 60 - (time.time() - started)))


if __name__ == "__main__":
    raise SystemExit(main())
