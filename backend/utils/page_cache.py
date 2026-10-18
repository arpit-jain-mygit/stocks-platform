"""
page_cache.py - Saves expensive per-page results to disk so they are never paid for twice.

Layout on disk:   <CACHE_DIR>/<doc_id>/<variant>/page_NNN.md
- doc_id  = SHA-256 of the PDF (ingest/ids.py), so a renamed copy still hits the cache.
- variant = short fingerprint of whatever shapes the result (model, prompt, DPI ...).
            Change any of those and the caller gets a fresh folder automatically,
            so old results are never reused with new settings by mistake.

Used by ingest/pdf_reader.py for Gemini page transcriptions, but nothing here
is Gemini-specific - any step that produces "text for page N of doc X" can use it.
"""

# --- Imports -----------------------------------------------------------------
# hashlib: builds the short "variant" fingerprint.
# os:      reads the optional PAGE_CACHE_DIR setting.
# Path:    friendly file-path handling.
import hashlib
import os
from pathlib import Path

# --- Settings ----------------------------------------------------------------
# Where results are cached. data/ is in .gitignore, so the cache never ends up
# in git. Override with PAGE_CACHE_DIR if you want it elsewhere.
CACHE_DIR = Path(os.getenv("PAGE_CACHE_DIR", "data/cache"))


# --- Variant fingerprint -------------------------------------------------------
def make_variant(*parts: object) -> str:
    """
    Turns the settings that affect a result into an 8-character fingerprint.
    Example: make_variant("gemini-3.5-flash", 200, PROMPT) -> "1711d98d"
    Same settings -> same fingerprint -> same cache folder.
    """
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode()).hexdigest()[:8]


# --- Where one page lives on disk ----------------------------------------------
def cache_path(doc_id: str, variant: str, page_no: int, kind: str = "") -> Path:
    """
    File that holds the result for one page.
    kind lets one page keep results from different readers side by side:
      kind=""    -> .../page_011.md       (main result, e.g. vision model)
      kind="ocr" -> .../page_011.ocr.md   (fallback result, e.g. Tesseract)
    """
    suffix = f".{kind}.md" if kind else ".md"
    return CACHE_DIR / doc_id / variant / f"page_{page_no:03d}{suffix}"


# --- Read one page from the cache ------------------------------------------------
def load(doc_id: str, variant: str, page_no: int, kind: str = "") -> str | None:
    """Returns the cached text for this page, or None if it was never saved."""
    path = cache_path(doc_id, variant, page_no, kind)
    return path.read_text(encoding="utf-8") if path.exists() else None


# --- Write one page to the cache -------------------------------------------------
def save(doc_id: str, variant: str, page_no: int, text: str, kind: str = "") -> None:
    """
    Saves one page's result. Writes to a temp file first, then renames it:
    a crash mid-write can never leave a half-written page in the cache.
    Empty results are not cached, so they get retried next run.
    """
    if not text:
        return
    path = cache_path(doc_id, variant, page_no, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
