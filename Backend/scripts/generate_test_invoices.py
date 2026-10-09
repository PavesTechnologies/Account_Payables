"""Generate the APM synthetic test-invoice set.

Writes 50 synthetic invoice documents, 3 vendor-agreement documents, the
vendor registry and the expected outcome of every scenario to
``test-documents/synthetic_invoices_v1/``.

* Deterministic: the same seed + vendor registry always produce the same
  documents and the same ``scenarios.json``.
* No database, network, AWS or Redis access - safe to run anywhere.
* Every page carries a "SYNTHETIC TEST DOCUMENT" footer and every invoice
  number starts with ``TST``.

GSTIN policy (see APM_AUTOMATION_PLAN.md section 4.2): the two existing
vendors (AWS, KEKA) use their vendor-master GSTINs. New ``TST-`` vendors use
PLACEHOLDER GSTINs that are format-valid but carry a deliberately WRONG
mod-36 check digit, so they cannot belong to any registered taxpayer. Once
approved test identities are available, put them in a vendors file and
regenerate::

    python Backend/scripts/generate_test_invoices.py
    python Backend/scripts/generate_test_invoices.py --vendors my_vendors.json
"""

import argparse
import copy
import io
import json
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "test-documents" / "synthetic_invoices_v1"
SEED = 20261009
AS_OF = date(2026, 10, 9)  # "today" the expected overdue/upcoming flags are computed against
FOOTER = "SYNTHETIC TEST DOCUMENT - NOT A TAX INVOICE - APM test data, no real transaction"

