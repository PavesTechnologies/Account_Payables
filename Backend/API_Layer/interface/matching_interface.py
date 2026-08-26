# Backend/API_Layer/interface/matching_interface.py
"""Typed contract for PO/GRN/Invoice matching (2-way and 3-way).

Read-only, computed on demand from existing invoice/purchase_order/
goods_receipt/*_line rows — nothing here is persisted. See
Business_Layer/services/matching_service.py for the actual comparison
logic.
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class MatchType(str, Enum):
    NONE = "NONE"          # invoice has no po_id at all (NON_PO invoice)
    TWO_WAY = "TWO_WAY"     # PO <-> Invoice only (no GRN involved)
    THREE_WAY = "THREE_WAY"  # PO <-> GRN <-> Invoice


class LineMatchStatus(str, Enum):
    MATCHED = "MATCHED"
    QUANTITY_VARIANCE = "QUANTITY_VARIANCE"
    PRICE_VARIANCE = "PRICE_VARIANCE"
    QUANTITY_AND_PRICE_VARIANCE = "QUANTITY_AND_PRICE_VARIANCE"
    NO_PO_LINE_LINKED = "NO_PO_LINE_LINKED"
    NO_GRN_RECEIPT_FOUND = "NO_GRN_RECEIPT_FOUND"


class OverallMatchStatus(str, Enum):
    NO_PO = "NO_PO"                                # NON_PO invoice, nothing to match
    MATCHED = "MATCHED"                            # every line matched within tolerance
    VARIANCE_DETECTED = "VARIANCE_DETECTED"         # at least one line has qty/price variance
    GRN_REQUIRED_BUT_MISSING = "GRN_REQUIRED_BUT_MISSING"  # GRN_MANDATORY=true but no GRN found
    INCOMPLETE = "INCOMPLETE"                       # PO exists but lines can't be resolved


class LineMatchResult(BaseModel):
    invoice_line_id: Optional[int] = None
    line_number: Optional[int] = None
    description: Optional[str] = None
    po_line_id: Optional[int] = None
    ordered_quantity: Optional[Decimal] = None
    po_unit_price: Optional[Decimal] = None
    received_quantity: Optional[Decimal] = None
    invoiced_quantity: Optional[Decimal] = None
    invoice_unit_price: Optional[Decimal] = None
    quantity_variance: Optional[Decimal] = None
    price_variance: Optional[Decimal] = None
    status: LineMatchStatus


class MatchResult(BaseModel):
    invoice_id: int
    po_id: Optional[int] = None
    po_number: Optional[str] = None
    grn_ids: List[int] = Field(default_factory=list)
    match_type: MatchType
    po_mandatory: bool
    grn_mandatory: bool
    overall_status: OverallMatchStatus
    lines: List[LineMatchResult] = Field(default_factory=list)
    messages: List[str] = Field(default_factory=list)
