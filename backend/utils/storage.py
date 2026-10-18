"""
storage.py - Where cache files are kept: a folder on this computer, or an S3 bucket on AWS.

The caches (page results and vectors) only need two things: read a text file by name,
and write a text file by name. This module provides that for both places.

    CACHE_BACKEND=local (default)  files under PAGE_CACHE_DIR (default data/cache)
    CACHE_BACKEND=s3               objects in CACHE_BUCKET under the prefix "cache/"

Keys are relative paths such as "<doc_id>/<variant>/page_001.md". The same key works in both.
"""

# --- Imports -----------------------------------------------------------------
# functools: keeps one storage object for the whole process.
# os:        reads CACHE_BACKEND, CACHE_BUCKET and PAGE_CACHE_DIR.
# Path:      local folders.
import functools
import os
from pathlib import Path


class Storage:
    """Read and write text files by key. Missing files read as None."""

    name = "base"

    def get_text(self, key: str) -> str | None:
        raise NotImplementedError(f"{self.name} storage must implement get_text")

    def put_text(self, key: str, text: str) -> None:
        raise NotImplementedError(f"{self.name} storage must implement put_text")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class LocalStorage(Storage):
    """Files in a folder on this computer. Writes go to a temp file first, then rename (no half files)."""

    name = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def get_text(self, key: str) -> str | None:
        path = self.root / key
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put_text(self, key: str, text: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    def __repr__(self) -> str:
        return f"LocalStorage({str(self.root)!r})"


class S3Storage(Storage):
    """Objects in an S3 bucket. Keys are stored under an optional prefix."""

    name = "s3"
    MISSING_CODES = ("NoSuchKey", "404")

    def __init__(self, bucket: str, prefix: str = "", client=None):
        if client is None:
            import boto3                     # imported only when S3 is used
            client = boto3.client("s3")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client

    def _object_key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def get_text(self, key: str) -> str | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._object_key(key))
        except Exception as error:           # botocore raises ClientError with a code
            code = getattr(error, "response", {}).get("Error", {}).get("Code")
            if code in self.MISSING_CODES:
                return None
            raise
        return response["Body"].read().decode("utf-8")

    def put_text(self, key: str, text: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._object_key(key),
                               Body=text.encode("utf-8"), ContentType="text/plain; charset=utf-8")

    def __repr__(self) -> str:
        return f"S3Storage(bucket={self.bucket!r}, prefix={self.prefix!r})"


@functools.lru_cache(maxsize=None)
def cache_storage() -> Storage:
    """The storage for page and vector caches, chosen by CACHE_BACKEND (created once)."""
    backend = os.getenv("CACHE_BACKEND", "local").lower().strip()
    if backend == "s3":
        bucket = os.getenv("CACHE_BUCKET", "")
        if not bucket:
            raise RuntimeError("CACHE_BACKEND=s3 needs CACHE_BUCKET")
        return S3Storage(bucket, prefix="cache")
    if backend == "local":
        return LocalStorage(os.getenv("PAGE_CACHE_DIR", "data/cache"))
    raise ValueError(f"Unknown CACHE_BACKEND {backend!r}. Use local or s3.")
