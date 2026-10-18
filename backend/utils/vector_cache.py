"""
vector_cache.py - Saves embedding vectors so the same text is never embedded twice.

Keys (in the storage chosen by utils/storage.py):   vectors/<model>-<dim>/<key>.json
- key = SHA-256 of (task type + text). Same text -> same key, whatever PDF it came from.
- The folder name includes the model and vector size: switching either one
  automatically uses a fresh folder, so old vectors are never mixed with new ones.
"""

# --- Imports -----------------------------------------------------------------
# hashlib: builds the key from the text.
# json:    vectors are stored as plain JSON lists of numbers.
# cache_storage: the local folder or S3 bucket (utils/storage.py).
import hashlib
import json

from utils.storage import cache_storage


# --- Which file holds one vector -----------------------------------------------------
def vector_key(model: str, dim: int, task_type: str, text: str) -> str:
    key = hashlib.sha256(f"{task_type}|{text}".encode()).hexdigest()
    return f"vectors/{model}-{dim}/{key}.json"


# --- Read / write ----------------------------------------------------------------------
def load(model: str, dim: int, task_type: str, text: str) -> list[float] | None:
    """Returns the cached vector for this text, or None if it was never saved."""
    stored = cache_storage().get_text(vector_key(model, dim, task_type, text))
    return json.loads(stored) if stored is not None else None


def save(model: str, dim: int, task_type: str, text: str, vector: list[float]) -> None:
    """Saves one vector."""
    cache_storage().put_text(vector_key(model, dim, task_type, text), json.dumps(vector))
