# Backend/Business_Layer/utils/tax_type_validator.py
import datetime
import decimal
from typing import Optional

VALID_CALCULATION_TYPES = {"PERCENTAGE", "FIXED"}


def validate_calculation_type(
    calculation_type: str,
    rate_percent: Optional[decimal.Decimal],
    fixed_amount: Optional[decimal.Decimal],
) -> str:
    """
    Mirrors the DB check constraint on tax_type: PERCENTAGE requires
    rate_percent, FIXED requires fixed_amount. Validated here too so the
    error surfaces as a clean 422 instead of an IntegrityError.
    """
    normalized = (calculation_type or "").strip().upper()

    if normalized not in VALID_CALCULATION_TYPES:
        raise ValueError(
            f"Invalid calculation_type '{calculation_type}': "
            f"must be one of {sorted(VALID_CALCULATION_TYPES)}"
        )

    if normalized == "PERCENTAGE" and rate_percent is None:
        raise ValueError("rate_percent is required when calculation_type is PERCENTAGE")

    if normalized == "FIXED" and fixed_amount is None:
        raise ValueError("fixed_amount is required when calculation_type is FIXED")

    return normalized


def validate_effective_range(
    effective_from: datetime.date,
    effective_to: Optional[datetime.date],
) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("effective_to cannot be earlier than effective_from")
