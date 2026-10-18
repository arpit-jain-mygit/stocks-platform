"""
docx_format.py - Word documents: headings, paragraphs and tables in document order, grouped
into pages (Word has no fixed pages).
"""

# --- Imports -----------------------------------------------------------------
# io:              read the uploaded bytes.
# python-docx:     reads documents; Table and Paragraph wrap the XML elements.
# DocumentReader, check_office_zip, cell_text, markdown_table, group_into_pages: shared pieces.
import io

from ingest.formats.base import DocumentReader
from ingest.formats.common import cell_text, check_office_zip, group_into_pages, markdown_table


class DocxReader(DocumentReader):
    name = "docx"
    extensions = (".docx",)

    def check(self, data: bytes) -> None:
        check_office_zip(data, ".docx")

    def read(self, data: bytes, doc_id: str, use_cache: bool):
        from docx import Document as WordDocument  # lazy: only Word files need python-docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = WordDocument(io.BytesIO(data))
        blocks = []
        for element in document.element.body.iterchildren():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "p":
                paragraph = Paragraph(element, document)
                text = paragraph.text.strip()
                if not text:
                    continue
                style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
                blocks.append(f"## {text}" if style.startswith("heading") or style == "title" else text)
            elif tag == "tbl":
                rows = [[cell_text(cell.text) for cell in row.cells] for row in Table(element, document).rows]
                if any(any(cell for cell in row) for row in rows):
                    blocks.append(markdown_table(rows))
        return group_into_pages(blocks)
