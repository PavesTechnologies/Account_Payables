from typing import Optional
import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, Integer, PrimaryKeyConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base


class InvoiceApproval(Base):
    __tablename__ = 'invoice_approval'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['ap.invoice.invoice_id'], ondelete='CASCADE', name='invoice_approval_invoice_id_fkey'),
        ForeignKeyConstraint(['invoice_issue_id'], ['ap.invoice_issue.invoice_issue_id'], name='invoice_approval_invoice_issue_id_fkey'),
        PrimaryKeyConstraint('invoice_approval_id', name='invoice_approval_pkey'),
        Index('idx_invoice_approval_invoice', 'invoice_id'),
        {'schema': 'ap'}
    )

    invoice_approval_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_name: Mapped[str] = mapped_column(String(150), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    invoice_issue_id: Mapped[Optional[int]] = mapped_column(Integer)
    comments: Mapped[Optional[str]] = mapped_column(String(500))
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    invoice: Mapped['Invoice'] = relationship('Invoice', back_populates='invoice_approval')
    invoice_issue: Mapped[Optional['InvoiceIssue']] = relationship('InvoiceIssue', back_populates='invoice_approval')