BUYER = {
    "name": "Paves Global Infotech Pvt Ltd",
    "address": ["Hyderabad, Telangana, India"],
    "state": "Telangana",
    "state_code": "36",
}

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    """Standard GSTIN mod-36 check character (weights 1,2,1,2,... from the left) - the same
    scheme as Business_Layer/utils/extraction/normalizers.gstin_checksum_valid."""
    factor, total = 1, 0
    for ch in first14:
        addend = factor * GSTIN_CHARS.index(ch)
        factor = 1 if factor == 2 else 2
        total += (addend // 36) + (addend % 36)
    return GSTIN_CHARS[(36 - (total % 36)) % 36]


def placeholder_gstin(state_code: str, pan: str) -> str:
    """Format-valid GSTIN whose check digit is deliberately wrong (never a real registration)."""
    first14 = f"{state_code}{pan}1Z"
    valid = gstin_check_char(first14)
    wrong = GSTIN_CHARS[(GSTIN_CHARS.index(valid) + 7) % 36]
    return first14 + wrong


# ---------------------------------------------------------------------------
# Master data (existing rows are read-only references; TST- rows are PROPOSED)
# ---------------------------------------------------------------------------

def _tst_vendor(code, name, pan, state, state_code, address, entity, master_term, msme=None, bank="TEST BANK LTD"):
    return {
        "vendor_code": code,
        "vendor_name": name,
        "existing": False,
        "pan": pan,
        "gstin": placeholder_gstin(state_code, pan),
        "gstin_status": "PLACEHOLDER_CHECKSUM_INVALID",
        "state": state,
        "state_code": state_code,
        "address": address,
        "entity_type": entity,
        "master_payment_term": master_term,
        "msme_category": msme,
        "bank_note": f"{bank} - A/c XXXXXXXX{4100 + int(code[-3:]) * 37} - IFSC TEST0000001 (synthetic)",
    }


DEFAULT_VENDORS: Dict[str, dict] = {
    "AWS": {
        "vendor_code": "AWSIPL0336", "vendor_id": 15, "existing": True,
        "vendor_name": "AMAZON WEB SERVICES INDIA PRIVATE LIMITED",
        "pan": "AAJCA9880A", "gstin": "07AAJCA9880A1ZL", "gstin_status": "VENDOR_MASTER",
        "state": "Delhi", "state_code": "07",
        "address": ["14th Floor, International Trade Tower, Block E", "Nehru Place, South Delhi", "Delhi - 110019, India"],
        "entity_type": "COMPANY", "master_payment_term": "Net 15", "msme_category": None,
        "bank_note": "Remit as per vendor master bank details",
    },
    "KEKA": {
        "vendor_code": "KTPL1020", "vendor_id": 16, "existing": True,
        "vendor_name": "KEKA TECHNOLOGIES PRIVATE LIMITED",
        "pan": "AAFCK5835K", "gstin": "36AAFCK5835K1Z6", "gstin_status": "VENDOR_MASTER",
        "state": "Telangana", "state_code": "36",
        "address": ["Survey no. 17, Vasavi Shalom Sky City", "Gachibowli, Rangareddy", "Hyderabad, Telangana - 500032"],
        "entity_type": "COMPANY", "master_payment_term": None, "msme_category": None,
        "bank_note": "Remit as per vendor master bank details",
    },
    "SKYLINE": _tst_vendor("TST-001", "[TEST] Skyline Realty LLP", "TSTFS0001T", "Telangana", "36",
                           ["Plot 21, Test Tech Park Road", "Madhapur, Hyderabad - 500081"], "FIRM", "Net 15"),
    "NIMBUS": _tst_vendor("TST-002", "[TEST] Nimbus Cloud Software Pvt Ltd", "TSTCN0002T", "Karnataka", "29",
                          ["4th Floor, Test Orbit Building", "Outer Ring Road, Bengaluru - 560103"], "COMPANY", "Net 30"),
    "ARORA": _tst_vendor("TST-003", "[TEST] Arora & Associates, Chartered Accountants", "TSTFA0003T", "Telangana", "36",
                         ["Suite 5, Test Chambers, Himayatnagar", "Hyderabad - 500029"], "FIRM", "Net 15"),
    "MERIDIAN": _tst_vendor("TST-004", "[TEST] Meridian Consulting Pvt Ltd", "TSTCM0004T", "Maharashtra", "27",
                            ["12th Floor, Test Business Bay", "Lower Parel, Mumbai - 400013"], "COMPANY", "Net 45"),
    "OFFICEMART": _tst_vendor("TST-005", "[TEST] Officemart Supplies Pvt Ltd", "TSTCO0005T", "Telangana", "36",
                              ["Shop 3-4, Test Market Complex", "Ameerpet, Hyderabad - 500016"], "COMPANY", "Net 30"),
    "VERTEX": _tst_vendor("TST-006", "[TEST] Vertex IT Hardware Pvt Ltd", "TSTCV0006T", "Tamil Nadu", "33",
                          ["No. 88, Test Electronics Street", "Guindy, Chennai - 600032"], "COMPANY", "Net 45"),
    "CLEANPRO": _tst_vendor("TST-007", "[TEST] CleanPro Facility Services (Prop. R. Test Kumar)", "TSTPK0007T",
                            "Telangana", "36", ["H.No 2-45, Test Colony", "Kukatpally, Hyderabad - 500072"],
                            "INDIVIDUAL", "Net 30"),
    "BRIGHTSPARK": _tst_vendor("TST-008", "[TEST] BrightSpark Electricals Pvt Ltd", "TSTCB0008T", "Telangana", "36",
                               ["Unit 7, Test Industrial Estate", "Balanagar, Hyderabad - 500037"], "COMPANY", "Net 30",
                               msme="MICRO"),
    "METROPOWER": _tst_vendor("TST-009", "[TEST] Metro Power & Utilities Ltd", "TSTCM0009T", "Telangana", "36",
                              ["Test Power House, Khairatabad", "Hyderabad - 500004"], "COMPANY", "Net 15"),
    "FIBERLINK": _tst_vendor("TST-010", "[TEST] FiberLink Broadband Pvt Ltd", "TSTCF0010T", "Telangana", "36",
                             ["2nd Floor, Test Fiber Tower", "Banjara Hills, Hyderabad - 500034"], "COMPANY", "Net 15"),
    "SAIKRISHNA": _tst_vendor("TST-011", "[TEST] Sai Krishna Packaging Works (Prop. S. Test Rao)", "TSTPS0011T",
                              "Telangana", "36", ["Plot 9, Test MSME Park", "Cherlapally, Hyderabad - 500051"],
                              "INDIVIDUAL", "Net 60", msme="SMALL"),
}

# purchase category -> (department, mapped TDS payment nature, existing?)
CATEGORIES = {
    "IT_HARDWARE": ("IT", "PURCHASE_OF_GOODS", True),
    "IT_SOFTWARE": ("IT", "PROFESSIONAL_SERVICE", True),
    "FIN_AUDIT": ("FIN", "OTHER", True),
    "FIN_ACCOUNTING": ("FIN", "OTHER", True),
    "ADMIN_OFFICE": ("ADMIN", "PURCHASE_OF_GOODS", True),
    "ADMIN_FACILITIES": ("ADMIN", "OTHER", True),
    "ADMIN_RENT": ("ADMIN", "RENT_LAND_BUILDING", False),
    "PROF_CONSULTING": ("FIN", "PROFESSIONAL_SERVICE", False),
    "IT_SERVICES": ("IT", "TECHNICAL_SERVICE", False),
    "ADMIN_UTILITIES": ("ADMIN", "OTHER", False),
}

# Active TDS_RATE rules in the dev DB (FY 2026-27, effective 2026-04-01).
# nature -> list of (section, rate %, threshold, threshold_type, entity filter)
TDS_RULES = {
    "RENT_LAND_BUILDING": [("194I", Decimal("10"), Decimal("50000"), "PER_TRANSACTION", None)],
    "PROFESSIONAL_SERVICE": [("194J", Decimal("10"), Decimal("50000"), "AGGREGATE_PERIOD", None)],
    "TECHNICAL_SERVICE": [("194J", Decimal("2"), Decimal("50000"), "AGGREGATE_PERIOD", None)],
    "CONTRACTOR": [("194C", Decimal("1"), Decimal("100000"), "AGGREGATE_PERIOD", {"INDIVIDUAL", "HUF"}),
                   ("194C", Decimal("2"), Decimal("100000"), "AGGREGATE_PERIOD", "OTHERS")],
    "PURCHASE_OF_GOODS": [("194Q", Decimal("0.1"), Decimal("5000000"), "AGGREGATE_PERIOD", None)],
}

# Vendor agreements (proposed feature). Generated as PDFs under agreements/.
AGREEMENTS = [
    {"id": "AGR-01", "vendor": "SKYLINE", "title": "Office Lease Agreement", "term_days": 15,
     "clause": "The Lessee shall pay the monthly rent within fifteen (15) days of receipt of a valid invoice.",
     "valid_from": date(2026, 4, 1), "valid_to": date(2027, 3, 31)},
    {"id": "AGR-02", "vendor": "MERIDIAN", "title": "Master Services Agreement", "term_days": 45,
     "clause": "Fees are payable within forty-five (45) days from the date of each undisputed invoice.",
     "valid_from": date(2026, 1, 1), "valid_to": date(2027, 12, 31)},
    {"id": "AGR-03", "vendor": "NIMBUS", "title": "SaaS Subscription Order Form", "term_days": 30,
     "clause": "Subscription fees are due Net 30 from the invoice date.",
     "valid_from": date(2025, 7, 1), "valid_to": date(2026, 6, 30)},  # expired -> renewal scenario
]

# Purchase orders the PO invoices reference (PROPOSED test POs; none exist yet).
POS = {
    "TST-PO-0001": {"vendor": "OFFICEMART", "terms": "Net 30", "days": 30, "basis": "INVOICE_DATE"},
    "TST-PO-0002": {"vendor": "OFFICEMART", "terms": "Net 30", "days": 30, "basis": "INVOICE_DATE"},
    "TST-PO-0003": {"vendor": "OFFICEMART", "terms": "Net 45", "days": 45, "basis": "INVOICE_DATE"},
    "TST-PO-0004": {"vendor": "OFFICEMART", "terms": None, "days": None, "basis": "INVOICE_DATE"},
    "TST-PO-0005": {"vendor": "OFFICEMART", "terms": "Net 60", "days": 60, "basis": "INVOICE_DATE"},
    "TST-PO-0006": {"vendor": "SAIKRISHNA", "terms": "Net 60", "days": 60, "basis": "INVOICE_DATE"},
    "TST-PO-0007": {"vendor": "SAIKRISHNA", "terms": "Net 60", "days": 60, "basis": "INVOICE_DATE"},
    "TST-PO-0008": {"vendor": "SAIKRISHNA", "terms": "Net 60", "days": 60, "basis": "INVOICE_DATE"},
    "TST-PO-0009": {"vendor": "VERTEX", "terms": "Net 45 from GRN date", "days": 45, "basis": "GRN_DATE", "grn": date(2026, 7, 20)},
    "TST-PO-0010": {"vendor": "VERTEX", "terms": "Net 45 from GRN date", "days": 45, "basis": "GRN_DATE", "grn": date(2026, 9, 12)},
    "TST-PO-0011": {"vendor": "VERTEX", "terms": "Net 45 from GRN date", "days": 45, "basis": "GRN_DATE", "grn": date(2026, 10, 8)},
    "TST-PO-0012": {"vendor": "VERTEX", "terms": "Net 45 from GRN date", "days": 45, "basis": "GRN_DATE", "grn": date(2026, 10, 9)},
}


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    sid: str
    vendor: str
    inv_no: str
    inv_date: date
    category: str
    lines: List[Tuple[str, str, Decimal, Decimal]]  # description, HSN/SAC, qty, rate
    title: str
    terms: Optional[str] = None  # printed payment-terms text
    due_printed: Optional[str] = "AUTO"  # "AUTO" = derive from terms; None = not printed; or ISO date
    po: Optional[str] = None  # authoritative PO the invoice belongs to
    po_printed: Optional[str] = None  # what the document shows (defaults to po)
    discount_pct: Decimal = Decimal("0")
    gst: object = "AUTO"  # "AUTO" (18%), Decimal rate, or "EXEMPT"
    layout: str = "A"
    quality: str = "clean"  # clean | scan | photo | png
    special: Optional[str] = None
    special_ref: Optional[str] = None
    nature_override: Optional[str] = None
    target: str = "OCR_REVIEW_PENDING"
    payments: List[Tuple[date, object]] = field(default_factory=list)  # (date, "FULL" | Decimal)
    note: str = ""
    extra: Dict[str, str] = field(default_factory=dict)  # layout-specific fields


D = Decimal


def L(desc, code, qty, rate):
    return (desc, code, D(str(qty)), D(str(rate)))


def build_scenarios() -> List[Scenario]:
    s: List[Scenario] = []
    months = ["April", "May", "June", "July", "August", "September", "October"]

    # --- Rent (ADMIN_RENT, 194I 10% above 50,000 per transaction) ------------------------
    rent_terms = "Payable within 15 days of invoice"
    for i, (m, target, pays, extra) in enumerate([
        (4, "PAID", [(date(2026, 4, 12), "FULL")], {}),
        (5, "PAID", [(date(2026, 5, 14), "FULL")], {}),
        (6, "PAID", [(date(2026, 6, 15), "FULL")], {}),
    ]):
        s.append(Scenario(f"S{i + 1:02d}", "SKYLINE", f"TST-SRL-2627-{i + 1:03d}", date(2026, m, 1), "ADMIN_RENT",
                          [L(f"Rent for office premises (4,000 sq ft) - {months[m - 4]} 2026", "997212", 1, 120000)],
                          "Monthly office rent", terms=rent_terms, layout="C", target=target, payments=pays))
    s.append(Scenario("S04", "SKYLINE", "TST-SRL-2627-004", date(2026, 7, 1), "ADMIN_RENT",
                      [L("Rent for office premises (4,000 sq ft) - July 2026", "997212", 1, 120000)],
                      "Invoice says Net 30; lease says 15 days", terms="Net 30", layout="C", target="PAID",
                      payments=[(date(2026, 7, 28), "FULL")], note="Paid after the lease due date (late payment KPI)."))
    s.append(Scenario("S05", "SKYLINE", "TST-SRL-2627-005", date(2026, 8, 1), "ADMIN_RENT",
                      [L("Rent for office premises (4,000 sq ft) - August 2026", "997212", 1, 120000)],
                      "Scanned rent invoice, unpaid and overdue", terms=rent_terms, layout="C", quality="scan",
                      target="READY_FOR_PAYMENT"))
    s.append(Scenario("S06", "SKYLINE", "TST-SRL-2627-006", date(2026, 9, 1), "ADMIN_RENT",
                      [L("Common area maintenance - September 2026", "997212", 1, 33000),
                       L("Reserved car parking (6 slots) - September 2026", "997212", 6, 2000)],
                      "Below the 194I per-transaction threshold - no TDS", terms=rent_terms, layout="C",
                      target="APPROVED"))
    s.append(Scenario("S07", "SKYLINE", "TST-SRL-2627-007", date(2026, 9, 1), "ADMIN_RENT",
                      [L("Rent for office premises (4,000 sq ft) - September 2026", "997212", 1, 120000)],
                      "Rent ready for payment, overdue", terms=rent_terms, layout="C", target="READY_FOR_PAYMENT"))
    s.append(Scenario("S08", "SKYLINE", "TST-SRL-2627-008", date(2026, 10, 1), "ADMIN_RENT",
                      [L("Rent for office premises (4,000 sq ft) - October 2026", "997212", 1, 120000)],
                      "Rent due within the next 7 days", terms=rent_terms, layout="C", target="READY_FOR_PAYMENT"))

    # --- Software subscriptions & IT services --------------------------------------------
    s.append(Scenario("S09", "AWS", "TST-AWS-2627-0412", date(2026, 4, 5), "IT_SOFTWARE",
                      [L("Amazon EC2 compute usage - March 2026", "998315", 1, 52000),
                       L("Amazon S3 storage & data transfer - March 2026", "998315", 1, 18500),
                       L("AWS Business Support plan - March 2026", "998315", 1, 14500)],
                      "Cloud usage, terms match vendor master", terms="Net 15", layout="B", target="PAID",
                      payments=[(date(2026, 4, 18), "FULL")]))
    s.append(Scenario("S10", "AWS", "TST-AWS-2627-0658", date(2026, 6, 5), "IT_SOFTWARE",
                      [L("Amazon EC2 compute usage - May 2026", "998315", 1, 57000),
                       L("Amazon RDS database usage - May 2026", "998315", 1, 21000),
                       L("AWS Business Support plan - May 2026", "998315", 1, 14000)],
                      "Paid 5 days late", terms="Net 15", layout="B", target="PAID",
                      payments=[(date(2026, 6, 25), "FULL")]))
    s.append(Scenario("S11", "AWS", "TST-AWS-2627-0871", date(2026, 8, 5), "IT_SOFTWARE",
                      [L("Amazon EC2 compute usage - July 2026", "998315", 1, 68000),
                       L("Amazon RDS database usage - July 2026", "998315", 1, 26000),
                       L("AWS Business Support plan - July 2026", "998315", 1, 16000)],
                      "No terms printed; due date printed (implies 15 days); partially paid",
                      terms=None, due_printed="2026-08-20", layout="B", target="PARTIALLY_PAID",
                      payments=[(date(2026, 8, 19), D("50000"))]))
    s.append(Scenario("S12", "AWS", "TST-AWS-2627-1093", date(2026, 10, 5), "IT_SOFTWARE",
                      [L("Amazon EC2 compute usage - September 2026", "998315", 1, 61000),
                       L("Amazon S3 storage & data transfer - September 2026", "998315", 1, 22000),
                       L("AWS Business Support plan - September 2026", "998315", 1, 15000)],
                      "Awaiting approval", terms="Net 15", layout="B", target="PENDING_APPROVAL"))
    s.append(Scenario("S13", "KEKA", "TST-KEKA-2627-0153", date(2026, 5, 10), "IT_SOFTWARE",
                      [L("Keka HRMS annual subscription (150 employees)", "997331", 150, 1600)],
                      "Vendor master has no payment term", terms="Net 30", layout="B", target="PAID",
                      payments=[(date(2026, 6, 8), "FULL")], note="Verified manually before Mark Ready."))
    s.append(Scenario("S14", "KEKA", "TST-KEKA-2627-0398", date(2026, 9, 10), "IT_SOFTWARE",
                      [L("Keka Payroll add-on module - annual", "997331", 1, 36000)],
                      "Unresolved payment-term exception (blocked from Ready for Payment)", terms="Net 30",
                      layout="B", target="APPROVED"))
    s.append(Scenario("S15", "NIMBUS", "TST-NCS-2026-0711", date(2026, 7, 1), "IT_SERVICES",
                      [L("Nimbus Analytics Platform - Enterprise plan (July 2026)", "998315", 1, 50000),
                       L("Additional named users", "998315", 10, 1000)],
                      "Agreement expired on 2026-06-30", terms="Net 30", layout="B", target="PAID",
                      payments=[(date(2026, 8, 5), "FULL")]))
    s.append(Scenario("S16", "NIMBUS", "TST-NCS-2026-0907", date(2026, 9, 1), "IT_SERVICES",
                      [L("Nimbus Analytics Platform - Enterprise plan (September 2026)", "998315", 1, 50000),
                       L("Additional named users", "998315", 10, 1000)],
                      "Invoice says Net 45; vendor master says Net 30 (scanned)", terms="Net 45", layout="B",
                      quality="scan", target="APPROVED"))
    usage = [L(f"{meter} usage - {date(2026, 9, d).strftime('%d %b %Y')} (calls x1000)", "998315",
               20 + (d * 7 + len(meter)) % 13, 55) for d in range(1, 31) for meter in ("Query API", "Ingest API")]
    usage += [L("Platform base fee - September 2026", "998315", 1, 16500),
              L("Premium support - September 2026", "998315", 1, 4000)]
    s.append(Scenario("S17", "NIMBUS", "TST-NCS-2026-1004", date(2026, 10, 1), "IT_SERVICES", usage,
                      "Multi-page metered usage invoice; agreement expired", terms="Net 30", layout="B",
                      target="OCR_REVIEW_PENDING"))

    # --- Professional / consulting -------------------------------------------------------
    s.append(Scenario("S18", "MERIDIAN", "TST-MER-0005", date(2026, 6, 15), "PROF_CONSULTING",
                      [L("Finance transformation advisory - Phase 1 (fixed fee)", "998311", 1, 350000)],
                      "Terms match agreement and vendor master", terms="Net 45", layout="A", target="PAID",
                      payments=[(date(2026, 7, 28), "FULL")]))
    s.append(Scenario("S19", "MERIDIAN", "TST-MER-0011", date(2026, 8, 14), "PROF_CONSULTING",
                      [L("Finance transformation advisory - Phase 2 milestone 1", "998311", 1, 275000)],
                      "No payment terms and no due date printed", terms=None, due_printed=None, layout="A",
                      target="APPROVED"))
    s.append(Scenario("S20", "MERIDIAN", "TST-MER-0016", date(2026, 9, 30), "PROF_CONSULTING",
                      [L("Process re-engineering workshop (3 days)", "998311", 3, 60000)],
                      "Ambiguous terms 'as per agreed terms'", terms="Payment as per agreed terms", due_printed=None,
                      layout="A", target="PENDING_APPROVAL"))
    s.append(Scenario("S21", "ARORA", "TST-AA-26-27-014", date(2026, 5, 20), "FIN_ACCOUNTING",
                      [L("Bookkeeping and accounting support - April & May 2026", "998222", 2, 15000)],
                      "Below the 194J aggregate threshold", terms="Net 15", layout="E",
                      nature_override="PROFESSIONAL_SERVICE", target="PAID", payments=[(date(2026, 6, 2), "FULL")]))
    s.append(Scenario("S22", "ARORA", "TST-AA-26-27-031", date(2026, 7, 31), "FIN_AUDIT",
                      [L("Statutory audit fee - FY 2025-26", "998221", 1, 150000)],
                      "Audit fee crosses the 194J aggregate threshold (scanned)", terms="Net 15", layout="E",
                      quality="scan", nature_override="PROFESSIONAL_SERVICE", target="PAID",
                      payments=[(date(2026, 8, 14), "FULL")]))
    s.append(Scenario("S23", "ARORA", "TST-AA-26-27-047", date(2026, 9, 15), "FIN_ACCOUNTING",
                      [L("GST return filing advisory - Q2 FY 2026-27", "998231", 1, 40000)],
                      "Ready for payment and overdue", terms="Net 15", layout="E",
                      nature_override="PROFESSIONAL_SERVICE", target="READY_FOR_PAYMENT"))
    s.append(Scenario("S24", "ARORA", "TST-AA-26-27-052", date(2026, 10, 3), "FIN_ACCOUNTING",
                      [L("Net-worth certification fee", "998221", 1, 25000)],
                      "'Due on receipt' conflicts with the vendor master Net 15", terms="Due on receipt", layout="E",
                      nature_override="PROFESSIONAL_SERVICE", target="PENDING_APPROVAL"))

    # --- Office supplies & procurement (PO invoices) -------------------------------------
    s.append(Scenario("S25", "OFFICEMART", "TST-OMS-1187", date(2026, 5, 12), "ADMIN_OFFICE",
                      [L("A4 copier paper 75 GSM (ream)", "4802", 100, 285),
                       L("Toner cartridge HP 12A compatible", "8443", 10, 3450),
                       L("Stationery kit (pens, files, notepads)", "9608", 50, 420)],
                      "PO invoice with trade discount, terms match PO", terms="Net 30", po="TST-PO-0001",
                      discount_pct=D("2"), layout="A", target="PAID", payments=[(date(2026, 6, 10), "FULL")]))
    s.append(Scenario("S26", "OFFICEMART", "TST-OMS-1302", date(2026, 7, 8), "ADMIN_OFFICE",
                      [L("Ergonomic office chair with lumbar support", "9401", 12, 8900)],
                      "PO invoice paid late", terms="Net 30", po="TST-PO-0002", layout="A", target="PAID",
                      payments=[(date(2026, 8, 20), "FULL")]))
    s.append(Scenario("S27", "OFFICEMART", "TST-OMS-1415", date(2026, 8, 20), "ADMIN_OFFICE",
                      [L("Magnetic whiteboard 6x4 ft", "9610", 6, 6500),
                       L("Cork notice board 4x3 ft", "9610", 4, 2750)],
                      "Invoice says Net 30; PO says Net 45", terms="Net 30", po="TST-PO-0003", layout="A",
                      target="READY_FOR_PAYMENT"))
    s.append(Scenario("S28", "OFFICEMART", "TST-OMS-1528", date(2026, 9, 18), "ADMIN_OFFICE",
                      [L("Pantry consumables (monthly pack)", "2101", 1, 22400),
                       L("Hot & cold water dispenser", "8516", 2, 9800)],
                      "The PO has no payment terms", terms="Net 30", po="TST-PO-0004", layout="A",
                      target="APPROVED"))
    s.append(Scenario("S29", "OFFICEMART", "TST-OMS-1611", date(2026, 10, 6), "ADMIN_OFFICE",
                      [L("A4 copier paper 75 GSM (ream)", "4802", 50, 285),
                       L("Box files (pack of 10)", "4820", 15, 300)],
                      "Phone photo of a PO invoice (JPG)", terms="Net 60", po="TST-PO-0005", layout="A",
                      quality="photo", target="READY_FOR_PAYMENT"))
    s.append(Scenario("S30", "SAIKRISHNA", "TST-SKP-0091", date(2026, 8, 1), "ADMIN_OFFICE",
                      [L("Corrugated shipping boxes 5-ply", "4819", 2000, 38),
                       L("Bubble wrap roll 1m x 100m", "3920", 40, 650)],
                      "MSME (small) vendor on Net 60: the 45-day statutory limit applies",
                      terms="Net 60", po="TST-PO-0006", gst=D("12"), layout="E", target="READY_FOR_PAYMENT"))
    s.append(Scenario("S31", "SAIKRISHNA", "TST-SKP-0127", date(2026, 9, 25), "ADMIN_OFFICE",
                      [L("Corrugated shipping boxes 3-ply", "4819", 1500, 31),
                       L("Packing tape 48mm (carton of 72)", "3919", 10, 1800)],
                      "MSME vendor; statutory due date comes before the contractual one", terms="Net 60",
                      po="TST-PO-0007", gst=D("12"), layout="E", target="APPROVED"))
    s.append(Scenario("S32", "SAIKRISHNA", "TST-SKP-0138", date(2026, 10, 2), "ADMIN_OFFICE",
                      [L("Corrugated shipping boxes 5-ply", "4819", 800, 38)],
                      "Invoice has no terms; PO terms apply (scanned)", terms=None, due_printed=None,
                      po="TST-PO-0008", gst=D("12"), layout="E", quality="scan", target="OCR_REVIEW_PENDING"))

    # --- IT hardware (PO, GRN-based terms, inter-state IGST) ---------------------------
    s.append(Scenario("S33", "VERTEX", "TST-VIT-2627-0072", date(2026, 7, 10), "IT_HARDWARE",
                      [L("Laptop 14\" i7 / 16GB / 512GB SSD", "8471", 5, 72000),
                       L("USB-C docking station", "8471", 5, 9500)],
                      "PO terms count from the GRN date", terms="Net 45 from GRN date", due_printed=None,
                      po="TST-PO-0009", layout="A", target="PAID", payments=[(date(2026, 9, 1), "FULL")]))
    hw = [L("27\" IPS monitor", "8528", 20, 14500), L("Wireless keyboard & mouse combo", "8471", 20, 1850)]
    hw += [L(f"HDMI 2.0 cable 2m - S/N TSTH{1000 + i}", "8544", 1, 450) for i in range(40)]
    s.append(Scenario("S34", "VERTEX", "TST-VIT-2627-0118", date(2026, 9, 5), "IT_HARDWARE", hw,
                      "Two-page PO invoice, partially paid", terms="Net 45 from GRN date", due_printed=None,
                      po="TST-PO-0010", layout="A", target="PARTIALLY_PAID",
                      payments=[(date(2026, 10, 1), D("150000"))]))
    s.append(Scenario("S35", "VERTEX", "TST-VIT-2627-0131", date(2026, 9, 28), "IT_HARDWARE",
                      [L("42U server rack with PDU", "9403", 1, 185000)],
                      "'45 days from delivery' must be read as GRN basis; GRN is after the invoice date",
                      terms="45 days from delivery", due_printed=None, po="TST-PO-0011", layout="A",
                      target="PENDING_APPROVAL"))
    s.append(Scenario("S36", "VERTEX", "TST-VIT-2627-0140", date(2026, 10, 7), "IT_HARDWARE",
                      [L("24-port managed gigabit switch", "8517", 4, 38000)],
                      "PO number misprinted (letter O instead of zero): PO not matched",
                      terms="Net 45 from GRN date", due_printed=None, po="TST-PO-0012", po_printed="TST-PO-OO12",
                      layout="A", target="OCR_REVIEW_PENDING"))

    # --- Facilities contractors (194C) -----------------------------------------------
    for sid, inv, d, target, pays, q in [
        ("S37", "TST-CFS/06/26", date(2026, 6, 30), "PAID", [(date(2026, 7, 25), "FULL")], "clean"),
        ("S38", "TST-CFS/07/26", date(2026, 7, 31), "PAID", [(date(2026, 8, 29), "FULL")], "scan"),
        ("S39", "TST-CFS/08/26", date(2026, 8, 31), "READY_FOR_PAYMENT", [], "clean"),
    ]:
        s.append(Scenario(sid, "CLEANPRO", inv, d, "ADMIN_FACILITIES",
                          [L(f"Housekeeping services - {d.strftime('%B %Y')} (4 staff)", "998533", 4, 11250)],
                          "Individual contractor; 194C 1% once the aggregate passes 1,00,000",
                          terms="Net 30", layout="E", quality=q, nature_override="CONTRACTOR",
                          target=target, payments=pays))
    s.append(Scenario("S40", "BRIGHTSPARK", "TST-BSE-2627-019", date(2026, 8, 10), "ADMIN_FACILITIES",
                      [L("Electrical AMC - Q2 FY 2026-27", "998719", 1, 125000)],
                      "MSME (micro) company contractor, 194C 2%, partially paid", terms="Net 30", layout="A",
                      nature_override="CONTRACTOR", target="PARTIALLY_PAID",
                      payments=[(date(2026, 9, 5), D("60000"))]))
    s.append(Scenario("S41", "BRIGHTSPARK", "TST-BSE-2627-027", date(2026, 9, 22), "ADMIN_FACILITIES",
                      [L("DG set repair & overhaul", "998719", 1, 38000)],
                      "MSME vendor prints Net 60 (above the 45-day limit); vendor master says Net 30",
                      terms="Net 60", layout="A", nature_override="CONTRACTOR", target="APPROVED"))

    # --- Utilities ----------------------------------------------------------------------
    for sid, bill_date, units, target, pays, q in [
        ("S42", date(2026, 8, 5), 2850, "PAID", [(date(2026, 8, 18), "FULL")], "clean"),
        ("S43", date(2026, 9, 5), 3120, "READY_FOR_PAYMENT", [], "clean"),
        ("S44", date(2026, 10, 5), 2960, "READY_FOR_PAYMENT", [], "png"),
    ]:
        period = (bill_date.replace(day=1) - timedelta(days=1)).strftime("%B %Y")
        energy = D(units) * D("8.40")
        duty = (energy * D("0.05")).quantize(D("1"), ROUND_HALF_UP)
        s.append(Scenario(sid, "METROPOWER", f"TST-MPU-{bill_date.strftime('%m%y')}-55021", bill_date,
                          "ADMIN_UTILITIES",
                          [L(f"Energy charges - {units} kWh @ 8.40", "2716", units, D("8.40")),
                           L("Fixed / demand charges", "2716", 1, 1500),
                           L("Electricity duty (5%)", "2716", 1, duty)],
                          "Utility bill: GST-exempt, due date printed, no terms text", terms=None,
                          due_printed=(bill_date + timedelta(days=15)).isoformat(), gst="EXEMPT", layout="D",
                          quality=q, target=target, payments=pays,
                          extra={"account": "TST-CONS-4471902", "period": period, "kind": "ELECTRICITY BILL"}))
    s.append(Scenario("S45", "FIBERLINK", "TST-FLB-Q2-0456", date(2026, 7, 1), "ADMIN_UTILITIES",
                      [L("Leased line 1 Gbps - Q2 (Jul-Sep 2026)", "998422", 3, 6000)],
                      "Quarterly broadband bill", terms="Net 15", layout="D", target="PAID",
                      payments=[(date(2026, 7, 10), "FULL")],
                      extra={"account": "TST-FL-88231", "period": "Jul - Sep 2026", "kind": "BROADBAND BILL"}))

    # --- Duplicates and invalid documents -----------------------------------------------
    s.append(Scenario("S46", "METROPOWER", "TST-MPU-0926-55021", date(2026, 9, 5), "ADMIN_UTILITIES", [],
                      "Byte-identical re-upload of S43", special="DUP_FILE", special_ref="S43", target="REJECTED_AT_INTAKE"))
    s.append(Scenario("S47", "OFFICEMART", "TST-OMS-1415", date(2026, 8, 20), "ADMIN_OFFICE", [],
                      "Same vendor + invoice number as S27, re-scanned with a different layout",
                      special="DUP_INVOICE", special_ref="S27", target="REJECTED_AT_INTAKE"))
    s.append(Scenario("S48", "MERIDIAN", "TSTMER0005", date(2026, 6, 18), "PROF_CONSULTING",
                      [L("Finance transformation advisory - Phase 1 (fixed fee)", "998311", 1, 350000)],
                      "Possible duplicate of S18 (same normalised number and amount, date +3 days)",
                      terms="Net 45", layout="B", special="POSSIBLE_DUP", special_ref="S18",
                      target="REJECTED", note="Reviewer confirms it duplicates S18 and rejects it."))
    s.append(Scenario("S49", "OFFICEMART", "TST-QTN-0442", date(2026, 9, 2), "ADMIN_OFFICE",
                      [L("Ergonomic office chair with lumbar support", "9401", 20, 8700),
                       L("Height-adjustable desk", "9403", 10, 18500)],
                      "Quotation, not an invoice", terms="Validity 30 days", due_printed=None, layout="A",
                      special="NOT_INVOICE", target="REJECTED_AT_INTAKE"))
    s.append(Scenario("S50", "FIBERLINK", "TST-FLB-Q3-0511", date(2026, 10, 1), "ADMIN_UTILITIES",
                      [L("Leased line 1 Gbps - Q3 (Oct-Dec 2026)", "998422", 3, 6000)],
                      "Corrupt / truncated PDF", terms="Net 15", layout="D", special="CORRUPT",
                      target="REJECTED_AT_INTAKE",
                      extra={"account": "TST-FL-88231", "period": "Oct - Dec 2026", "kind": "BROADBAND BILL"}))
    return s


# ---------------------------------------------------------------------------
# Amounts, payment terms, TDS (expected outcomes)
# ---------------------------------------------------------------------------

def money(x: Decimal) -> Decimal:
    return x.quantize(D("0.01"), ROUND_HALF_UP)


def fmt_inr(x: Decimal) -> str:
    """Indian digit grouping: 1,23,45,678.90"""
    x = money(x)
    neg = x < 0
    whole, frac = f"{abs(x):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + whole + "." + frac


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _words_below_1000(n: int) -> str:
    out = []
    if n >= 100:
        out.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        out.append(_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))
    elif n:
        out.append(_ONES[n])
    return " ".join(out)


