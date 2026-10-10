# Backend/Business_Layer/utils/bulk_upload_files.py
"""Turns a bulk-upload request (several invoice files, or one ZIP) into a flat list of candidate
files. Pure - no S3 / DB - so every limit is unit-testable.

Per-file problems (wrong type, empty, too large, not really a PDF/image) do not reject the whole
upload: the file comes back with ``problem`` set and is recorded as a FAILED item, so the other
files still go through. Request-level problems (no files, too many, a bad / encrypted / nested
ZIP, a ZIP mixed with loose files) raise BulkUploadRejected and nothing is stored.

Per-file limits match the single-upload /invoice-extract/extract-fields endpoint.
"""
import hashlib
import io
import posixpath
import zipfile
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from Backend.config.env_loader import get_env_var

MAX_FILES_PER_BATCH = int(get_env_var("BULK_UPLOAD_MAX_FILES", "25"))
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ZIP_BYTES = MAX_FILES_PER_BATCH * MAX_FILE_BYTES
MAX_TOTAL_BYTES = MAX_FILES_PER_BATCH * MAX_FILE_BYTES

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
ZIP_TYPES = {"application/zip", "application/x-zip-compressed", "application/x-zip", "multipart/x-zip"}

# OS / archiver clutter silently ignored inside a ZIP.
_IGNORED_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}

_SIGNATURES = {
    "application/pdf": (b"%PDF",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/tiff": (b"II*\x00", b"MM\x00*"),
}


class BulkUploadRejected(ValueError):
    """The upload as a whole is invalid; nothing is stored."""


@dataclass
class CandidateFile:
    file_name: str
    content: bytes
    content_type: Optional[str]
    sha256: Optional[str]
    problem: Optional[str] = None

    @property
    def size(self) -> int:
        return len(self.content)


def extension(name: str) -> str:
    base = posixpath.basename(name.replace("\\", "/"))
    dot = base.rfind(".")
    return base[dot:].lower() if dot > 0 else ""


def is_zip(file_name: str, content_type: Optional[str]) -> bool:
    return extension(file_name) == ".zip" or (content_type or "").lower() in ZIP_TYPES


def _check(file_name: str, content: bytes) -> Tuple[Optional[str], Optional[str]]:
    """(content_type, problem) for one invoice file."""
    content_type = CONTENT_TYPES.get(extension(file_name))
    if content_type is None:
        return None, "Unsupported file type. Supported formats: PDF, JPEG, PNG, TIFF."
    if not content:
        return content_type, "The file is empty."
    if len(content) > MAX_FILE_BYTES:
        return content_type, "The file exceeds the 10 MB size limit."
    if not content.startswith(_SIGNATURES[content_type]):
        return content_type, "The file is damaged or is not really a PDF / image (its contents do not match its type)."
    return content_type, None


def _candidate(file_name: str, content: bytes) -> CandidateFile:
    content_type, problem = _check(file_name, content)
    sha = hashlib.sha256(content).hexdigest() if content else None
    return CandidateFile(file_name=file_name[:255], content=content, content_type=content_type, sha256=sha, problem=problem)


def _zip_members(zip_name: str, payload: bytes) -> List[CandidateFile]:
    if len(payload) > MAX_ZIP_BYTES:
        raise BulkUploadRejected(f"The ZIP file exceeds the {MAX_ZIP_BYTES // (1024 * 1024)} MB size limit.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise BulkUploadRejected(f"'{zip_name}' is not a valid ZIP file.") from exc

    out: List[CandidateFile] = []
    total = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            parts = [p for p in name.split("/") if p]
            base = parts[-1] if parts else ""
            if (not base or base.lower() in _IGNORED_NAMES or base.startswith("._") or base.startswith(".")
                    or any(p == "__MACOSX" for p in parts)):
                continue
            if info.flag_bits & 0x1:
                raise BulkUploadRejected("Password-protected ZIP files are not supported.")
            if extension(base) == ".zip":
                raise BulkUploadRejected("ZIP files inside a ZIP are not supported - put all invoices in one ZIP.")
            if len(out) >= MAX_FILES_PER_BATCH:
                raise BulkUploadRejected(f"The ZIP contains more than {MAX_FILES_PER_BATCH} files.")
            # Never trust the header's size: read at most one byte past the limit.
            with archive.open(info) as handle:
                content = handle.read(MAX_FILE_BYTES + 1)
            total += len(content)
            if total > MAX_TOTAL_BYTES:
                raise BulkUploadRejected("The ZIP contents are too large to process in one batch.")
            # Only the base name is kept - folder paths inside the ZIP are never used.
            out.append(_candidate(base, content))
    if not out:
        raise BulkUploadRejected(f"'{zip_name}' contains no invoice files.")
    return out


def expand_upload(files: Iterable[Tuple[str, Optional[str], bytes]]) -> Tuple[List[CandidateFile], str]:
    """``files`` is (file_name, content_type, content) per uploaded part. Returns the candidates and
    a display name for the batch (the ZIP's name, or "<n> files")."""
    files = list(files)
    if not files:
        raise BulkUploadRejected("Select at least one invoice file or a ZIP file.")
    zips = [f for f in files if is_zip(f[0] or "", f[1])]
    if zips and len(files) > 1:
        raise BulkUploadRejected("Upload either one ZIP file or several invoice files, not both.")
    if zips:
        name, _, payload = zips[0]
        name = posixpath.basename((name or "invoices.zip").replace("\\", "/"))
        return _zip_members(name, payload), name[:255]
    if len(files) > MAX_FILES_PER_BATCH:
        raise BulkUploadRejected(f"A batch can contain at most {MAX_FILES_PER_BATCH} invoices; {len(files)} were selected.")
    candidates = [_candidate(posixpath.basename((name or "invoice").replace("\\", "/")), content)
                  for name, _, content in files]
    return candidates, f"{len(candidates)} file" + ("" if len(candidates) == 1 else "s")


def expand_attachments(files: Iterable[Tuple[str, Optional[str], bytes]]) -> List[CandidateFile]:
    """Email intake: an email may carry loose invoices and/or several ZIPs. Unlike a manual upload
    nothing is rejected as a whole - a bad ZIP becomes one FAILED file with the reason, and files
    beyond the batch limit are recorded as FAILED ("upload the rest manually"), so the AP team
    always sees everything the email contained."""
    out: List[CandidateFile] = []
    for name, content_type, content in files:
        name = posixpath.basename((name or "attachment").replace("\\", "/"))
        if is_zip(name, content_type):
            try:
                out.extend(_zip_members(name, content))
            except BulkUploadRejected as exc:
                out.append(CandidateFile(file_name=name[:255], content=content, content_type="application/zip",
                                         sha256=hashlib.sha256(content).hexdigest() if content else None,
                                         problem=str(exc)))
        else:
            out.append(_candidate(name, content))
    for extra in out[MAX_FILES_PER_BATCH:]:
        extra.problem = (f"The email has more than {MAX_FILES_PER_BATCH} invoice files; "
                         "this one was not processed - upload it manually.")
    return out
