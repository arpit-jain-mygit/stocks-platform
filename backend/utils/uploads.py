"""
uploads.py - Large files go straight to S3, not through the API.

API Gateway limits request bodies to 10 MB, so on AWS the browser asks for a presigned
URL, uploads the file to S3 directly, then calls /ingest with the S3 key (upload_key).

    POST /uploads   -> { upload_url, upload_key, expires_in }   (needs UPLOAD_BUCKET)
    PUT upload_url  -> the file bytes (sent by the browser)
    POST /ingest    -> with upload_key instead of a file

Locally (no UPLOAD_BUCKET) the normal multipart upload to /ingest is used.
"""

# --- Imports -----------------------------------------------------------------
# os:    reads UPLOAD_BUCKET.
# uuid:  unique key per upload.
# re:    keeps file names safe inside a key.
import os
import re
import uuid

# --- Settings ----------------------------------------------------------------
UPLOAD_URL_SECONDS = 15 * 60         # the presigned link works for 15 minutes
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # same limit as /ingest


def upload_bucket() -> str:
    """The bucket for uploads, or "" when uploads go through the API (local)."""
    return os.getenv("UPLOAD_BUCKET", "").strip()


def safe_name(file_name: str) -> str:
    """'Report 2025 (final).pdf' -> 'Report_2025_final_.pdf' (keeps letters, digits, . _ -)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", file_name or "upload")


def _s3_client(client=None):
    if client is not None:
        return client
    import boto3                          # imported only when S3 is used
    return boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-south-1"))


def create_upload(file_name: str, client=None) -> dict:
    """A presigned PUT link and the S3 key to ingest from later."""
    bucket = upload_bucket()
    if not bucket:
        raise RuntimeError("Direct uploads need UPLOAD_BUCKET. Locally, upload the file to /ingest instead.")
    key = f"uploads/{uuid.uuid4().hex}/{safe_name(file_name)}"
    url = _s3_client(client).generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=UPLOAD_URL_SECONDS)
    return {"upload_url": url, "upload_key": key, "expires_in": UPLOAD_URL_SECONDS}


def read_upload(key: str, client=None) -> bytes:
    """The bytes of an uploaded file. Raises ValueError for keys that are not uploads or too large."""
    bucket = upload_bucket()
    if not bucket:
        raise RuntimeError("Direct uploads need UPLOAD_BUCKET.")
    if not key.startswith("uploads/") or ".." in key:
        raise ValueError("upload_key must come from POST /uploads")
    s3 = _s3_client(client)
    size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(f"Upload is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