def amount_in_words(x: Decimal) -> str:
    x = money(x)
    rupees, paise = int(x), int((x - int(x)) * 100)
    parts = []
    for div, name in [(10000000, "Crore"), (100000, "Lakh"), (1000, "Thousand")]:
        if rupees >= div:
            parts.append(_words_below_1000(rupees // div) + " " + name)
            rupees %= div
    if rupees:
        parts.append(_words_below_1000(rupees))
    text = "Indian Rupees " + (" ".join(parts) or "Zero")
    if paise:
        text += " and " + _words_below_1000(paise) + " Paise"
    return text + " Only"


def compute_amounts(sc: Scenario, vendor: dict) -> dict:
    gross = money(sum((q * r for _, _, q, r in sc.lines), D("0")))
    discount = money(gross * sc.discount_pct / 100)
    taxable = gross - discount
    taxes = []
    if sc.gst != "EXEMPT":
        rate = D("18") if sc.gst == "AUTO" else D(sc.gst)
        if vendor["state_code"] == BUYER["state_code"]:
            half = rate / 2
            amt = money(taxable * half / 100)
            taxes = [("CGST", half, amt), ("SGST", half, amt)]
        else:
            taxes = [("IGST", rate, money(taxable * rate / 100))]
    tax_total = sum((t[2] for t in taxes), D("0"))
    return {"gross": gross, "discount": discount, "taxable": taxable, "taxes": taxes, "tax_total": tax_total,
            "net": taxable + tax_total}


def parse_terms(text: Optional[str]) -> Tuple[Optional[int], str]:
    """Days + basis the way the proposed parser reads the printed terms (None = not determinable)."""
    if not text:
        return None, "INVOICE_DATE"
    t = text.lower()
    if "receipt" in t or "immediate" in t:
        return 0, "INVOICE_DATE"
    if "agreed" in t or "validity" in t:
        return None, "INVOICE_DATE"
    import re
    m = re.search(r"(\d{1,3})\s*days?", t) or re.search(r"net\s*(\d{1,3})", t)
    if not m:
        return None, "INVOICE_DATE"
    basis = "GRN_DATE" if ("grn" in t or "delivery" in t or "receipt of goods" in t) else "INVOICE_DATE"
    return int(m.group(1)), basis


def term_days(name: Optional[str]) -> Optional[int]:
    return parse_terms(name)[0] if name else None


def expected_payment_terms(sc: Scenario, vendor: dict) -> dict:
    inv_days, inv_basis = parse_terms(sc.terms)
    implied = False
    if inv_days is None and sc.terms is None and sc.due_printed not in (None, "AUTO"):
        inv_days = (date.fromisoformat(sc.due_printed) - sc.inv_date).days
        implied = True

    status, reason, source, applied, basis, suggested = None, None, None, None, inv_basis, None
    if sc.po:
        po = POS[sc.po]
        source, basis = "PO", po["basis"]
        if (sc.po_printed or sc.po) != sc.po:
            status, reason, suggested = "REVIEW_REQUIRED", "PO_NOT_MATCHED", po["days"]
        elif po["days"] is None:
            status, reason, suggested = "REVIEW_REQUIRED", "PO_TERMS_MISSING", inv_days
        elif inv_days is not None and inv_days != po["days"]:
            status, reason, applied = "MISMATCH", "INVOICE_VS_PO", po["days"]
        else:
            status, applied = "COMPLIANT", po["days"]
            reason = "INVOICE_SILENT_PO_TERMS_APPLIED" if inv_days is None else None
    else:
        agreements = [a for a in AGREEMENTS if a["vendor"] == sc.vendor]
        valid = [a for a in agreements if a["valid_from"] <= sc.inv_date <= a["valid_to"]]
        agr = valid[0] if valid else None
        master = term_days(vendor.get("master_payment_term"))
        reference = agr["term_days"] if agr else master
        source = "AGREEMENT" if agr else ("VENDOR_MASTER" if master is not None else "NONE")
        if inv_days is None:
            status = "REVIEW_REQUIRED"
            reason = "INVOICE_TERMS_AMBIGUOUS" if sc.terms else "INVOICE_TERMS_MISSING"
            suggested = reference
        elif agr and master is not None and agr["term_days"] != master:
            status, reason, applied = "MISMATCH", "VENDOR_MASTER_VS_AGREEMENT", agr["term_days"]
        elif reference is None:
            status, reason, suggested = "REVIEW_REQUIRED", "NO_AUTHORISED_TERMS", inv_days
        elif inv_days != reference:
            status, applied = "MISMATCH", reference
            reason = "INVOICE_VS_AGREEMENT" if agr else "INVOICE_VS_VENDOR_MASTER"
        elif agreements and not agr:
            status, reason, suggested = "REVIEW_REQUIRED", "AGREEMENT_EXPIRED", reference
        else:
            status, applied = "COMPLIANT", reference
            reason = "IMPLIED_FROM_PRINTED_DUE_DATE" if implied else None

    basis_date = sc.inv_date
    if basis == "GRN_DATE" and sc.po and POS[sc.po].get("grn"):
        basis_date = POS[sc.po]["grn"]
    contractual = basis_date + timedelta(days=applied) if applied is not None and status != "REVIEW_REQUIRED" else None

    statutory, statutory_rule = None, None
    if vendor.get("msme_category") in ("MICRO", "SMALL"):
        agreed = applied if applied is not None else suggested
        limit = 45 if agreed is not None else 15
        statutory = basis_date + timedelta(days=min(limit, agreed) if agreed is not None else limit)
        statutory_rule = f"MSMED_S15_{limit}_DAYS"
    candidates = [d for d in (contractual, statutory) if d is not None]
    effective = min(candidates) if candidates else None

    printed_due = None
    if sc.due_printed == "AUTO" and inv_days is not None:
        printed_due = (sc.inv_date + timedelta(days=inv_days)).isoformat()
    elif sc.due_printed not in (None, "AUTO"):
        printed_due = sc.due_printed
    return {
        "invoice_terms_text": sc.terms,
        "invoice_term_days": inv_days,
        "printed_due_date": printed_due,
        "reference_source": source,
        "validation_status": status,
        "reason": reason,
        "applied_term_days": applied,
        "suggested_term_days": suggested,
        "due_basis": basis,
        "basis_date": basis_date.isoformat(),
        "contractual_due_date": contractual.isoformat() if contractual else None,
        "statutory_due_date": statutory.isoformat() if statutory else None,
        "statutory_rule": statutory_rule,
        "effective_due_date": effective.isoformat() if effective else None,
        "blocks_ready_for_payment": status in ("MISMATCH", "REVIEW_REQUIRED"),
    }


def tds_rule_for(nature: str, entity: str):
    for section, rate, threshold, ttype, ent in TDS_RULES.get(nature, []):
        if ent is None or (ent == "OTHERS" and entity not in ("INDIVIDUAL", "HUF")) or \
                (isinstance(ent, set) and entity in ent):
            return section, rate, threshold, ttype
    return None


def expected_tds(scenarios: List[Scenario], vendors: Dict[str, dict], amounts: Dict[str, dict]) -> Dict[str, dict]:
    aggregate: Dict[Tuple[str, str], Decimal] = {}
    out = {}
    for sc in sorted(scenarios, key=lambda x: (x.inv_date, x.sid)):
        if sc.special in ("DUP_FILE", "DUP_INVOICE", "NOT_INVOICE", "CORRUPT"):
            continue
        vendor = vendors[sc.vendor]
        mapped = CATEGORIES[sc.category][1]
        nature = sc.nature_override or mapped
        base = amounts[sc.sid]["taxable"]
        rule = tds_rule_for(nature, vendor["entity_type"])
        rec = {"mapped_payment_nature": mapped, "expected_payment_nature": nature,
               "nature_correction_needed": nature != mapped, "taxable_base": str(base)}
        if rule is None:
            rec.update(applicable=False, reason=f"No active TDS rule for nature {nature}")
        else:
            section, rate, threshold, ttype = rule
            key = (sc.vendor, nature)
            if sc.special != "POSSIBLE_DUP":
                prior = aggregate.get(key, D("0"))
                aggregate[key] = prior + base
            else:
                prior = aggregate.get(key, D("0"))
            compare = prior + base if ttype == "AGGREGATE_PERIOD" else base
            rec.update(section=section, rate_percent=str(rate), threshold=str(threshold), threshold_type=ttype,
                       prior_aggregate_in_set=str(prior))
            if compare < threshold:
                rec.update(applicable=False, reason=f"{ttype.lower()} {fmt_inr(compare)} below {fmt_inr(threshold)}")
                rec["tds_amount"] = "0.00"
            else:
                tds = (base * rate / 100).quantize(D("1"), ROUND_HALF_UP)
                rec.update(applicable=True, tds_amount=str(money(tds)))
        out[sc.sid] = rec
    return out


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

A4 = fitz.paper_rect("a4")
INK = (0.12, 0.12, 0.14)
MUTED = (0.42, 0.42, 0.46)


PDF_METADATA = {"creator": "APM synthetic test-data generator", "producer": "PyMuPDF",
                "title": "SYNTHETIC TEST DOCUMENT", "creationDate": "D:20261009000000", "modDate": "D:20261009000000"}


def deterministic_bytes(pdf: fitz.Document) -> bytes:
    """Fixed metadata + no fresh /ID so regeneration is byte-identical."""
    pdf.set_metadata(PDF_METADATA)
    return pdf.tobytes(garbage=3, deflate=True, no_new_id=True)


class Doc:
    def __init__(self, font="helv", bold="hebo"):
        self.pdf = fitz.open()
        self.font, self.bold = font, bold
        self.page = None
        self.new_page()

    def new_page(self):
        self.page = self.pdf.new_page(width=A4.width, height=A4.height)
        return self.page

    def text(self, x, y, s, size=9, bold=False, color=INK, align="left", font=None):
        fn = font or (self.bold if bold else self.font)
        if align != "left":
            w = fitz.get_text_length(s, fontname=fn, fontsize=size)
            x = x - w if align == "right" else x - w / 2
        self.page.insert_text((x, y), s, fontsize=size, fontname=fn, color=color)

    def wrap(self, x, y, s, width, size=9, bold=False, leading=1.35):
        fn = self.bold if bold else self.font
        words, line, lines = s.split(), "", []
        for w in words:
            trial = (line + " " + w).strip()
            if fitz.get_text_length(trial, fontname=fn, fontsize=size) > width and line:
                lines.append(line)
                line = w
            else:
                line = trial
        if line:
            lines.append(line)
        for ln in lines:
            self.text(x, y, ln, size, bold)
            y += size * leading
        return y

    def rect(self, x0, y0, x1, y1, fill=None, color=INK, width=0.6):
        self.page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=color, fill=fill, width=width)

    def hline(self, x0, x1, y, color=INK, width=0.6):
        self.page.draw_line((x0, y), (x1, y), color=color, width=width)

    def footer(self):
        for i, p in enumerate(self.pdf):
            p.insert_text((36, A4.height - 22), FOOTER, fontsize=6.5, fontname="helv", color=MUTED)
            p.insert_text((A4.width - 80, A4.height - 22), f"Page {i + 1} of {len(self.pdf)}", fontsize=6.5,
                          fontname="helv", color=MUTED)

    def bytes(self):
        self.footer()
        return deterministic_bytes(self.pdf)


def _line_table(doc: Doc, y, lines, cols, header_fill, size=8.5, row_h=15, bottom=740, on_new_page=None):
    """cols: list of (title, x_left, x_right, align, getter). Paginates, repeating the header."""
    def header(yy):
        if header_fill:
            doc.rect(cols[0][1] - 4, yy - 11, cols[-1][2] + 4, yy + 5, fill=header_fill, color=header_fill)
        for title, x0, x1, align, _ in cols:
            doc.text(x1 if align == "right" else x0, yy, title, size, bold=True, align=align)
        doc.hline(cols[0][1] - 4, cols[-1][2] + 4, yy + 6)
        return yy + row_h + 2

    y = header(y)
    for i, ln in enumerate(lines):
        if y > bottom:
            doc.new_page()
            y = on_new_page() if on_new_page else 60
            y = header(y)
        for title, x0, x1, align, get in cols:
            val = get(i, ln)
            if align == "right":
                doc.text(x1, y, val, size, align="right")
            else:
                max_w = x1 - x0
                while fitz.get_text_length(val, fontname=doc.font, fontsize=size) > max_w and len(val) > 4:
                    val = val[:-2]
                doc.text(x0, y, val, size)
        y += row_h
    doc.hline(cols[0][1] - 4, cols[-1][2] + 4, y - row_h + 5, color=MUTED, width=0.4)
    return y


def _std_cols(right=559):
    return [
        ("#", 40, 55, "left", lambda i, ln: str(i + 1)),
        ("Description", 60, 300, "left", lambda i, ln: ln[0]),
        ("HSN/SAC", 305, 350, "left", lambda i, ln: ln[1]),
        ("Qty", 355, 395, "right", lambda i, ln: f"{ln[2]:g}"),
        ("Rate", 400, 470, "right", lambda i, ln: fmt_inr(ln[3])),
        ("Amount", 475, right, "right", lambda i, ln: fmt_inr(ln[2] * ln[3])),
    ]


def _totals(doc: Doc, y, amt, x_label=380, x_val=559, size=9):
    rows = [("Sub-total", amt["gross"])]
    if amt["discount"]:
        rows.append(("Less: Trade discount", -amt["discount"]))
        rows.append(("Taxable value", amt["taxable"]))
    for name, rate, val in amt["taxes"]:
        rows.append((f"{name} @ {rate:g}%", val))
    if not amt["taxes"]:
        rows.append(("GST", D("0")))
    if y > 700:
        doc.new_page()
        y = 70
    for label, val in rows:
        doc.text(x_label, y, label, size)
        doc.text(x_val, y, fmt_inr(val), size, align="right")
        y += size * 1.6
    doc.hline(x_label, x_val, y - 6)
    y += 6
    doc.text(x_label, y, "Total (INR)", size + 1.5, bold=True)
    doc.text(x_val, y, fmt_inr(amt["net"]), size + 1.5, bold=True, align="right")
    return y + 18


def _meta_rows(sc: Scenario, terms_info: dict, quotation=False):
    rows = [("Quotation No." if quotation else "Invoice No.", sc.inv_no),
            ("Quotation Date" if quotation else "Invoice Date", sc.inv_date.strftime("%d-%m-%Y"))]
    if sc.po or sc.po_printed:
        rows.append(("PO Number", sc.po_printed or sc.po))
    if sc.terms:
        rows.append(("Validity" if quotation else "Payment Terms", sc.terms.replace("Validity ", "")))
    if terms_info["printed_due_date"] and not quotation:
        rows.append(("Due Date", date.fromisoformat(terms_info["printed_due_date"]).strftime("%d-%m-%Y")))
    rows.append(("Place of Supply", f"{BUYER['state']} ({BUYER['state_code']})"))
    return rows


def render_classic(sc, v, amt, ti, quotation=False):
    """Layout A - bordered GST tax invoice."""
    doc = Doc("helv", "hebo")
    doc.rect(30, 30, 565, 812, width=0.8)
    doc.text(297, 58, "QUOTATION" if quotation else "TAX INVOICE", 15, bold=True, align="center")
    doc.text(297, 72, "(Original for Recipient)" if not quotation else "(Not a tax invoice)", 7.5, color=MUTED,
             align="center")
    doc.hline(30, 565, 82)
    y = 100
    doc.text(40, y, v["vendor_name"], 11, bold=True)
    for a in v["address"]:
        y += 12
        doc.text(40, y, a, 8.5)
    y += 13
    doc.text(40, y, f"GSTIN: {v['gstin']}    PAN: {v['pan']}", 8.5, bold=True)
    my = 100
    for label, val in _meta_rows(sc, ti, quotation):
        doc.text(360, my, label + ":", 8.5, color=MUTED)
        doc.text(450, my, val, 8.5, bold=True)
        my += 13
    y = max(y, my) + 14
    doc.hline(30, 565, y - 10)
    doc.text(40, y + 4, "Bill To", 8.5, bold=True, color=MUTED)
    doc.text(40, y + 18, BUYER["name"], 10, bold=True)
    doc.text(40, y + 31, BUYER["address"][0], 8.5)
    y += 52
    doc.hline(30, 565, y - 10)
    y = _line_table(doc, y + 6, sc.lines, _std_cols(), header_fill=(0.92, 0.92, 0.92))
    y = _totals(doc, y + 8, amt)
    if y > 730:
        doc.new_page()
        y = 70
    doc.text(40, y, "Amount in words:", 8, color=MUTED)
    doc.wrap(40, y + 12, amount_in_words(amt["net"]), 330, 8.5, bold=True)
    doc.text(40, y + 42, f"Bank: {v['bank_note']}", 7.5, color=MUTED)
    doc.text(559, y + 60, f"For {v['vendor_name'][:48]}", 8, align="right")
    doc.text(559, y + 88, "Authorised Signatory", 8, color=MUTED, align="right")
    return doc.bytes()


def render_modern(sc, v, amt, ti):
    """Layout B - SaaS / modern invoice."""
    doc = Doc("helv", "hebo")
    accent = (0.15, 0.35, 0.75)
    doc.rect(0, 0, A4.width, 8, fill=accent, color=accent)
    doc.text(40, 60, "Invoice", 26, bold=True, color=accent)
    doc.text(40, 80, v["vendor_name"], 10, bold=True)
    y = 80
    for a in v["address"]:
        y += 11
        doc.text(40, y, a, 8, color=MUTED)
    doc.text(40, y + 13, f"GSTIN {v['gstin']}  |  PAN {v['pan']}", 8)
    my = 50
    for label, val in _meta_rows(sc, ti):
        doc.text(400, my, label, 7.5, color=MUTED)
        doc.text(555, my, val, 8.5, bold=True, align="right")
        my += 14
    y = max(y + 40, my + 16)
    doc.text(40, y, "BILLED TO", 7.5, bold=True, color=accent)
    doc.text(40, y + 14, BUYER["name"], 10, bold=True)
    doc.text(40, y + 27, BUYER["address"][0], 8.5, color=MUTED)
    y += 55
    cols = [
        ("Item", 40, 330, "left", lambda i, ln: ln[0]),
        ("SAC", 335, 380, "left", lambda i, ln: ln[1]),
        ("Qty", 385, 420, "right", lambda i, ln: f"{ln[2]:g}"),
        ("Unit price", 425, 490, "right", lambda i, ln: fmt_inr(ln[3])),
        ("Amount", 495, 555, "right", lambda i, ln: fmt_inr(ln[2] * ln[3])),
    ]
    y = _line_table(doc, y, sc.lines, cols, header_fill=(0.90, 0.93, 0.99), size=8, row_h=14)
    y = _totals(doc, y + 10, amt, x_label=380, x_val=555)
    if y > 740:
        doc.new_page()
        y = 70
    doc.wrap(40, y, amount_in_words(amt["net"]), 320, 8)
    doc.text(40, y + 28, "Questions? billing@example.invalid", 7.5, color=MUTED)
    return doc.bytes()


def render_letter(sc, v, amt, ti):
    """Layout C - landlord letter-style rent invoice (Times)."""
    doc = Doc("tiro", "tibo")
    doc.text(297, 60, v["vendor_name"].upper(), 14, bold=True, align="center")
    doc.text(297, 76, ", ".join(v["address"]), 8.5, align="center")
    doc.text(297, 89, f"GSTIN: {v['gstin']}   PAN: {v['pan']}", 8.5, align="center")
    doc.hline(60, 535, 98, width=1.2)
    doc.text(297, 125, "RENT INVOICE", 13, bold=True, align="center")
    doc.text(60, 155, f"Invoice No: {sc.inv_no}", 10)
    doc.text(535, 155, f"Date: {sc.inv_date.strftime('%d %B %Y')}", 10, align="right")
    doc.text(60, 185, "To,", 10)
    doc.text(60, 199, BUYER["name"], 10, bold=True)
    doc.text(60, 213, BUYER["address"][0], 10)
    y = doc.wrap(60, 245, "Being the amount due towards rent and related charges for the premises leased to you "
                          "under the lease agreement, as detailed below.", 475, 10)
    y = _line_table(doc, y + 18, sc.lines, [
        ("Particulars", 60, 380, "left", lambda i, ln: ln[0]),
        ("SAC", 385, 430, "left", lambda i, ln: ln[1]),
        ("Amount (Rs.)", 435, 535, "right", lambda i, ln: fmt_inr(ln[2] * ln[3])),
    ], header_fill=None, size=9.5, row_h=17)
    y = _totals(doc, y + 10, amt, x_label=330, x_val=535, size=9.5)
    doc.text(60, y, f"Rupees: {amount_in_words(amt['net'])}", 9.5)
    if sc.terms:
        doc.text(60, y + 24, f"Payment terms: {sc.terms}.", 10, bold=True)
    if ti["printed_due_date"]:
        doc.text(60, y + 40, f"Kindly remit on or before {date.fromisoformat(ti['printed_due_date']).strftime('%d %B %Y')}.", 10)
    doc.text(60, y + 60, f"Bank: {v['bank_note']}", 8.5)
    doc.text(535, y + 100, f"For {v['vendor_name']}", 10, align="right")
    doc.text(535, y + 130, "Partner", 10, align="right")
    return doc.bytes()


def render_utility(sc, v, amt, ti):
    """Layout D - utility / broadband bill."""
    doc = Doc("helv", "hebo")
    band = (0.05, 0.45, 0.40)
    doc.rect(30, 30, 565, 95, fill=band, color=band)
    doc.text(45, 58, v["vendor_name"], 13, bold=True, color=(1, 1, 1))
    doc.text(45, 76, sc.extra.get("kind", "BILL"), 10, bold=True, color=(1, 1, 1))
    doc.text(550, 58, f"GSTIN {v['gstin']}", 8, color=(1, 1, 1), align="right")
    doc.text(550, 72, ", ".join(v["address"])[:70], 7, color=(1, 1, 1), align="right")
    rows = [("Bill Number", sc.inv_no), ("Bill Date", sc.inv_date.strftime("%d/%m/%Y")),
            ("Consumer / Account No", sc.extra.get("account", "-")), ("Billing Period", sc.extra.get("period", "-")),
            ("Customer", BUYER["name"])]
    if sc.terms:
        rows.append(("Payment terms", sc.terms))
    y = 120
    for label, val in rows:
        doc.text(45, y, label, 8.5, color=MUTED)
        doc.text(190, y, val, 9, bold=True)
        y += 15
    doc.rect(380, 112, 555, 180, fill=(0.95, 0.98, 0.97), color=band)
    doc.text(392, 130, "AMOUNT PAYABLE", 8, bold=True, color=band)
    doc.text(545, 155, f"Rs. {fmt_inr(amt['net'])}", 14, bold=True, align="right")
    if ti["printed_due_date"]:
        doc.text(392, 172, f"Pay by (Due Date): {date.fromisoformat(ti['printed_due_date']).strftime('%d/%m/%Y')}",
                 8.5, bold=True)
    y += 20
    y = _line_table(doc, y, sc.lines, [
        ("Charge", 45, 360, "left", lambda i, ln: ln[0]),
        ("Code", 365, 410, "left", lambda i, ln: ln[1]),
        ("Amount", 415, 555, "right", lambda i, ln: fmt_inr(ln[2] * ln[3])),
    ], header_fill=(0.90, 0.95, 0.94), size=8.5)
    y = _totals(doc, y + 10, amt, x_label=380, x_val=555)
    if sc.gst == "EXEMPT":
        doc.text(45, y, "Supply of electricity is exempt from GST.", 8, color=MUTED)
    doc.text(45, y + 16, "Late payment surcharge applies after the due date.", 8, color=MUTED)
    return doc.bytes()


def render_sparse(sc, v, amt, ti):
    """Layout E - typewriter-style small-vendor invoice (Courier, no borders)."""
    doc = Doc("cour", "cobo")
    y = 60
    doc.text(45, y, v["vendor_name"], 11, bold=True)
    for a in v["address"]:
        y += 12
        doc.text(45, y, a, 8.5)
    y += 12
    doc.text(45, y, f"GST No. {v['gstin']}", 8.5)
    y += 12
    doc.text(45, y, f"PAN {v['pan']}", 8.5)
    y += 28
    doc.text(45, y, "INVOICE", 13, bold=True)
    y += 20
    for label, val in _meta_rows(sc, ti):
        doc.text(45, y, f"{label:<16}: {val}", 8.5)
        y += 12
    y += 8
    doc.text(45, y, f"To: {BUYER['name']}, {BUYER['address'][0]}", 8.5)
    y += 22
    y = _line_table(doc, y, sc.lines, [
        ("Description", 45, 330, "left", lambda i, ln: ln[0]),
        ("HSN/SAC", 335, 380, "left", lambda i, ln: ln[1]),
        ("Qty", 385, 425, "right", lambda i, ln: f"{ln[2]:g}"),
        ("Amount", 430, 550, "right", lambda i, ln: fmt_inr(ln[2] * ln[3])),
    ], header_fill=None, size=8.5, row_h=13)
    y = _totals(doc, y + 8, amt, x_label=340, x_val=550, size=8.5)
    doc.wrap(45, y, amount_in_words(amt["net"]), 450, 8)
    doc.text(45, y + 34, f"Bank: {v['bank_note']}", 7.5)
    doc.text(45, y + 70, "Signature: ____________________", 8.5)
    return doc.bytes()


RENDERERS = {"A": render_classic, "B": render_modern, "C": render_letter, "D": render_utility, "E": render_sparse}


def render_agreement(agr: dict, v: dict) -> bytes:
    doc = Doc("tiro", "tibo")
    doc.text(297, 70, agr["title"].upper(), 15, bold=True, align="center")
    doc.text(297, 88, f"Agreement Ref: TST-{agr['id']}", 9, align="center")
    y = doc.wrap(60, 125, f"This {agr['title']} is entered into on {agr['valid_from'].strftime('%d %B %Y')} between "
                          f"{v['vendor_name']}, having its office at {', '.join(v['address'])} (GSTIN {v['gstin']}, "
                          f"PAN {v['pan']}) (the \"Vendor\") and {BUYER['name']}, {BUYER['address'][0]} "
                          f"(the \"Company\").", 475, 10.5)
    clauses = [
        ("1. Term", f"This agreement is valid from {agr['valid_from'].strftime('%d %B %Y')} to "
                    f"{agr['valid_to'].strftime('%d %B %Y')} unless terminated earlier in writing."),
        ("2. Services", "The Vendor shall provide the services described in Schedule A in a professional manner."),
        ("3. Invoicing", "The Vendor shall raise GST-compliant invoices quoting this agreement reference."),
        ("4. Payment Terms", agr["clause"] + " Payments are subject to deduction of tax at source as applicable."),
        ("5. Late Payment", "Undisputed amounts unpaid beyond the payment term may attract interest as permitted by law."),
        ("6. Governing Law", "This agreement is governed by the laws of India; courts at Hyderabad have jurisdiction."),
    ]
    y += 14
    for head, body in clauses:
        doc.text(60, y, head, 11, bold=True)
        y = doc.wrap(60, y + 15, body, 475, 10.5) + 10
    y += 30
    doc.text(60, y, f"For {v['vendor_name']}", 10)
    doc.text(330, y, f"For {BUYER['name']}", 10)
    doc.text(60, y + 40, "Authorised Signatory", 9, color=MUTED)
    doc.text(330, y + 40, "Authorised Signatory", 9, color=MUTED)
    return doc.bytes()


# ---------------------------------------------------------------------------
# Document-quality degradation
# ---------------------------------------------------------------------------

def _page_images(pdf_bytes: bytes, dpi: int, gray=True) -> List[Image.Image]:
    src = fitz.open("pdf", pdf_bytes)
    out = []
    for p in src:
        pix = p.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY if gray else fitz.csRGB)
        mode = "L" if gray else "RGB"
        out.append(Image.frombytes(mode, (pix.width, pix.height), pix.samples))
    return out


