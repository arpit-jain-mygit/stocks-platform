"""
chunker.py - Cuts the pages from pdf_reader into "cards" (chunks) for search.

The strategies, in the order they run:
  1. Clean      - drop stamps/signatures, OCR junk and the footer repeated on every page.
  2. Paragraphs - turn each page into paragraphs, headings and tables.
  3. Join pages - a paragraph cut by a page break is glued back together.
  4. Cut        - tables stay whole; prose is cut at headings and numbered points,
                  kept between MIN_WORDS and MAX_WORDS, with a small overlap
                  when a long text has to be split.
  5. Label      - every card starts with "company | period | section" so it
                  still makes sense on its own.
  6. Facts      - (optional) one small card per table row, so direct questions
                  like "what were finance costs?" match easily.
"""

# --- Imports -----------------------------------------------------------------
# re:         pattern matching for labels like "a)", "(ii)", "5.".
# Counter:    counts how many pages a line appears on (to find footers).
# dataclass:  simple record classes (Block, Chunk).
# PageResult: one page of text from pdf_reader.py.
import re
from collections import Counter
from dataclasses import dataclass

from ingest.pdf_reader import PageResult

# --- Settings ----------------------------------------------------------------
MIN_WORDS = 80           # don't start a new card at a numbered point if the current one is this small
MAX_WORDS = 400          # a prose card is closed once it reaches this size
OVERLAP_SENTENCES = 1    # sentences repeated when one long text is split into several cards
MAKE_FACT_CARDS = True   # also make one small card per table row

# A line counts as a repeated page header / footer only if it is on at least
# 3 pages AND on at least this share of all pages (a letterhead on 3 of 13
# pages: yes; a table label like "Revenue from operations" on 6 of 196: no).
REPEAT_PAGE_SHARE = 0.2

# Repeated lines that must never be removed: they carry units.
KEEP_ALWAYS = re.compile(r"amounts? in|in (₹|rs\.?|inr)|million|crore|lakh", re.IGNORECASE)

# A numbered point at the start of a line: "5. ", "a) ", "(ii) ", "xiv) ", "iv.) "
LABEL = re.compile(r"^\(?(\d{1,2}|[a-z]|[ivx]{1,5})[.)]\)?\s", re.IGNORECASE)

# Notes the vision model writes for stamps and signatures: "[Stamp: ...]", "[Signature]"
STAMP_OR_SIGNATURE = re.compile(r"\[(Stamp|Signature)[^\]]*\]")


# --- Records -------------------------------------------------------------------
@dataclass
class Block:
    """One piece of a page before cutting: a heading, a paragraph or a table."""
    kind: str          # "heading", "para" or "table"
    text: str
    page_start: int
    page_end: int
    source: str        # how the page was read: "text", "vision" or "ocr"


@dataclass
class Chunk:
    """One card, ready to be embedded and stored."""
    kind: str          # "prose", "table" or "fact"
    section: str       # nearest heading, e.g. "5. Basis for Disclaimer of Conclusion"
    text: str          # label line + body - this is what gets embedded
    page_start: int
    page_end: int
    source: str
    chunk_no: int = 0  # position in the document, set at the end


# --- Small helpers ---------------------------------------------------------------
def word_count(text: str) -> int:
    return len(text.split())


def short(text: str, max_words: int = 12) -> str:
    """First few words of a text, used for section names ("Notes: -" -> "Notes")."""
    words = text.strip("#:- ").split()
    return " ".join(words[:max_words]) + (" ..." if len(words) > max_words else "")


