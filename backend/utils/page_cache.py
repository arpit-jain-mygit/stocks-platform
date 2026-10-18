"""
page_cache.py - Saves expensive per-page results so they are never paid for twice.

Keys (in the storage chosen by utils/storage.py):   <doc_id>/<variant>/page_NNN.md
- doc_id  = SHA-256 of the PDF (ingest/ids.py), so a renamed copy still hits the cache.
- variant = short fingerprint of whatever shapes the result (model, prompt, DPI ...).
            Change any of those and the caller gets a fresh folder automatically,
            so old results are never reused with new settings by mistake.

Used by ingest/pdf_reader.py for Gemini page transcriptions, but nothing here
is Gemini-specific - any step that produces "text for page N of doc X" can use it.
Where the files live (a local folder or S3) is decided by CACHE_BACKEND.
"""

# --- Imports -----------------------------------------------------------------
# hashlib: builds the short "variant" fingerprint.
# cache_storage: the local folder or S3 bucket for cache files (utils/storage.py).
import hashlib

from utils.storage import cache_storage


# --- Variant fingerprint -------------------------------------------------------
def make_variant(*parts: object) -> str:
    """
    Turns the settings that affect a result into an 8-character fingerprint.
    Example: make_variant("gemini-3.5-flash", 200, PROMPT) -> "1711d98d"
    Same settings -> same fingerprint -> same cache folder.
    """
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode()).hexdigest()[:8]


# --- Which file holds one page's result ----------------------------------------------
def page_key(doc_id: str, variant: str, page_no: int, kind: str = "") -> str:
    """
    kind lets one page keep results from different readers side by side:
      kind=""    -> <doc>/<variant>/page_011.md       (main result, e.g. vision model)
      kind="ocr" -> <doc>/<variant>/page_011.ocr.md   (fallback result, e.g. Tesseract)
    """
    suffix = f".{kind}.md" if kind else ".md"
    return f"{doc_id}/{variant}/page_{page_no:03d}{suffix}"


# --- Read one page from the cache ------------------------------------------------
def load(doc_id: str, variant: str, page_no: int, kind: str = "") -> str | None:
    """Returns the cached text for this page, or None if it was never saved."""
    return cache_storage().get_text(page_key(doc_id, variant, page_no, kind))


# --- Write one page to the cache -------------------------------------------------
def save(doc_id: str, variant: str, page_no: int, text: str, kind: str = "") -> None:
    """
    Saves one page's result. Empty results are not cached, so they get retried next run.
    """
    if not text:
        return
    cache_storage().put_text(page_key(doc_id, variant, page_no, kind), text)
