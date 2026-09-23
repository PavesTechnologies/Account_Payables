# Backend/Business_Layer/services/nda_service.py
"""NDA document lifecycle: requirement -> reuse-or-generate -> S3 -> email.

Reuses existing infrastructure throughout and re-implements none of it:
the NDA *requirement* comes from VendorEngagement (set by the existing
VendorScreeningRule engine during Pre-Screen), status comes from
ap.status_master via (module_name='NDA', status_code) - never a hardcoded id -
email goes through Business_Layer.utils.email_service, and storage goes
through API_Layer.utils.s3_utils.

``s3_utils`` is imported lazily inside the methods that need it. It imports
boto3 and reads AWS_* at module scope, so a top-level import here would make
this service - and every test touching it - uncollectable in an environment
without boto3/AWS configured. Same lazy-import approach the codebase already
uses in Business_Layer/utils/notifications.py.

Send semantics mirror RFQService.send_rfq exactly: the attempt is audited
whether it succeeds or fails, and the NDA only moves to SENT after the email
actually succeeds - a failed send leaves the NDA in its prior state with an
NDA_SEND_FAILED audit row.

EDITABLE CONTENT
----------------
``vendor_nda.content`` holds the internal working copy of the NDA wording.
Generation seeds it with the rendered template body at revision 1; the editor
saves over it through ``update_content``; and ``send_nda`` builds the document
the vendor actually receives FROM IT, so a saved edit can never be silently
dropped in favour of the original generated PDF. It is never the
vendor-signed document - that stays in S3 behind ``signed_document_key``.
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import List, Optional

from Backend.Business_Layer.utils.email_service import EmailAttachment, EmailSendResult, send_email
from Backend.Business_Layer.utils.nda_document import (
    build_nda_context,
    build_nda_document_title,
    build_nda_object_key,
    build_nda_pdf,
    normalize_nda_content,
    render_template_body,
)
from Backend.Data_Access_Layer.dao.nda_dao import NdaDAO
from Backend.Data_Access_Layer.models.audit import AuditLog
from Backend.Data_Access_Layer.models.nda import VendorNda
from Backend.config.env_loader import get_env_var

logger = logging.getLogger(__name__)

NDA_STATUS_MODULE = "NDA"
NDA_HISTORY_TABLE = "vendor_nda"
VENDOR_HISTORY_TABLE = "vendor"

STATUS_NOT_REQUIRED = "NOT_REQUIRED"
STATUS_PENDING = "PENDING"
STATUS_SENT = "SENT"
STATUS_SIGNED = "SIGNED"
STATUS_COMPLETED = "COMPLETED"
STATUS_REJECTED = "REJECTED"
STATUS_EXPIRED = "EXPIRED"

NDA_TRANSITIONS = {
    STATUS_NOT_REQUIRED: set(),
    STATUS_PENDING: {STATUS_SENT, STATUS_REJECTED, STATUS_EXPIRED},
    STATUS_SENT: {STATUS_SIGNED, STATUS_COMPLETED, STATUS_REJECTED, STATUS_EXPIRED},
    STATUS_SIGNED: {STATUS_COMPLETED, STATUS_REJECTED, STATUS_EXPIRED},
    STATUS_COMPLETED: {STATUS_EXPIRED},
    # REJECTED means "requires correction/resubmission", so a corrected signed
    # document may be uploaded against it - but it can never jump straight to
    # COMPLETED without that resubmission.
    STATUS_REJECTED: {STATUS_SIGNED},
    STATUS_EXPIRED: set(),
}

# States from which a vendor-signed document may be uploaded.
SIGNED_UPLOAD_ALLOWED_FROM = {STATUS_SENT, STATUS_SIGNED, STATUS_REJECTED}

# States in which the editable NDA wording may still be changed.
#
# PENDING is the normal editing window (generate -> edit -> save -> send).
# SENT is included so a draft can keep being corrected while the vendor's
# response is outstanding. REJECTED is included because the existing workflow
# treats it as "requires correction/resubmission".
#
# Everything else is deliberately closed: NOT_REQUIRED has no document to
# edit, SIGNED and COMPLETED have a countersigned document whose wording must
# not be rewritten after the fact, and EXPIRED follows the existing
# "generate a new NDA" route rather than being edited back to life. No
# reopening rule exists anywhere in this workflow, so COMPLETED stays closed.
CONTENT_EDIT_ALLOWED_FROM = {STATUS_PENDING, STATUS_SENT, STATUS_REJECTED}

_CONTENT_EDIT_REJECTION_REASONS = {
    STATUS_NOT_REQUIRED: "An NDA is not required for this vendor engagement",
    STATUS_SIGNED: "This NDA has already been signed and its content can no longer be edited",
    STATUS_COMPLETED: "This NDA is already completed and its content can no longer be edited",
    STATUS_EXPIRED: "This NDA has expired; generate a new NDA instead of editing it",
}

_SIGNED_UPLOAD_REJECTION_REASONS = {
    STATUS_NOT_REQUIRED: "An NDA is not required for this vendor engagement",
    STATUS_PENDING: "The NDA has not been sent to the vendor yet",
    STATUS_COMPLETED: "This NDA is already completed",
    STATUS_EXPIRED: "This NDA has expired and cannot accept a signed document",
}

# Existing-NDA lookup outcomes
LOOKUP_VALID = "VALID"
LOOKUP_NOT_FOUND = "NOT_FOUND"
LOOKUP_INVALID = "INVALID"
LOOKUP_EXPIRED = "EXPIRED"

CONFIG_SIGNED_IS_FINAL = "NDA_SIGNED_IS_FINAL"
CONFIG_VALIDITY_MONTHS = "NDA_VALIDITY_MONTHS"
CONFIG_TEMPLATE_CODE = "NDA_TEMPLATE_CODE"

DEFAULT_VALIDITY_MONTHS = 24
DEFAULT_TEMPLATE_CODE = "STANDARD_NDA"

ACTION_REQUIREMENT_DECIDED = "NDA_REQUIREMENT_DECIDED"
ACTION_EXISTING_CHECKED = "NDA_EXISTING_CHECKED"
ACTION_REUSED = "NDA_REUSED"
ACTION_GENERATED = "NDA_GENERATED"
ACTION_UPLOADED = "NDA_UPLOADED"
ACTION_SEND_ATTEMPTED = "NDA_SEND_ATTEMPTED"
ACTION_SENT = "NDA_SENT"
ACTION_SEND_FAILED = "NDA_SEND_FAILED"
ACTION_SIGNED = "NDA_SIGNED"
ACTION_SIGNED_UPLOADED = "NDA_SIGNED_DOCUMENT_UPLOADED"
ACTION_COMPLETED = "NDA_COMPLETED"
ACTION_REJECTED = "NDA_REJECTED"
ACTION_EXPIRED = "NDA_EXPIRED"
ACTION_DOCUMENT_ACCESSED = "NDA_DOCUMENT_ACCESSED"
ACTION_CONTENT_UPDATED = "NDA_CONTENT_UPDATED"

_STATUS_ACTIONS = {
    STATUS_SIGNED: ACTION_SIGNED,
    STATUS_COMPLETED: ACTION_COMPLETED,
    STATUS_REJECTED: ACTION_REJECTED,
    STATUS_EXPIRED: ACTION_EXPIRED,
    STATUS_SENT: ACTION_SENT,
}


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _add_months(start: datetime.date, months: int) -> datetime.date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp to the last valid day of the target month (e.g. 31 Jan + 1 month).
    day = min(start.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return datetime.date(year, month, day)


class NdaContentConflict(ValueError):
    """Raised when a content save carries a stale ``content_version``.

    Subclasses ValueError so the existing ``except ValueError`` handlers in
    the routes still degrade safely if one is ever reached first; the content
    route catches this type explicitly and answers 409 instead of 422.
    """

    def __init__(self, message: str, current_version: int):
        super().__init__(message)
        self.current_version = current_version


@dataclass
class NdaLookupResult:
    outcome: str
    nda: Optional[VendorNda] = None
    reason: Optional[str] = None


@dataclass
class NdaGenerationResult:
    nda: VendorNda
    reused: bool
    required: bool


class NdaService:
    def __init__(self, db):
        self.db = db
        self.nda_dao = NdaDAO(db)

    # =========================================================
    # Existing NDA check / reuse
    # =========================================================

    def check_existing_nda(
        self,
        vendor_id: int,
        department_id: Optional[int],
        purchase_category_id: Optional[int],
        as_of: Optional[datetime.date] = None,
    ) -> NdaLookupResult:
        """Find a reusable NDA for this vendor and scope.

        Only a COMPLETED NDA still inside its validity window counts. A NULL
        department/category on the NDA means company-wide scope and therefore
        applies; an NDA scoped to a different department/category is never
        considered (the DAO filters those out).
        """

        today = as_of or datetime.date.today()
        candidates = self.nda_dao.get_ndas_in_scope(
            vendor_id, department_id, purchase_category_id
        )

        if not candidates:
            return NdaLookupResult(LOOKUP_NOT_FOUND, None, "No NDA on file for this vendor and scope.")

        saw_expired = False
        for nda in candidates:
            status_code = self._status_code(nda)
            if status_code != STATUS_COMPLETED:
                continue
            if nda.valid_until is not None and nda.valid_until < today:
                saw_expired = True
                continue
            if nda.valid_from is not None and nda.valid_from > today:
                continue
            return NdaLookupResult(LOOKUP_VALID, nda)

        if saw_expired:
            return NdaLookupResult(LOOKUP_EXPIRED, candidates[0], "The vendor's NDA has expired.")

        return NdaLookupResult(
            LOOKUP_INVALID, candidates[0], "The vendor's NDA is not completed."
        )

    # =========================================================
    # Generation
    # =========================================================

    def generate_nda(
        self,
        vendor_id: int,
        user_id: str,
        pr_id: Optional[int] = None,
        department_id: Optional[int] = None,
        purchase_category_id: Optional[int] = None,
        template_code: Optional[str] = None,
        recipient_email: Optional[str] = None,
    ) -> NdaGenerationResult:

        vendor = self.nda_dao.get_vendor_by_id(vendor_id)
        if vendor is None:
            raise ValueError("Vendor not found")

        pr = self.nda_dao.get_pr_by_id(pr_id) if pr_id is not None else None
        if pr_id is not None and pr is None:
            raise ValueError("Purchase requisition not found")

        # PR context wins when available, so the NDA scope always matches the
        # engagement the requirement was decided against.
        if pr is not None:
            department_id = department_id or pr.department_id
            purchase_category_id = purchase_category_id or pr.purchase_category_id

        engagement = None
        if department_id is not None and purchase_category_id is not None:
            engagement = self.nda_dao.get_engagement(
                vendor_id, department_id, purchase_category_id
            )

        required = self._is_nda_required(engagement)
        # Recorded on the vendor's timeline: this decision is made before any
        # NDA row exists, so there is no nda_id to hang it on.
        self._record_vendor_history(
            vendor_id, ACTION_REQUIREMENT_DECIDED, user_id,
            {
                "pr_id": pr_id,
                "department_id": department_id, "purchase_category_id": purchase_category_id,
                "nda_required": required,
            },
        )

        if not required:
            nda = self._create_nda_row(
                vendor_id=vendor_id, pr_id=pr_id, department_id=department_id,
                purchase_category_id=purchase_category_id, required=False,
                status_code=STATUS_NOT_REQUIRED, user_id=user_id,
                recipient_email=recipient_email or vendor.email,
            )
            self.db.commit()
            self.db.refresh(nda)
            return NdaGenerationResult(nda=nda, reused=False, required=False)

        lookup = self.check_existing_nda(vendor_id, department_id, purchase_category_id)
        if lookup.nda is not None:
            self._record_history(
                lookup.nda.nda_id, ACTION_EXISTING_CHECKED, user_id,
                {"vendor_id": vendor_id, "outcome": lookup.outcome},
            )
        else:
            self._record_vendor_history(
                vendor_id, ACTION_EXISTING_CHECKED, user_id, {"outcome": lookup.outcome}
            )

        if lookup.outcome == LOOKUP_VALID and lookup.nda is not None:
            self._record_history(
                lookup.nda.nda_id, ACTION_REUSED, user_id,
                {"vendor_id": vendor_id, "valid_until": str(lookup.nda.valid_until)},
            )
            self.db.commit()
            return NdaGenerationResult(nda=lookup.nda, reused=True, required=True)

        return NdaGenerationResult(
            nda=self._generate_new_nda(
                vendor=vendor, pr=pr, department_id=department_id,
                purchase_category_id=purchase_category_id, engagement=engagement,
                template_code=template_code, recipient_email=recipient_email, user_id=user_id,
            ),
            reused=False,
            required=True,
        )

    def _generate_new_nda(
        self, vendor, pr, department_id, purchase_category_id, engagement,
        template_code, recipient_email, user_id,
    ) -> VendorNda:

        template = self._resolve_template(template_code)

        department_name = None
        purchase_category_name = None
        if engagement is not None:
            department_name = getattr(getattr(engagement, "department", None), "name", None)
            purchase_category_name = getattr(
                getattr(engagement, "purchase_category", None), "name", None
            )

        context = build_nda_context(
            vendor_name=vendor.vendor_name,
            vendor_code=vendor.vendor_code,
            pr_number=getattr(pr, "pr_number", None),
            department_name=department_name,
            purchase_category_name=purchase_category_name,
            business_requirement=getattr(engagement, "business_requirement", None),
            company_name=self._company_name(),
            effective_date=datetime.date.today(),
        )

        # The rendered template body is the INITIAL revision of the editable
        # content. The user may edit it before the NDA is sent; send_nda
        # rebuilds the vendor's document from whatever is persisted then.
        body = render_template_body(template.body, context)

        stored_key, _pdf_bytes = self._render_and_store_document(
            content=body,
            vendor_name=vendor.vendor_name,
            vendor_code=vendor.vendor_code,
            pr_number=getattr(pr, "pr_number", None),
            version=template.version,
        )

        nda = self._create_nda_row(
            vendor_id=vendor.vendor_id,
            pr_id=getattr(pr, "id", None),
            department_id=department_id,
            purchase_category_id=purchase_category_id,
            required=True,
            status_code=STATUS_PENDING,
            user_id=user_id,
            recipient_email=recipient_email or vendor.email,
            template=template,
            document_key=stored_key,
            content=body,
        )

        self._record_history(
            nda.nda_id, ACTION_GENERATED, user_id,
            {
                "vendor_id": vendor.vendor_id, "template_code": template.code,
                "template_version": template.version,
                "content_version": nda.content_version,
            },
        )
        self._record_history(
            nda.nda_id, ACTION_UPLOADED, user_id, {"document_key": stored_key}
        )

        self.db.commit()
        self.db.refresh(nda)
        return nda

    # =========================================================
    # Document generation (shared by generate and send)
    # =========================================================

    def build_final_document(
        self,
        content: str,
        vendor_name: Optional[str],
        vendor_code: Optional[str],
        pr_number: Optional[str],
        version: Optional[str],
    ) -> tuple[str, bytes]:
        """Render NDA wording into the final document. -> (object_key, bytes)

        The single document-generation entry point for this module: initial
        generation renders the template body through it, and send renders the
        user's persisted edits through it. Same renderer, same S3 key
        convention, so the sent document is laid out exactly like the one
        reviewed on screen. Nothing is uploaded here.
        """

        clean_content = normalize_nda_content(content)

        pdf_bytes = build_nda_pdf(
            title=build_nda_document_title(vendor_name), body=clean_content
        )
        object_key = build_nda_object_key(
            pr_number=pr_number, vendor_code=vendor_code, version=version
        )

        return object_key, pdf_bytes

    def _render_and_store_document(
        self,
        content: str,
        vendor_name: Optional[str],
        vendor_code: Optional[str],
        pr_number: Optional[str],
        version: Optional[str],
    ) -> tuple[str, bytes]:
        """build_final_document + upload to the private bucket.

        Returns the STORED key (what S3 reports, not what we asked for) and
        the exact bytes that were archived, so the caller can attach the very
        same object it just stored rather than a second render of it.
        """

        object_key, pdf_bytes = self.build_final_document(
            content=content, vendor_name=vendor_name, vendor_code=vendor_code,
            pr_number=pr_number, version=version,
        )

        # Lazy: s3_utils imports boto3 and reads AWS_* at module scope.
        from Backend.API_Layer.utils.s3_utils import upload_to_s3

        upload_result = upload_to_s3(
            filename=object_key.split("/")[-1],
            content=pdf_bytes,
            content_type="application/pdf",
            key=object_key,
        )

        return upload_result.get("filepath", object_key), pdf_bytes

    # =========================================================
    # Editable content
    # =========================================================

    def update_content(
        self,
        nda_id: int,
        content: str,
        user_id: str,
        version: Optional[int] = None,
    ) -> VendorNda:
        """Persist the latest editable NDA wording (the editor's Save Draft).

        Only the content columns change - no status transition, no S3 write,
        no email. The document the vendor receives is built from whatever is
        stored here at send time.

        ``version``, when supplied, is the revision the client believes it is
        editing. A mismatch means someone else saved in the meantime, so the
        save is refused rather than silently discarding their work.
        """

        nda = self._require_nda(nda_id)

        current_status = self._status_code(nda)
        if current_status not in CONTENT_EDIT_ALLOWED_FROM:
            raise ValueError(
                _CONTENT_EDIT_REJECTION_REASONS.get(
                    current_status,
                    f"NDA content cannot be edited while the NDA is {current_status}",
                )
            )

        clean_content = normalize_nda_content(content)

        current_version = int(nda.content_version or 1)
        if version is not None and int(version) != current_version:
            raise NdaContentConflict(
                f"NDA content has changed since version {version} was loaded "
                f"(current version is {current_version}); reload before saving",
                current_version=current_version,
            )

        self.nda_dao.update_nda_content(
            nda=nda,
            content=clean_content,
            content_version=current_version + 1,
            user_id=user_id,
            updated_at=_utcnow(),
        )

        self._record_history(
            nda.nda_id, ACTION_CONTENT_UPDATED, user_id,
            {
                "from_version": current_version,
                "to_version": nda.content_version,
                "content_length": len(clean_content),
                "status": current_status,
            },
        )

        self.db.commit()
        self.db.refresh(nda)
        return nda

    # =========================================================
    # Send
    # =========================================================

    def send_nda(self, nda_id: int, user_id: str) -> tuple[VendorNda, EmailSendResult]:
        nda = self._require_nda(nda_id)

        if self._status_code(nda) == STATUS_NOT_REQUIRED:
            raise ValueError("This NDA is not required and cannot be sent")
        if not nda.document_key and not nda.content:
            raise ValueError("NDA document has not been generated yet")
        if not nda.recipient_email:
            raise ValueError("Vendor has no email address on file for the NDA")

        vendor = self.nda_dao.get_vendor_by_id(nda.vendor_id)
        vendor_name = vendor.vendor_name if vendor is not None else "Vendor"

        # The document the vendor receives is built from the PERSISTED
        # content, so a saved edit is never silently replaced by the original
        # generated PDF. Generating and archiving both happen BEFORE the
        # email and before any status change: if S3 fails the exception
        # propagates, the route rolls back and the NDA stays exactly as it
        # was - the same rule upload_signed_document follows.
        #
        # NDAs generated before editable content existed have no content to
        # render, so they fall back to attaching the archived object as
        # before. Nothing about their behaviour changes.
        attachment_name, pdf_bytes = self._build_send_attachment(nda, vendor, user_id)

        subject, html_body, text_body = self._build_email_content(vendor_name)

        self._record_history(
            nda.nda_id, ACTION_SEND_ATTEMPTED, user_id,
            {
                "recipient_email": nda.recipient_email,
                "content_version": nda.content_version if nda.content else None,
                "document_key": nda.document_key,
            },
        )

        result = send_email(
            to_address=nda.recipient_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=[
                EmailAttachment(
                    filename=attachment_name,
                    content=pdf_bytes,
                    content_type="application/pdf",
                )
            ],
        )

        if not result.success:
            # Status deliberately unchanged - a failed delivery must never
            # look like a sent NDA. The failure audit row is still committed.
            self._record_history(
                nda.nda_id, ACTION_SEND_FAILED, user_id,
                {"recipient_email": nda.recipient_email, "error": result.error},
            )
            self.db.commit()
            return nda, result

        self._transition(nda, STATUS_SENT)
        nda.sent_at = _utcnow()
        nda.updated_by = user_id

        self._record_history(
            nda.nda_id, ACTION_SENT, user_id, {"recipient_email": nda.recipient_email}
        )

        self.db.commit()
        self.db.refresh(nda)
        return nda, result

    def _build_send_attachment(
        self, nda: VendorNda, vendor, user_id: str
    ) -> tuple[str, bytes]:
        """The exact document the vendor will receive, already archived in S3.

        With persisted content: re-render it, store it under the existing NDA
        key convention, point ``document_key`` at the stored object and return
        those same bytes - so the archived copy and the emailed copy are
        byte-identical and both reflect the user's edits.

        Without persisted content (an NDA generated before this feature):
        attach the archived object unchanged.

        ``signed_document_key`` is never read or written here - the signed
        document is a separate workflow.
        """

        if not nda.content:
            from Backend.API_Layer.utils.s3_utils import get_object_bytes

            return nda.document_key.split("/")[-1], get_object_bytes(nda.document_key)

        previous_key = nda.document_key

        stored_key, pdf_bytes = self._render_and_store_document(
            content=nda.content,
            vendor_name=getattr(vendor, "vendor_name", None),
            vendor_code=getattr(vendor, "vendor_code", None),
            pr_number=getattr(
                self.nda_dao.get_pr_by_id(nda.pr_id) if nda.pr_id is not None else None,
                "pr_number",
                None,
            ),
            version=nda.template_version,
        )

        # This IS the version being sent, so it becomes the generated document
        # of record. The key convention is deterministic, so a re-render
        # normally overwrites the same object rather than orphaning one.
        nda.document_key = stored_key

        self._record_history(
            nda.nda_id, ACTION_UPLOADED, user_id,
            {
                "document_key": stored_key,
                "previous_document_key": previous_key if previous_key != stored_key else None,
                "content_version": nda.content_version,
                "final": True,
            },
        )

        return stored_key.split("/")[-1], pdf_bytes

    # =========================================================
    # Manual signed-document upload
    # =========================================================

    def upload_signed_document(
        self,
        nda_id: int,
        filename: str,
        content: bytes,
        content_type: Optional[str],
        user_id: str,
    ) -> VendorNda:
        """Store a vendor-signed NDA and move the NDA to SIGNED.

        Ordering is deliberate: the S3 upload happens BEFORE any status change,
        and nothing is committed until it succeeds. A failed upload therefore
        leaves the NDA exactly as it was rather than claiming a signed document
        exists - the same "only advance state after the side effect succeeds"
        rule send_nda follows for email.

        SIGNED is not the end of the line: it means "signed document received,
        pending internal review". RFQ eligibility stays blocked until someone
        explicitly moves the NDA to COMPLETED.
        """

        nda = self._require_nda(nda_id)
        current_status = self._status_code(nda)

        if current_status not in SIGNED_UPLOAD_ALLOWED_FROM:
            raise ValueError(
                _SIGNED_UPLOAD_REJECTION_REASONS.get(
                    current_status,
                    f"A signed NDA cannot be uploaded while the NDA is {current_status}",
                )
            )

        if not content:
            raise ValueError("Signed NDA document is empty")

        vendor = self.nda_dao.get_vendor_by_id(nda.vendor_id)
        pr = self.nda_dao.get_pr_by_id(nda.pr_id) if nda.pr_id is not None else None

        object_key = build_nda_object_key(
            pr_number=getattr(pr, "pr_number", None),
            vendor_code=getattr(vendor, "vendor_code", None),
            version=nda.template_version,
            signed=True,
        )

        # Lazy: s3_utils imports boto3 and reads AWS_* at module scope.
        from Backend.API_Layer.utils.s3_utils import upload_to_s3

        upload_result = upload_to_s3(
            filename=filename,
            content=content,
            content_type=content_type or "application/pdf",
            key=object_key,
        )
        stored_key = upload_result.get("filepath", object_key)

        nda.signed_document_key = stored_key
        nda.signed_at = _utcnow()
        nda.updated_by = user_id

        if current_status != STATUS_SIGNED:
            self._transition(nda, STATUS_SIGNED)

        self._record_history(
            nda.nda_id, ACTION_SIGNED_UPLOADED, user_id,
            {"signed_document_key": stored_key, "from": current_status, "uploaded_by": user_id},
        )
        self._record_history(
            nda.nda_id, ACTION_SIGNED, user_id, {"from": current_status, "to": STATUS_SIGNED}
        )

        self.db.commit()
        self.db.refresh(nda)
        return nda

    # =========================================================
    # Lifecycle
    # =========================================================

    def update_status(
        self,
        nda_id: int,
        status_code: str,
        user_id: str,
        signed_document_key: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> VendorNda:

        nda = self._require_nda(nda_id)
        previous = self._status_code(nda)
        self._transition(nda, status_code)

        now = _utcnow()
        if status_code == STATUS_SIGNED:
            nda.signed_at = now
        elif status_code == STATUS_COMPLETED:
            nda.completed_at = now
            if nda.signed_at is None:
                nda.signed_at = now
            # An NDA's validity runs from the moment it is actually completed.
            nda.valid_from = now.date()
            nda.valid_until = _add_months(nda.valid_from, self._validity_months())

        if signed_document_key:
            nda.signed_document_key = signed_document_key

        nda.updated_by = user_id

        self._record_history(
            nda.nda_id,
            _STATUS_ACTIONS.get(status_code, "NDA_STATUS_CHANGED"),
            user_id,
            {"from": previous, "to": status_code, "reason": reason,
             "signed_document_key": signed_document_key},
        )

        self.db.commit()
        self.db.refresh(nda)
        return nda

    # =========================================================
    # Secure document access
    # =========================================================

    def get_document_url(
        self,
        nda_id: int,
        user_id: str,
        signed: bool = False,
        expires_in: Optional[int] = None,
    ) -> tuple[str, int]:
        """Short-lived presigned URL for an authorized user. Authorization is
        enforced by the route's permission dependency before this is reached;
        every issue is audited."""

        nda = self._require_nda(nda_id)
        key = nda.signed_document_key if signed else nda.document_key
        if not key:
            raise ValueError("NDA document not found")

        from Backend.API_Layer.utils.s3_utils import (
            DEFAULT_PRESIGNED_URL_TTL_SECONDS,
            generate_presigned_url,
        )

        ttl = int(expires_in or DEFAULT_PRESIGNED_URL_TTL_SECONDS)
        url = generate_presigned_url(key, expires_in=ttl)

        self._record_history(
            nda.nda_id, ACTION_DOCUMENT_ACCESSED, user_id,
            {"document_key": key, "signed": signed},
        )
        self.db.commit()

        return url, ttl

    # =========================================================
    # Reads
    # =========================================================

    def get_nda(self, nda_id: int) -> VendorNda:
        return self._require_nda(nda_id)

    def list_for_vendor(self, vendor_id: int) -> List[VendorNda]:
        return self.nda_dao.get_ndas_by_vendor(vendor_id)

    # =========================================================
    # Internal helpers
    # =========================================================

    @staticmethod
    def _is_nda_required(engagement) -> bool:
        """Requirement comes from the engagement's recorded decision, falling
        back to the screening-rule recommendation. Unknown means required -
        fail closed."""

        if engagement is None:
            return True
        required = engagement.nda_final_required
        if required is None:
            required = engagement.nda_recommended
        return bool(required) if required is not None else True

    def _resolve_template(self, template_code: Optional[str]):
        code = template_code or self.nda_dao.get_config_value(CONFIG_TEMPLATE_CODE) or DEFAULT_TEMPLATE_CODE

        template = self.nda_dao.get_active_template_by_code(code)
        if template is None:
            existing = self.nda_dao.get_template_by_code(code)
            if existing is not None:
                raise ValueError(f"NDA template '{code}' is not active")
            template = self.nda_dao.get_default_active_template()

        if template is None:
            raise ValueError("No active NDA template is configured")
        return template

    def _create_nda_row(
        self, vendor_id, pr_id, department_id, purchase_category_id, required,
        status_code, user_id, recipient_email=None, template=None, document_key=None,
        content=None,
    ) -> VendorNda:

        status = self._require_status(status_code)
        nda = VendorNda(
            vendor_id=vendor_id,
            pr_id=pr_id,
            department_id=department_id,
            purchase_category_id=purchase_category_id,
            nda_required=required,
            nda_status_id=status.status_id,
            template_id=getattr(template, "id", None),
            template_version=getattr(template, "version", None),
            document_key=document_key,
            recipient_email=recipient_email,
            # Revision 1 is the generated wording, before any user edit. A
            # NOT_REQUIRED NDA has no document and therefore no content.
            content=content,
            content_version=1,
            content_updated_at=_utcnow() if content else None,
            content_updated_by=user_id if content else None,
            created_by=user_id,
            updated_by=user_id,
        )
        nda.status = status
        self.nda_dao.create_nda(nda)
        return nda

    def _require_nda(self, nda_id: int) -> VendorNda:
        nda = self.nda_dao.get_nda_by_id(nda_id)
        if nda is None:
            raise ValueError("NDA not found")
        return nda

    def _require_status(self, status_code: str):
        status = self.nda_dao.get_status_by_module_code(NDA_STATUS_MODULE, status_code)
        if status is None:
            raise ValueError(
                f"Status '{status_code}' is not configured for module '{NDA_STATUS_MODULE}'"
            )
        return status

    @staticmethod
    def _status_code(nda: VendorNda) -> Optional[str]:
        return nda.status.status_code if nda.status is not None else None

    def _transition(self, nda: VendorNda, target_code: str) -> None:
        current_code = self._status_code(nda)
        allowed = NDA_TRANSITIONS.get(current_code, set())
        if target_code not in allowed:
            raise ValueError(f"NDA cannot move from {current_code} to {target_code}")

        target_status = self._require_status(target_code)
        nda.nda_status_id = target_status.status_id
        nda.status = target_status

    def _validity_months(self) -> int:
        raw = self.nda_dao.get_config_value(CONFIG_VALIDITY_MONTHS)
        try:
            months = int(str(raw).strip())
            return months if months > 0 else DEFAULT_VALIDITY_MONTHS
        except (TypeError, ValueError):
            return DEFAULT_VALIDITY_MONTHS

    @staticmethod
    def _company_name() -> str:
        try:
            return get_env_var("BUYER_NAME")
        except ValueError:
            return "The Company"

    @staticmethod
    def _build_email_content(vendor_name: str) -> tuple[str, str, str]:
        subject = "Non-Disclosure Agreement for your review and signature"
        text_body = (
            f"Dear {vendor_name},\n\n"
            "Please find attached the Non-Disclosure Agreement required to proceed "
            "with our procurement process.\n\n"
            "Kindly review, sign and return the attached document at your earliest "
            "convenience. Our team will confirm once the signed copy has been "
            "received and recorded.\n\n"
            "Regards,\nProcurement Team"
        )
        html_body = (
            f"<p>Dear {vendor_name},</p>"
            "<p>Please find attached the Non-Disclosure Agreement required to proceed "
            "with our procurement process.</p>"
            "<p>Kindly review, sign and return the attached document at your earliest "
            "convenience. Our team will confirm once the signed copy has been received "
            "and recorded.</p>"
            "<p>Regards,<br/>Procurement Team</p>"
        )
        return subject, html_body, text_body

    def _record_history(
        self,
        nda_id: int,
        action: str,
        user_id: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:
        """Audit row on the NDA's own timeline (table_name='vendor_nda',
        record_id=nda_id), matching the existing _record_pr_history idiom."""

        self._write_audit(NDA_HISTORY_TABLE, nda_id, action, user_id, metadata)

    def _record_vendor_history(
        self,
        vendor_id: int,
        action: str,
        user_id: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:
        """For NDA events that happen before any NDA row exists (requirement
        decision, "no existing NDA found"), so they are still queryable
        against the vendor rather than an invented record_id."""

        self._write_audit(VENDOR_HISTORY_TABLE, vendor_id, action, user_id, metadata)

    def _write_audit(
        self,
        table_name: str,
        record_id: int,
        action: str,
        user_id: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:

        values = {key: value for key, value in (metadata or {}).items() if value is not None}
        self.nda_dao.create_audit_log(
            AuditLog(
                table_name=table_name,
                record_id=record_id,
                action=action,
                changed_by=user_id,
                new_values=values or None,
            )
        )
