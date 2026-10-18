"""
fakes.py - In-memory stand-ins for the three outside services, used only by tests.

  FakeLLM            instead of Gemini     (vision, answers, embeddings) - no network, no cost
  FakeVectorStore    instead of Qdrant     (chunks + vectors in a Python dict)
  FakeMetadataStore  instead of Postgres   (companies, doc types, filings in Python dicts)

Each fake follows the same interface as the real class (utils/llm/base.py,
utils/vectorstore/base.py, utils/metadata/base.py), so the app code under
test cannot tell the difference. Everything else - the API, pipeline,
chunker, search and answer code - is the REAL code.
"""

# --- Imports -----------------------------------------------------------------
# hashlib / math / re: build simple, repeatable "embeddings" from words.
# asdict / copy:       turn records into plain dicts for export.
import copy
import hashlib
import math
import re
from dataclasses import asdict
from itertools import count

from utils.llm.base import DOCUMENT, LLMClient
from utils.metadata.base import Company, MetadataStore
from utils.vectorstore.base import SearchResult, VectorRecord, VectorStore

# --- What the fake vision model "reads" from every image page --------------------
# A small results table, so the chunker makes one fact card per row.
VISION_MARKDOWN = """## Statement of standalone results

| Particulars | Quarter ended 31-Dec-2024 | Quarter ended 30-Sep-2024 |
|---|---|---|
| Revenue from operations | 1,234.5 | 1,100.0 |
| Finance costs | 56.7 | 55.1 |
| Net profit for the period | 300.2 | 280.9 |
"""

# The fake answer model's reply when it is given sources: cites the first one.
FAKE_ANSWER = "Revenue from operations was 1,234.5 for the quarter [S1]."


# --- Fake embeddings: same words -> similar vectors ----------------------------------
def fake_vector(text: str, dim: int) -> list[float]:
    """
    Each word adds 1 to one position (picked by hashing the word); the vector is
    then scaled to length 1. Texts sharing words point the same way, so search
    still finds the right chunk - without any model.
    """
    vector = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % dim] += 1.0
    length = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / length for x in vector]


# --- Fake LLM -------------------------------------------------------------------------
class FakeLLM(LLMClient):
    """Answers every call instantly and counts the calls, so tests can check them."""

    provider = "fake"

    def __init__(self, model: str = "fake-model", embed_dim: int | None = None):
        super().__init__(api_key="fake-key", model=model, embed_dim=embed_dim)
        self.calls = {"describe_image": 0, "generate_text": 0, "embed_texts": 0}
        self.prompts: list[str] = []          # every prompt sent to generate_text

    def describe_image(self, png: bytes, prompt: str) -> str:
        self.calls["describe_image"] += 1
        return VISION_MARKDOWN

    def generate_text(self, prompt: str) -> str:
        self.calls["generate_text"] += 1
        self.prompts.append(prompt)
        return FAKE_ANSWER

    def embed_texts(self, texts: list[str], task: str = DOCUMENT) -> list[list[float]]:
        self.calls["embed_texts"] += 1
        return [fake_vector(text, self.embed_dim) for text in texts]


# --- Fake vector store ----------------------------------------------------------------------
def _matches(payload: dict, filters: dict) -> bool:
    """True if the payload has every filter value (filters set to None are ignored)."""
    return all(payload.get(key) == value for key, value in filters.items() if value is not None)


class FakeVectorStore(VectorStore):
    """Chunks kept in a dict: id -> VectorRecord. Search = cosine similarity over all of them."""

    provider = "fake"

    def __init__(self, dim: int):
        super().__init__(dim)
        self.points: dict[str, VectorRecord] = {}

    def setup(self) -> None:
        pass                                   # nothing to create in memory

    def upsert_chunks(self, records: list[VectorRecord]) -> None:
        for record in records:
            assert len(record.vector) == self.dim, "vector size must match the store"
            self.points[record.id] = copy.deepcopy(record)

    def delete_chunks(self, doc_id: str) -> None:
        self.delete_where(doc_id=doc_id)

    def count_where(self, **filters) -> int:
        return sum(_matches(p.payload, filters) for p in self.points.values())

    def delete_where(self, **filters) -> None:
        assert filters, "delete_where needs at least one filter"
        self.points = {i: p for i, p in self.points.items() if not _matches(p.payload, filters)}

    def count_chunks(self, doc_id: str) -> int:
        return self.count_where(doc_id=doc_id)

    def search(self, vector: list[float], limit: int = 6, **filters) -> list[SearchResult]:
        # Vectors are length 1, so the dot product is the cosine similarity.
        scored = [SearchResult(id=p.id, score=sum(a * b for a, b in zip(vector, p.vector)), payload=p.payload)
                  for p in self.points.values() if _matches(p.payload, filters)]
        return sorted(scored, key=lambda r: r.score, reverse=True)[:limit]

    def export_points(self) -> list[VectorRecord]:
        return copy.deepcopy(list(self.points.values()))

    def clear(self) -> None:
        self.points = {}

    def stats(self) -> dict:
        return {"chunks": len(self.points), "where": "memory"}


