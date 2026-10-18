"""
common.py - Helpers shared by the format readers: cell text, Markdown tables, paging.

Every reader turns its content into Markdown tables or plain paragraphs, so the chunker's
rules (fact cards per table row, headings, labels) apply to every file type the same way.
"""

# --- Imports -----------------------------------------------------------------
# datetime:  dates in spreadsheets.
# zipfile / io: Office files (.xlsx, .pptx, .docx) are zip archives.
# os:        optional page-size settings.
import datetime
import io
import os
import zipfile

from ingest.pdf_reader import PageResult

# --- Settings ----------------------------------------------------------------
# Rows per page for spreadsheets and CSV. Each page repeats the header row, so every
# chunk still knows what its columns are.
MAX_ROWS_PER_PAGE = int(os.getenv("MAX_ROWS_PER_PAGE", "60"))
# Characters per page for plain text and Word documents (they have no real pages).
CHARS_PER_PAGE = int(os.getenv("CHARS_PER_PAGE", "4000"))


def check_office_zip(data: bytes, extension: str) -> None:
    """Office files must be zip archives (xlsx / pptx / docx). Raises ValueError otherwise."""
    if not data.startswith(b"PK\x03\x04") or not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError(f"File is not a valid {extension} file")


def check_utf8(data: bytes, extension: str) -> None:
    """Text formats must be UTF-8. Raises ValueError otherwise."""
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(f"{extension} files must be UTF-8 text")


def cell_text(value) -> str:
    """One cell as text: numbers keep their precision and get thousands separators; dates as ISO."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{int(value):,}" if value.is_integer() else f"{value:,}"
    if isinstance(value, datetime.datetime):
        return value.date().isoformat() if value.time() == datetime.time(0) else value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value).replace("\n", " ").strip()


def markdown_table(rows: list[list[str]]) -> str:
    """Rows (first one is the header) -> a Markdown table. Pipes in cells are escaped."""
    width = max(len(row) for row in rows)
    padded = [[cell.replace("|", "\\|") for cell in row] + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(padded[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(row) + " |" for row in padded[1:]]
    return "\n".join(lines)


def table_pages(title: str, rows: list[list[str]], first_page: int,
                row_numbers: list[int] | None = None) -> list[PageResult]:
    """
    Splits table rows into pages of MAX_ROWS_PER_PAGE. Each page starts with the title (a
    heading, if any) and repeats the header row. Pages are numbered from first_page.

    row_numbers: the row numbers in the original file (1 = first row), so each page can say
    which rows it holds even when blank rows were skipped. Each page gets a location label,
    e.g. "sheet 'Income Statements', rows 2-61", which is what citations show for spreadsheets.
    """
    numbered = [(n, row) for n, row in zip(row_numbers or range(1, len(rows) + 1), rows)
                if any(cell.strip() for cell in row)]
    if not numbered:
        return []
    (header_no, header), body = numbered[0], numbered[1:]
    pages = []
    for start in range(0, max(len(body), 1), MAX_ROWS_PER_PAGE):
        chunk = body[start:start + MAX_ROWS_PER_PAGE]
        first_no = chunk[0][0] if chunk else header_no
        last_no = chunk[-1][0] if chunk else header_no
        rows_label = f"rows {first_no}" if first_no == last_no else f"rows {first_no}-{last_no}"
        location = f"sheet '{title}', {rows_label}" if title else rows_label
        text = (f"## {title}\n\n" if title else "") + markdown_table([header] + [row for _, row in chunk])
        pages.append(PageResult(first_page + len(pages), text, "text", location=location))
    return pages


def group_into_pages(blocks: list[str]) -> list[PageResult]:
    """Joins text blocks (paragraphs, headings, tables) into pages of about CHARS_PER_PAGE characters."""
    pages, current = [], ""
    for block in blocks:
        if current and len(current) + len(block) > CHARS_PER_PAGE:
            pages.append(PageResult(len(pages) + 1, current.strip(), "text"))
            current = ""
        current += block + "\n\n"
    if current.strip():
        pages.append(PageResult(len(pages) + 1, current.strip(), "text"))
    return pages
