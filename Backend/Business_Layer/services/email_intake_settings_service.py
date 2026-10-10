# Backend/Business_Layer/services/email_intake_settings_service.py
"""On/off switch and last-run status for email invoice intake (Phase 3b).

Stored in ap.system_configuration so it can be flipped from the UI without touching .env or the
scheduler: the runner checks EMAIL_INTAKE_ENABLED at the start of every run and does nothing while
it is off. A missing row means OFF. Every change is written to audit_log.
"""
import datetime
import json
from typing import Any, Dict, Optional

from Backend.Data_Access_Layer.dao.master_dao import MasterDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.master import SystemConfiguration
from Backend.config.env_loader import get_env_var

KEY_ENABLED = "EMAIL_INTAKE_ENABLED"
KEY_LAST_RUN = "EMAIL_INTAKE_LAST_RUN"
EMAIL_INTAKE_MANAGE = "EMAIL_INTAKE_MANAGE"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class EmailIntakeSettingsService:
    def __init__(self, db):
        self.db = db
        self.dao = MasterDAO(db)

    def _row(self, key: str) -> Optional[SystemConfiguration]:
        return self.dao.get_system_config_by_key(key)

    def _upsert(self, key: str, value: str, data_type: str, description: str, user_id: Optional[str]) -> SystemConfiguration:
        row = self._row(key)
        if row is None:
            row = SystemConfiguration(config_key=key, config_value=value, data_type=data_type, description=description)
            self.db.add(row)
        row.config_value = value
        row.updated_by = user_id
        row.updated_at = _now().replace(tzinfo=None)  # column is timestamp without time zone
        return row

    # ------------------------------------------------------------------
    def is_enabled(self) -> bool:
        row = self._row(KEY_ENABLED)
        return row is not None and (row.config_value or "").strip().lower() == "true"

    def set_enabled(self, enabled: bool, user_id: str, user_name: Optional[str] = None) -> Dict[str, Any]:
        """updated_by shows the person's name on the card; audit_log keeps the user id."""
        before = self.is_enabled()
        self._upsert(KEY_ENABLED, "true" if enabled else "false", "BOOLEAN",
                     "Email invoice intake from the AP mailbox (on/off)", (user_name or user_id)[:100])
        if before != enabled:
            self.db.add(AuditLog(table_name="system_configuration", record_id=0,
                                 action="EMAIL_INTAKE_ENABLED" if enabled else "EMAIL_INTAKE_DISABLED",
                                 changed_by=str(user_id), old_values={KEY_ENABLED: before},
                                 new_values={KEY_ENABLED: enabled}))
        self.db.commit()
        return self.status()

    def record_run(self, summary: Dict[str, Any]) -> None:
        """Last run, kept small enough for the 255-char config_value column. Caller commits."""
        payload = {"at": _now().isoformat(timespec="seconds"), **summary}
        text_value = json.dumps(payload, separators=(",", ":"))
        if len(text_value) > 255:
            text_value = json.dumps({k: payload[k] for k in ("at", "status") if k in payload}, separators=(",", ":"))
        self._upsert(KEY_LAST_RUN, text_value, "JSON", "Last email intake run (written by the runner)", "EMAIL_INTAKE")

    def status(self, can_manage: bool = False) -> Dict[str, Any]:
        enabled_row = self._row(KEY_ENABLED)
        last_row = self._row(KEY_LAST_RUN)
        try:
            last_run = json.loads(last_row.config_value) if last_row else None
        except ValueError:
            last_run = None
        senders = [s.strip() for s in (get_env_var("VENDOR_EMAIL", "") or "").split(",") if s.strip()]
        return {
            "enabled": self.is_enabled(),
            "updated_by": enabled_row.updated_by if enabled_row else None,
            "updated_at": enabled_row.updated_at if enabled_row else None,
            "mailbox": get_env_var("MAIL_ADDRESS", "") or None,
            "sender_filter": senders,
            "start_date": get_env_var("EMAIL_INTAKE_START_DATE", "") or None,
            "interval_minutes": int(get_env_var("EMAIL_INTAKE_INTERVAL_MINUTES", "15")),
            "last_run": last_run,
            "can_manage": can_manage,
        }
