# Backend/scripts/seed_demo_data.py
"""Client-demo dataset: 3 vendors, ~50 invoices across FY 2026-27 (Apr - Oct 2026), driven
through the REAL application services so every record, document and audit entry is genuine.

Run from the Account_Payables project root, on a freshly reset database
(python -m Backend.scripts.reset_demo_transactions --execute):

    python -m Backend.scripts.seed_demo_data                 # dry run: plan + PDF previews only
    python -m Backend.scripts.seed_demo_data --execute       # build the dataset

What --execute does, in story order (Mar - Oct 2026):

* onboards WEWORK INDIA MANAGEMENT LIMITED through VendorService (live GSTIN check), adds the
  KEKA subscription and WeWork lease agreements (uploaded by Vendor Intake, verified by the
  Finance Manager) and two Facilities approval policies (up to / above Rs 1 lakh);
* raises 3 purchase requisitions -> quotation -> PO -> goods receipts through ProcurementService;
* renders each invoice PDF (footer: DEMO DOCUMENT), uploads it through the bulk-upload service
  (S3 + Textract OCR + validation + AP automation, exactly like an AP Executive's upload);
* AP Executive review / TDS nature / send for approval, policy approvers approve (or reject /
  send back), Finance verifies TDS, marks ready, records the payment with a payment-advice PDF,
  records the TDS deduction; monthly challans deposit the TDS and the Q1 26Q return is filed.

Timestamps: the services stamp everything with the real clock. After each step the rows that
step wrote (and its audit entries) are moved to the step's story time, so the audit trail reads
as it happened - uploaded on 3 Apr, approved on 6 Apr, paid on 16 Apr. Use --no-backdate to keep
real timestamps (business dates - invoice / payment / deposit dates - are always the story dates).

Nothing here bypasses validation: invoices that fail a control stay where the system puts them.
"""
import argparse
import asyncio
import datetime as dt
import json
import re
import sys
import traceback
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "Backend" / ".env"
PREVIEW_DIR = ROOT / "test-documents" / "demo_v1"
EXPECTED_DATABASE = "accounts_payable"

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
AS_OF = dt.date(2026, 10, 12)
FOOTER = "DEMO DOCUMENT - generated for the Paves APM product demonstration - not a tax invoice"

# --- people (UMS user ids) -------------------------------------------------------------
VENKATESH, KALASAGAR = "5100007", "5100027"   # AP Executives
AJAY = "5100005"                               # IT - IT Policy approver, IT requester
BINDU = "5100026"                              # Finance Manager
BOLLI = "5100020"                              # Finance Executive
JAGADISH_R = "5100031"                         # Finance Executive / PR approver / Vendor intake
MOHAN, SAMBI = "5100002", "5100025"            # Super Admins
RAKESH = "5100024"                             # Procurement Officer
NAMES = {VENKATESH: "Venkatesh Gali", KALASAGAR: "Kalasagar P", AJAY: "Ajay Korada", BINDU: "Bindu Bhargavi U",
         BOLLI: "Bolli Teja", JAGADISH_R: "Jagadish Reddy Pannala", MOHAN: "Mohan", SAMBI: "Sambi Eada",
         RAKESH: "rakesh k"}

# --- master data ----------------------------------------------------------------------
INDIA, INR = 1, 1
DEPT_IT, CAT_IT_SOFTWARE = 1, 2
DEPT_ADMIN, CAT_FACILITIES = 5, 6
WEWORK = {
    "vendor_name": "WEWORK INDIA MANAGEMENT LIMITED", "gstin": "36AADCH8710J1ZH", "pan": "AADCH8710J",
    "address_line1": "Rajapushpa Summit, 115/1, Nanakramguda Village", "address_line2": "Serilingampally Mandal",
    "city": "Hyderabad", "state": "Telangana", "postal_code": "500032",
}
WORKSPACE = "RMZ Spire, HITEC City"
BSR_CODE = "0510308"
D = Decimal


def money(x) -> Decimal:
    return D(x).quantize(D("0.01"), ROUND_HALF_UP)


# ======================================================================
# Calendar
# ======================================================================
def bd(d: dt.date, n: int = 1) -> dt.date:
    """n business days after d (n=0: d itself, or the next business day if d is a weekend)."""
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def at(d: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, hh, 0, tzinfo=IST) + dt.timedelta(minutes=mm)


def month_name(d: dt.date) -> str:
    return d.strftime("%b %Y")


def prev_month(d: dt.date) -> dt.date:
    return (d.replace(day=1) - dt.timedelta(days=1)).replace(day=1)


# ======================================================================
# The story
# ======================================================================
@dataclass
class Story:
    key: str
    vendor: str                      # AWS | KEKA | WEWORK
    inv_no: str
    inv_date: dt.date
    lines: List[Tuple[str, str, Decimal, Decimal]]   # description, SAC, qty, rate
    terms: str
    term_days: int
    target: str
    uploader: str
    upload: dt.date
    layout: str = "A"
    po: Optional[str] = None         # PO key (PO invoice)
    dept: int = DEPT_IT
    cat: int = CAT_IT_SOFTWARE
    nature: Optional[str] = None     # TDS payment nature the AP Executive selects
    pays: List[Tuple[dt.date, object, str]] = field(default_factory=list)  # (date, "FULL" | amount, remarks)
    approve_days: List[int] = field(default_factory=lambda: [1, 2])        # business days after upload, per level
    approvers: List[str] = field(default_factory=list)                     # preferred approvers, in order
    comment: str = "Verified against usage / contract - approved."
    decision: str = "APPROVE"        # APPROVE | REJECT | SEND_BACK (at level 1)
    terms_override: Optional[str] = None  # Finance verifies a payment-term mismatch with this remark
    title: str = ""


def L(desc, sac, qty, rate):
    return (desc, sac, D(str(qty)), money(rate))


