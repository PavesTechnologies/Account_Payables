import datetime
import decimal
from typing import Any, List, Optional

from pydantic import BaseModel


class RecordTdsDeductionRequest(BaseModel):
    deduction_date: datetime.date
    remarks: Optional[str] = None


class RecordTdsDepositRequest(BaseModel):
    challan_number: str
    deposit_date: datetime.date        # TDS payment (challan) date
    bsr_code: Optional[str] = None     # 7 digits
    remarks: Optional[str] = None


class RecordTdsFilingRequest(BaseModel):
    filing_date: datetime.date
    filing_reference: str              # e.g. return acknowledgement number
    remarks: Optional[str] = None


class TdsNatureRefDTO(BaseModel):
    id: int
    code: str
    name: str


class TdsTrackingRowDTO(BaseModel):
    invoice_id: int
    invoice_number: str
    vendor_id: int
    vendor_name: str
    invoice_date: datetime.date
    currency_code: Optional[str] = None
    currency_symbol: Optional[str] = None
    invoice_status_code: Optional[str] = None   # payment lifecycle - independent of TDS status
    invoice_status_name: Optional[str] = None
    payment_nature: Optional[TdsNatureRefDTO] = None
    rule_code: Optional[str] = None
    old_section: Optional[str] = None
    new_section: Optional[str] = None
    invoice_amount: decimal.Decimal
    taxable_base: Optional[decimal.Decimal] = None
    tds_rate: Optional[decimal.Decimal] = None
    tds_amount: decimal.Decimal
    net_payable: decimal.Decimal
    determination_status: str                   # PENDING / DETERMINED / VERIFIED
    tds_tracking_status: str                    # TDS_PENDING / TDS_DEDUCTED / TDS_DEPOSITED / TDS_FILED
    tds_tracking_status_label: str
    deduction_date: Optional[datetime.date] = None
    deposit_date: Optional[datetime.date] = None
    challan_number: Optional[str] = None
    filing_date: Optional[datetime.date] = None
    filing_reference: Optional[str] = None
    allowed_actions: List[str] = []             # RECORD_DEDUCTION / RECORD_DEPOSIT / RECORD_FILING


class TdsTrackingPageDTO(BaseModel):
    items: List[TdsTrackingRowDTO]
    total: int
    page: int
    page_size: int


class TdsDeterminationInfoDTO(BaseModel):
    tds_applicable: bool
    determination_status: str
    determination_reason: Optional[str] = None
    threshold_amount: Optional[decimal.Decimal] = None
    threshold_type: Optional[str] = None
    pan_status: Optional[str] = None
    entity_type: Optional[str] = None
    rule_name: Optional[str] = None
    rule_snapshot: Optional[dict] = None
    determined_at: Optional[datetime.datetime] = None
    determined_by: Optional[str] = None
    verified_at: Optional[datetime.datetime] = None
    verified_by: Optional[str] = None


class TdsInvoicePaymentInfoDTO(BaseModel):
    status_code: Optional[str] = None
    status_name: Optional[str] = None
    net_payable: decimal.Decimal
    amount_paid: decimal.Decimal
    pending_amount: decimal.Decimal
    remaining_amount: decimal.Decimal
    last_payment_date: Optional[datetime.date] = None
    payment_count: int


class TdsTrackingInfoDTO(BaseModel):
    tracking_status: str
    deduction_date: Optional[datetime.date] = None
    challan_number: Optional[str] = None
    bsr_code: Optional[str] = None
    deposit_date: Optional[datetime.date] = None
    filing_date: Optional[datetime.date] = None
    filing_reference: Optional[str] = None
    remarks: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None


class TdsDocumentDTO(BaseModel):
    id: int
    document_type: str
    file_name: str
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_by: Optional[str] = None
    uploaded_at: datetime.datetime


class TdsActivityDTO(BaseModel):
    action: str
    changed_at: datetime.datetime
    changed_by: Optional[str] = None
    old_values: Optional[Any] = None
    new_values: Optional[Any] = None


class TdsTrackingDetailDTO(TdsTrackingRowDTO):
    determination: TdsDeterminationInfoDTO
    payment: TdsInvoicePaymentInfoDTO
    tracking: TdsTrackingInfoDTO
    documents: List[TdsDocumentDTO] = []
    activity: List[TdsActivityDTO] = []


class TdsOptionDTO(BaseModel):
    value: str
    label: str


class TdsStatusOptionDTO(TdsOptionDTO):
    order: int


class TdsActionOptionDTO(TdsOptionDTO):
    results_in: str


class TdsTrackingMetadataDTO(BaseModel):
    tracking_statuses: List[TdsStatusOptionDTO]
    actions: List[TdsActionOptionDTO]
    document_types: List[TdsOptionDTO]
    allowed_file_extensions: List[str]
    max_file_size_bytes: int
