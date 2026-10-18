"""
pdf_reader.py - Turns a PDF into clean text, one page at a time.

Why this file exists:
Financial result PDFs are a mix of two kinds of pages:
- "Text" pages: the PDF has a real text layer (e.g. a typed cover letter).
  PyMuPDF can pull the text out directly - fast and free.
- "Scanned" pages: the page is just a photo of paper (e.g. the P&L table).
  There is no text to pull out, so we render the page as an image and hand
  it to the vision model (get_llm("vision"), utils/llm) to transcribe into Markdown.
  If the vision model refuses the page (RECITATION), we fall back to local
  OCR (utils/ocr.py). If nothing can read it, the page is marked "failed"
  with the reason - never silently left blank.

Typed pages that are mostly figures (financial statements) go to the vision
model too: their text layer has the numbers but not the table layout (which
number is 2026 and which 2025). Switch off with TABLE_PAGES_TO_VISION=false.

Output: a list of PageResult objects, one per page, ready for chunking.

Scanned-page results are saved in the page cache (utils/page_cache.py), so
re-running on the same PDF never pays for the same page twice. If a run
crashes on page 9, pages 4-8 are already cached and the next run only
processes pages 9-13.
"""

# --- Imports -----------------------------------------------------------------
# dataclass:   a quick way to define a simple "record" class (PageResult).
# Path:        friendly file-path handling.
# pymupdf:     opens PDFs, reads text, and renders pages to images.
# llm:         the configured vision model (utils/llm) - image in, text out.
# page_cache:  disk cache for per-page results (utils/page_cache.py).
# prompts:     instructions sent with each page image (utils/prompts.py).
# ocr:         local Tesseract fallback (utils/ocr.py).
# doc_id_from_bytes: same PDF -> same ID (ingest/ids.py).
# (Importing anything from utils also loads the local .env file.)
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from utils import ocr, page_cache, prompts
from utils.llm import LLMBlocked, RecitationBlocked, get_llm, role_settings
from ingest.ids import doc_id_from_bytes

# --- Settings ----------------------------------------------------------------
# A page with fewer characters than this is treated as "scanned".
# Real text pages have hundreds or thousands; scanned pages have 0.
MIN_TEXT_CHARS = 50

# Typed pages that are mostly figures are read by the vision model too, so the
# table keeps its columns. A page counts as a table page when at least
# TABLE_NUMERIC_SHARE of its lines are figures ("1,305", "(26.99)", "34%",
# "5 times", "-") and it has at least TABLE_MIN_LINES lines.
TABLE_PAGES_TO_VISION = os.getenv("TABLE_PAGES_TO_VISION", "true").lower() == "true"
TABLE_NUMERIC_SHARE = 0.35
TABLE_MIN_LINES = 15
# A figure: optional bracket / minus, optional currency (₹ $ € £ ¥, Rs, US$), digits with any
# grouping (1,234.5  1.234,5  1,23,456.7  1 234), optional closing bracket, %, "times" or "x";
# or a lone dash (an empty cell).
FIGURE_LINE = re.compile(
    r"^[(\-–]?(?:[₹$€£¥`]|rs\.?|us\$)?\s?\d[\d,.\u00a0 ]*\)?\s?(%|times|x)?$|^[-–—]$",
    re.IGNORECASE)

# Image resolution used when rendering a scanned page. Higher = sharper small
# print (pages with tiny notes need ~200), but bigger images and slower calls.
RENDER_DPI = 200

# Fingerprint of everything that shapes a scanned page's text: model, image
# resolution and prompt. Change any of them -> new cache folder, fresh results.
VISION_MODEL = role_settings("vision")["model"]
CACHE_VARIANT = page_cache.make_variant(VISION_MODEL, RENDER_DPI, prompts.TRANSCRIBE_PAGE)


