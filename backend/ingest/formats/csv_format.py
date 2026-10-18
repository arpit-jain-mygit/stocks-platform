"""
csv_format.py - CSV files: the first row is the header; each page is a Markdown table.
"""

# --- Imports -----------------------------------------------------------------
# csv / io:  parse the text.
# DocumentReader, check_utf8, cell_text, table_pages: shared pieces (base.py, common.py).
import csv
import io

from ingest.formats.base import DocumentReader
from ingest.formats.common import cell_text, check_utf8, table_pages


class CsvReader(DocumentReader):
    name = "csv"
    extensions = (".csv",)

    def check(self, data: bytes) -> None:
        check_utf8(data, ".csv")

    def read(self, data: bytes, doc_id: str, use_cache: bool):
        text = data.decode("utf-8-sig")
        rows = [[cell_text(cell) for cell in row] for row in csv.reader(io.StringIO(text))]
        return table_pages("", rows, first_page=1)
