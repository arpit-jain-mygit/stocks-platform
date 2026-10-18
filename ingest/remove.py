"""
remove.py - Removes ingested data from BOTH stores, so they never disagree:
chunks from the vector store (Qdrant) and records from the metadata store (Postgres).

Three operations, each with dry_run (default True = only report, change nothing):
  remove_filing(doc_id)                         one PDF
  remove_company_filings(company, period, doc_type)   a company's PDFs (optionally one period / type)
  remove_company(company)                       filings + chunks + aliases + the company itself

Order inside each: chunks first, then records. If something fails half-way,
what's left is a record whose chunks are gone - re-running the same call
finishes the job (or a --force re-ingest restores the chunks).

Used by the guarded API in api/risky_delete_apis/. No model calls.
"""

# --- Imports -----------------------------------------------------------------
from ingest import store
from utils.companies import require_company
from utils.doc_types import require_doc_type
from utils.metadata import get_metadata_store
from utils.periods import parse_period
from utils.vectorstore import get_store


def _describe(filing: dict, chunks: int) -> dict:
    """The parts of a filing worth showing in a delete report."""
    return {"doc_id": filing["doc_id"], "company_id": filing["company_id"], "period": filing["period"],
            "doc_type": filing["doc_type"], "status": filing["status"], "file_name": filing["file_name"],
            "chunks": chunks}


def _remove_filings(filings: list[dict], dry_run: bool) -> list[dict]:
    """Deletes each filing's chunks, then its record. Returns what was (or would be) removed."""
    vectors, metadata = get_store(), get_metadata_store()
    removed = []
    for filing in filings:
        removed.append(_describe(filing, vectors.count_chunks(filing["doc_id"])))
        if not dry_run:
            vectors.delete_chunks(filing["doc_id"])
            metadata.delete_filing(filing["doc_id"])
    return removed


# --- One PDF ------------------------------------------------------------------------
def remove_filing(doc_id: str, dry_run: bool = True) -> dict:
    """One filing by doc_id. Also clears chunks left behind with no record ("orphans")."""
    filing = store.get_document(doc_id)
    if filing:
        removed = _remove_filings([filing], dry_run)
    else:
        orphan_chunks = get_store().count_chunks(doc_id)
        if not orphan_chunks:
            raise LookupError(f"No filing and no chunks with doc_id {doc_id}")
        if not dry_run:
            get_store().delete_chunks(doc_id)
        removed = [{"doc_id": doc_id, "note": "no filing record, chunks only", "chunks": orphan_chunks}]
    return {"dry_run": dry_run, "filings": removed, "chunks": sum(r["chunks"] for r in removed)}


# --- A company's PDFs ------------------------------------------------------------------
def remove_company_filings(company: str, period: str | None = None, doc_type: str | None = None,
                           dry_run: bool = True) -> dict:
    """
    A company's filings and their chunks. Company and aliases stay.
    period: "Q3 FY25" (that quarter) or "FY26" (that full-year filing); None = all periods.
    doc_type: e.g. "financial_statements"; None = all types.
    """
    company_id = require_company(company).company_id
    wanted = {"company_id": company_id}
    if period:
        parsed = parse_period(period)
        wanted.update(fiscal_year=parsed.fiscal_year, quarter=parsed.quarter)   # quarter None = full year only
    if doc_type:
        wanted["doc_type"] = require_doc_type(doc_type)

    filings = [f for f in store.list_documents() if all(f.get(k) == v for k, v in wanted.items())]
    removed = _remove_filings(filings, dry_run)
    return {"dry_run": dry_run, "company_id": company_id, "filters": wanted,
            "filings": removed, "chunks": sum(r["chunks"] for r in removed)}


# --- A whole company -----------------------------------------------------------------------
def remove_company(company: str, dry_run: bool = True) -> dict:
    """
    Everything about a company: chunks (incl. any without a record), filings,
    aliases and the company row - no trace left in Postgres or Qdrant.
    """
    found = require_company(company)
    filings = [f for f in store.list_documents() if f["company_id"] == found.company_id]
    report = {"dry_run": dry_run, "company_id": found.company_id, "name": found.name,
              "filings": [_describe(f, get_store().count_chunks(f["doc_id"])) for f in filings],
              "chunks": get_store().count_where(company_id=found.company_id),
              "aliases": len(found.aliases)}
    if not dry_run:
        get_store().delete_where(company_id=found.company_id)       # every chunk, with or without a record
        for f in filings:
            get_metadata_store().delete_filing(f["doc_id"])
        get_metadata_store().delete_company(found.company_id)
    return report
