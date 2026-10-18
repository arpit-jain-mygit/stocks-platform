"""
security.py - Request checks shared by every router.

  require_api_key    X-API-Key must equal APP_API_KEY (if set). Every endpoint but /health.
  require_admin_key  X-Admin-Key must equal ADMIN_API_KEY. Only the risky delete APIs.
                     If ADMIN_API_KEY is empty, those APIs refuse every request.
"""

# --- Imports -----------------------------------------------------------------
# load_dotenv runs here too: this module can be imported before anything else
# has loaded .env, and reading the keys too early would leave them empty
# (= checks switched off). Keys are also read on every request, not at import.
import os
import secrets

from dotenv import load_dotenv
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

load_dotenv()

# scheme_name keeps the two apart on the /docs "Authorize" page (both are
# APIKeyHeader, and without distinct names one would hide the other).
api_key_header = APIKeyHeader(name="X-API-Key", scheme_name="ApiKey", auto_error=False,
                              description="APP_API_KEY from .env - every endpoint except /health")
admin_key_header = APIKeyHeader(name="X-Admin-Key", scheme_name="AdminKey", auto_error=False,
                                description="ADMIN_API_KEY from .env - only the /risky-delete endpoints")


def require_api_key(key: str | None = Security(api_key_header)) -> None:
    """Rejects the request with 401 if APP_API_KEY is set and the header doesn't match."""
    expected = os.getenv("APP_API_KEY", "")
    if expected and not secrets.compare_digest(key or "", expected):
        raise HTTPException(status_code=401, detail="Missing or wrong X-API-Key header")


def require_admin_key(key: str | None = Security(admin_key_header)) -> None:
    """403 unless ADMIN_API_KEY is set AND the X-Admin-Key header matches it."""
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=403, detail="Delete APIs are disabled: ADMIN_API_KEY is not set")
    if not secrets.compare_digest(key or "", expected):
        raise HTTPException(status_code=403, detail="Missing or wrong X-Admin-Key header")
