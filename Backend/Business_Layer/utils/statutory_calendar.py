# Backend/Business_Layer/utils/statutory_calendar.py
"""Statutory TDS deadlines, kept apart from contractual payment terms.

* Deposit: by the 7th of the month after the month of deduction; deductions made in
  March are due by 30 April (non-government deductors).
* Quarterly TDS statement (Indian financial year quarters): Q1 Apr-Jun by 31 Jul,
  Q2 Jul-Sep by 31 Oct, Q3 Oct-Dec by 31 Jan, Q4 Jan-Mar by 31 May.

The day numbers are read from ap.system_configuration when configured
(TDS_DEPOSIT_DUE_DAY, TDS_MARCH_DEPOSIT_DUE_DAY), so a rule change under the
Income-tax Act 2025 is a configuration change, not a release.
"""
from __future__ import annotations

import calendar
import datetime
from typing import Optional, Tuple

DEFAULT_DEPOSIT_DUE_DAY = 7
DEFAULT_MARCH_DEPOSIT_DUE_DAY = 30  # of April
DEPOSIT_DUE_DAY_CONFIG_KEY = "TDS_DEPOSIT_DUE_DAY"
MARCH_DEPOSIT_DUE_DAY_CONFIG_KEY = "TDS_MARCH_DEPOSIT_DUE_DAY"

# quarter -> (month, day) the statement is due, and whether that falls in the next calendar year
_FILING_DUE = {1: (7, 31, 0), 2: (10, 31, 0), 3: (1, 31, 1), 4: (5, 31, 0)}


def _clamp_day(year: int, month: int, day: int) -> datetime.date:
    return datetime.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def tds_deposit_due_date(
    deduction_date: Optional[datetime.date],
    due_day: int = DEFAULT_DEPOSIT_DUE_DAY,
    march_due_day: int = DEFAULT_MARCH_DEPOSIT_DUE_DAY,
) -> Optional[datetime.date]:
    if deduction_date is None:
        return None
    if deduction_date.month == 3:
        return _clamp_day(deduction_date.year, 4, march_due_day)
    year, month = (deduction_date.year + 1, 1) if deduction_date.month == 12 else (deduction_date.year, deduction_date.month + 1)
    return _clamp_day(year, month, due_day)


def financial_quarter(on_date: datetime.date) -> Tuple[str, int]:
    """("2026-27", 2) for 15 Aug 2026 - the Indian FY label and quarter number 1-4."""
    start_year = on_date.year if on_date.month >= 4 else on_date.year - 1
    quarter = ((on_date.month - 4) % 12) // 3 + 1
    return f"{start_year}-{str(start_year + 1)[2:]}", quarter


def tds_statement_due_date(deduction_date: Optional[datetime.date]) -> Optional[datetime.date]:
    if deduction_date is None:
        return None
    fy_label, quarter = financial_quarter(deduction_date)
    start_year = int(fy_label[:4])
    month, day, next_year = _FILING_DUE[quarter]
    year = start_year + 1 if quarter == 4 else start_year + next_year
    return datetime.date(year, month, day)


def configured_deposit_days(db) -> Tuple[int, int]:
    from Backend.Business_Layer.utils.vendor_auto_onboarding import get_numeric_system_config
    from decimal import Decimal

    due = get_numeric_system_config(db, DEPOSIT_DUE_DAY_CONFIG_KEY, Decimal(DEFAULT_DEPOSIT_DUE_DAY))
    march = get_numeric_system_config(db, MARCH_DEPOSIT_DUE_DAY_CONFIG_KEY, Decimal(DEFAULT_MARCH_DEPOSIT_DUE_DAY))
    return int(due if due is not None else DEFAULT_DEPOSIT_DUE_DAY), int(march if march is not None else DEFAULT_MARCH_DEPOSIT_DUE_DAY)