def is_heading(text: str) -> bool:
    """
    A heading is one of:
      - a Markdown "#" line, or a "Notes" / "Sub.:" line
      - a short numbered title, e.g. "5. Basis for Disclaimer of Conclusion"
      - a short line in CAPITALS of 2+ words, no digits or ":",
        e.g. "VIDEOCON INDUSTRIES LIMITED" (not a one-word logo like "ORACLE",
        not a code like "CIN: L99999MH1986PLC103624")
    Lines that are mostly numbers are never headings - they are table remnants,
    e.g. "(45) (45) Other financial assets".
    (The vision model doesn't always add "#", so the last two rules matter.)
    """
    if text.startswith("#") or text.lower().startswith(("notes", "sub.:", "subject:")):
        return True
    if word_count(text) > 12:
        return False
    tokens = text.split()
    body = tokens[1:] if LABEL.match(text) else tokens          # "7." in "7. Other Matters" is a label, not data
    is_number = [bool(re.fullmatch(r"[\d,.()\-–]+", tok)) for tok in body]
    # A title never starts with a figure after its label ("(45) (45) Other ..." is a table remnant).
    if not body or is_number[0] or sum(is_number) / len(body) >= 0.3:
        return False
    real_words = re.findall(r"[A-Za-z]{2,}", text)
    if LABEL.match(text) and not text.endswith(".") and len(real_words) >= 2:
        return True
    if re.search(r"[\d:]", text):
        return False
    letters = [ch for ch in text if ch.isalpha()]
    word_tokens = [tok for tok in tokens if re.search(r"[A-Za-z]", tok)]
    return (len(word_tokens) >= 2 and len(letters) >= 4
            and sum(ch.isupper() for ch in letters) / len(letters) > 0.6)


def is_junk(line: str) -> bool:
    """OCR noise from stamps/signatures: fewer than 2 real words, e.g. 'wos?' or '| Martered'."""
    real_words = re.findall(r"[A-Za-z]{3,}", line)
    return len(real_words) < 2 and not LABEL.match(line)


# --- Strategy 1: clean ------------------------------------------------------------
def find_repeated_lines(pages: list[PageResult]) -> set[str]:
    """
    Letterhead / page-header / footer lines: printed on at least 3 pages and on
    at least REPEAT_PAGE_SHARE of all pages. Never removed, however often they
    repeat: lines without letters (figures like "17,210" or "(26.99)") and
    units lines ("Amounts in ₹ million") - those are data, not decoration.
    """
    counts = Counter()
    for page in pages:
        counts.update({line.strip() for line in page.text.splitlines() if line.strip()})
    threshold = max(3, REPEAT_PAGE_SHARE * len(pages))
    return {line for line, n in counts.items()
            if n >= threshold and re.search(r"[A-Za-z]", line) and not KEEP_ALWAYS.search(line)}


def clean_lines(page: PageResult, repeated: set[str]) -> list[str]:
    """Returns the page's lines with stamps, bold/italic marks, footers and OCR junk removed."""
    text = STAMP_OR_SIGNATURE.sub("", page.text).replace("*", "")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line in repeated or line == "---":
            continue
        if page.source == "ocr" and line and is_junk(line):
            continue
        lines.append(line)   # empty lines are kept: they separate paragraphs
    return lines


# --- Strategy 2: paragraphs, headings, tables -------------------------------------
def page_to_blocks(page: PageResult, repeated: set[str]) -> list[Block]:
    """Groups a page's lines into headings, paragraphs and tables."""
    blocks: list[Block] = []
    para: list[str] = []
    table: list[str] = []

    def close_para():
        if para:
            text = " ".join(para)
            if is_heading(text):
                blocks.append(Block("heading", text.lstrip("# "), page.page_no, page.page_no, page.source))
            else:
                blocks.append(Block("para", text, page.page_no, page.page_no, page.source))
            para.clear()

    def close_table():
        if table:
            blocks.append(Block("table", "\n".join(table), page.page_no, page.page_no, page.source))
            table.clear()

    for line in clean_lines(page, repeated):
        if line.startswith("|"):              # table row
            close_para()
            table.append(line)
            continue
        close_table()
        # On vision/OCR pages a heading can sit directly above its text with no
        # blank line ("7. Other Matters" + next line), so check each line.
        # (Not on "text" pages: their long sentences are wrapped over many
        # short lines, which would look like headings.)
        heading_line = page.source != "text" and bool(line) and is_heading(line)
        # A blank line, a heading, or (on OCR pages, which have no blank
        # lines) a numbered point starts a new paragraph.
        if not line or heading_line or (page.source == "ocr" and LABEL.match(line)):
            close_para()
        if line:
            para.append(line)
        if heading_line:                     # a heading line stands alone
            close_para()

    close_para()
    close_table()
    return blocks


