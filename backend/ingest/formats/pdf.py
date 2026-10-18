"""
pdf.py - PDF files. Pages come from ingest/pdf_reader.py: the text layer where it exists,
the vision model for scanned and table-heavy pages, and OCR as the last fallback.
"""

# --- Imports -----------------------------------------------------------------
# DocumentReader: the base class (base.py).
# read_pdf: the PDF page reader (ingest/pdf_reader.py).
from ingest.formats.base import DocumentReader
from ingest.pdf_reader import read_pdf


class PdfReader(DocumentReader):
    name = "pdf"
    extensions = (".pdf",)

    def check(self, data: bytes) -> None:
        if not data.startswith(b"%PDF"):
            raise ValueError("File is not a PDF (it does not start with %PDF)")

    def read(self, data: bytes, doc_id: str, use_cache: bool):
        return read_pdf(data, use_cache=use_cache)