def build_stories() -> List[Story]:
    s: List[Story] = []
    months = [dt.date(2026, m, 1) for m in range(4, 11)]  # Apr .. Oct

    # ---- AWS: three linked accounts, billed on the 2nd for last month's usage (Net 15) ------
    aws_pays = {4: dt.date(2026, 4, 16), 5: dt.date(2026, 5, 15), 6: dt.date(2026, 6, 16),
                7: dt.date(2026, 7, 16), 8: dt.date(2026, 8, 14), 9: dt.date(2026, 9, 16)}
    for i, m in enumerate(months):
        inv_date, usage = m.replace(day=2), month_name(prev_month(m))
        upload = bd(inv_date, 1)
        prod = Story(
            key=f"AWS-PROD-{m:%m}", vendor="AWS", inv_no=f"AWSIN26-{4180 + i * 37:04d}{i + 1:03d}", inv_date=inv_date,
            lines=[L(f"Amazon EC2 - compute ({usage}) - Production a/c 4417", "998315", 1, 118000 + i * 3400),
                   L(f"Amazon RDS - managed databases ({usage})", "998315", 1, 38500 + i * 900),
                   L(f"Amazon S3 - storage & requests ({usage})", "998315", 1, 12400 + i * 650),
                   L(f"Amazon CloudFront - data transfer ({usage})", "998315", 1, 8900 + (i % 3) * 420),
                   L(f"AWS Business Support ({usage})", "998315", 1, 17800 + i * 240)],
            terms="Net 15 days", term_days=15, target="PAID", uploader=VENKATESH, upload=upload, layout="B",
            nature="TECHNICAL_SERVICE", approvers=[MOHAN, SAMBI] if i % 2 == 0 else [SAMBI, MOHAN],
            comment=f"{usage} production spend in line with the Cost Explorer forecast - approved.",
            title=f"AWS production usage {usage}")
        dev = Story(
            key=f"AWS-DEV-{m:%m}", vendor="AWS", inv_no=f"AWSIN26-{4180 + i * 37:04d}{i + 101:03d}", inv_date=inv_date,
            lines=[L(f"Amazon EC2 - compute ({usage}) - Dev/QA a/c 2290", "998315", 1, 24000 + i * 800),
                   L(f"Amazon RDS - dev databases ({usage})", "998315", 1, 9500 + (i % 2) * 300),
                   L(f"Amazon S3 - storage ({usage})", "998315", 1, 2100 + i * 90)],
            terms="Net 15 days", term_days=15, target="PAID", uploader=VENKATESH, upload=upload, layout="B",
            nature="TECHNICAL_SERVICE", approvers=[AJAY],
            comment=f"Dev/QA spend for {usage} checked with the engineering team - approved.",
            title=f"AWS dev/QA usage {usage}")
        if m.month in aws_pays:
            prod.pays = [(aws_pays[m.month], "FULL", f"AWS production {usage}")]
            dev.pays = [(dt.date(2026, 6, 22) if m.month == 6 else aws_pays[m.month], "FULL", f"AWS dev/QA {usage}")]
        else:  # October
            prod.target = "PENDING_APPROVAL"
            dev.target, dev.upload, dev.approve_days = "READY_FOR_PAYMENT", dt.date(2026, 10, 7), [1]
        s += [prod, dev]
        if m.month >= 6:  # data-platform account went live in May
            data = Story(
                key=f"AWS-DATA-{m:%m}", vendor="AWS", inv_no=f"AWSIN26-{4180 + i * 37:04d}{i + 201:03d}", inv_date=inv_date,
                lines=[L(f"Amazon Redshift - data warehouse ({usage}) - Data a/c 8830", "998315", 1, 38000 + i * 2500),
                       L(f"AWS Glue - ETL jobs ({usage})", "998315", 1, 9800 + i * 310),
                       L(f"Amazon S3 - data lake storage ({usage})", "998315", 1, 6700 + i * 420),
                       L(f"Amazon Athena - queries ({usage})", "998315", 1, 3200 + i * 150)],
                terms="Net 15 days", term_days=15, target="PAID", uploader=VENKATESH, upload=upload, layout="B",
                nature="TECHNICAL_SERVICE", approvers=[AJAY],
                comment=f"Data platform spend for {usage} approved.", title=f"AWS data platform {usage}")
            if m.month in aws_pays and m.month <= 8:
                data.pays = [(aws_pays[m.month], "FULL", f"AWS data platform {usage}")]
            elif m.month == 9:
                data.target, data.decision = "RETURNED_FOR_REVIEW", "SEND_BACK"
                data.comment = ("Includes Redshift charges for the eu-west cluster decommissioned on 14 Aug. "
                                "Please obtain a credit note or confirmation from DevOps before resubmitting.")
            else:
                data.target, data.uploader, data.upload = "OCR_REVIEW_PENDING", KALASAGAR, dt.date(2026, 10, 9)
            s.append(data)

    # AWS Professional Services - migration engagement on PO (Net 30)
    s.append(Story(key="AWS-PS-1", vendor="AWS", inv_no="AWSPS26-000318", inv_date=dt.date(2026, 6, 15),
                   lines=[L("Migration readiness assessment", "998313", 1, 150000)], terms="Net 30 days", term_days=30,
                   target="PAID", uploader=VENKATESH, upload=dt.date(2026, 6, 16), layout="B", po="PO-AWS-PS",
                   approvers=[AJAY], comment="Assessment report accepted by IT (GRN recorded) - approved.",
                   pays=[(dt.date(2026, 7, 14), "FULL", "AWS ProServe milestone 1")], title="AWS ProServe - assessment"))
    s.append(Story(key="AWS-PS-2", vendor="AWS", inv_no="AWSPS26-000502", inv_date=dt.date(2026, 8, 20),
                   lines=[L("Landing zone implementation", "998313", 1, 300000)], terms="Net 30 days", term_days=30,
                   target="PARTIALLY_PAID", uploader=VENKATESH, upload=dt.date(2026, 8, 21), layout="B", po="PO-AWS-PS",
                   approvers=[SAMBI, MOHAN], comment="Landing zone delivered; release 50% now, balance on UAT sign-off.",
                   pays=[(dt.date(2026, 9, 18), D("170000.00"), "Milestone 2 - 50% released; balance on UAT sign-off")],
                   title="AWS ProServe - landing zone"))

    # ---- KEKA: HRMS subscription on agreement (Net 30), billed on the 1st ------------------
    heads = [118, 121, 124, 128, 133, 139, 146]
    keka_pays = [dt.date(2026, 4, 28), dt.date(2026, 5, 28), dt.date(2026, 6, 29), dt.date(2026, 7, 29),
                 dt.date(2026, 8, 28), dt.date(2026, 9, 29)]
    for i, m in enumerate(months):
        story = Story(
            key=f"KEKA-SUB-{m:%m}", vendor="KEKA", inv_no=f"KTPL/26-27/{412 + i * 23:04d}", inv_date=m,
            lines=[L(f"Keka HR & Payroll - per employee ({month_name(m)})", "997331", heads[i], 350),
                   L(f"Statutory compliance pack - PF / ESI / PT ({month_name(m)})", "997331", 1, 4500)],
            terms="Net 30 days", term_days=30, target="PAID", uploader=VENKATESH, upload=bd(m, 1),
            nature="TECHNICAL_SERVICE", approvers=[AJAY],
            comment=f"Head count {heads[i]} matches the HRMS active-employee report - approved.",
            title=f"Keka subscription {month_name(m)}")
        if i < len(keka_pays):
            story.pays = [(keka_pays[i], "FULL", f"Keka subscription {month_name(m)}")]
        else:
            story.target, story.approve_days = "READY_FOR_PAYMENT", [3]
        s.append(story)
    s.append(Story(key="KEKA-HIRE-1", vendor="KEKA", inv_no="KTPL/26-27/0498", inv_date=dt.date(2026, 6, 5),
                   lines=[L("Implementation & data migration - Keka Hire", "998313", 1, 40000)], terms="Net 30 days",
                   term_days=30, target="PAID", uploader=VENKATESH, upload=dt.date(2026, 6, 8), po="PO-KEKA-HIRE",
                   approvers=[AJAY], comment="Implementation signed off by HR - approved.",
                   pays=[(dt.date(2026, 7, 3), "FULL", "Keka Hire implementation")], title="Keka Hire implementation"))
    s.append(Story(key="KEKA-HIRE-2", vendor="KEKA", inv_no="KTPL/26-27/0517", inv_date=dt.date(2026, 7, 1),
                   lines=[L("Keka Hire - annual subscription", "997331", 1, 96000)], terms="Net 30 days", term_days=30,
                   target="PAID", uploader=VENKATESH, upload=dt.date(2026, 7, 2), po="PO-KEKA-HIRE",
                   approvers=[AJAY], comment="Annual Hire subscription as per PO - approved.",
                   pays=[(dt.date(2026, 7, 30), "FULL", "Keka Hire annual subscription")], title="Keka Hire annual"))
    s.append(Story(key="KEKA-LIC-1", vendor="KEKA", inv_no="KTPL/26-27/0561", inv_date=dt.date(2026, 8, 10),
                   lines=[L("Additional employee licences - H2 FY26-27", "997331", 20, 900)], terms="Net 30 days",
                   term_days=30, target="PAID", uploader=VENKATESH, upload=dt.date(2026, 8, 11), po="PO-KEKA-LIC",
                   approvers=[AJAY], pays=[(dt.date(2026, 9, 8), "FULL", "Keka additional licences (20)")],
                   title="Keka licences - first 20"))
    s.append(Story(key="KEKA-LIC-2", vendor="KEKA", inv_no="KTPL/26-27/0633", inv_date=dt.date(2026, 10, 6),
                   lines=[L("Additional employee licences - H2 FY26-27", "997331", 25, 900)], terms="Net 30 days",
                   term_days=30, target="OCR_REVIEW_PENDING", uploader=VENKATESH, upload=dt.date(2026, 10, 7),
                   po="PO-KEKA-LIC", title="Keka licences - 25 billed, 20 received"))
    s.append(Story(key="KEKA-ENGAGE", vendor="KEKA", inv_no="KTPL/26-27/0522", inv_date=dt.date(2026, 7, 1),
                   lines=[L("Keka Engage - annual (pulse surveys, OKRs)", "997331", 1, 60000)], terms="Net 30 days",
                   term_days=30, target="REJECTED", uploader=VENKATESH, upload=dt.date(2026, 7, 2),
                   nature="TECHNICAL_SERVICE", approvers=[AJAY], decision="REJECT",
                   comment="Engage module is not in the FY26-27 budget and no PO was raised. Rejected - "
                           "vendor to cancel the invoice.", title="Keka Engage (not ordered)"))

    # ---- WeWork: lease (payable within 10 days), membership billed on the 1st ---------------
    wework_kw = dict(vendor="WEWORK", dept=DEPT_ADMIN, cat=CAT_FACILITIES, uploader=KALASAGAR,
                     terms="Net 10 days", term_days=10)
    rent_pays = [dt.date(2026, 4, 9), dt.date(2026, 5, 8), dt.date(2026, 6, 10), dt.date(2026, 7, 9),
                 dt.date(2026, 8, 10), dt.date(2026, 9, 9), dt.date(2026, 10, 9)]
    for i, m in enumerate(months):
        desks = 40 if m.month < 7 else 45
        s.append(Story(key=f"WW-RENT-{m:%m}", inv_no=f"WWIM/HYD/26-27/{1847 + i * 211:05d}", inv_date=m,
                       lines=[L(f"Dedicated desks - RMZ Spire, Floor 6 ({month_name(m)})", "997212", desks, 6000)],
                       target="PAID", upload=bd(m, 1), nature="RENT_LAND_BUILDING", approvers=[BINDU, MOHAN],
                       comment=f"{desks} desks as per the lease" + (" (5 added from July)." if m.month >= 7 else "."),
                       pays=[(rent_pays[i], "FULL", f"WeWork membership {month_name(m)}")],
                       title=f"WeWork membership {month_name(m)}", **wework_kw))
    addon_pays = {5: dt.date(2026, 5, 14), 6: dt.date(2026, 6, 15), 7: dt.date(2026, 7, 14),
                  8: dt.date(2026, 8, 14), 9: dt.date(2026, 9, 14)}
    for i, m in enumerate(months[1:]):
        inv_date, period = m.replace(day=5), month_name(prev_month(m))
        story = Story(key=f"WW-ADDON-{m:%m}", inv_no=f"WWIM/HYD/26-27/{1902 + i * 211:05d}", inv_date=inv_date,
                      lines=[L(f"Meeting room credits - overage ({period})", "997212", 6 + i * 2, 1200),
                             L(f"Car parking - 6 slots ({period})", "997212", 6, 2500),
                             L(f"Printing & business services ({period})", "998599", 1, 2800 + i * 450)],
                      target="PAID", upload=bd(inv_date, 1), nature="CONTRACTOR", approvers=[BINDU],
                      comment=f"Add-on usage for {period} matches the community-team report - approved.",
                      title=f"WeWork add-on services {period}", **wework_kw)
        if m.month in addon_pays:
            story.pays = [(addon_pays[m.month], "FULL", f"WeWork add-ons {period}")]
        if m.month >= 9:  # the vendor printed 7 days instead of the lease's 10
            story.terms = "Net 7 days"
        if m.month == 9:
            story.terms_override = ("Lease clause 4 allows 10 days for all WeWork charges; invoice text is "
                                    "the vendor's default template. Applying the lease term.")
        if m.month == 10:
            story.target = "APPROVED"
        s.append(story)
    for i, m in enumerate(months[4:]):  # private office from August
        inv_date = m.replace(day=5)
        story = Story(key=f"WW-OFFICE-{m:%m}", inv_no=f"WWIM/HYD/26-27/{2391 + i * 97:05d}", inv_date=inv_date,
                      lines=[L(f"Private office, 6 seats - Floor 5 ({month_name(m)})", "997212", 1, 72000)],
                      target="PAID", upload=bd(inv_date, 1), nature="RENT_LAND_BUILDING", approvers=[BINDU],
                      comment="Private office for the client delivery team, as per the lease addendum - approved.",
                      title=f"WeWork private office {month_name(m)}", **wework_kw)
        if m.month == 8:
            story.pays = [(dt.date(2026, 8, 14), "FULL", "WeWork private office Aug 2026")]
        elif m.month == 9:
            story.pays = [(dt.date(2026, 9, 14), "FULL", "WeWork private office Sep 2026")]
        else:
            story.target = "PENDING_APPROVAL"
        s.append(story)
    s.append(Story(key="WW-EVENT", inv_no="WWIM/HYD/26-27/02604", inv_date=dt.date(2026, 10, 9),
                   lines=[L("Event space - client workshop (8 Oct 2026)", "997212", 1, 45000),
                          L("Event support & AV set-up", "998599", 1, 18500)],
                   target="OCR_REVIEWED", upload=dt.date(2026, 10, 9), nature="CONTRACTOR",
                   title="WeWork event space (client workshop)", **wework_kw))
    return s