# --- Strategy 3: join paragraphs split by a page break ------------------------------
def join_across_pages(blocks: list[Block]) -> list[Block]:
    """
    If a page ends mid-sentence and the next page starts in lowercase,
    the two parts are one paragraph: glue them and record both pages.
    """
    joined: list[Block] = []
    for block in blocks:
        prev = joined[-1] if joined else None
        if (prev and prev.kind == block.kind == "para"
                and block.page_start == prev.page_end + 1
                and not prev.text.endswith((".", ":"))
                and block.text[:1].islower()):
            prev.text += " " + block.text
            prev.page_end = block.page_end
        else:
            joined.append(block)
    return joined


# --- Strategy 4a: split one long text with overlap ----------------------------------
def split_long_text(text: str) -> list[str]:
    """
    Cuts a text longer than MAX_WORDS at sentence ends. Each new piece repeats
    the last OVERLAP_SENTENCES sentences of the previous one, so a sentence
    on the cut is never lost.
    """
    sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(])", text)
    pieces, current = [], []
    for sentence in sentences:
        current.append(sentence)
        if word_count(" ".join(current)) >= MAX_WORDS:
            pieces.append(" ".join(current))
            current = current[-OVERLAP_SENTENCES:] if OVERLAP_SENTENCES else []
    if current and (not pieces or len(current) > OVERLAP_SENTENCES):
        pieces.append(" ".join(current))
    return pieces


# --- Strategy 6: one fact card per table row ------------------------------------------
def table_to_facts(table: str) -> list[str]:
    """
    Turns each table row into one sentence, e.g.
      "f Finance costs: Quarter Ended 31.12.2024 (Unaudited) = 24,023.62; ..."
    Columns whose header contains a digit (a date) hold the numbers.
    A row whose number cells are all blank ("ii) Segment Results") is a group
    name and is put in front of the rows below it, so "Crude Oil and Natural
    Gas" under revenue and under results don't look the same.
    """
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in table.splitlines()]
    header, body = rows[0], rows[2:]                 # rows[1] is the |---| line
    number_cols = [i for i, h in enumerate(header) if re.search(r"\d", h)]
    label_cols = [i for i in range(len(header)) if i not in number_cols]

    facts, group = [], ""
    for row in body:
        if len(row) != len(header):
            continue
        label = " ".join(row[i] for i in label_cols if row[i])
        if re.fullmatch(r"[IVX]+", row[0]):          # top-level row (I, II, ...) ends the old group
            group = ""
        if all(row[i] == "" for i in number_cols):   # no numbers at all -> group name
            group = label or group
            continue
        values = [(header[i], row[i]) for i in number_cols if row[i] not in ("", "-")]
        if values:                                   # rows of only "-" have nothing to say
            name = f"{group} > {label}" if group else label
            facts.append(f"{name}: " + "; ".join(f"{h} = {v}" for h, v in values))
    return facts


