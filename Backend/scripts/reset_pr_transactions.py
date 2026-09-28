# Backend/scripts/reset_pr_transactions.py
"""Reset Purchase Requisition transaction data (see pr_reset_service.py).

Run from the Account_Payables project root:

    python -m Backend.scripts.reset_pr_transactions            # dry run (default)
    python -m Backend.scripts.reset_pr_transactions --pr-ids 12 15
    python -m Backend.scripts.reset_pr_transactions --execute  # really delete

A dry run only reads. --execute deletes the eligible PRs in one transaction,
verifies the cascade and every protected table, and rolls back on any
failure. The report is printed as JSON.
"""
import argparse
import json
import sys

from Backend.Business_Layer.services.pr_reset_service import PrResetError, PrResetService


def _plan_report(plan) -> dict:
    return {
        "eligible_pr_ids": plan.eligible,
        "blocked": {str(pr_id): reasons for pr_id, reasons in plan.blocked.items()},
        "rows_removed_by_cascade": plan.cascade_counts,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Reset PR transaction data.")
    parser.add_argument("--execute", action="store_true", help="Delete eligible PRs (default: dry run).")
    parser.add_argument("--pr-ids", type=int, nargs="+", help="Limit to these PR ids (default: all PRs).")
    args = parser.parse_args(argv)

    # Imported here so --help works without a configured DATABASE_URL.
    from Backend.Data_Access_Layer.utils.database import engine

    with engine.connect() as conn:
        service = PrResetService(conn)
        try:
            if args.execute:
                result = service.execute(args.pr_ids)
                report = {
                    "mode": "execute",
                    "executed": result.executed,
                    "deleted_pr_ids": result.deleted_pr_ids,
                    "deleted_rows": result.deleted_counts,
                    "protected_tables_verified_unchanged": result.protected_tables_checked,
                    **_plan_report(result.plan),
                }
            else:
                plan = service.plan(args.pr_ids)
                conn.rollback()  # read-only: never leave the implicit transaction open
                report = {"mode": "dry-run", **_plan_report(plan)}
        except PrResetError as exc:
            print(json.dumps({"error": str(exc)}, indent=2))
            return 1

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