# --- Result record -------------------------------------------------------------
@dataclass
class PageResult:
    """What we know about one page after reading it."""
    page_no: int     # 1-based page number, same as a PDF viewer shows
    text: str        # the page content (plain text or Markdown); "" if failed
    source: str      # "text"   = read from the PDF's text layer
                     # "vision" = read from page image by the vision model
                     # "ocr"    = vision model refused, read by local OCR
                     # "failed" = nothing could read it (see error)
    error: str = ""  # why the page failed or fell back; "" when all went well


# --- Decide: text page or scanned page? ----------------------------------------
def has_text_layer(page: pymupdf.Page) -> bool:
    """True if PyMuPDF can read enough real text from this page."""
    return len(page.get_text().strip()) >= MIN_TEXT_CHARS


def is_table_page(text: str) -> bool:
    """True if a typed page is mostly figures (a financial statement or table)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < TABLE_MIN_LINES:
        return False
    return sum(bool(FIGURE_LINE.match(line)) for line in lines) / len(lines) >= TABLE_NUMERIC_SHARE


# --- Render a page to an image ---------------------------------------------------
def page_to_png(page: pymupdf.Page, dpi: int = RENDER_DPI) -> bytes:
    """Draws the page as a PNG picture and returns the image bytes."""
    pixmap = page.get_pixmap(dpi=dpi)
    return pixmap.tobytes("png")


# --- Read one scanned page ---------------------------------------------------------
def read_scanned_page(page: pymupdf.Page, doc_id: str, page_no: int, use_cache: bool,
                      text_layer: str | None = None) -> PageResult:
    """
    Reads one page from its image, cheapest option first:
      1. cached vision result      -> "vision"  (free)
      2. cached OCR fallback       -> "ocr"     (free; vision model refused it before,
                                                 so don't ask again)
      3. vision model              -> "vision"
      4. the model gave no usable text:
         - typed table page (text_layer given) -> its own text layer -> "text"
         - scanned page refused (RECITATION)   -> local OCR -> "ocr"
         - anything else                        -> "failed" with the reason
    Successful results are cached straight away; failures are not, so they are
    retried on the next run.
    """
    # 1 + 2: already read in an earlier run.
    if use_cache:
        cached = page_cache.load(doc_id, CACHE_VARIANT, page_no)
        if cached is not None:
            print(f"page {page_no}: {'table' if text_layer else 'scanned'} -> cache")
            return PageResult(page_no, cached, "vision")
        cached = page_cache.load(doc_id, CACHE_VARIANT, page_no, kind="ocr")
        if cached is not None:
            print(f"page {page_no}: scanned -> cache (ocr)")
            return PageResult(page_no, cached, "ocr", error="vision model refused (RECITATION)")

    # 3: ask the vision model.
    print(f"page {page_no}: {'table (typed)' if text_layer else 'scanned'} -> vision model ({VISION_MODEL})")
    try:
        markdown = get_llm("vision").describe_image(page_to_png(page), prompts.TRANSCRIBE_PAGE)
        page_cache.save(doc_id, CACHE_VARIANT, page_no, markdown)
        return PageResult(page_no, markdown, "vision")
    except LLMBlocked as blocked:
        # 4a: a typed page always has its own text as a fallback.
        if text_layer is not None:
            print(f"page {page_no}:   vision model gave no text -> text layer")
            return PageResult(page_no, text_layer, "text", error=f"table page, vision failed: {blocked}")
        # 4b: a scanned page refused because the wording looks already published.
        if isinstance(blocked, RecitationBlocked):
            return ocr_fallback(page, doc_id, page_no, blocked)
        # 4c: empty / cut-off / filtered reply -> flag it, don't hide it.
        print(f"page {page_no}:   FAILED: {blocked}")
        return PageResult(page_no, "", "failed", error=str(blocked))


def ocr_fallback(page: pymupdf.Page, doc_id: str, page_no: int, refused: Exception) -> PageResult:
    """A scanned page the vision model refused (RECITATION) -> local OCR."""
    print(f"page {page_no}:   refused (RECITATION) -> local OCR")
    try:
        text = ocr.ocr_page(page)
    except RuntimeError as ocr_error:
        return PageResult(page_no, "", "failed", error=f"{refused}; OCR failed: {ocr_error}")
    if not text:
        return PageResult(page_no, "", "failed", error=f"{refused}; OCR found no text")
    page_cache.save(doc_id, CACHE_VARIANT, page_no, text, kind="ocr")
    return PageResult(page_no, text, "ocr", error="vision model refused (RECITATION)")


# --- Main entry point: read a whole PDF -------------------------------------------
def read_pdf(
    pdf_bytes: bytes,
    force_vision: bool = False,
    use_cache: bool = True,
) -> list[PageResult]:
    """
    Reads every page of a PDF and returns one PageResult per page.

    pdf_bytes:    the raw PDF (from an upload or Path.read_bytes()).
    force_vision: True = read every page from its image, even text pages.
                  Useful if a text page contains a table whose layout
                  gets scrambled by plain text extraction.
    use_cache:    True  = reuse saved results for pages already done.
                  False = re-read every scanned page
                          (fresh results still overwrite the cache).

    Pages that could not be read come back with source="failed" and an
    error message, so the caller can decide what to do (skip, retry, stop).
    """
    doc_id = doc_id_from_bytes(pdf_bytes)
    results: list[PageResult] = []

    # Open the PDF straight from memory - no temp file needed.
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for index, page in enumerate(doc):
            page_no = index + 1

            # Cheap path: the page already has real text...
            if not force_vision and has_text_layer(page):
                text = page.get_text().strip()
                # ...unless it is mostly figures: then the vision model rebuilds the
                # table (columns + years), with the text layer as fallback.
                if TABLE_PAGES_TO_VISION and is_table_page(text):
                    results.append(read_scanned_page(page, doc_id, page_no, use_cache, text_layer=text))
                    continue
                results.append(PageResult(page_no, text, "text"))
                print(f"page {page_no}: text layer")
                continue

            # Scanned page: cache, vision model, or OCR fallback.
            results.append(read_scanned_page(page, doc_id, page_no, use_cache))

    return results


# --- Quick manual test -------------------------------------------------------
# Run:  .venv/bin/python -m ingest.pdf_reader data/<file>.pdf
#       add --refresh to ignore the cache and re-read scanned pages
# Prints progress per page and writes everything to data/<file>.pages.md
# so you can open it and check the tables came out right.
if __name__ == "__main__":
    import sys

    pdf_path = Path(sys.argv[1])
    refresh = "--refresh" in sys.argv
    pages = read_pdf(pdf_path.read_bytes(), use_cache=not refresh)

    out_path = pdf_path.with_suffix(".pages.md")
    with open(out_path, "w", encoding="utf-8") as f:
        for p in pages:
            f.write(f"\n\n<!-- page {p.page_no} | source: {p.source} -->\n\n")
            # Failed pages get a visible marker instead of an empty gap.
            f.write(p.text if p.source != "failed" else f"> **PAGE FAILED:** {p.error}")

    # Summary: how each page was read, and loud warnings for problems.
    counts = {s: sum(p.source == s for p in pages) for s in ("text", "vision", "ocr", "failed")}
    print(f"\n{len(pages)} pages: {counts['text']} text, {counts['vision']} vision, "
          f"{counts['ocr']} ocr, {counts['failed']} failed. Output: {out_path}")

    ocr_pages = [p.page_no for p in pages if p.source == "ocr"]
    if ocr_pages:
        print(f"NOTE: pages {ocr_pages} were read by local OCR (plain text, tables not rebuilt).")

    failed = [p for p in pages if p.source == "failed"]
    for p in failed:
        print(f"WARNING: page {p.page_no} FAILED - {p.error}")
    sys.exit(1 if failed else 0)   # non-zero exit = something needs attention
