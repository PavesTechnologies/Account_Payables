# Backend/API_Layer/utils/vendor_permissions.py
"""UMS permission codes for Vendor Management, vendor intake, and the vendor-side
PO / GRN records (vendor_route.py, vendor_intake_route.py, purchase_order_route.py,
goods_receipt_route.py). Every check is any-of (permission_based_access).

New codes (create in UMS, assign to Vendor_Intake):
    VENDOR_VIEW          read Vendor Management screens (vendor detail tabs, engagements, PO/GRN records)
    VENDOR_MANAGE        create / edit vendors, status, addresses, tax registrations, intake & pre-screen,
                         PO and GRN records + their documents
    VENDOR_BANK_MANAGE   add / edit / delete vendor bank accounts (kept separate - changing a payee's
                         bank account is the classic payment-fraud path)

Reads that other modules already rely on stay open to the permissions those modules use, so
invoice review, payments, procurement, NDA, onboarding and reports keep working unchanged.
"""

VENDOR_VIEW = "VENDOR_VIEW"
VENDOR_MANAGE = "VENDOR_MANAGE"
VENDOR_BANK_MANAGE = "VENDOR_BANK_MANAGE"

# Vendor Management's own screens.
VENDOR_READ = [VENDOR_VIEW, VENDOR_MANAGE, VENDOR_BANK_MANAGE]
VENDOR_WRITE = [VENDOR_MANAGE]
VENDOR_BANK_WRITE = [VENDOR_BANK_MANAGE]

# GET /vendor (vendor pickers / filters across AP): invoice OCR review, mark-as-paid, AP reports,
# procurement (quotations, vendor selection, POs, PR detail, RFQ), onboarding.
VENDOR_LIST_READ = VENDOR_READ + [
    "INVOICE_VIEW", "PAYMENT_VIEW", "PAYMENT_PROCESS",
    "PR_VIEW", "QUOTATION_VIEW", "VENDOR_SELECTION_VIEW", "PO_VIEW",
    "ONBOARDING_VIEW", "ONBOARDING_PROCESS",
    "AP_MANAGEMENT_REPORTS_VIEW", "AP_MANAGEMENT_DASHBOARD_VIEW",
]

# GET /vendor/{id}: payments (bank details for mark-as-paid), NDA modal on RFQ, onboarding.
VENDOR_DETAIL_READ = VENDOR_READ + [
    "INVOICE_VIEW", "PAYMENT_VIEW", "PAYMENT_PROCESS",
    "QUOTATION_VIEW", "NDA_VIEW", "INVITE_VENDOR", "SEND_RFQ",
    "ONBOARDING_VIEW", "ONBOARDING_PROCESS",
]

# Vendor intake: the procurement onboarding-request flow (ONBOARDING_PROCESS) runs the same
# intake / pre-screen / NDA-decision steps.
INTAKE_READ = VENDOR_READ + ["ONBOARDING_VIEW", "ONBOARDING_PROCESS", "QUOTATION_VIEW"]
INTAKE_WRITE = VENDOR_WRITE + ["ONBOARDING_PROCESS"]

# Purchase orders: procurement owns PO_VIEW / PO_CREATE; vendor management records POs too.
PO_READ = VENDOR_READ + ["PO_VIEW", "PR_VIEW"]
PO_WRITE = VENDOR_WRITE + ["PO_CREATE"]

# Goods receipts are recorded from the vendor's GRN tab.
GRN_READ = VENDOR_READ + ["PO_VIEW"]
GRN_WRITE = VENDOR_WRITE
