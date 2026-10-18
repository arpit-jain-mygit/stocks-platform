"""
factory.py - Picks the right file reader from a file's extension.

    get_reader("report.xlsx")       -> XlsxReader
    check_format("report.xlsx", b…) -> ".xlsx"   (checks the extension AND the file's content)
    read_document(b…, "report.xlsx") -> list of PageResult

Each reader class is listed once in READER_CLASSES. Adding a format: write one class
(see base.py), add it to the list. The pipeline and the API do not change.
"""

# --- Imports -----------------------------------------------------------------
# os / pathlib: the file extension.
# doc_id_from_bytes: the document's ID (SHA-256 of its bytes).
# One reader class per format (each file is one class, like utils/llm/gemini.py).
from pathlib import Path

from ingest.formats.base import DocumentReader
from ingest.formats.csv_format import CsvReader
from ingest.formats.docx_format import DocxReader
from ingest.formats.pdf import PdfReader
from ingest.formats.pptx_format import PptxReader
from ingest.formats.text_format import TextReader
from ingest.formats.xlsx_format import XlsxReader
from ingest.ids import doc_id_from_bytes

# --- Registry: every format this app can ingest ---------------------------------------------
READER_CLASSES: list[type[DocumentReader]] = [PdfReader, CsvReader, XlsxReader, PptxReader, DocxReader, TextReader]

# Extension -> reader instance (built once). Several extensions may share a reader (.txt, .md).
READERS: dict[str, DocumentReader] = {ext: cls() for cls in READER_CLASSES for ext in cls.extensions}
SUPPORTED: tuple[str, ...] = tuple(sorted(READERS))


def extension(file_name: str) -> str:
    """'Report.XLSX' -> '.xlsx'."""
    return Path(file_name or "").suffix.lower()


def get_reader(file_name: str) -> DocumentReader:
    """The reader for this file's extension. Raises ValueError listing the supported types."""
    ext = extension(file_name)
    if ext not in READERS:
        raise ValueError(f"File type {ext or '(none)'!r} is not supported. Allowed: {', '.join(SUPPORTED)}")
    return READERS[ext]


def check_format(file_name: str, data: bytes) -> str:
    """Returns the extension when the file is supported AND its content matches it. Raises ValueError."""
    reader = get_reader(file_name)
    reader.check(data)
    return extension(file_name)


def read_document(data: bytes, file_name: str, use_cache: bool = True):
    """Checks the file, then reads it with the right reader. Returns its pages, in order."""
    reader = get_reader(file_name)
    reader.check(data)
    return reader.read(data, doc_id_from_bytes(data), use_cache)
