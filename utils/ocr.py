"""
ocr.py - Local, free OCR with Tesseract, used as a fallback.

Why this file exists:
Gemini sometimes refuses to transcribe a page (RECITATION) because standard
auditor/legal wording looks like text already published on the web.
Tesseract runs on your own machine, has no such filter and no quota, so it
can always read those pages.

Trade-off: Tesseract returns plain text lines - it does NOT rebuild tables.
That is fine for the pages Gemini refuses (they are paragraphs of prose),
but it is why Gemini stays the first choice for scanned pages.

Needs the Tesseract program installed on the machine:
  macOS:   brew install tesseract
  Railway: install the "tesseract-ocr" system package in the container.
PyMuPDF talks to it directly, so no extra Python package is needed.
"""

# --- Imports -----------------------------------------------------------------
# os:      reads the optional TESSDATA_PREFIX / OCR_LANGUAGE settings.
# pymupdf: renders the page and hands it to Tesseract.
import os

import pymupdf

# --- Settings ----------------------------------------------------------------
# Tesseract reads small print best at around 300 DPI.
OCR_DPI = 300

# Tesseract language pack(s) to use. "eng" = English.
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "eng")


# --- Is Tesseract available? -----------------------------------------------------
def tessdata_dir() -> str | None:
    """
    Folder holding Tesseract's language files, or None if Tesseract
    isn't installed. Uses TESSDATA_PREFIX if set, otherwise asks PyMuPDF
    to find it.
    """
    try:
        return os.getenv("TESSDATA_PREFIX") or pymupdf.get_tessdata()
    except RuntimeError:
        return None


# --- OCR one page --------------------------------------------------------------
def ocr_page(page: pymupdf.Page, dpi: int = OCR_DPI) -> str:
    """
    Reads a scanned page with Tesseract and returns its plain text.
    Raises RuntimeError if Tesseract is not installed.
    """
    tessdata = tessdata_dir()
    if tessdata is None:
        raise RuntimeError("Tesseract is not installed (macOS: brew install tesseract).")

    # full=True: OCR the whole page as one image (scanned pages have no text
    # layer to keep anyway).
    textpage = page.get_textpage_ocr(dpi=dpi, full=True, language=OCR_LANGUAGE, tessdata=tessdata)
    return page.get_text(textpage=textpage).strip()
