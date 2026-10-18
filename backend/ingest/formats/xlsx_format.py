"""
xlsx_format.py - Excel workbooks: one section per sheet (titled with the sheet name), each
sheet's first non-empty row is its header. Stored formula values are used, not recalculated.
"""

# --- Imports -----------------------------------------------------------------
# io:        read the uploaded bytes.
# openpyxl:  reads Excel workbooks.
# DocumentReader, check_office_zip, cell_text, table_pages: shared pieces.
import io

from ingest.formats.base import DocumentReader
from ingest.formats.common import cell_text, check_office_zip, table_pages


class XlsxReader(DocumentReader):
    name = "xlsx"
    extensions = (".xlsx",)

    def check(self, data: bytes) -> None:
        check_office_zip(data, ".xlsx")

    def read(self, data: bytes, doc_id: str, use_cache: bool):
        import openpyxl  # lazy: only spreadsheets need it
        workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        pages = []
        for sheet in workbook.worksheets:
            numbered = list(enumerate(sheet.iter_rows(values_only=True), start=1))   # keep the sheet's own row numbers
            rows = [[cell_text(cell) for cell in row] for _, row in numbered]
            pages += table_pages(sheet.title, rows, first_page=len(pages) + 1,
                                 row_numbers=[number for number, _ in numbered])
        workbook.close()
        return pages
