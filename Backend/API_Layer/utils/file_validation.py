# Backend/API_Layer/utils/file_validation.py
"""Upload validation for /process-invoice.

No such utility existed before this endpoint — every check here
(extension/content-type allow-list, size, empty-file) is new but kept
in one small function so the route stays thin.
"""
from __future__ import annotations

from fastapi import UploadFile

from Backend.Business_Layer.utils.exceptions import InvalidUploadFile, UnsupportedFileType

MAX_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
}


_PDF_EXTENSIONS = {".pdf"}
_PDF_CONTENT_TYPES = {"application/pdf"}


def validate_upload_file(file: UploadFile, content: bytes) -> None:
    """Raise UnsupportedFileType (415) or InvalidUploadFile (400) if the upload is unusable."""
    _validate(file, content, _ALLOWED_EXTENSIONS, _ALLOWED_CONTENT_TYPES)


def validate_pdf_upload(file: UploadFile, content: bytes) -> None:
    """PDF-only variant, for documents that must be a real PDF rather than a
    scan/photo - e.g. a vendor-signed NDA. Same size/empty/filename rules and
    the same MAX_UPLOAD_SIZE_BYTES limit as every other upload in the app."""
    _validate(file, content, _PDF_EXTENSIONS, _PDF_CONTENT_TYPES)


def _validate(
    file: UploadFile,
    content: bytes,
    allowed_extensions: set,
    allowed_content_types: set,
) -> None:

    if not file.filename or not file.filename.strip():
        raise InvalidUploadFile("Uploaded file must have a filename")

    extension = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in allowed_extensions:
        raise UnsupportedFileType(
            f"Unsupported file extension '{extension}' for '{file.filename}'"
        )

    if file.content_type and file.content_type.lower() not in allowed_content_types:
        raise UnsupportedFileType(
            f"Unsupported content type '{file.content_type}' for '{file.filename}'"
        )

    if not content:
        raise InvalidUploadFile(f"Uploaded file '{file.filename}' is empty")

    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise InvalidUploadFile(
            f"Uploaded file '{file.filename}' exceeds the maximum allowed size of "
            f"{MAX_UPLOAD_SIZE_BYTES} bytes"
        )