def degrade_scan(pdf_bytes: bytes, rng: np.random.RandomState) -> bytes:
    """Re-render as an image-only 'scanned' PDF: skew, noise, blur, JPEG artefacts."""
    out = fitz.open()
    for img in _page_images(pdf_bytes, dpi=int(rng.choice([110, 130, 150]))):
        img = img.rotate(float(rng.uniform(-3.0, 3.0)), resample=Image.BICUBIC, fillcolor=245)
        arr = np.asarray(img).astype(np.int16)
        arr = arr - 18 + rng.normal(0, 10, arr.shape).astype(np.int16)  # toner/paper tone + noise
        speck = rng.random_sample(arr.shape) < 0.0015
        arr[speck] = 30
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=int(rng.choice([35, 45, 55])))
        page = out.new_page(width=A4.width, height=A4.height)
        page.insert_image(page.rect, stream=buf.getvalue())
    return deterministic_bytes(out)


def phone_photo(pdf_bytes: bytes, rng: np.random.RandomState) -> bytes:
    """First page as a phone photo: perspective, desk background, uneven light (JPEG)."""
    img = np.asarray(_page_images(pdf_bytes, dpi=140, gray=False)[0])
    h, w = img.shape[:2]
    canvas_w, canvas_h = int(w * 1.25), int(h * 1.2)
    j = lambda a: float(rng.uniform(-a, a))
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    ox, oy = (canvas_w - w) / 2, (canvas_h - h) / 2
    dst = np.float32([[ox + 40 + j(20), oy + 30 + j(15)], [ox + w - 25 + j(20), oy + 10 + j(15)],
                      [ox + w + 10 + j(20), oy + h - 20 + j(15)], [ox - 15 + j(20), oy + h - 5 + j(15)]])
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, m, (canvas_w, canvas_h), borderValue=(92, 74, 58))
    yy, xx = np.mgrid[0:canvas_h, 0:canvas_w]
    light = 0.78 + 0.25 * (1 - ((xx - canvas_w * 0.3) ** 2 + (yy - canvas_h * 0.25) ** 2) /
                           ((canvas_w ** 2 + canvas_h ** 2) * 0.6))
    shaded = np.clip(warped.astype(np.float32) * light[..., None], 0, 255).astype(np.uint8)
    shaded = cv2.GaussianBlur(shaded, (3, 3), 0.8)
    buf = io.BytesIO()
    Image.fromarray(shaded).save(buf, format="JPEG", quality=72)
    return buf.getvalue()


