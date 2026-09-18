# Backend/tests/manual_verify_ocr_reviewed_state.py
"""Manual, read-only DB verification script for the OCR_REVIEWED rollout.

Not a pytest test (no test_ prefix, no assertions) - this is a one-off
diagnostic to run by hand from the command line:

    python -m Backend.tests.manual_verify_ocr_reviewed_state

Connects using the same SessionLocal (and therefore the same Backend/.env
DATABASE_URL) the application itself uses, and queries entirely through
the real SQLAlchemy ORM models - no raw SQL/text() - so this always
reflects what the app's own models believe the schema looks like.

Checks, in order, matching the migration files:
  Backend/Data_Access_Layer/migration_add_ocr_reviewed_status.sql
  Backend/Data_Access_Layer/migration_fix_invoice_approval_step_fk.sql

  1. status_master has every expected INVOICE + PAYMENT status row.
  2. Invoices sitting at PENDING_APPROVAL with no InvoiceApproval row at
     all (ambiguously stuck under the old status meaning).
  3. The invoice_approval_step -> invoice_approval FK actually targets
     ap.invoice_approval, not the renamed ap.invoice_approval_legacy.
  4. ap.invoice_approval_legacy is empty (nothing orphaned there).

Read-only: issues no INSERT/UPDATE/DDL.
"""
from __future__ import annotations

from sqlalchemy import inspect, select

from Backend.Data_Access_Layer.utils.database import SessionLocal
from Backend.Data_Access_Layer.models.master import StatusMaster
from Backend.Data_Access_Layer.models.invoice import Invoice
from Backend.Data_Access_Layer.models.approval import InvoiceApproval

EXPECTED_INVOICE_STATUSES = {
    "OCR_REVIEW_PENDING", "OCR_REVIEWED", "OCR_FAILED", "PENDING_APPROVAL",
    "APPROVED", "REJECTED", "RETURNED_FOR_REVIEW", "READY_FOR_PAYMENT",
    "PARTIALLY_PAID", "PAID", "DISPUTED",
}
EXPECTED_PAYMENT_STATUSES = {"SCHEDULED", "SENT", "CLEARED", "FAILED"}


def check_status_master(db) -> None:
    print("=== 1. status_master ===")

    invoice_rows = db.execute(
        select(StatusMaster)
        .where(StatusMaster.module_name == "INVOICE")
        .order_by(StatusMaster.display_order)
    ).scalars().all()
    for row in invoice_rows:
        print(f"  INVOICE  status_id={row.status_id:<4} status_code={row.status_code:<22} "
              f"display_order={row.display_order}")

    invoice_codes = {row.status_code for row in invoice_rows}
    missing_invoice = EXPECTED_INVOICE_STATUSES - invoice_codes
    print("  Missing INVOICE statuses:", missing_invoice or "NONE")

    payment_rows = db.execute(
        select(StatusMaster)
        .where(StatusMaster.module_name == "PAYMENT")
        .order_by(StatusMaster.display_order)
    ).scalars().all()
    for row in payment_rows:
        print(f"  PAYMENT  status_id={row.status_id:<4} status_code={row.status_code}")

    payment_codes = {row.status_code for row in payment_rows}
    missing_payment = EXPECTED_PAYMENT_STATUSES - payment_codes
    print("  Missing PAYMENT statuses:", missing_payment or "NONE")


def check_stuck_invoices(db) -> None:
    print("\n=== 2. Invoices at PENDING_APPROVAL with no InvoiceApproval row ===")

    pending_status_id = db.execute(
        select(StatusMaster.status_id).where(
            StatusMaster.module_name == "INVOICE",
            StatusMaster.status_code == "PENDING_APPROVAL",
        )
    ).scalar_one_or_none()

    if pending_status_id is None:
        print("  PENDING_APPROVAL status not found in status_master - cannot check.")
        return

    approved_invoice_ids = set(
        db.execute(select(InvoiceApproval.invoice_id)).scalars().all()
    )

    candidates = db.execute(
        select(Invoice).where(Invoice.status_id == pending_status_id)
    ).scalars().all()

    stuck = [inv for inv in candidates if inv.invoice_id not in approved_invoice_ids]

    for inv in stuck:
        print(f"  invoice_id={inv.invoice_id} invoice_number={inv.invoice_number!r} "
              f"status_id={inv.status_id} updated_at={inv.updated_at}")

    print(f"  Stuck count: {len(stuck)}")


def check_fk_target(db) -> None:
    print("\n=== 3. invoice_approval_step -> invoice_approval FK target ===")

    bind = db.get_bind()
    inspector = inspect(bind)
    fks = inspector.get_foreign_keys("invoice_approval_step", schema="ap")

    match = next((fk for fk in fks if fk.get("name") == "fk_invoice_approval_step_approval"), None)

    if match is None:
        print("  Constraint 'fk_invoice_approval_step_approval' NOT FOUND at all.")
        return

    target = match["referred_table"]
    print(f"  fk_invoice_approval_step_approval -> {target}")
    if target == "invoice_approval":
        print("  OK: FK points at the correct (new, multi-level) table.")
    else:
        print(f"  BROKEN: FK still points at '{target}', not 'invoice_approval'.")


def check_legacy_table(db) -> None:
    print("\n=== 4. ap.invoice_approval_legacy row count ===")

    bind = db.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names(schema="ap")

    if "invoice_approval_legacy" not in tables:
        print("  Table ap.invoice_approval_legacy does not exist (nothing to check).")
        return

    # No ORM model exists for the legacy table by design (it's a dead
    # remnant, not part of the app) - reflect it via Core just for this count.
    from sqlalchemy import Table, MetaData, func

    metadata = MetaData()
    legacy = Table("invoice_approval_legacy", metadata, schema="ap", autoload_with=bind)
    count = db.execute(select(func.count()).select_from(legacy)).scalar_one()

    print(f"  Row count: {count}")
    if count == 0:
        print("  OK: legacy table is empty, as expected.")
    else:
        print("  STOP: legacy table is NOT empty - real historical data may be sitting here.")


def main() -> None:
    db = SessionLocal()
    try:
        check_status_master(db)
        check_stuck_invoices(db)
        check_fk_target(db)
        check_legacy_table(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
