import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class DashboardAmountDTO(BaseModel):
    currency_code: Optional[str] = None
    currency_symbol: Optional[str] = None
    amount: str  # decimal as string, 2 dp - never summed across currencies


class DashboardKpiDTO(BaseModel):
    key: str                      # stable identifier for the frontend
    title: str
    type: str                     # "count" | "amount"
    value: Optional[int] = None   # type == count
    amounts: Optional[List[DashboardAmountDTO]] = None  # type == amount, one per currency
    module: str                   # invoice / payment / tds / tds_tracking / procurement / vendor
    permission: str               # permission (or VENDOR_MANAGEMENT role capability) that granted it
    scope: Optional[str] = None   # amount KPIs: "current" (as of now) | "period"
    filter: Optional[dict] = None  # hint for deep-linking to the matching list


class DashboardActionDTO(BaseModel):
    key: str
    title: str
    type: str
    value: int
    permission: str
    priority: str                 # high / medium
    filter: Optional[dict] = None


class DashboardStatusItemDTO(BaseModel):
    status_code: Optional[str] = None
    label: str
    count: int


class DashboardStatusSummaryDTO(BaseModel):
    key: str
    title: str
    module: str
    permission: str
    items: List[DashboardStatusItemDTO]


class DashboardFinancialDTO(BaseModel):
    key: str
    title: str
    scope: str                    # "current" | "period"
    permission: str
    amounts: List[DashboardAmountDTO]


class DashboardTrendPointDTO(BaseModel):
    period: datetime.date         # start of the day / week / month bucket
    value: Any                    # int for count trends, decimal string for amount trends


class DashboardTrendSeriesDTO(BaseModel):
    currency_code: Optional[str] = None
    points: List[DashboardTrendPointDTO]


class DashboardTrendDTO(BaseModel):
    key: str
    title: str
    type: str
    granularity: str              # day / week / month
    permission: str
    series: List[DashboardTrendSeriesDTO]


class DashboardActivityDTO(BaseModel):
    id: int
    action: str
    title: str
    entity_type: str
    entity_id: int
    reference: Optional[str] = None   # invoice number / PR number / vendor name
    actor: Optional[str] = None       # user id, as recorded in the audit log
    occurred_at: datetime.datetime


class DashboardPeriodDTO(BaseModel):
    from_date: datetime.date
    to_date: datetime.date
    granularity: str


class DashboardSummaryDTO(BaseModel):
    generated_at: datetime.datetime
    period: DashboardPeriodDTO
    sections: List[str]           # dashboard sections this user was granted
    kpis: List[DashboardKpiDTO]
    action_required: List[DashboardActionDTO]
    status_summary: List[DashboardStatusSummaryDTO]
    financial_summary: List[DashboardFinancialDTO]
    trends: List[DashboardTrendDTO]
    recent_activity: List[DashboardActivityDTO]
