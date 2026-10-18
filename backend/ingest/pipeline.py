"""
pipeline.py - Ingests one PDF end to end, running the steps of this package in order:

    1. ids         PDF bytes -> doc_id                          (ingest/ids.py)
    2. pdf_reader  PDF -> pages (text / vision model / OCR)     (ingest/pdf_reader.py)
    3. chunker     pages -> chunks                              (ingest/chunker.py)
    4. embeddings  chunks -> vectors                            (ingest/embeddings.py)
    5. store       vector store + duplicate check               (ingest/store.py)

The FastAPI endpoint (api/main.py) calls ingest_pdf().

Idempotent: the same PDF is processed only once. A second upload is skipped
straight away (no model calls) unless force=True. If a run fails half-way,
the document is NOT marked complete, so the next run simply tries again -
and thanks to the page and vector caches it only pays for the missing work.
"""

# --- Imports -----------------------------------------------------------------
# One import per step, in pipeline order.
from ingest.ids import doc_id_from_bytes
from ingest.pdf_reader import read_pdf
from ingest.chunker import chunk_pages
from ingest.embeddings import embed_chunks
from ingest import store
from utils.companies import require_company
from utils.doc_types import require_doc_type
from utils.periods import parse_period


# --- Step 1: ids + duplicate check -----------------------------------------------------
def check_existing(pdf_bytes: bytes) -> tuple[str, dict | None]:
    """
    Returns (doc_id, skipped) where `skipped` is the "already ingested" reply
    if this exact PDF is fully stored, else None.
    Cheap (one hash + one Qdrant lookup), so the API calls it before starting
    a background job, and ingest_pdf() calls it before doing any real work.
    """
    store.setup()
    doc_id = doc_id_from_bytes(pdf_bytes)
    if not store.is_ingested(doc_id):
        return doc_id, None
    # Record first, then our fields: the record has its own "status": "complete",
    # which must not overwrite "skipped".
    return doc_id, {**store.get_document(doc_id), "status": "skipped", "detail": "This PDF is already ingested"}


# --- Company + period + doc type: validate and structure ---------------------------------
def describe(company: str, period: str, doc_type: str | None = None) -> dict:
    """
    Turns the caller's company (ID, code, name or alias), period ("Q3 FY25")
    and document type (a code from /doc-types; empty = the default) into the
    fields stored on every chunk and document record, e.g.
      {"company_id": "VIDEOIND", "company": "Videocon Industries Ltd",
       "fiscal_year": 2025, "quarter": 3, "period_end": "2024-12-31",
       "period": "Q3 FY25 (quarter ended 31-Dec-2024)", "doc_type": "quarterly_results"}
    Raises ValueError for an unknown company, unreadable period or unknown doc type.
    """
    found = require_company(company)
    # The period's end date depends on the company's own financial-year end (e.g. March, December).
    return {"company_id": found.company_id, "company": found.name,
            **parse_period(period, found.fy_end_month).fields(),
            "doc_type": require_doc_type(doc_type)}


# --- Main entry point -------------------------------------------------------------
def ingest_pdf(pdf_bytes: bytes, file_name: str, company: str, period: str,
               doc_type: str | None = None, force: bool = False) -> dict:
    """
    Stores one PDF in the vector store and returns a short summary.
    company: ID / exchange code / name / alias of a known company (/companies)
    period:  e.g. "Q3 FY25" or "FY25"
    doc_type: e.g. "annual_report" (/doc-types); empty = quarterly_results
    status = "skipped"  -> this exact PDF was already ingested (nothing done)
             "complete" -> stored now
    Raises ValueError for an unknown company, period or doc type, and RuntimeError
    (leaving status "failed") if a page could not be read or not every chunk
    reached the vector store.
    """
    meta = describe(company, period, doc_type)     # fail fast on bad input

    # 1. ids - and the duplicate check, before any expensive work.
    doc_id, skipped = check_existing(pdf_bytes)
    if skipped and not force:
        print(f"already ingested: {file_name} ({doc_id[:12]}...) - skipping")
        return skipped

    details = {"file_name": file_name, **meta}
    store.save_document(doc_id, status="processing", **details)

    # 2. pdf_reader - a page nobody could read means incomplete data, so stop.
    pages = read_pdf(pdf_bytes)
    failed = [p.page_no for p in pages if p.source == "failed"]
    if failed:
        store.save_document(doc_id, status="failed", error=f"unreadable pages {failed}", **details)
        raise RuntimeError(f"pages {failed} could not be read - fix or re-run before storing")

    # 3. chunker, 4. embeddings
    chunks = chunk_pages(pages, meta["company"], meta["period"])
    vectors = embed_chunks(chunks)

    # 5. store - replace this PDF's chunks, then mark it complete.
    try:
        stored = store.store_chunks(doc_id, file_name, meta, chunks, vectors)
    except RuntimeError as error:
        store.save_document(doc_id, status="failed", error=str(error), **details)
        raise

    summary = {
        **details,
        "status": "complete",
        "pages": len(pages),
        "ocr_pages": [p.page_no for p in pages if p.source == "ocr"],
        "chunks": stored,
    }
    store.save_document(doc_id, **summary)
    print(f"stored {stored} chunks for {file_name} in {store.where()}")
    return {"doc_id": doc_id, **summary}


# --- Command line -------------------------------------------------------------
# Run:  python -m ingest.pipeline data/<file>.pdf VIDEOIND "Q3 FY25" [--doc-type=annual_report] [--force]
#       company can be its ID, BSE code, name or alias (see /companies)
#       --doc-type defaults to quarterly_results (see /doc-types)
#       --force re-stores the PDF even if it was already ingested
#       (handy after changing chunking; the caches keep it cheap).
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Positional values (pdf, company, period) are everything that isn't a --flag,
    # so flags can go anywhere and a missing value gets a clear message.
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(positional) != 3:
        sys.exit('Usage: python -m ingest.pipeline <pdf> <company> <period> [--doc-type=...] [--force]\n'
                 '  e.g. python -m ingest.pipeline data/file.pdf OFSS FY26 --doc-type=financial_statements\n'
                 f'  got {len(positional)} value(s): {positional}')
    pdf_path, company, period = Path(positional[0]), positional[1], positional[2]
    doc_type = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--doc-type=")), None)
    result = ingest_pdf(pdf_path.read_bytes(), pdf_path.name, company, period,
                        doc_type=doc_type, force="--force" in sys.argv)
    print(result)
