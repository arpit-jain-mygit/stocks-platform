"""
search.py - Finds the chunks that best match a question.

Steps:
  1. Embed the question (same model and size as the chunks, task type QUERY).
  2. Ask the vector store for the closest chunks, optionally only for one company/period.
  3. Return them as simple Hit records, best match first.

Filters: company can be an ID, BSE code, name or alias (/companies);
period is like "Q3 FY25" or "FY25"; doc_type is a code from /doc-types. Both are turned into exact fields
(company_id, fiscal_year, quarter), so spelling differences never matter.
"""

# --- Imports -----------------------------------------------------------------
# dataclass:       simple record class (Hit).
# require_company: company text -> canonical company_id (utils/companies.py).
# parse_period:    "Q3 FY25" -> fiscal_year + quarter (utils/periods.py).
# llm:             the configured embedding model, for the question.
# get_store:       the configured vector database (utils/vectorstore).
from dataclasses import dataclass

from utils.companies import require_company
from utils.doc_types import require_doc_type
from utils.llm import QUERY, get_llm
from utils.periods import parse_period
from utils.vectorstore import get_store

# --- Settings ----------------------------------------------------------------
# How many chunks to fetch per question. Enough to include the table, its
# row facts and a bit of prose, without flooding the answer prompt.
TOP_K = 6


# --- Result record -------------------------------------------------------------
@dataclass
class Hit:
    """One chunk found by search, plus where it came from."""
    score: float       # similarity to the question: higher = closer in meaning
    text: str          # the chunk text (label line + body)
    file_name: str
    page_start: int
    page_end: int
    section: str
    kind: str          # prose / table / fact
    chunk_no: int
    doc_id: str
    company_id: str
    location: str = ""  # citation label ("" = cite the pages)

    @property
    def citation(self) -> str:
        """What to show for this chunk: its location (sheets, rows) or its page."""
        return self.location or f"page {self.pages}"

    @property
    def pages(self) -> str:
        """'11' or '6-7', for citations."""
        return str(self.page_start) if self.page_start == self.page_end else f"{self.page_start}-{self.page_end}"


# --- Filters --------------------------------------------------------------------
def build_filters(company: str | None = None, period: str | None = None, doc_type: str | None = None) -> dict:
    """
    Turns the caller's company / period text into exact filter fields, e.g.
      build_filters("Videocon", "Q3 FY25") -> {"company_id": "VIDEOIND", "fiscal_year": 2025, "quarter": 3}
    Raises ValueError for an unknown company, unreadable period or unknown doc type.
    """
    filters = {}
    if doc_type:
        filters["doc_type"] = require_doc_type(doc_type)
    if company:
        filters["company_id"] = require_company(company).company_id
    if period:
        parsed = parse_period(period)
        filters["fiscal_year"] = parsed.fiscal_year
        filters["quarter"] = parsed.quarter     # None for a full year -> not filtered
    return filters


# --- Main entry point ------------------------------------------------------------
def search(question: str, company: str | None = None, period: str | None = None,
           doc_type: str | None = None, top_k: int = TOP_K) -> list[Hit]:
    """Returns the top_k chunks closest in meaning to the question, best first."""
    filters = build_filters(company, period, doc_type)   # validate before any model call
    [question_vector] = get_llm("embed").embed_texts([question], QUERY)
    points = get_store().search(question_vector, limit=top_k, **filters)
    return [
        Hit(
            score=point.score,
            text=point.payload["text"],
            file_name=point.payload["file_name"],
            page_start=point.payload["page_start"],
            page_end=point.payload["page_end"],
            section=point.payload["section"],
            kind=point.payload["kind"],
            chunk_no=point.payload["chunk_no"],
            doc_id=point.payload["doc_id"],
            company_id=point.payload.get("company_id", ""),
            location=point.payload.get("location", ""),
        )
        for point in points
    ]


# --- Quick manual test -------------------------------------------------------
# Run:  python -m query.search "your question" ["company"]
#       company: ID, BSE code, name or alias, e.g. VIDEOIND or "Videocon"
if __name__ == "__main__":
    import sys

    question = sys.argv[1]
    company = sys.argv[2] if len(sys.argv) > 2 else None
    for hit in search(question, company=company):
        body = hit.text.split("\n\n", 1)[-1].replace("\n", " ")
        print(f"{hit.score:.3f}  #{hit.chunk_no} {hit.kind:5} {hit.file_name} p{hit.pages}  {body[:100]}")