# Purchase orders: PR -> quotation -> PO -> GRNs (story dates).
PURCHASES = [
    dict(key="PO-AWS-PS", vendor="AWS", requester=AJAY, pr_on=dt.date(2026, 5, 20), approve_on=dt.date(2026, 5, 21),
         quote_on=dt.date(2026, 5, 25), po_on=dt.date(2026, 5, 27), quote_no="AWS-PS-Q-2026-118",
         justification="Cloud migration of the client-delivery platform: readiness assessment and landing zone.",
         lines=[("Migration readiness assessment", "EA", 1, 150000), ("Landing zone implementation", "EA", 1, 300000)],
         grns=[(dt.date(2026, 6, 12), {"Migration readiness assessment": 1}),
               (dt.date(2026, 8, 18), {"Landing zone implementation": 1})]),
    dict(key="PO-KEKA-HIRE", vendor="KEKA", requester=AJAY, pr_on=dt.date(2026, 5, 12), approve_on=dt.date(2026, 5, 13),
         quote_on=dt.date(2026, 5, 15), po_on=dt.date(2026, 5, 18), quote_no="KEKA-Q-26-0091",
         justification="Applicant tracking for the FY26-27 hiring plan (HR request HR-0042).",
         lines=[("Keka Hire - annual subscription", "YR", 1, 96000),
                ("Implementation & data migration - Keka Hire", "EA", 1, 40000)],
         grns=[(dt.date(2026, 6, 3), {"Implementation & data migration - Keka Hire": 1}),
               (dt.date(2026, 6, 30), {"Keka Hire - annual subscription": 1})]),
    dict(key="PO-KEKA-LIC", vendor="KEKA", requester=AJAY, pr_on=dt.date(2026, 7, 28), approve_on=dt.date(2026, 7, 29),
         quote_on=dt.date(2026, 7, 31), po_on=dt.date(2026, 8, 3), quote_no="KEKA-Q-26-0144",
         justification="40 additional HRMS licences for H2 joiners (onboarding in two tranches of 20).",
         lines=[("Additional employee licences - H2 FY26-27", "EA", 40, 900)],
         grns=[(dt.date(2026, 8, 8), {"Additional employee licences - H2 FY26-27": 20}),
               (dt.date(2026, 10, 3), {"Additional employee licences - H2 FY26-27": 20})]),
]


# ======================================================================
# Documents
# ======================================================================
def _gti():
    from Backend.scripts import generate_test_invoices as gti
    gti.FOOTER = FOOTER
    gti.PDF_METADATA = {**gti.PDF_METADATA, "creator": "Paves APM demo-data generator", "title": "DEMO DOCUMENT"}
    return gti


def amounts(story: Story, vendor: dict) -> dict:
    gti = _gti()
    sc = gti.Scenario(sid=story.key, vendor=story.vendor, inv_no=story.inv_no, inv_date=story.inv_date,
                      category="DEMO", lines=story.lines, title=story.title)
    return gti.compute_amounts(sc, vendor)


def render_invoice(story: Story, vendor: dict, po_number: Optional[str]) -> bytes:
    gti = _gti()
    sc = gti.Scenario(sid=story.key, vendor=story.vendor, inv_no=story.inv_no, inv_date=story.inv_date,
                      category="DEMO", lines=story.lines, title=story.title, terms=story.terms, po=po_number,
                      layout=story.layout)
    due = story.inv_date + dt.timedelta(days=story.term_days)
    return gti.RENDERERS[story.layout](sc, vendor, gti.compute_amounts(sc, vendor), {"printed_due_date": due.isoformat()})


def render_quotation(purchase: dict, vendor: dict) -> bytes:
    gti = _gti()
    lines = [L(name, "998313", qty, rate) for name, _, qty, rate in purchase["lines"]]
    sc = gti.Scenario(sid=purchase["key"], vendor=purchase["vendor"], inv_no=purchase["quote_no"],
                      inv_date=purchase["quote_on"], category="DEMO", lines=lines, title="Quotation",
                      terms="Validity 30 days")
    return gti.render_classic(sc, vendor, gti.compute_amounts(sc, vendor), {"printed_due_date": None}, quotation=True)


