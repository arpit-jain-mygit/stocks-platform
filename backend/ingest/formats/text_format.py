"""
text_format.py - Plain text (.txt) and Markdown (.md): paragraphs, grouped into pages.
"""

# --- Imports -----------------------------------------------------------------
# DocumentReader, check_utf8, group_into_pages: shared pieces (base.py, common.py).
from ingest.formats.base import DocumentReader
from ingest.formats.common import check_utf8, group_into_pages


class TextReader(DocumentReader):
    name = "text"
    extensions = (".txt", ".md")

    def check(self, data: bytes) -> None:
        check_utf8(data, "text")

    def read(self, data: bytes, doc_id: str, use_cache: bool):
        text = data.decode("utf-8-sig").replace("\r\n", "\n")
        return group_into_pages([p.strip() for p in text.split("\n\n") if p.strip()])
