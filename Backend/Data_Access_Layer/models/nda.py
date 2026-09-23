# Backend/Data_Access_Layer/models/nda.py
"""NDA template and per-vendor NDA document lifecycle.

Status lives in ``ap.status_master`` under module ``NDA`` and is referenced by
``vendor_nda.nda_status_id`` -> ``status_master.status_id`` (the real primary
key; there is no ``status_master.id``). There is deliberately no NDA status
table and no free-text status column - status is resolved by
(module_name, status_code) exactly like every other module in this app.

Only the S3 object KEY is stored here (``document_key`` /
``signed_document_key``). The PDF bytes live in the private S3 bucket and are
never persisted to Postgres, and no public URL is ever stored or returned -
access goes through a short-lived presigned URL issued to an authorized user.

``vendor_nda.content`` is the one exception and holds TEXT, not a document:
it is the editable NDA wording (the internal working copy) that the final
vendor document is rendered from at send time. It never holds signed content.
"""
from typing import Optional, TYPE_CHECKING
import datetime

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKeyConstraint, Index, Integer,
    PrimaryKeyConstraint, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Backend.Data_Access_Layer.models.base import Base

if TYPE_CHECKING:
    from Backend.Data_Access_Layer.models.master import StatusMaster
    from Backend.Data_Access_Layer.models.purchase import (
        Department,
        PurchaseCategory,
        PurchaseRequisition,
    )
    from Backend.Data_Access_Layer.models.vendor import Vendor


class NdaTemplate(Base):
    """Approved NDA wording. The body is stored verbatim and only supported
    placeholders are substituted at generation time - no clause is ever
    generated dynamically. ``version`` is copied onto every NDA produced from
    the template so an issued document can always be traced back to the exact
    wording it was built from, even after the template is revised."""

    __tablename__ = 'nda_template'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='nda_template_pkey'),
        UniqueConstraint('code', name='nda_template_code_key'),
        {'schema': 'ap'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))


class VendorNda(Base):
    __tablename__ = 'vendor_nda'
    __table_args__ = (
        ForeignKeyConstraint(['vendor_id'], ['ap.vendor.vendor_id'], name='fk_vendor_nda_vendor'),
        ForeignKeyConstraint(['pr_id'], ['ap.purchase_requisition.id'], name='fk_vendor_nda_pr'),
        ForeignKeyConstraint(['department_id'], ['ap.department.id'], name='fk_vendor_nda_department'),
        ForeignKeyConstraint(['purchase_category_id'], ['ap.purchase_category.id'], name='fk_vendor_nda_category'),
        ForeignKeyConstraint(['nda_status_id'], ['ap.status_master.status_id'], name='fk_vendor_nda_status'),
        ForeignKeyConstraint(['template_id'], ['ap.nda_template.id'], name='fk_vendor_nda_template'),
        PrimaryKeyConstraint('nda_id', name='vendor_nda_pkey'),
        Index('idx_vendor_nda_vendor', 'vendor_id'),
        Index('idx_vendor_nda_status', 'nda_status_id'),
        Index('idx_vendor_nda_scope', 'vendor_id', 'department_id', 'purchase_category_id'),
        Index('idx_vendor_nda_pr', 'pr_id'),
        {'schema': 'ap'}
    )

    nda_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vendor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nda_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    nda_status_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    pr_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    department_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    purchase_category_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    template_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    template_version: Mapped[Optional[str]] = mapped_column(String(20))
    # S3 object keys only - never a URL, never the PDF bytes.
    document_key: Mapped[Optional[str]] = mapped_column(String(500))
    signed_document_key: Mapped[Optional[str]] = mapped_column(String(500))
    # Latest editable NDA text. This is the INTERNAL working copy the user
    # edits before the NDA is sent - it is deliberately NOT the vendor-signed
    # document, which lives in S3 behind signed_document_key and is never
    # written here. ``content`` is seeded at generation time with the rendered
    # template body and is the source of truth the final document is built
    # from when the NDA is sent.
    content: Mapped[Optional[str]] = mapped_column(Text)
    # Revision counter for optimistic concurrency: a client that supplies a
    # stale version is rejected instead of silently overwriting a newer edit.
    content_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text('1')
    )
    content_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    content_updated_by: Mapped[Optional[str]] = mapped_column(String(100))
    recipient_email: Mapped[Optional[str]] = mapped_column(String(150))
    valid_from: Mapped[Optional[datetime.date]] = mapped_column(Date)
    valid_until: Mapped[Optional[datetime.date]] = mapped_column(Date)
    sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    signed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    vendor: Mapped['Vendor'] = relationship('Vendor')
    pr: Mapped[Optional['PurchaseRequisition']] = relationship('PurchaseRequisition')
    department: Mapped[Optional['Department']] = relationship('Department')
    purchase_category: Mapped[Optional['PurchaseCategory']] = relationship('PurchaseCategory')
    status: Mapped['StatusMaster'] = relationship('StatusMaster')
    template: Mapped[Optional['NdaTemplate']] = relationship('NdaTemplate')
