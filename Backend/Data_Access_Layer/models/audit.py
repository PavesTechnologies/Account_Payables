from typing import Optional
import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, PrimaryKeyConstraint, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from Backend.Data_Access_Layer.models.base import Base


class AuditLog(Base):
    __tablename__ = 'audit_log'
    __table_args__ = (
        PrimaryKeyConstraint('audit_log_id', name='audit_log_pkey'),
        Index('idx_audit_new_values', 'new_values', postgresql_using='gin'),
        Index('idx_audit_table_record', 'table_name', 'record_id'),
        {'schema': 'ap'}
    )

    audit_log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    changed_by: Mapped[Optional[str]] = mapped_column(String(100))
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB)