def render_sheet(title: str, subtitle: str, rows: List[Tuple[str, str]], note: str = "") -> bytes:
    """A simple one-page document (agreement summary, payment advice, challan counterfoil)."""
    gti = _gti()
    doc = gti.Doc("helv", "hebo")
    doc.rect(30, 30, 565, 812, width=0.8)
    doc.text(297, 66, title, 15, bold=True, align="center")
    doc.text(297, 82, subtitle, 8.5, color=gti.MUTED, align="center")
    doc.hline(30, 565, 96)
    y = 126
    for label, value in rows:
        doc.text(50, y, label, 9, color=gti.MUTED)
        y = max(doc.wrap(230, y, value, 320, 9.5, bold=True), y + 16) + 4
    if note:
        doc.wrap(50, y + 20, note, 495, 9)
    return doc.bytes()


def render_agreement(title, ref, vendor, valid_from, valid_to, clause) -> bytes:
    return render_sheet(title.upper(), f"Agreement Ref: {ref}", [
        ("Vendor", vendor["vendor_name"]), ("Vendor GSTIN / PAN", f"{vendor['gstin']} / {vendor['pan']}"),
        ("Company", "Paves Global Infotech Pvt Ltd, Hyderabad, Telangana"),
        ("Term", f"{valid_from:%d %B %Y} to {valid_to:%d %B %Y}"), ("Payment terms", clause),
        ("TDS", "Payments are subject to deduction of tax at source as applicable."),
        ("Governing law", "Laws of India; courts at Hyderabad have jurisdiction."),
    ], "Signed for and on behalf of both parties. Summary copy for the vendor master.")


# ======================================================================
# Timestamp re-stamping
# ======================================================================
EXCLUDED_TABLES = {"ums_user_cache", "approver_directory", "approver_directory_role", "cdc_failure_log"}


class Restamper:
    """Moves the rows a step wrote (timestamp >= script start) to the step's story time, keeping
    the seconds between them. A step's rows are found by their own timestamps, so this works for
    every table the services touch - including ones written by background helpers."""

    def __init__(self, engine, enabled: bool):
        from sqlalchemy import text
        self.engine, self.enabled = engine, enabled
        now_utc = dt.datetime.now(dt.timezone.utc)
        with engine.connect() as c:
            db_local = c.execute(text("select localtimestamp")).scalar()
            cols = c.execute(text("""
                select table_name, column_name, data_type from information_schema.columns
                where table_schema = 'ap' and data_type like 'timestamp%'""")).fetchall()
            self.audit_json = {r[0]: r[1] for r in c.execute(text("""
                select column_name, data_type from information_schema.columns
                where table_schema='ap' and table_name='audit_log' and column_name in ('old_values','new_values')"""))}
        self.started = now_utc
        margin = dt.timedelta(minutes=2)
        self.since_tz = now_utc - margin
        # naive columns may hold UTC, IST or DB-local wall time - take the earliest
        self.since_naive = min(now_utc.replace(tzinfo=None), now_utc.astimezone(IST).replace(tzinfo=None), db_local) - margin
        self.columns = [(t, c, "with time zone" in dtype) for t, c, dtype in cols
                        if t not in EXCLUDED_TABLES and not t.startswith("cdc")]
        # Story times must stay well before the real clock (IST wall time in a naive column reads
        # 5h30 ahead of UTC), or a moved row would look "new" again to the next step.
        self.latest_story = now_utc - dt.timedelta(hours=6)

    def clamp(self, ts: dt.datetime) -> dt.datetime:
        return min(ts, self.latest_story.astimezone(IST))

    def apply(self, story_ts: dt.datetime, step_started: dt.datetime, today_dates: Optional[dt.date] = None):
        if not self.enabled:
            return
        from sqlalchemy import text
        delta = self.clamp(story_ts) - step_started
        with self.engine.begin() as c:
            probe = " union all ".join(
                f"select {i} where exists (select 1 from ap.\"{t}\" where \"{col}\" >= :s{'t' if tz else 'n'})"
                for i, (t, col, tz) in enumerate(self.columns))
            hits = [r[0] for r in c.execute(text(probe), {"st": self.since_tz, "sn": self.since_naive})]
            touched = {self.columns[i][0] for i in hits}
            if today_dates:
                self._fix_dates(c, touched, story_ts.date(), today_dates)
            if "audit_log" in touched:
                self._shift_audit_json(c, delta)
            for i in hits:
                t, col, tz = self.columns[i]
                c.execute(text(f'update ap."{t}" set "{col}" = "{col}" + :d where "{col}" >= :s'),
                          {"d": delta, "s": self.since_tz if tz else self.since_naive})

    def _fix_dates(self, c, touched, story_date, today):
        """Business dates a service filled with 'today' (PO date) take the story date."""
        from sqlalchemy import text
        if "purchase_order" in touched:
            c.execute(text("update ap.purchase_order set po_date = :d where po_date = :t and created_at >= :s"),
                      {"d": story_date, "t": today, "s": self.since_tz})

    def _shift_audit_json(self, c, delta):
        from sqlalchemy import text
        rows = c.execute(text("select audit_log_id, old_values, new_values from ap.audit_log where changed_at >= :s"),
                         {"s": self.since_tz}).fetchall()
        for audit_id, old, new in rows:
            changed = {}
            for name, value in (("old_values", old), ("new_values", new)):
                if value is None:
                    continue
                shifted = self._shift_value(value, delta)
                if shifted != value:
                    changed[name] = shifted
            for name, value in changed.items():
                cast = "jsonb" if self.audit_json.get(name) == "jsonb" else "json"
                c.execute(text(f"update ap.audit_log set {name} = cast(:v as {cast}) where audit_log_id = :i"),
                          {"v": json.dumps(value), "i": audit_id})

    _ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2}(?:\.\d+)?)(Z|[+-]\d{2}:?\d{2})?$")

    def _shift_value(self, value, delta):
        if isinstance(value, dict):
            return {k: self._shift_value(v, delta) for k, v in value.items()}
        if isinstance(value, list):
            return [self._shift_value(v, delta) for v in value]
        if isinstance(value, str) and self._ISO.match(value):
            try:
                parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
            since = self.since_tz if parsed.tzinfo else self.since_naive
            if parsed >= since:
                out = (parsed + delta).isoformat()
                return out.replace("+00:00", "Z") if value.endswith("Z") else out
        return value

    def finish(self):
        """Notifications were read when they were acted on; the last week's stay unread (pending approvals)."""
        if not self.enabled:
            return
        from sqlalchemy import text
        with self.engine.begin() as c:
            c.execute(text("""update ap.notification set is_read = true, read_at = created_at + interval '2 hours'
                              where not is_read and created_at < :cut"""),
                      {"cut": at(AS_OF - dt.timedelta(days=7), 0)})


# ======================================================================
# Runner
# ======================================================================
@dataclass
class Event:
    ts: dt.datetime
    seq: int
    label: str
    run: Callable[[], object]


