# Backend/scripts/reset_demo_transactions.py
"""Clear all AP transaction data before loading the client demo dataset.

Run from the Account_Payables project root:

    python -m Backend.scripts.reset_demo_transactions                 # dry run (default)
    python -m Backend.scripts.reset_demo_transactions --execute       # really delete
    python -m Backend.scripts.reset_demo_transactions --execute --delete-files

What is cleared: purchase requisitions, RFQs, quotations, POs, GRNs, invoices
(lines, attachments, issues, approvals, payment terms, TDS, challans, filings),
payments, upload batches, bulk imports, inbound documents, notifications and
the audit rows of those records.

What is kept: vendors (and their addresses, tax, TDS profiles, banks,
agreements, NDAs, onboarding requests), approval policies, departments,
categories, tax rules, payment terms, system configuration, and the audit
rows of vendors and configuration.

A dry run only reads. --execute refuses to run against any database other
than accounts_payable, deletes everything in one transaction and rolls back
on any failure. Stored files (S3) are left in place unless --delete-files is
given, so a database restore from backup still finds its documents.
"""
import argparse
import json
import sys

EXPECTED_DATABASE = "accounts_payable"

# Every table here is emptied (row DELETEs, children before parents, foreign keys
# checked), and the dry run proves no kept table with rows points into them.
CLEARED_TABLES = [
    "purchase_requisition", "purchase_requisition_line", "rfq", "rfq_vendor", "quotation",
    "purchase_order", "purchase_order_line", "goods_receipt", "goods_receipt_line",
    "invoice", "invoice_line", "invoice_attachment", "invoice_issue", "invoice_payment_term",
    "invoice_approval", "invoice_approval_step", "invoice_approval_step_approver", "invoice_approval_legacy",
    "invoice_tds", "invoice_tds_tracking", "invoice_tds_document",
    "tds_challan", "tds_challan_allocation", "tds_return_filing", "tds_return_filing_invoice",
    "payment", "payment_invoice", "payment_document",
    "inbound_document", "invoice_upload_batch", "invoice_upload_batch_item",
    "bulk_import_job", "bulk_import_row", "notification", "recurring_occurrence", "invoice_gst", "vendor_note", "invoice_assignment", "payment_run", "payment_run_item",
    "gstr2b_entry", "gstr2b_import",
]

# Audit rows are kept for vendors and configuration; these table names go.
CLEARED_AUDIT_TABLES = sorted(set(CLEARED_TABLES) - {"notification"})

# (table, column) holding a stored-file key, for --delete-files.
FILE_COLUMNS = [
    ("invoice_attachment", "file_path"), ("inbound_document", "file_path"),
    ("invoice_tds_document", "file_path"), ("payment_document", "file_path"),
    ("goods_receipt", "file_path"), ("quotation", "file_url"),
    ("tds_challan", "file_path"), ("tds_return_filing", "file_path"),
    ("invoice_upload_batch_item", "file_path"), ("bulk_import_job", "file_path"),
    ("bulk_import_row", "document_path"), ("vendor_note", "file_path"), ("gstr2b_import", "file_path"),
]

# Spot-checked before and after: these counts must not change.
PROTECTED_TABLES = [
    "vendor", "vendor_agreement", "vendor_agreement_document", "vendor_nda", "vendor_onboarding_request", "recurring_schedule",
    "approval_policy", "department", "purchase_category", "payment_term", "tax_rule",
    "tax_rate_rule", "system_configuration",
]


def _existing(conn, tables):
    from sqlalchemy import text
    rows = conn.execute(text(
        "select table_name from information_schema.tables where table_schema='ap' and table_name = any(:t)"
    ), {"t": list(tables)}).scalars()
    found = set(rows)
    return [t for t in tables if t in found]


def _counts(conn, tables):
    from sqlalchemy import text
    return {t: conn.execute(text(f'select count(*) from ap."{t}"')).scalar() for t in tables}


def _foreign_keys(conn):
    from sqlalchemy import text
    return conn.execute(text("""
        select distinct tc.table_name, ccu.table_name
        from information_schema.table_constraints tc
        join information_schema.constraint_column_usage ccu
          on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
        where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'ap'
    """)).fetchall()


def _blocking(fks, rows, kept_count):
    """Kept tables WITH rows that reference a cleared table with rows - these would
    lose their parent rows, so the reset refuses to run."""
    return sorted(f"{child} -> {parent}" for child, parent in fks
                  if parent in rows and rows[parent] and child not in rows and kept_count(child))


def _break_cycles(conn, pending):
    """Rows that reference each other (invoice <-> inbound_document): clear the nullable
    foreign-key columns between the remaining tables - those rows are being deleted anyway."""
    from sqlalchemy import text
    cols = conn.execute(text("""
        select kcu.table_name, kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema
        join information_schema.constraint_column_usage ccu
          on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
        join information_schema.columns c
          on c.table_schema = kcu.table_schema and c.table_name = kcu.table_name and c.column_name = kcu.column_name
        where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'ap' and c.is_nullable = 'YES'
          and kcu.table_name = any(:p) and ccu.table_name = any(:p)"""), {"p": list(pending)}).fetchall()
    for table, column in cols:
        conn.execute(text(f'update ap."{table}" set "{column}" = null where "{column}" is not null'))
    return bool(cols)


