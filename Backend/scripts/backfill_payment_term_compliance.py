# Backend/scripts/backfill_payment_term_compliance.py
"""Evaluate payment-term compliance for invoices created before the feature existed
(see payment_term_compliance_service.py). Requires migration_payment_term_compliance.sql.

Run from the Account_Payables project root:

    python -m Backend.scripts.backfill_payment_term_compliance             # dry run (default)
    python -m Backend.scripts.backfill_payment_term_compliance --include-closed
    python -m Backend.scripts.backfill_payment_term_compliance --execute   # really write

A dry run computes every result inside a transaction that is always rolled back, so
nothing - neither invoice_payment_term rows nor invoice.due_date - is changed. --execute
commits one invoice at a time (a failure on one invoice does not block the others). By
default PAID / REJECTED invoices are skipped. The report is printed as JSON.
"""
import argparse
import json
from collections import Counter


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backfill payment-term compliance records.")
    parser.add_argument("--execute", action="store_true", help="Write the results (default: dry run).")
    parser.add_argument("--include-closed", action="store_true", help="Also evaluate PAID / REJECTED invoices.")
    parser.add_argument("--invoice-ids", type=int, nargs="+", help="Limit to these invoice ids.")
    args = parser.parse_args(argv)

    # Imported here so --help works without a configured DATABASE_URL.
    from Backend.Business_Layer.services.payment_term_compliance_service import (
        CLOSED_INVOICE_STATUS_CODES,
        PaymentTermComplianceService,
    )
    from Backend.Data_Access_Layer.dao.payment_term_dao import PaymentTermDAO
    from Backend.Data_Access_Layer.utils.database import SessionLocal

    db = SessionLocal()
    results, errors, statuses = [], [], Counter()
    try:
        ids = args.invoice_ids or PaymentTermDAO(db).list_invoice_ids_for_backfill(
            CLOSED_INVOICE_STATUS_CODES, args.include_closed
        )
        for invoice_id in ids:
            try:
                service = PaymentTermComplianceService(db)
                invoice = service.dao.get_invoice(invoice_id)
                due_before = invoice.due_date if invoice else None
                record = service.evaluate_invoice_id(invoice_id, "backfill")
                statuses[record.validation_status] += 1
                results.append({
                    "invoice_id": invoice_id,
                    "validation_status": record.validation_status,
                    "reason_code": record.reason_code,
                    "due_date_before": due_before.isoformat() if due_before else None,
                    "effective_due_date": record.effective_due_date.isoformat() if record.effective_due_date else None,
                })
                if args.execute:
                    db.commit()
            except Exception as exc:  # report and continue with the next invoice
                db.rollback()
                errors.append({"invoice_id": invoice_id, "error": str(exc)})
        if not args.execute:
            db.rollback()
    finally:
        db.close()

    print(json.dumps({
        "mode": "execute" if args.execute else "dry-run (rolled back, nothing written)",
        "evaluated": len(results),
        "by_status": dict(statuses),
        "errors": errors,
        "invoices": results,
    }, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