# --- Main entry point -------------------------------------------------------------------
def chunk_pages(pages: list[PageResult], company: str, period: str) -> list[Chunk]:
    """Runs all strategies and returns the cards in document order."""
    repeated = find_repeated_lines(pages)
    blocks = [block for page in pages for block in page_to_blocks(page, repeated)]
    blocks = join_across_pages(blocks)

    chunks: list[Chunk] = []
    section = "General"
    buffer: list[Block] = []     # prose waiting to become a card
    last_caption = ""            # last table units line, e.g. "(₹ In Million ...)"

    # Strategy 5: every card starts with a label line.
    def add_chunk(kind: str, body: str, first: Block, last: Block):
        label = f"{company} | {period} | {section}"
        chunks.append(Chunk(kind, section, f"{label}\n\n{body}",
                            first.page_start, last.page_end, first.source))

    def flush_prose():
        # Nothing to write, or only a heading (e.g. a table title) - the
        # heading already appears in the label line, so skip it.
        if all(block.kind == "heading" for block in buffer):
            buffer.clear()
            return
        body = "\n\n".join(block.text for block in buffer)
        pieces = split_long_text(body) if word_count(body) > MAX_WORDS else [body]
        for piece in pieces:
            add_chunk("prose", piece, buffer[0], buffer[-1])
        buffer.clear()

    for block in blocks:
        # Heading: close the current card; the heading opens the next one.
        if block.kind == "heading":
            flush_prose()
            section = short(block.text)
            buffer.append(block)

        # Table: always one whole card. A short "(₹ In Million ...)" line just
        # before it is its caption, so it moves into the table card. A table
        # without its own caption reuses the last one seen in this document,
        # so its numbers still carry their units.
        elif block.kind == "table":
            if buffer and buffer[-1].text.startswith("(") and word_count(buffer[-1].text) <= 12:
                last_caption = buffer.pop().text + "\n"
            caption = last_caption
            flush_prose()
            add_chunk("table", caption + block.text, block, block)
            if MAKE_FACT_CARDS:
                for fact in table_to_facts(block.text):
                    add_chunk("fact", fact + (f" {caption.strip()}" if caption else ""), block, block)

        # Paragraph: a numbered point starts a new card, unless the current
        # card is still tiny. A card is closed once it is big enough.
        else:
            buffer_words = sum(word_count(b.text) for b in buffer)
            # A new page starts a new card (keeps citations page-accurate),
            # unless the current card is still tiny. A paragraph that runs
            # across the page break was already glued into one block.
            new_page = bool(buffer) and block.page_start > buffer[-1].page_end
            if (LABEL.match(block.text) or new_page) and buffer_words >= MIN_WORDS:
                flush_prose()
            buffer.append(block)
            if buffer_words + word_count(block.text) >= MAX_WORDS:
                flush_prose()

    flush_prose()
    for number, chunk in enumerate(chunks):
        chunk.chunk_no = number
    return chunks


# --- Quick manual test -------------------------------------------------------
# Run:  python -m ingest.chunker data/<file>.pdf VIDEOIND "Q3 FY25"
#       company + period are validated like the pipeline (same chunk labels).
# Reads the PDF (from cache - no model calls if already read), cuts it into
# cards, prints a summary and writes every card to data/<file>.chunks.md.
if __name__ == "__main__":
    import sys
    from pathlib import Path

    from ingest.pdf_reader import read_pdf
    from ingest.pipeline import describe

    pdf_path = Path(sys.argv[1])
    meta = describe(sys.argv[2], sys.argv[3])
    cards = chunk_pages(read_pdf(pdf_path.read_bytes()), meta["company"], meta["period"])

    out_path = pdf_path.with_suffix(".chunks.md")
    with open(out_path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(f"\n\n===== chunk {c.chunk_no} | {c.kind} | pages {c.page_start}-{c.page_end} "
                    f"| {c.source} | {word_count(c.text)} words =====\n{c.text}\n")

    kinds = Counter(c.kind for c in cards)
    sizes = [word_count(c.text) for c in cards if c.kind == "prose"]
    print(f"\n{len(cards)} chunks: {dict(kinds)}")
    print(f"prose size: min {min(sizes)}, max {max(sizes)}, avg {sum(sizes) // len(sizes)} words")
    print(f"Output: {out_path}")
