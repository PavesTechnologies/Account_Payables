# Backend/Business_Layer/services/matching_service.py
"""PO / GRN / Invoice matching (2-way and 3-way).

Read-only and computed on demand from existing rows — nothing here is
persisted, and a matching result never changes invoice.status_id or
creates an InvoiceApproval row on its own. Callers (e.g. the approval
flow) decide what to do with the result; this service only reports it.

2-way match: invoice line vs its linked purchase_order_line (quantity
ordered, unit price).
3-way match: same, plus invoice quantity is also compared against the
quantity actually received (goods_receipt_line.received_quantity summed
across every GRN linked to the PO), not just what was ordered.

GRN_MANDATORY (system_configuration) determines whether the ABSENCE of
any goods receipt for a PO-linked invoice is itself reported as a
problem (GRN_REQUIRED_BUT_MISSING) rather than silently treating a
2-way match as sufficient.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional

from Backend.API_Layer.interface.matching_interface import (
    LineMatchResult,
    LineMatchStatus,
    MatchResult,
    MatchType,
    OverallMatchStatus,
)
from Backend.Data_Access_Layer.dao.goods_receipt_dao import GoodsReceiptDAO
from Backend.Data_Access_Layer.dao.invoice_dao import InvoiceDAO
from Backend.Data_Access_Layer.dao.purchase_order_dao import PurchaseOrderDAO
from Backend.Data_Access_Layer.dao.master_dao import MasterDAO

QUANTITY_VARIANCE_TOLERANCE = Decimal("0.01")
PRICE_VARIANCE_TOLERANCE = Decimal("0.01")

PO_MANDATORY_CONFIG_KEY = "PO_MANDATORY"
GRN_MANDATORY_CONFIG_KEY = "GRN_MANDATORY"


def _config_bool(db, key: str) -> bool:
    config = MasterDAO(db).get_system_config_by_key(key)
    if config is None:
        return False
    return config.config_value.strip().lower() == "true"


class MatchingService:
    def __init__(self, db):
        self.db = db
        self.invoice_dao = InvoiceDAO(db)
        self.po_dao = PurchaseOrderDAO(db)
        self.grn_dao = GoodsReceiptDAO(db)

    def match_invoice(self, invoice_id: int) -> MatchResult:
        invoice = self.invoice_dao.get_invoice_by_id(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")

        po_mandatory = _config_bool(self.db, PO_MANDATORY_CONFIG_KEY)
        grn_mandatory = _config_bool(self.db, GRN_MANDATORY_CONFIG_KEY)

        if invoice.po_id is None:
            messages = ["Invoice has no linked purchase order (NON_PO, or vendor-matched invoice with no PO reference)."]
            if po_mandatory:
                messages.append("PO_MANDATORY is enabled — this invoice should reference a PO.")
            return MatchResult(
                invoice_id=invoice_id,
                po_id=None,
                match_type=MatchType.NONE,
                po_mandatory=po_mandatory,
                grn_mandatory=grn_mandatory,
                overall_status=OverallMatchStatus.NO_PO,
                lines=[],
                messages=messages,
            )

        po = self.po_dao.get_purchase_order_by_id(invoice.po_id)
        if po is None:
            return MatchResult(
                invoice_id=invoice_id,
                po_id=invoice.po_id,
                match_type=MatchType.NONE,
                po_mandatory=po_mandatory,
                grn_mandatory=grn_mandatory,
                overall_status=OverallMatchStatus.INCOMPLETE,
                lines=[],
                messages=[f"Invoice references po_id={invoice.po_id}, but that purchase order no longer exists."],
            )

        po_lines_by_id = {line.po_line_id: line for line in po.purchase_order_line}

        grn_lines = self.grn_dao.get_lines_by_po_id(po.po_id)
        received_by_po_line: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        grn_ids: List[int] = []
        for grn_line in grn_lines:
            if grn_line.grn_id not in grn_ids:
                grn_ids.append(grn_line.grn_id)
            if grn_line.po_line_id is not None:
                received_by_po_line[grn_line.po_line_id] += grn_line.received_quantity

        has_grn = len(grn_ids) > 0
        match_type = MatchType.THREE_WAY if has_grn else MatchType.TWO_WAY

        lines: List[LineMatchResult] = []
        any_linked = False
        for invoice_line in invoice.invoice_line:
            po_line = po_lines_by_id.get(invoice_line.po_line_id) if invoice_line.po_line_id else None

            if po_line is None:
                lines.append(
                    LineMatchResult(
                        invoice_line_id=invoice_line.invoice_line_id,
                        line_number=invoice_line.line_number,
                        description=invoice_line.description,
                        invoiced_quantity=invoice_line.quantity,
                        invoice_unit_price=invoice_line.unit_price,
                        status=LineMatchStatus.NO_PO_LINE_LINKED,
                    )
                )
                continue

            any_linked = True
            received_quantity = received_by_po_line.get(po_line.po_line_id)
            baseline_quantity = received_quantity if has_grn and received_quantity is not None else po_line.quantity

            quantity_variance = invoice_line.quantity - (baseline_quantity if baseline_quantity is not None else po_line.quantity)
            price_variance = invoice_line.unit_price - po_line.unit_price

            has_qty_variance = abs(quantity_variance) > QUANTITY_VARIANCE_TOLERANCE
            has_price_variance = abs(price_variance) > PRICE_VARIANCE_TOLERANCE

            if has_grn and received_quantity is None:
                line_status = LineMatchStatus.NO_GRN_RECEIPT_FOUND
            elif has_qty_variance and has_price_variance:
                line_status = LineMatchStatus.QUANTITY_AND_PRICE_VARIANCE
            elif has_qty_variance:
                line_status = LineMatchStatus.QUANTITY_VARIANCE
            elif has_price_variance:
                line_status = LineMatchStatus.PRICE_VARIANCE
            else:
                line_status = LineMatchStatus.MATCHED

            lines.append(
                LineMatchResult(
                    invoice_line_id=invoice_line.invoice_line_id,
                    line_number=invoice_line.line_number,
                    description=invoice_line.description,
                    po_line_id=po_line.po_line_id,
                    ordered_quantity=po_line.quantity,
                    po_unit_price=po_line.unit_price,
                    received_quantity=received_quantity,
                    invoiced_quantity=invoice_line.quantity,
                    invoice_unit_price=invoice_line.unit_price,
                    quantity_variance=quantity_variance,
                    price_variance=price_variance,
                    status=line_status,
                )
            )

        messages: List[str] = []
        if grn_mandatory and not has_grn:
            overall_status = OverallMatchStatus.GRN_REQUIRED_BUT_MISSING
            messages.append("GRN_MANDATORY is enabled but no goods receipt is linked to this purchase order.")
        elif not any_linked and po.purchase_order_line:
            overall_status = OverallMatchStatus.INCOMPLETE
            messages.append("None of this invoice's lines are linked to a purchase_order_line (invoice_line.po_line_id is not set).")
        elif any(
            line.status in (
                LineMatchStatus.QUANTITY_VARIANCE,
                LineMatchStatus.PRICE_VARIANCE,
                LineMatchStatus.QUANTITY_AND_PRICE_VARIANCE,
                LineMatchStatus.NO_GRN_RECEIPT_FOUND,
            )
            for line in lines
        ):
            overall_status = OverallMatchStatus.VARIANCE_DETECTED
        else:
            overall_status = OverallMatchStatus.MATCHED

        return MatchResult(
            invoice_id=invoice_id,
            po_id=po.po_id,
            po_number=po.po_number,
            grn_ids=grn_ids,
            match_type=match_type,
            po_mandatory=po_mandatory,
            grn_mandatory=grn_mandatory,
            overall_status=overall_status,
            lines=lines,
            messages=messages,
        )