def to_png(pdf_bytes: bytes) -> bytes:
    img = _page_images(pdf_bytes, dpi=170, gray=False)[0]
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")[:40]


def ext_for(sc: Scenario) -> str:
    return {"photo": ".jpg", "png": ".png"}.get(sc.quality, ".pdf")


EXPECTED_INTAKE = {
    None: "CREATED_OCR_REVIEW_PENDING",
    "DUP_FILE": "DUPLICATE_FILE (same SHA-256 as an earlier upload; not processed)",
    "DUP_INVOICE": "DUPLICATE_INVOICE (vendor + invoice number already exists; not created)",
    "POSSIBLE_DUP": "CREATED_WITH_POSSIBLE_DUPLICATE_FLAG",
    "NOT_INVOICE": "NEEDS_ATTENTION / NOT_AN_INVOICE (quotation, no invoice number)",
    "CORRUPT": "FAILED_INVALID_FILE (unreadable PDF; not retried)",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--vendors", type=Path, help="JSON vendor registry overriding the defaults (e.g. approved GSTINs)")
    args = ap.parse_args(argv)

    vendors = copy.deepcopy(DEFAULT_VENDORS)
    if args.vendors:
        for key, override in json.loads(args.vendors.read_text(encoding="utf-8")).items():
            vendors.setdefault(key, {}).update(override)
            if override.get("gstin"):
                vendors[key]["gstin_status"] = override.get("gstin_status", "PROVIDED")

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "invoices").mkdir(parents=True)
    (out / "agreements").mkdir()

    rng = np.random.RandomState(SEED)
    scenarios = build_scenarios()
    by_id = {sc.sid: sc for sc in scenarios}

    # duplicates re-use their source's content
    for sc in scenarios:
        if sc.special in ("DUP_FILE", "DUP_INVOICE"):
            src = by_id[sc.special_ref]
            sc.lines, sc.terms, sc.due_printed, sc.po, sc.po_printed = src.lines, src.terms, src.due_printed, src.po, src.po_printed
            sc.discount_pct, sc.gst, sc.extra = src.discount_pct, src.gst, src.extra
            if sc.special == "DUP_INVOICE":
                sc.layout, sc.quality = "B", "scan"

    amounts = {sc.sid: compute_amounts(sc, vendors[sc.vendor]) for sc in scenarios}
    terms = {sc.sid: expected_payment_terms(sc, vendors[sc.vendor]) for sc in scenarios}
    tds = expected_tds(scenarios, vendors, amounts)

    files: Dict[str, str] = {}
    records = []
    for sc in scenarios:
        v, amt, ti = vendors[sc.vendor], amounts[sc.sid], terms[sc.sid]
        name = f"{sc.sid}_{slug(sc.vendor.title())}_{slug(sc.inv_no)}{ext_for(sc)}"
        if sc.special == "DUP_FILE":
            name = f"{sc.sid}_DUPLICATE_OF_{files[sc.special_ref]}"
            shutil.copyfile(out / "invoices" / files[sc.special_ref], out / "invoices" / name)
        else:
            if sc.special == "NOT_INVOICE":
                data = render_classic(sc, v, amt, ti, quotation=True)
            else:
                data = RENDERERS[sc.layout](sc, v, amt, ti)
            if sc.quality == "scan":
                data = degrade_scan(data, rng)
            elif sc.quality == "photo":
                data = phone_photo(data, rng)
            elif sc.quality == "png":
                data = to_png(data)
            if sc.special == "CORRUPT":
                # truncated download whose header was also overwritten: not identifiable as a PDF
                data = rng.bytes(512) + data[512: int(len(data) * 0.35)]
            (out / "invoices" / name).write_bytes(data)
        files[sc.sid] = name

        created = sc.special in (None, "POSSIBLE_DUP")
        tds_rec = tds.get(sc.sid)
        net_payable = amt["net"] - (D(tds_rec["tds_amount"]) if tds_rec and tds_rec.get("applicable") else D("0"))
        pays = [{"payment_date": d.isoformat(), "amount": str(money(net_payable if a == "FULL" else a))}
                for d, a in sc.payments]
        paid = sum((D(p["amount"]) for p in pays), D("0"))
        eff = ti["effective_due_date"]
        balance = net_payable - paid
        overdue = bool(created and sc.target != "REJECTED" and eff and date.fromisoformat(eff) < AS_OF and balance > 0)
        last_pay = max((d for d, _ in sc.payments), default=None)
        records.append({
            "id": sc.sid,
            "file": f"invoices/{name}",
            "scenario": sc.title,
            "note": sc.note,
            "vendor_key": sc.vendor,
            "vendor_name": v["vendor_name"],
            "vendor_code": v["vendor_code"],
            "vendor_existing": v["existing"],
            "vendor_gstin": v["gstin"],
            "vendor_gstin_status": v["gstin_status"],
            "invoice_number": sc.inv_no,
            "invoice_date": sc.inv_date.isoformat(),
            "invoice_type": "PO" if sc.po else "NON_PO",
            "po_number": sc.po,
            "po_number_printed": sc.po_printed or sc.po,
            "purchase_category": sc.category,
            "department": CATEGORIES[sc.category][0],
            "category_exists_in_db": CATEGORIES[sc.category][2],
            "layout": sc.layout,
            "quality": sc.quality,
            "pages": None if ext_for(sc) != ".pdf" or sc.special == "CORRUPT" else len(fitz.open(out / "invoices" / name)),
            "special": sc.special,
            "special_ref": sc.special_ref,
            "amounts": {"gross": str(amt["gross"]), "discount": str(amt["discount"]), "taxable": str(amt["taxable"]),
                        "taxes": [{"type": t, "rate": str(r), "amount": str(a)} for t, r, a in amt["taxes"]],
                        "tax_total": str(amt["tax_total"]), "net": str(amt["net"]),
                        "net_payable_after_tds": str(money(net_payable)) if created else None},
            "expected": {
                "intake": EXPECTED_INTAKE[sc.special],
                "intake_precondition": None if v["existing"] else
                    "Vendor must be onboarded (with an approved GSTIN) first; until then expect NEEDS_ATTENTION / VENDOR_NOT_FOUND.",
                "payment_terms": ti if created else None,
                "tds": tds_rec if created else None,
            },
            "e2e_target": {
                "final_state": sc.target,
                "payments": pays,
                "balance_after_payments": str(money(balance)) if created else None,
                "overdue_as_of": AS_OF.isoformat() if overdue else None,
                "paid_on_time": (last_pay <= date.fromisoformat(eff)) if (created and pays and eff and balance <= 0) else None,
            },
        })

    for agr in AGREEMENTS:
        v = vendors[agr["vendor"]]
        (out / "agreements" / f"{agr['id']}_{slug(agr['vendor'].title())}_{slug(agr['title'])}.pdf").write_bytes(
            render_agreement(agr, v))

    manifest = {
        "set": "synthetic_invoices_v1",
        "generator": "Backend/scripts/generate_test_invoices.py",
        "seed": SEED,
        "as_of_date": AS_OF.isoformat(),
        "buyer": BUYER,
        "rules_assumed": {
            "payment_terms": "APM_AUTOMATION_PLAN.md section 3.1 (proposed - not yet implemented)",
            "tds": "Active TDS_RATE rules in the dev DB as of 2026-10-09; taxable base = gross - discount; "
                   "vendor PAN status assumed VALID (otherwise section 206AA 20% floor applies)",
            "tds_aggregate": "Aggregates are computed within this set only (vendor + nature, FY 2026-27); "
                             "existing invoices for AWS/KEKA in the DB may raise the prior aggregate.",
        },
        "vendors": vendors,
        "proposed_purchase_categories": {k: {"department": d, "tds_nature": n}
                                         for k, (d, n, exists) in CATEGORIES.items() if not exists},
        "proposed_category_mapping_fixes": {"FIN_AUDIT": "PROFESSIONAL_SERVICE", "FIN_ACCOUNTING": "PROFESSIONAL_SERVICE",
                                            "ADMIN_FACILITIES": "CONTRACTOR"},
        "purchase_orders": {k: {**p, "grn": p["grn"].isoformat() if p.get("grn") else None} for k, p in POS.items()},
        "agreements": [{**a, "valid_from": a["valid_from"].isoformat(), "valid_to": a["valid_to"].isoformat(),
                        "file": f"agreements/{a['id']}_{slug(a['vendor'].title())}_{slug(a['title'])}.pdf"}
                       for a in AGREEMENTS],
        "scenarios": records,
    }
    (out / "scenarios.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (out / "vendors.json").write_text(json.dumps(vendors, indent=2, default=str), encoding="utf-8")
    (out / "SCENARIOS.md").write_text(render_markdown(manifest), encoding="utf-8")
    print(f"Wrote {len(records)} invoice documents and {len(AGREEMENTS)} agreements to {out}")


def render_markdown(m: dict) -> str:
    sc = m["scenarios"]
    lines = [
        "# Synthetic invoice set v1: scenarios and expected outcomes",
        "",
        f"Generated by `{m['generator']}` (seed {m['seed']}). Expected flags are computed as of **{m['as_of_date']}**.",
        "",
        "> All documents are synthetic test data. Every page carries a \"SYNTHETIC TEST DOCUMENT\" footer, and every "
        "invoice number starts with `TST`. Do not use them outside the dev environment.",
        "",
        "## Prerequisites before an end-to-end run",
        "",
        "1. **Vendors.** The 11 `TST-` vendors in `vendors.json` must be onboarded through the normal vendor flow, which "
        "includes the live GST verification. The GSTINs printed today are **placeholders with a deliberately invalid "
        "check digit**, so they cannot belong to a real taxpayer, and the GST check will reject them. Replace them with "
        "approved test identities, then regenerate with `--vendors` (see APM_AUTOMATION_PLAN.md section 4.2). "
        "AWS and KEKA are the existing vendor-master records.",
        "2. **Purchase categories** `ADMIN_RENT`, `PROF_CONSULTING`, `IT_SERVICES` and `ADMIN_UTILITIES`, with the TDS "
        "nature mappings shown below.",
        "3. **Purchase orders** `TST-PO-0001` to `TST-PO-0012` (with GRNs for 0009 to 0012), as listed in `scenarios.json`.",
        "4. **Agreements** AGR-01 to AGR-03 uploaded once the vendor-agreement feature exists.",
        "5. **Payment-term statuses** depend on the proposed compliance rules (plan section 3.1). TDS expectations use "
        "the active dev-DB rules.",
        "",
        "## Coverage",
        "",
    ]
    def count(fn):
        return sum(1 for s in sc if fn(s))
    stats = [
        ("PO invoices", count(lambda s: s["invoice_type"] == "PO")),
        ("Non-PO invoices", count(lambda s: s["invoice_type"] == "NON_PO")),
        ("Scanned / photo / PNG", count(lambda s: s["quality"] != "clean")),
        ("Multi-page", count(lambda s: (s["pages"] or 1) > 1)),
        ("Intra-state (CGST+SGST) / inter-state (IGST) / exempt",
         f"{count(lambda s: any(t['type'] == 'CGST' for t in s['amounts']['taxes']))} / "
         f"{count(lambda s: any(t['type'] == 'IGST' for t in s['amounts']['taxes']))} / "
         f"{count(lambda s: not s['amounts']['taxes'])}"),
        ("Payment terms COMPLIANT / MISMATCH / REVIEW_REQUIRED",
         " / ".join(str(count(lambda s, st=st: (s['expected']['payment_terms'] or {}).get('validation_status') == st))
                    for st in ("COMPLIANT", "MISMATCH", "REVIEW_REQUIRED"))),
        ("MSME statutory deadline applies", count(lambda s: (s['expected']['payment_terms'] or {}).get('statutory_due_date'))),
        ("TDS applicable", count(lambda s: (s['expected']['tds'] or {}).get('applicable'))),
        ("TDS nature correction needed (category maps to OTHER)",
         count(lambda s: (s['expected']['tds'] or {}).get('nature_correction_needed'))),
        ("Overdue as of the as-of date", count(lambda s: s['e2e_target']['overdue_as_of'])),
        ("Duplicates / invalid documents", count(lambda s: s["special"] not in (None,))),
    ]
    lines += ["| Dimension | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in stats]
    lines += ["", "## Scenarios", "",
              "| ID | File | Vendor | Type | Category | Scenario | Net (INR) | Terms status (reason) | Effective due | TDS | E2E target |",
              "|---|---|---|---|---|---|---:|---|---|---|---|"]
    for s in sc:
        pt = s["expected"]["payment_terms"] or {}
        t = s["expected"]["tds"] or {}
        if s["expected"]["tds"] is None:
            tds_txt = "-"
        elif t.get("applicable"):
            tds_txt = f"{t['section']} {t['rate_percent']}% = {fmt_inr(D(t['tds_amount']))}"
        else:
            tds_txt = "None (" + t.get("reason", "") + ")"
        if t.get("nature_correction_needed"):
            tds_txt += f" [correct nature to {t['expected_payment_nature']}]"
        status = pt.get("validation_status") or s["expected"]["intake"].split(" ")[0]
        if pt.get("reason"):
            status += f" ({pt['reason']})"
        due = pt.get("effective_due_date") or "-"
        if pt.get("statutory_due_date"):
            due += " (MSME)"
        target = s["e2e_target"]["final_state"]
        if s["e2e_target"]["overdue_as_of"]:
            target += " - OVERDUE"
        lines.append(f"| {s['id']} | `{s['file'].split('/')[-1]}` | {s['vendor_name'].replace('[TEST] ', '')} | "
                     f"{s['invoice_type']} | {s['purchase_category']} | {s['scenario']} | {fmt_inr(D(s['amounts']['net']))} | "
                     f"{status} | {due} | {tds_txt} | {target} |")
    lines += ["", "## Vendor agreements", "", "| ID | Vendor | Terms | Valid | File |", "|---|---|---|---|---|"]
    for a in m["agreements"]:
        lines.append(f"| {a['id']} | {a['vendor']} | {a['term_days']} days | {a['valid_from']} to {a['valid_to']} | `{a['file']}` |")
    lines += ["", "## Purchase orders referenced", "", "| PO | Vendor | Terms | Basis | GRN date |", "|---|---|---|---|---|"]
    for k, p in m["purchase_orders"].items():
        lines.append(f"| {k} | {p['vendor']} | {p['terms'] or '(none)'} | {p['basis']} | {p['grn'] or '-'} |")
    lines += ["", "Full machine-readable expectations, including amounts, dates and planned payments, are in `scenarios.json`.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
