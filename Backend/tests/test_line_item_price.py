"""Textract line items: PRICE is the line total, UNIT_PRICE the rate (quantity > 1 regression)."""
from Backend.API_Layer.utils.invoice_extraction_fields import parse_line_items


def _group(*fields):
    return [{"LineItems": [{"LineItemExpenseFields": [
        {"Type": {"Text": kind}, "ValueDetection": {"Text": text}} for kind, text in fields]}]}]


def test_price_is_the_line_total_and_the_rate_is_derived():
    [line] = parse_line_items(_group(("ITEM", "Additional employee licences"), ("QUANTITY", "20"), ("PRICE", "18,000.00")))
    assert line.quantity == 20 and line.unit_price == 900 and line.line_total == 18000


def test_unit_price_and_price_both_present():
    [line] = parse_line_items(_group(("ITEM", "Licences"), ("QUANTITY", "20"), ("UNIT_PRICE", "900.00"), ("PRICE", "18,000.00")))
    assert line.unit_price == 900 and line.line_total == 18000


def test_price_column_that_is_really_the_rate():
    [line] = parse_line_items(_group(("ITEM", "Desks"), ("QUANTITY", "45"), ("PRICE", "6,000.00"), ("AMOUNT", "2,70,000.00")))
    assert line.unit_price == 6000 and line.line_total == 270000


def test_service_line_without_quantity():
    [line] = parse_line_items(_group(("ITEM", "Landing zone implementation"), ("PRICE", "3,00,000.00")))
    assert line.unit_price == 300000 and line.line_total == 300000 and line.quantity is None