class Seeder:
    def __init__(self, engine, restamper: Restamper):
        from Backend.Data_Access_Layer.utils.database import SessionLocal
        self.engine, self.Session, self.stamp = engine, SessionLocal, restamper
        self.vendors: Dict[str, dict] = {}
        self.pos: Dict[str, dict] = {}
        self.invoice_ids: Dict[str, int] = {}
        self.paid: Dict[str, Decimal] = {}
        self.log: List[str] = []
        self.failures: List[str] = []
        self.counter = 0

    # ---------- helpers ----------
    def q(self, db, sql, **params):
        from sqlalchemy import text
        return db.execute(text(sql), params)

    def session(self):
        return self.Session()

    def status_of(self, db, invoice_id) -> Optional[str]:
        return self.q(db, """select s.status_code from ap.invoice i join ap.status_master s on s.status_id = i.status_id
                             where i.invoice_id = :i""", i=invoice_id).scalar()

    def load_vendor(self, db, key, name):
        row = self.q(db, """select v.vendor_id, v.vendor_name, v.pan_number, a.address_line1, a.address_line2, a.city,
                                   a.state, a.postal_code, t.registration_number
                            from ap.vendor v
                            join ap.vendor_address a on a.vendor_id = v.vendor_id
                            join ap.vendor_tax t on t.vendor_address_id = a.vendor_address_id and t.registration_type = 'GST'
                            where v.vendor_name = :n order by a.is_primary desc limit 1""", n=name).fetchone()
        if row is None:
            return None
        address = [", ".join(p for p in (row.address_line1, row.address_line2) if p),
                   ", ".join(p for p in (row.city, row.state, row.postal_code) if p)]
        self.vendors[key] = {"vendor_id": row.vendor_id, "vendor_name": row.vendor_name, "address": address,
                             "gstin": row.registration_number, "pan": row.pan_number or row.registration_number[2:12],
                             "bank_note": "As per vendor master", "state_code": row.registration_number[:2]}
        return self.vendors[key]

    # ---------- setup ----------
    def onboard_wework(self):
        from Backend.API_Layer.interface.vendor_interface import (VendorAddressCreateRequest, VendorCreateRequest,
                                                                   VendorTaxCreateRequest)
        from Backend.Business_Layer.services.vendor_service import VendorService
        db = self.session()
        try:
            if self.load_vendor(db, "WEWORK", WEWORK["vendor_name"]):
                return "already onboarded"
            service = VendorService(db)
            vendor = service.create_vendor(VendorCreateRequest(
                vendor_name=WEWORK["vendor_name"], country_id=INDIA, currency_id=INR, pan_number=WEWORK["pan"],
                gstin=WEWORK["gstin"], msme_registered=False), JAGADISH_R)
            address = service.create_address(vendor.vendor_id, VendorAddressCreateRequest(
                address_type="REGISTERED", address_line1=WEWORK["address_line1"], address_line2=WEWORK["address_line2"],
                city=WEWORK["city"], state=WEWORK["state"], postal_code=WEWORK["postal_code"], country_id=INDIA,
                is_primary=True), JAGADISH_R)
            service.create_tax(address.vendor_address_id, VendorTaxCreateRequest(
                registration_type="GST", registration_number=WEWORK["gstin"], is_verified=True), JAGADISH_R)
            service.change_status(vendor.vendor_id, True, JAGADISH_R)
            self.load_vendor(db, "WEWORK", WEWORK["vendor_name"])
            return f"vendor #{vendor.vendor_id}"
        finally:
            db.close()

    def agreement(self, key, title, ref, agreement_type, valid_from, valid_to, term_days, clause):
        from Backend.Business_Layer.services.vendor_agreement_service import VendorAgreementService
        db = self.session()
        try:
            v = self.vendors[key]
            existing = self.q(db, "select agreement_id from ap.vendor_agreement where vendor_id = :v and reference_no = :r",
                              v=v["vendor_id"], r=ref).scalar()
            if existing:  # kept by the reset - a re-run must not supersede it with a copy
                return f"agreement #{existing} already active"
            content = render_agreement(title, ref, v, valid_from, valid_to, clause)
            created = VendorAgreementService(db).create(v["vendor_id"], {
                "title": title, "agreement_type": agreement_type, "reference_no": ref, "valid_from": valid_from,
                "valid_to": valid_to, "auto_renew": False, "term_days": term_days, "due_basis": "INVOICE_DATE",
                "payment_terms_text": clause}, f"{ref}.pdf", content, "application/pdf", JAGADISH_R)
            VendorAgreementService(db).verify(created["agreement_id"], "Checked against the signed copy.", BINDU)
            return f"agreement #{created['agreement_id']}"
        finally:
            db.close()

    def policies(self):
        from Backend.API_Layer.interface.approval_policy_interface import (ApprovalPolicyCreateRequest,
                                                                            ApprovalPolicyLevelRequest)
        from Backend.Business_Layer.services.approval_policy_service import ApprovalPolicyService
        db = self.session()
        try:
            service = ApprovalPolicyService(db)
            made = []
            for name, low, high, levels in (
                ("Facilities & Workspace - up to Rs 1 lakh", D("0"), D("100000"), [("Finance_Manager", 1)]),
                ("Facilities & Workspace - above Rs 1 lakh", D("100000.01"), None,
                 [("Finance_Manager", 1), ("Super_Admin", 2)]),
            ):
                if service.dao.get_policy_by_name(name) is not None:
                    continue
                policy = service.create_policy(ApprovalPolicyCreateRequest(
                    name=name, department_id=DEPT_ADMIN, purchase_category_id=CAT_FACILITIES, min_amount=low,
                    max_amount=high, is_active=True,
                    description="Workspace membership, rent and facility services (ADMIN / Facilities).",
                    levels=[ApprovalPolicyLevelRequest(level_number=n, approver_type="ROLE", approval_rule="ANY_ONE",
                                                       role_code=role) for role, n in levels]))
                made.append(policy.id)
            return f"policies {made}"
        finally:
            db.close()

    # ---------- procurement ----------
    def raise_pr(self, p):
        from Backend.API_Layer.interface.procurement_interface import (PurchaseRequisitionCreateRequest,
                                                                       PurchaseRequisitionLineRequest)
        from Backend.Business_Layer.services.procurement_service import ProcurementService
        db = self.session()
        try:
            pr = ProcurementService(db).create_purchase_requisition(PurchaseRequisitionCreateRequest(
                department_id=DEPT_IT, purchase_category_id=CAT_IT_SOFTWARE, priority="NORMAL",
                required_by=dt.date.today() + dt.timedelta(days=30), delivery_location="Paves Global Infotech, Hyderabad",
                justification=p["justification"],
                lines=[PurchaseRequisitionLineRequest(item_name=name, quantity=D(str(qty)), uom=uom,
                                                      estimated_unit_price=D(str(rate)))
                       for name, uom, qty, rate in p["lines"]]), p["requester"])
            # required_by must be a future date when entered; the story's request was for ~3 weeks out
            self.q(db, "update ap.purchase_requisition set required_by = :d where id = :i",
                   d=p["pr_on"] + dt.timedelta(days=21), i=pr.id)
            db.commit()
            ProcurementService(db).submit_purchase_requisition(pr.id, p["requester"])
            self.pos[p["key"]] = {"pr_id": pr.id}
            return f"{pr.pr_number}"
        finally:
            db.close()

    def approve_pr(self, p):
        from Backend.Business_Layer.services.procurement_service import ProcurementService
        db = self.session()
        try:
            ProcurementService(db).approve_purchase_requisition(self.pos[p["key"]]["pr_id"], JAGADISH_R,
                                                                "Budgeted in the FY26-27 IT plan - approved.")
        finally:
            db.close()

    def quotation(self, p):
        from Backend.API_Layer.utils.s3_utils import upload_to_s3
        from Backend.Business_Layer.services.procurement_service import ProcurementService
        db = self.session()
        try:
            v = self.vendors[p["vendor"]]
            subtotal = sum(D(str(q)) * D(str(r)) for _, _, q, r in p["lines"])
            total = money(subtotal * D("1.18"))
            stored = upload_to_s3(f"{p['quote_no']}.pdf", render_quotation(p, v), "application/pdf")
            quote = ProcurementService(db).create_quotation(
                self.pos[p["key"]]["pr_id"], v["vendor_id"], stored["filepath"], p["quote_no"], p["quote_on"],
                p["quote_on"] + dt.timedelta(days=30), total, RAKESH, delivery_days=14, payment_terms="Net 30 days")
            self.pos[p["key"]]["quotation_id"] = quote.id
            return f"quotation #{quote.id} Rs {total:,}"
        finally:
            db.close()

    def purchase_order(self, p):
        from Backend.Business_Layer.services.procurement_service import ProcurementService
        db = self.session()
        try:
            service = ProcurementService(db)
            pr_id = self.pos[p["key"]]["pr_id"]
            service.select_vendor(pr_id, self.pos[p["key"]]["quotation_id"],
                                  "Single-source: existing platform vendor; commercials within budget.", RAKESH)
            po = service.generate_purchase_order(pr_id, RAKESH)
            lines = {r.item_name: r.id for r in self.q(db, "select id, item_name from ap.purchase_order_line where po_id = :p",
                                                         p=po.po_id)}
            self.pos[p["key"]].update(po_id=po.po_id, po_number=po.po_number, lines=lines)
            return po.po_number
        finally:
            db.close()

    def goods_receipt(self, p, n, received_on, quantities):
        from Backend.API_Layer.interface.goods_receipt_interface import GoodsReceiptCreateRequest, GoodsReceiptLineRequest
        from Backend.Business_Layer.services.goods_receipt_service import GoodsReceiptService
        db = self.session()
        try:
            po = self.pos[p["key"]]
            grn = GoodsReceiptService(db).create_goods_receipt(GoodsReceiptCreateRequest(
                vendor_id=self.vendors[p["vendor"]]["vendor_id"], po_id=po["po_id"],
                grn_number=f"GRN-{po['po_number']}-{n}", receipt_date=received_on,
                lines=[GoodsReceiptLineRequest(po_line_id=po["lines"][name], description=name,
                                               received_quantity=D(str(qty))) for name, qty in quantities.items()]),
                AJAY)
            return f"GRN #{grn.grn_id}"
        finally:
            db.close()

    # ---------- invoices ----------
    def upload_batch(self, stories: List[Story], uploader: str, duplicate_of: Optional[Story] = None):
        from Backend.Business_Layer.services.invoice_bulk_upload_service import InvoiceBulkUploadService, process_batch
        from Backend.Business_Layer.utils.bulk_upload_files import _candidate
        files = []
        for story in stories:
            po = self.pos.get(story.po, {}).get("po_number") if story.po else None
            name = f"{story.vendor}_{re.sub(r'[^A-Za-z0-9-]+', '-', story.inv_no)}.pdf"
            files.append((story, name, render_invoice(story, self.vendors[story.vendor], po)))
        candidates = [_candidate(name, content) for _, name, content in files]
        if duplicate_of is not None:  # the same PDF forwarded twice - caught by the batch's file check
            original = next(c for (st, _, _), c in zip(files, candidates) if st is duplicate_of)
            candidates.append(_candidate(original.file_name.replace(".pdf", " (copy).pdf"), original.content))
        db = self.session()
        try:
            label = f"Invoices received {stories[0].upload:%d %b %Y}"
            batch_id = InvoiceBulkUploadService(db).create_batch(candidates, label, uploader, NAMES[uploader])
        finally:
            db.close()
        asyncio.run(process_batch(batch_id, uploader))
        db = self.session()
        try:
            items = {r.file_name: r for r in self.q(db, """select file_name, status, invoice_id, error_message
                                                            from ap.invoice_upload_batch_item where batch_id = :b""",
                                                     b=batch_id)}
        finally:
            db.close()
        out = []
        for story, name, _ in files:
            item = items.get(name)
            if item is not None and item.invoice_id:
                self.invoice_ids[story.key] = item.invoice_id
                out.append(f"{story.key}=#{item.invoice_id}")
            else:
                self.failures.append(f"{story.key}: upload {item.status if item else 'missing'} - "
                                     f"{item.error_message if item else ''}")
                out.append(f"{story.key}=FAILED")
        return f"batch #{batch_id}: " + ", ".join(out)

    def review(self, story: Story):
        from Backend.API_Layer.interface.invoice_process_interface import InvoiceOCRReviewRequest
        from Backend.Business_Layer.services.invoice_process_service import apply_ocr_review
        from Backend.Business_Layer.services.invoice_review_automation_service import auto_determine_tds
        from Backend.Business_Layer.services.tds_determination_service import TDSDeterminationService
        invoice_id = self.invoice_ids.get(story.key)
        if invoice_id is None:
            return "no invoice"
        db = self.session()
        try:
            status = self.status_of(db, invoice_id)
            if status not in ("OCR_REVIEW_PENDING", "RETURNED_FOR_REVIEW", "OCR_FAILED"):
                return f"skipped ({status})"
            inv = self.q(db, """select inbound_document_id, invoice_number, invoice_date, net_amount, tax_amount
                                from ap.invoice where invoice_id = :i""", i=invoice_id).fetchone()
            amt = amounts(story, self.vendors[story.vendor])
            fields = {}
            if inv.invoice_number != story.inv_no:
                fields["invoice_number"] = story.inv_no
            if inv.invoice_date != story.inv_date:
                fields["invoice_date"] = story.inv_date
            if inv.net_amount is None or money(inv.net_amount) != money(amt["net"]):
                fields.update(gross_amount=money(amt["net"]), net_amount=money(amt["net"]))
            if inv.tax_amount is None or money(inv.tax_amount) != money(amt["tax_total"]):
                fields["tax_amount"] = money(amt["tax_total"])
            if story.po:
                fields.update(invoice_type="PO", po_id=self.pos[story.po]["po_id"])
            else:
                fields.update(invoice_type="NON_PO", department_id=story.dept, purchase_category_id=story.cat)
            apply_ocr_review(inv.inbound_document_id, InvoiceOCRReviewRequest(**fields), db, story.uploader)
            note = auto_determine_tds(db, invoice_id, story.uploader)
            if story.nature:
                TDSDeterminationService(db).determine(invoice_id, story.uploader, payment_nature_code=story.nature)
                note = None
            corrected = sorted(k for k in fields if k not in ("invoice_type", "po_id", "department_id",
                                                               "purchase_category_id"))
            return "reviewed" + (f", corrected {corrected}" if corrected else "") + (f" ({note})" if note else "")
        finally:
            db.close()

    def send(self, story: Story):
        from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService
        invoice_id = self.invoice_ids.get(story.key)
        db = self.session()
        try:
            status = self.status_of(db, invoice_id) if invoice_id else None
            if status != "OCR_REVIEWED":
                return f"skipped ({status})"
            InvoiceApprovalService(db).send_for_approval(invoice_id, story.uploader)
            return "sent for approval"
        finally:
            db.close()

    def decide(self, story: Story, level: int):
        from Backend.Business_Layer.services.invoice_approval_service import InvoiceApprovalService
        invoice_id = self.invoice_ids.get(story.key)
        db = self.session()
        try:
            if not invoice_id or self.status_of(db, invoice_id) != "PENDING_APPROVAL":
                return "nothing pending"
            pending = [r[0] for r in self.q(db, """
                select u.user_id::text from ap.invoice_approval a
                join ap.invoice_approval_step s on s.invoice_approval_id = a.invoice_approval_id and s.status = 'PENDING'
                join ap.invoice_approval_step_approver sa on sa.approval_step_id = s.id and sa.status = 'PENDING'
                join ap.ums_user_cache u on u.user_uuid = sa.user_uuid
                where a.invoice_approval_id = (select max(invoice_approval_id) from ap.invoice_approval where invoice_id = :i)
                """, i=invoice_id)]
            preferred = story.approvers + [AJAY, BINDU, MOHAN, SAMBI, BOLLI]
            actor = next((p for p in preferred if p in pending), pending[0] if pending else None)
            if actor is None:
                return "no eligible approver"
            service = InvoiceApprovalService(db)
            if level == 1 and story.decision == "REJECT":
                service.reject(invoice_id, actor, story.comment)
                return f"rejected by {NAMES.get(actor, actor)}"
            if level == 1 and story.decision == "SEND_BACK":
                service.send_back(invoice_id, actor, story.comment)
                return f"sent back by {NAMES.get(actor, actor)}"
            service.approve(invoice_id, actor, story.comment)
            return f"level {level} approved by {NAMES.get(actor, actor)}"
        finally:
            db.close()

    def verify_tds(self, story: Story):
        from Backend.Business_Layer.services.tds_determination_service import TDSDeterminationService
        invoice_id = self.invoice_ids.get(story.key)
        db = self.session()
        try:
            if not invoice_id or self.status_of(db, invoice_id) != "APPROVED":
                return "skipped"
            row = self.q(db, """select t.determination_status, t.tds_applicable, t.tds_rate, r.old_section
                                from ap.invoice_tds t left join ap.tax_rule r on r.tax_rule_id = t.tds_rule_id
                                where t.invoice_id = :i""", i=invoice_id).fetchone()
            if row is None or row.determination_status == "VERIFIED":
                return "skipped"
            remark = (f"Section {row.old_section} @ {money(row.tds_rate):g}% verified against PAN and the contract."
                      if row.tds_applicable else "No TDS: below the threshold for this vendor and nature - verified.")
            TDSDeterminationService(db).verify(invoice_id, BOLLI, remark)
            return remark
        finally:
            db.close()

    def override_terms(self, story: Story):
        from Backend.Business_Layer.services.payment_term_compliance_service import PaymentTermComplianceService
        invoice_id = self.invoice_ids.get(story.key)
        db = self.session()
        try:
            PaymentTermComplianceService(db).verify(invoice_id, 10, "INVOICE_DATE", story.terms_override, BINDU)
            db.commit()
            return "payment terms verified (10 days per lease)"
        finally:
            db.close()

    def ready(self, story: Story):
        from Backend.Business_Layer.services.payment_service import PaymentService
        invoice_id = self.invoice_ids.get(story.key)
        db = self.session()
        try:
            if not invoice_id or self.status_of(db, invoice_id) != "APPROVED":
                return "skipped"
            PaymentService(db).mark_ready_for_payment(invoice_id, BOLLI)
            return "ready for payment"
        finally:
            db.close()

    def pay(self, story: Story, n: int, pay_date: dt.date, amount, remarks: str):
        from Backend.API_Layer.interface.payment_interface import RecordPaymentRequest
        from Backend.API_Layer.interface.tds_tracking_interface import RecordTdsDeductionRequest
        from Backend.Business_Layer.services.payment_tracking_service import PaymentTrackingService
        from Backend.Business_Layer.services.tds_tracking_service import TdsTrackingService
        invoice_id = self.invoice_ids.get(story.key)
        db = self.session()
        try:
            if not invoice_id or self.status_of(db, invoice_id) not in ("READY_FOR_PAYMENT", "PARTIALLY_PAID"):
                return "skipped"
            inv = self.q(db, """select i.net_amount, coalesce(case when t.tds_applicable then t.tds_amount end, 0) tds,
                                       t.tds_applicable
                                from ap.invoice i left join ap.invoice_tds t on t.invoice_id = i.invoice_id
                                where i.invoice_id = :i""", i=invoice_id).fetchone()
            payable = money(inv.net_amount) - money(inv.tds) - self.paid.get(story.key, D("0"))
            value = payable if amount == "FULL" else money(amount)
            self.counter += 1
            mode = "RTGS" if value >= D("200000") else "NEFT"
            utr = f"HDFC{mode[0]}{pay_date:%y}{pay_date.timetuple().tm_yday:03d}{410000 + self.counter * 137:06d}"
            actor = JAGADISH_R if self.counter % 3 else BOLLI
            result = PaymentTrackingService(db).record_payment(invoice_id, RecordPaymentRequest(
                payment_date=pay_date, amount=value, payment_mode=mode, reference_number=utr, remarks=remarks,
                entry_mode="MANUAL"), actor)
            v = self.vendors[story.vendor]
            advice = render_sheet("PAYMENT ADVICE", "Paves Global Infotech Pvt Ltd - Accounts Payable", [
                ("Payment date", f"{pay_date:%d %b %Y}"), ("Beneficiary", v["vendor_name"]),
                ("Beneficiary GSTIN", v["gstin"]), ("Invoice", f"{story.inv_no} dated {story.inv_date:%d %b %Y}"),
                ("Invoice amount", f"Rs {money(inv.net_amount):,}"), ("TDS deducted", f"Rs {money(inv.tds):,}"),
                ("Amount paid", f"Rs {value:,}"), ("Mode", mode), ("UTR / reference", utr),
                ("Debit account", "Current account XXXXXX4521"), ("Remarks", remarks)])
            PaymentTrackingService(db).upload_document(result["recorded_payment_id"], f"payment-advice-{utr}.pdf",
                                                       advice, "application/pdf", "RECEIPT", actor)
            self.paid[story.key] = self.paid.get(story.key, D("0")) + value
            if n == 0 and inv.tds_applicable:
                TdsTrackingService(db).record_deduction(invoice_id, RecordTdsDeductionRequest(
                    deduction_date=pay_date, remarks="TDS deducted at payment"), actor)
            return f"paid Rs {value:,} by {mode} {utr}"
        finally:
            db.close()

    def challans(self, month: dt.date, deposit_on: dt.date, serial_base: int):
        from Backend.Business_Layer.services.tds_challan_service import TdsChallanService
        db = self.session()
        try:
            end = (month.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
            rows = self.q(db, """select k.invoice_id, t.tds_amount, coalesce(r.old_section, '-') section
                                 from ap.invoice_tds_tracking k join ap.invoice_tds t on t.invoice_id = k.invoice_id
                                 left join ap.tax_rule r on r.tax_rule_id = t.tds_rule_id
                                 where k.tracking_status = 'TDS_DEDUCTED' and t.tds_applicable
                                   and k.deduction_date between :a and :b order by k.invoice_id""",
                          a=month, b=end).fetchall()
            groups: Dict[str, list] = {}
            for r in rows:
                groups.setdefault(r.section, []).append(r)
            done = []
            for n, (section, items) in enumerate(sorted(groups.items())):
                total = sum((money(r.tds_amount) for r in items), D("0"))
                serial = f"{serial_base + n:05d}"
                doc = render_sheet("CHALLAN NO./ITNS 281", "Taxpayer's counterfoil - TDS / TCS", [
                    ("Deductor", "Paves Global Infotech Pvt Ltd"), ("Assessment year", "2027-28"),
                    ("Section", f"{section} - TDS payable by taxpayer (200)"),
                    ("Period", f"{month:%B %Y} deductions"), ("BSR code", BSR_CODE),
                    ("Challan serial no.", serial), ("Date of deposit", f"{deposit_on:%d %b %Y}"),
                    ("Amount (Rs)", f"{total:,}"), ("Invoices", str(len(items)))])
                result = TdsChallanService(db).create_challan({
                    "challan_serial_no": serial, "bsr_code": BSR_CODE, "deposit_date": deposit_on,
                    "tax_amount": total, "surcharge": 0, "cess": 0, "interest": 0, "fee": 0, "total_amount": total,
                    "assessment_year": "2027-28",
                    "remarks": f"{month:%B %Y} TDS u/s {section} deposited via net banking (ITNS 281)"},
                    [{"invoice_id": r.invoice_id} for r in items], BOLLI,
                    (f"challan-{BSR_CODE}-{serial}.pdf", doc, "application/pdf"))
                done.append(f"{section}: Rs {total:,} x{len(items)} -> challan #{result.get('challan_id', '?')}")
            return "; ".join(done) or "no deductions"
        finally:
            db.close()

    def file_q1(self):
        from Backend.Business_Layer.services.tds_challan_service import TdsChallanService
        db = self.session()
        try:
            ids = [r[0] for r in self.q(db, """select invoice_id from ap.invoice_tds_tracking
                                              where tracking_status = 'TDS_DEPOSITED'
                                                and deduction_date between '2026-04-01' and '2026-06-30'
                                              order by invoice_id""")]
            ack = "452017286620714"
            doc = render_sheet("FORM 26Q - PROVISIONAL RECEIPT", "Quarterly TDS statement (other than salary)", [
                ("Deductor", "Paves Global Infotech Pvt Ltd"), ("Financial year", "2026-27"), ("Quarter", "Q1 (Apr - Jun)"),
                ("Token / acknowledgement no.", ack), ("Date of filing", "28 Jul 2026"), ("Deductee records", str(len(ids)))])
            result = TdsChallanService(db).create_filing({
                "form_type": "26Q", "financial_year": "2026-27", "quarter": 1, "acknowledgement_no": ack,
                "filing_date": dt.date(2026, 7, 28), "is_revision": False,
                "remarks": "Q1 26Q filed through TIN-FC; challans matched in OLTAS."},
                ids, BINDU, (f"26Q-Q1-{ack}.pdf", doc, "application/pdf"))
            return f"Q1 26Q filed for {len(ids)} invoices (filing #{result.get('filing_id', '?')})"
        finally:
            db.close()

    # ---------- schedule ----------
    def events(self, stories: List[Story]) -> List[Event]:
        ev: List[Event] = []

        def add(ts, label, fn):
            ev.append(Event(ts, len(ev), label, fn))

        add(at(dt.date(2026, 3, 18), 11, 20), "Onboard WeWork India (GST verified)", self.onboard_wework)
        add(at(dt.date(2026, 3, 18), 12, 5), "Facilities approval policies", self.policies)
        add(at(dt.date(2026, 3, 20), 15, 10), "WeWork lease agreement",
            lambda: self.agreement("WEWORK", "Workspace membership agreement - RMZ Spire, HITEC City",
                                   "WW-HYD-RMZ-2026-117", "LEASE", dt.date(2026, 4, 1), dt.date(2029, 3, 31), 10,
                                   "All WeWork charges are payable within 10 days of the invoice date."))
        add(at(dt.date(2026, 3, 25), 16, 40), "Keka subscription agreement",
            lambda: self.agreement("KEKA", "Keka HRMS subscription agreement FY26-27", "KEKA-SUB-2026-27-031",
                                   "SUBSCRIPTION", dt.date(2026, 4, 1), dt.date(2027, 3, 31), 30,
                                   "Invoices are payable within 30 days of the invoice date."))
        for p in PURCHASES:
            add(at(p["pr_on"], 11, 15), f"{p['key']}: purchase requisition", lambda p=p: self.raise_pr(p))
            add(at(p["approve_on"], 10, 40), f"{p['key']}: PR approved", lambda p=p: self.approve_pr(p))
            add(at(p["quote_on"], 14, 30), f"{p['key']}: quotation", lambda p=p: self.quotation(p))
            add(at(p["po_on"], 12, 0), f"{p['key']}: purchase order", lambda p=p: self.purchase_order(p))
            for n, (on, qty) in enumerate(p["grns"], start=1):
                add(at(on, 16, 20), f"{p['key']}: goods receipt {n}", lambda p=p, n=n, on=on, qty=qty: self.goods_receipt(p, n, on, qty))

        batches: Dict[Tuple[dt.date, str], List[Story]] = {}
        for st in stories:
            batches.setdefault((st.upload, st.uploader), []).append(st)
        for i, ((day, who), group) in enumerate(sorted(batches.items())):
            dup = next((x for x in group if x.key == "AWS-PROD-10"), None)
            add(at(day, 10, 5 + (i % 4) * 9), f"Bulk upload by {NAMES[who]}: {len(group)} invoice(s)",
                lambda g=group, w=who, d=dup: self.upload_batch(g, w, d))

        for i, st in enumerate(stories):
            jitter = (i * 7) % 50
            review_at = at(st.upload, 11, 30 + jitter)
            if st.target == "OCR_REVIEW_PENDING":
                continue
            add(review_at, f"{st.key}: AP review", lambda st=st: self.review(st))
            if st.target == "OCR_REVIEWED":
                continue
            add(review_at + dt.timedelta(minutes=4), f"{st.key}: send for approval", lambda st=st: self.send(st))
            if st.target == "PENDING_APPROVAL":
                continue
            last = st.upload
            for level, offset in enumerate(st.approve_days, start=1):
                last = bd(st.upload, offset)
                add(at(last, 10, 20 + jitter + level * 3), f"{st.key}: approval L{level}",
                    lambda st=st, level=level: self.decide(st, level))
                if st.decision != "APPROVE":
                    break
            if st.target in ("REJECTED", "RETURNED_FOR_REVIEW"):
                continue
            verify_day = bd(last, 1)
            if st.pays and verify_day >= st.pays[0][0]:
                verify_day = last
            add(at(verify_day, 14, 10 + jitter), f"{st.key}: TDS verified", lambda st=st: self.verify_tds(st))
            if st.terms_override:
                add(at(verify_day, 14, 40 + jitter), f"{st.key}: payment terms verified", lambda st=st: self.override_terms(st))
            if st.target == "APPROVED":
                continue
            add(at(verify_day, 15, 5 + jitter), f"{st.key}: ready for payment", lambda st=st: self.ready(st))
            for n, (on, amount, remarks) in enumerate(st.pays):
                add(at(on, 16, 0 + jitter), f"{st.key}: payment {n + 1}",
                    lambda st=st, n=n, on=on, a=amount, r=remarks: self.pay(st, n, on, a, r))

        for n, month in enumerate(dt.date(2026, m, 1) for m in range(4, 10)):
            deposit_on = bd(dt.date(month.year, month.month + 1, 6), 0)
            add(at(deposit_on, 11, 45), f"TDS challans for {month:%b %Y}",
                lambda month=month, d=deposit_on, n=n: self.challans(month, d, 21400 + n * 13))
        add(at(dt.date(2026, 7, 28), 15, 30), "Q1 26Q return filed", self.file_q1)
        late = [e.label for e in ev if e.ts.date() > AS_OF]
        if late:
            raise ValueError(f"Story events after {AS_OF}: {late}")
        return sorted(ev, key=lambda e: (e.ts, e.seq))

    def run(self, events: List[Event]):
        for e in events:
            started = dt.datetime.now(dt.timezone.utc)
            try:
                outcome = e.run()
            except Exception as exc:
                outcome = f"FAILED: {exc}"
                self.failures.append(f"{e.label}: {exc}")
                traceback.print_exc(limit=3)
            try:
                self.stamp.apply(e.ts, started, today_dates=dt.date.today())
            except Exception as exc:
                self.failures.append(f"re-stamp after {e.label}: {exc}")
            line = f"{self.stamp.clamp(e.ts):%d %b %H:%M}  {e.label}: {outcome}"
            self.log.append(line)
            print(line, flush=True)
        self.stamp.finish()


# ======================================================================
# Entry point
# ======================================================================
def plan_report(stories: List[Story], vendors: Dict[str, dict]) -> dict:
    by_status: Dict[str, int] = {}
    total = D("0")
    rows = []
    for st in stories:
        amt = amounts(st, vendors[st.vendor])
        total += amt["net"]
        by_status[st.target] = by_status.get(st.target, 0) + 1
        rows.append(f"{st.inv_date:%d %b}  {st.vendor:<6} {st.inv_no:<22} Rs {money(amt['net']):>12,}  "
                    f"{'PO ' if st.po else 'NON'} {st.target:<20} {st.title}")
    return {"invoices": len(stories), "by_vendor": {k: sum(1 for s in stories if s.vendor == k) for k in vendors},
            "by_status": dict(sorted(by_status.items(), key=lambda kv: -kv[1])), "total_value": f"Rs {total:,}",
            "invoices_list": rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed the APM client-demo dataset.")
    parser.add_argument("--execute", action="store_true", help="Build the dataset (default: dry run).")
    parser.add_argument("--no-backdate", action="store_true", help="Keep real timestamps on every row.")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)  # S3 / Textract / GST-lookup settings, as the backend loads them
    from sqlalchemy import text
    from Backend.Data_Access_Layer.utils.database import engine

    stories = build_stories()
    seeder = Seeder(engine, Restamper(engine, enabled=not args.no_backdate and args.execute) if args.execute
                    else None)
    db = seeder.session()
    try:
        database = db.execute(text("select current_database()")).scalar()
        existing = db.execute(text("select count(*) from ap.invoice")).scalar()
        seeder.load_vendor(db, "AWS", "AMAZON WEB SERVICES INDIA PRIVATE LIMITED")
        seeder.load_vendor(db, "KEKA", "KEKA TECHNOLOGIES PRIVATE LIMITED")
        if "WEWORK" not in seeder.vendors and not seeder.load_vendor(db, "WEWORK", WEWORK["vendor_name"]):
            seeder.vendors["WEWORK"] = {"vendor_id": None, "vendor_name": WEWORK["vendor_name"],
                                        "address": [f"{WEWORK['address_line1']}, {WEWORK['address_line2']}",
                                                    f"{WEWORK['city']}, {WEWORK['state']}, {WEWORK['postal_code']}"],
                                        "gstin": WEWORK["gstin"], "pan": WEWORK["pan"],
                                        "bank_note": "As per vendor master", "state_code": "36"}
    finally:
        db.close()

    report = {"mode": "execute" if args.execute else "dry-run", "database": database,
              "existing_invoices": existing, **plan_report(stories, seeder.vendors)}
    if not args.execute:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        for st in stories:
            po = f"<{st.po}>" if st.po else None
            (PREVIEW_DIR / f"{st.key}.pdf").write_bytes(render_invoice(st, seeder.vendors[st.vendor], po))
        report["events"] = len(seeder.events(stories))
        report["previews"] = str(PREVIEW_DIR)
        print(json.dumps(report, indent=2, default=str))
        return 0

    if database != EXPECTED_DATABASE:
        print(json.dumps({"error": f"Refusing to seed {database!r}; expected {EXPECTED_DATABASE!r}."}))
        return 1
    if existing:
        print(json.dumps({"error": f"{existing} invoices already exist. Run reset_demo_transactions --execute first."}))
        return 1
    missing = [k for k in ("AWS", "KEKA") if k not in seeder.vendors]
    if missing:
        print(json.dumps({"error": f"Vendor(s) not found: {missing}"}))
        return 1
    seeder.vendors.pop("WEWORK", None) if seeder.vendors.get("WEWORK", {}).get("vendor_id") is None else None
    seeder.run(seeder.events(stories))

    db = seeder.session()
    try:
        final = dict(db.execute(text("""select s.status_code, count(*) from ap.invoice i
                                        join ap.status_master s on s.status_id = i.status_id group by 1""")).fetchall())
        mismatched = [f"{st.key}: wanted {st.target}, got {seeder.status_of(db, seeder.invoice_ids[st.key])}"
                      for st in stories if st.key in seeder.invoice_ids
                      and seeder.status_of(db, seeder.invoice_ids[st.key]) != st.target]
    finally:
        db.close()
    print(json.dumps({"final_status_counts": final, "not_at_target": mismatched, "failures": seeder.failures},
                     indent=2, default=str))
    return 0 if not seeder.failures else 2


if __name__ == "__main__":
    sys.exit(main())
