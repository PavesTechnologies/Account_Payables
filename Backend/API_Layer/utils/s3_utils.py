# Backend/API_Layer/utils/s3_utils.py

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
)

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from Backend.config.env_loader import get_env_var


# ============================================================
# Configuration
# ============================================================

AWS_ACCESS_KEY = get_env_var(
    "AWS_ACCESS_KEY_ID"
)

AWS_SECRET_KEY = get_env_var(
    "AWS_SECRET_ACCESS_KEY"
)

AWS_REGION = get_env_var(
    "AWS_REGION",
    "ap-south-1"
)

BUCKET_NAME = get_env_var(
    "AWS_BUCKET_NAME"
)


if not all(
    [
        AWS_ACCESS_KEY,
        AWS_SECRET_KEY,
        AWS_REGION,
        BUCKET_NAME,
    ]
):

    raise RuntimeError(
        "Missing required AWS configuration."
    )


# ============================================================
# Constants
# ============================================================

_UNSAFE_FILENAME_CHARS = re.compile(
    r"[^A-Za-z0-9._-]+"
)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024


# ============================================================
# Client
# ============================================================

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
)


# ============================================================
# Filename
# ============================================================

def sanitize_filename(
    filename: Optional[str],
) -> str:

    if not filename:
        return "invoice"

    filename = _UNSAFE_FILENAME_CHARS.sub(
        "_",
        filename,
    )

    filename = filename.strip(
        "._"
    )

    return filename or "invoice"


# ============================================================
# Upload
# ============================================================

def upload_to_s3(
    filename: str,
    content: bytes,
    content_type: Optional[str] = None,
    prefix: str = "invoices/",
    key: Optional[str] = None,
) -> dict:
    """Upload bytes to the private bucket and return the stored object key.

    ``prefix`` and ``key`` are additive and both default to the original
    behaviour, so every existing invoice/quotation/GRN/PO caller is unaffected:
    omitting them still produces ``invoices/{year}/{month}/{uuid}_{filename}``.

    ``key``, when given, is used verbatim as the object key. NDA documents need
    a fully deterministic, human-traceable key
    (``ap/nda/generated/{year}/{pr}/{vendor}/NDA-...-v{version}.pdf``), which a
    prefix alone cannot express because the default layout injects a random
    uuid segment.
    """

    if not content:

        raise HTTPException(
            status_code=400,
            detail="Cannot upload empty file.",
        )

    if len(content) > MAX_UPLOAD_SIZE:

        raise HTTPException(
            status_code=413,
            detail="File exceeds maximum allowed size.",
        )

    safe_filename = sanitize_filename(
        filename
    )

    now = datetime.now(
        timezone.utc
    )

    if key:
        s3_key = key
    else:
        s3_key = (
            f"{prefix}"
            f"{now.year}/"
            f"{now.month:02d}/"
            f"{uuid.uuid4().hex}_"
            f"{safe_filename}"
        )

    try:

        params = {
            "Bucket": BUCKET_NAME,
            "Key": s3_key,
            "Body": content,
        }

        if content_type:
            params[
                "ContentType"
            ] = content_type

        s3_client.put_object(
            **params
        )

        return {
            "status": "success",
            "filename": filename,
            "filepath": s3_key,
        }

    except (
        ClientError,
        BotoCoreError,
    ) as exc:

        raise HTTPException(
            status_code=502,
            detail="S3 upload failed.",
        ) from exc


# ============================================================
# Raw bytes (server-side use, e.g. email attachments)
# ============================================================

def get_object_bytes(
    key: str,
) -> bytes:
    """Fetch one private object's bytes for server-side use.

    Used to attach the exact stored NDA PDF to an email - re-generating the
    document instead would risk sending something that differs from the
    archived copy. Bytes are never persisted to Postgres or logged.
    """

    try:

        response = s3_client.get_object(
            Bucket=BUCKET_NAME,
            Key=key,
        )

        return response["Body"].read()

    except ClientError as exc:

        error_code = (
            exc.response
            .get("Error", {})
            .get("Code")
        )

        if error_code in {
            "NoSuchKey",
            "404",
        }:

            raise HTTPException(
                status_code=404,
                detail="File not found.",
            ) from exc

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve file.",
        ) from exc

    except BotoCoreError as exc:

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve file.",
        ) from exc


# ============================================================
# Presigned URL
# ============================================================

DEFAULT_PRESIGNED_URL_TTL_SECONDS = 300

MAX_PRESIGNED_URL_TTL_SECONDS = 3600


def generate_presigned_url(
    key: str,
    expires_in: int = DEFAULT_PRESIGNED_URL_TTL_SECONDS,
) -> str:
    """Short-lived, authenticated URL for one private object.

    The bucket stays private - this grants temporary read access to a single
    key and nothing else. Callers MUST authorize the user before calling;
    this function performs no permission checks of its own. TTL is clamped so
    a caller cannot mint a long-lived link.
    """

    if not key:

        raise HTTPException(
            status_code=400,
            detail="Document key is required.",
        )

    ttl = max(
        1,
        min(
            int(expires_in),
            MAX_PRESIGNED_URL_TTL_SECONDS,
        ),
    )

    try:

        return s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": key,
            },
            ExpiresIn=ttl,
        )

    except (
        ClientError,
        BotoCoreError,
    ) as exc:

        raise HTTPException(
            status_code=502,
            detail="Unable to generate document access URL.",
        ) from exc


# ============================================================
# View
# ============================================================

def view_from_s3(
    filename: str,
) -> StreamingResponse:

    try:

        response = s3_client.get_object(
            Bucket=BUCKET_NAME,
            Key=filename,
        )

        return StreamingResponse(
            response["Body"],
            media_type=response.get(
                "ContentType",
                "application/octet-stream",
            ),
        )

    except ClientError as exc:

        error_code = (
            exc.response
            .get("Error", {})
            .get("Code")
        )

        if error_code in {
            "NoSuchKey",
            "404",
        }:

            raise HTTPException(
                status_code=404,
                detail="File not found.",
            ) from exc

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve file.",
        ) from exc


# ============================================================
# Download
# ============================================================

def download_from_s3(
    filename: str,
) -> StreamingResponse:

    try:

        response = s3_client.get_object(
            Bucket=BUCKET_NAME,
            Key=filename,
        )

        safe_filename = sanitize_filename(
            filename.split("/")[-1]
        )

        headers = {
            "Content-Disposition": (
                f'attachment; filename="{safe_filename}"'
            )
        }

        return StreamingResponse(
            response["Body"],
            media_type="application/octet-stream",
            headers=headers,
        )

    except ClientError as exc:

        error_code = (
            exc.response
            .get("Error", {})
            .get("Code")
        )

        if error_code in {
            "NoSuchKey",
            "404",
        }:

            raise HTTPException(
                status_code=404,
                detail="File not found.",
            ) from exc

        raise HTTPException(
            status_code=500,
            detail="Unable to download file.",
        ) from exc


# ============================================================
# Delete
# ============================================================

def delete_from_s3(
    filename: str,
) -> dict:

    try:

        s3_client.delete_object(
            Bucket=BUCKET_NAME,
            Key=filename,
        )

        return {
            "status": "success",
            "message": (
                "File deleted successfully."
            ),
        }

    except (
        ClientError,
        BotoCoreError,
    ) as exc:

        raise HTTPException(
            status_code=500,
            detail="S3 deletion failed.",
        ) from exc