# --- Fake metadata store --------------------------------------------------------------------
# Same starting data as db/migrations/003_seed_reference_data.sql.
SEED_COMPANIES = [
    Company(company_id="VIDEOIND", name="Videocon Industries Ltd", nse_symbol="VIDEOIND", bse_code="511389",
            cin="L99999MH1986PLC103624", aliases=("Videocon", "Videocon Industries Limited")),
    Company(company_id="OFSS", name="Oracle Financial Services Software Ltd", nse_symbol="OFSS",
            bse_code="532466", isin="INE881D01027", aliases=("Oracle Financial Services",)),
]
SEED_DOC_TYPES = [
    {"code": "quarterly_results", "name": "Quarterly financial results"},
    {"code": "annual_report", "name": "Annual report"},
    {"code": "financial_statements", "name": "Financial statements"},
]
DEFAULT_DOC_TYPE = "quarterly_results"


class FakeMetadataStore(MetadataStore):
    """Companies, doc types and filing records in plain Python structures."""

    provider = "fake"

    def __init__(self):
        self.companies: list[Company] = list(SEED_COMPANIES)
        self.types: list[dict] = copy.deepcopy(SEED_DOC_TYPES)
        self.filings: dict[str, dict] = {}
        self._clock = count(1)                 # stands in for updated_at (newest = biggest)

    # --- Companies and doc types ---------------------------------------------------
    def list_companies(self) -> list[Company]:
        return list(self.companies)

    def doc_types(self) -> dict:
        return {"default": DEFAULT_DOC_TYPE, "doc_types": copy.deepcopy(self.types)}

    # --- Filings -----------------------------------------------------------------------
    def get_filing(self, doc_id: str) -> dict | None:
        record = self.filings.get(doc_id)
        return copy.deepcopy(record) if record else None

    def save_filing(self, doc_id: str, fields: dict) -> None:
        tick = next(self._clock)
        record = self.filings.setdefault(doc_id, {"doc_id": doc_id, "superseded_by": None, "error": None,
                                                  "created_at": tick})
        record.update(fields, updated_at=tick)
        # Same rule as Postgres: a new complete filing supersedes the old one
        # for the same company + doc type + period.
        if fields.get("status") == "complete":
            for other in self.filings.values():
                same_slot = all(other.get(k) == record.get(k) for k in ("company_id", "doc_type", "fiscal_year", "quarter"))
                if other["doc_id"] != doc_id and same_slot and other.get("status") == "complete":
                    other.update(status="superseded", superseded_by=doc_id)

    def list_filings(self) -> list[dict]:
        return sorted(copy.deepcopy(list(self.filings.values())), key=lambda f: f["updated_at"], reverse=True)

    # --- Deletes -------------------------------------------------------------------------
    def delete_filing(self, doc_id: str) -> bool:
        existed = self.filings.pop(doc_id, None) is not None
        for other in self.filings.values():
            if other.get("superseded_by") == doc_id:
                other["superseded_by"] = None
        return existed

    def delete_company(self, company_id: str) -> bool:
        assert not any(f["company_id"] == company_id for f in self.filings.values()), "delete filings first"
        before = len(self.companies)
        self.companies = [c for c in self.companies if c.company_id != company_id]
        return len(self.companies) < before

    # --- Backup / restore ------------------------------------------------------------------
    def export_data(self) -> dict:
        return {
            "migrations": ["001_init", "002_filings", "003_seed_reference_data"],
            "doc_types": copy.deepcopy(self.types),
            "companies": [asdict(c) | {"aliases": list(c.aliases)} for c in self.companies],
            "filings": self.list_filings(),
        }

    def import_data(self, data: dict, mode: str) -> dict:
        if mode == "replace":
            self.companies, self.types, self.filings = [], [], {}
        known = {c.company_id: c for c in self.companies}
        for c in data["companies"]:
            known[c["company_id"]] = Company(**{**c, "aliases": tuple(c["aliases"])})
        self.companies = list(known.values())
        types = {t["code"]: t for t in self.types} | {t["code"]: t for t in data["doc_types"]}
        self.types = list(types.values())
        for filing in data["filings"]:
            self.filings[filing["doc_id"]] = copy.deepcopy(filing)
        return {"companies": len(self.companies), "doc_types": len(self.types), "filings": len(self.filings)}
