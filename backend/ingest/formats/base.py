"""
base.py - The common shape every file-format reader follows.

Like utils/llm/base.py and utils/vectorstore/base.py: each file type is one class
(csv_format.py, xlsx_format.py ...) that fills in these methods, and factory.py
picks the right class from the file extension. The rest of the app (pipeline,
chunker, storage) only sees a list of PageResult and never knows the file type.

To add a format: write one DocumentReader subclass, list it in factory.py. Nothing else changes.
"""

# --- Imports -----------------------------------------------------------------
# PageResult: the page record every reader returns (defined with the PDF reader).
from ingest.pdf_reader import PageResult


class DocumentReader:
    """One file type. Subclasses set `extensions` and implement read()."""

    name = "base"                  # e.g. "csv", "xlsx"
    extensions: tuple[str, ...] = ()   # e.g. (".csv",)

    def check(self, data: bytes) -> None:
        """Raises ValueError if these bytes are not really this file type (default: no check)."""

    def read(self, data: bytes, doc_id: str, use_cache: bool) -> list[PageResult]:
        """The file's pages, in order. doc_id is the SHA-256 of the bytes (used for the page cache)."""
        raise NotImplementedError(f"{self.name} reader must implement read()")

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(self.extensions)})"