def _restart_identities(conn, tables):
    """IDs of the emptied tables start again from 1 (serial sequences and identity columns)."""
    from sqlalchemy import text
    cols = conn.execute(text("""
        select table_name, column_name, is_identity, column_default from information_schema.columns
        where table_schema = 'ap' and table_name = any(:t)
          and (is_identity = 'YES' or column_default like 'nextval(%')"""), {"t": list(tables)}).fetchall()
    for table, column, is_identity, _ in cols:
        if is_identity == "YES":
            conn.execute(text(f'alter table ap."{table}" alter column "{column}" restart'))
        else:
            seq = conn.execute(text("select pg_get_serial_sequence(:t, :c)"), {"t": f"ap.{table}", "c": column}).scalar()
            if seq:
                conn.execute(text(f"alter sequence {seq} restart"))


def _file_keys(conn, present):
    from sqlalchemy import text
    keys = set()
    for table, column in FILE_COLUMNS:
        if table in present:
            keys.update(k for k in conn.execute(text(f'select "{column}" from ap."{table}" where "{column}" is not null')).scalars() if k)
    # never touch a file a kept record still uses
    if "vendor_agreement_document" in _existing(conn, ["vendor_agreement_document"]):
        keys -= set(conn.execute(text("select file_path from ap.vendor_agreement_document where file_path is not null")).scalars())
    return sorted(keys)


def _audit_count(conn):
    from sqlalchemy import text
    return conn.execute(text("select count(*) from ap.audit_log where table_name = any(:t)"), {"t": CLEARED_AUDIT_TABLES}).scalar()


def plan(conn):
    from sqlalchemy import text
    present = _existing(conn, CLEARED_TABLES)
    rows = _counts(conn, present)
    kept = {}

    def kept_count(table):
        if table not in kept:
            kept[table] = _counts(conn, [table])[table]
        return kept[table]

    blocking = _blocking(_foreign_keys(conn), rows, kept_count)
    return {
        "database": conn.execute(text("select current_database()")).scalar(),
        "rows_to_delete": rows,
        "audit_log_rows_to_delete": _audit_count(conn),
        "audit_log_rows_kept": conn.execute(text("select count(*) from ap.audit_log where not (table_name = any(:t))"),
                                            {"t": CLEARED_AUDIT_TABLES}).scalar(),
        "tables_not_in_this_database": sorted(set(CLEARED_TABLES) - set(present)),
        "kept_tables_referencing_cleared_ones": blocking,
        "tables_with_rows": sorted(t for t, n in rows.items() if n),
        "protected_counts": _counts(conn, _existing(conn, PROTECTED_TABLES)),
        "stored_files": _file_keys(conn, set(present)),
    }


def execute(conn, report):
    from sqlalchemy import text
    if report["database"] != EXPECTED_DATABASE:
        raise RuntimeError(f"Refusing to run against database {report['database']!r}; expected {EXPECTED_DATABASE!r}.")
    if report["kept_tables_referencing_cleared_ones"]:
        raise RuntimeError("Kept tables still reference cleared ones: " + ", ".join(report["kept_tables_referencing_cleared_ones"]))
    tables = report["tables_with_rows"]
    try:
        conn.execute(text("delete from ap.audit_log where table_name = any(:t)"), {"t": CLEARED_AUDIT_TABLES})
        # Plain DELETEs, no CASCADE: a table whose rows are still referenced is retried after the
        # others; anything outside the list still pointing in makes the whole reset fail.
        pending = list(tables)
        while pending:
            progressed = False
            for t in list(pending):
                try:
                    with conn.begin_nested():
                        conn.execute(text(f'delete from ap."{t}"'))
                    pending.remove(t)
                    progressed = True
                except Exception:
                    continue
            if not progressed and not _break_cycles(conn, pending):
                raise RuntimeError(f"Could not delete rows from: {pending}")
        left = {t: n for t, n in _counts(conn, list(report["rows_to_delete"])).items() if n}
        if left:
            raise RuntimeError(f"Rows left after delete: {left}")
        _restart_identities(conn, list(report["rows_to_delete"]))
        changed = {t: (before, after) for t, before in report["protected_counts"].items()
                   if (after := _counts(conn, [t])[t]) != before}
        if changed:
            raise RuntimeError(f"Protected tables changed: {changed}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def delete_files(keys):
    from Backend.API_Layer.utils.s3_utils import delete_from_s3
    failed = []
    for key in keys:
        if (delete_from_s3(key) or {}).get("status") != "success":
            failed.append(key)
    return failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Clear AP transaction data for the demo dataset.")
    parser.add_argument("--execute", action="store_true", help="Delete (default: dry run).")
    parser.add_argument("--delete-files", action="store_true", help="With --execute, also delete the stored files.")
    parser.add_argument("--show-files", action="store_true", help="List every stored-file key in the report.")
    args = parser.parse_args(argv)

    # Imported here so --help works without a configured DATABASE_URL.
    from Backend.Data_Access_Layer.utils.database import engine

    with engine.connect() as conn:
        report = plan(conn)
        conn.rollback()
        keys = report.pop("stored_files")
        report["stored_files"] = {"count": len(keys), "action": "delete" if args.delete_files else "keep"}
        if args.show_files:
            report["stored_files"]["keys"] = keys
        if not args.execute:
            print(json.dumps({"mode": "dry-run", **report}, indent=2))
            return 0
        try:
            execute(conn, report)
        except RuntimeError as exc:
            print(json.dumps({"mode": "execute", "error": str(exc)}, indent=2))
            return 1

    report["mode"] = "execute"
    report["deleted"] = True
    if args.delete_files:
        report["stored_files"]["failed"] = delete_files(keys)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
