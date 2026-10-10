# Backend/Business_Layer/services/ap_automation_settings_service.py
"""Touchless PO-invoice automation settings (APM_AUTOMATION_PLAN.md Step B), managed by the
Finance Manager (AP_AUTOMATION_MANAGE). Stored in ap.system_configuration; a missing row falls
back to the default below, so nothing needs seeding and automation is OFF until switched on.
Every change is written to audit_log."""
import datetime
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import SystemConfiguration

AP_AUTOMATION_MANAGE = "AP_AUTOMATION_MANAGE"

# key -> (attribute, data_type, default, description)
_KEYS = {
    "AP_AUTOMATION_ENABLED": ("enabled", "BOOLEAN", "false", "Touchless PO invoices: link PO, match, review and send automatically"),
    "AP_MATCH_PRICE_TOLERANCE_PCT": ("price_tolerance_pct", "NUMBER", "1", "Unit-price tolerance, % of PO price"),
    "AP_MATCH_PRICE_TOLERANCE_AMOUNT": ("price_tolerance_amount", "NUMBER", "100", "Unit-price tolerance, amount (lower of % and amount applies)"),
    "AP_MATCH_QTY_TOLERANCE": ("quantity_tolerance", "NUMBER", "0", "Quantity tolerance (units)"),
    "AP_AUTO_REQUIRE_GRN": ("require_grn", "BOOLEAN", "true", "Require a goods receipt (3-way match)"),
    "AP_AUTO_APPROVE_MAX_AMOUNT": ("auto_approve_max_amount", "NUMBER", "0", "Auto-approve matched PO invoices up to this net amount (0 = never)"),
}
_LIMITS = {
    "price_tolerance_pct": (Decimal("0"), Decimal("10")),
    "price_tolerance_amount": (Decimal("0"), Decimal("100000")),
    "quantity_tolerance": (Decimal("0"), Decimal("1000")),
    "auto_approve_max_amount": (Decimal("0"), Decimal("100000000")),
}


@dataclass
class AutomationSettings:
    enabled: bool = False
    price_tolerance_pct: Decimal = Decimal("1")
    price_tolerance_amount: Decimal = Decimal("100")
    quantity_tolerance: Decimal = Decimal("0")
    require_grn: bool = True
    auto_approve_max_amount: Decimal = Decimal("0")

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse(data_type: str, value: str, default: str):
    raw = (value if value is not None else default).strip()
    if data_type == "BOOLEAN":
        return raw.lower() == "true"
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal(default)  # a malformed row never loosens a control: fall back to the default


class APAutomationSettingsService:
    def __init__(self, db):
        self.db = db
        self.dao = MasterDAO(db)

    def get(self) -> AutomationSettings:
        values = {}
        for key, (attr, data_type, default, _) in _KEYS.items():
            row = self.dao.get_system_config_by_key(key)
            values[attr] = _parse(data_type, row.config_value if row else None, default)
        return AutomationSettings(**values)

    def last_change(self) -> Dict[str, Any]:
        rows = [self.dao.get_system_config_by_key(k) for k in _KEYS]
        rows = [r for r in rows if r is not None and r.updated_at is not None]
        latest = max(rows, key=lambda r: r.updated_at, default=None)
        return {"updated_by": latest.updated_by if latest else None, "updated_at": latest.updated_at if latest else None}

    def update(self, changes: Dict[str, Any], user_id: str, user_name: Optional[str] = None) -> AutomationSettings:
        before = self.get()
        after = AutomationSettings(**{**before.as_dict(), **{k: v for k, v in changes.items() if v is not None}})
        for attr, (low, high) in _LIMITS.items():
            value = Decimal(str(getattr(after, attr)))
            if value < low or value > high:
                raise ValueError(f"{attr.replace('_', ' ')} must be between {low} and {high}")
            setattr(after, attr, value)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        diff_old, diff_new = {}, {}
        for key, (attr, data_type, _default, description) in _KEYS.items():
            old, new = getattr(before, attr), getattr(after, attr)
            if old == new:
                continue
            row = self.dao.get_system_config_by_key(key)
            if row is None:
                row = SystemConfiguration(config_key=key, config_value="", data_type=data_type, description=description)
                self.db.add(row)
            row.config_value = ("true" if new else "false") if data_type == "BOOLEAN" else str(new)
            row.updated_by = (user_name or user_id)[:100]
            row.updated_at = now
            diff_old[attr], diff_new[attr] = str(old), str(new)
        if diff_new:
            self.db.add(AuditLog(table_name="system_configuration", record_id=0, action="AP_AUTOMATION_SETTINGS_CHANGED",
                                 changed_by=str(user_id), old_values=diff_old, new_values=diff_new))
        self.db.commit()
        return after
