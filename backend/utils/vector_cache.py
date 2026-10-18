"""
vector_cache.py - Saves embedding vectors to disk so the same text is never embedded twice.

Layout on disk:   <CACHE_DIR>/vectors/<model>-<dim>/<key>.json
- key = SHA-256 of (task type + text). Same text -> same file, whatever PDF it came from.
- The folder name includes the model and vector size: switching either one
  automatically uses a fresh folder, so old vectors are never mixed with new ones.
"""

# --- Imports -----------------------------------------------------------------
# hashlib:    builds the key (file name) from the text.
# json:       vectors are stored as plain JSON lists of numbers.
# CACHE_DIR:  same root folder as the page cache (data/cache by default).
import hashlib
import json

from utils.page_cache import CACHE_DIR


# --- Where one vector lives on disk ------------------------------------------------
def vector_path(model: str, dim: int, task_type: str, text: str):
    key = hashlib.sha256(f"{task_type}|{text}".encode()).hexdigest()
    return CACHE_DIR / "vectors" / f"{model}-{dim}" / f"{key}.json"


# --- Read / write ----------------------------------------------------------------------
def load(model: str, dim: int, task_type: str, text: str) -> list[float] | None:
    """Returns the cached vector for this text, or None if it was never saved."""
    path = vector_path(model, dim, task_type, text)
    return json.loads(path.read_text()) if path.exists() else None


def save(model: str, dim: int, task_type: str, text: str, vector: list[float]) -> None:
    """Saves one vector. Temp file + rename, so a crash never leaves half a file."""
    path = vector_path(model, dim, task_type, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(vector))
    tmp.replace(path)
