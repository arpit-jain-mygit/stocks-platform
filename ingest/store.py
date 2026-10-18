"""
store.py - Step 5 of ingestion: save chunks, and keep the filing record (the "already ingested?" check).

Two stores, two jobs:
  1. Filing records (one per PDF) -> metadata store (Postgres, or JSON files)
       is_ingested(doc_id)  -> True only if a previous run finished completely
       save_document(...)   -> status: processing / failed / complete
  2. Chunks -> vector store (Qdrant): replace this PDF's chunks and confirm they arrived
       store_chunks(...)    -> delete old, upload new, count check

Which databases are used is decided in .env (METADATA_STORE, VECTOR_STORE);
this file only decides WHAT is stored.
"""

# --- Imports -----------------------------------------------------------------
# Chunk:              one card from chunker.py.
# point_id:           fixed ID for each chunk (ingest/ids.py).
# get_metadata_store: where filing records live (utils/metadata).
# vectorstore:        where chunks live + its plain record type (utils/vectorstore).
from ingest.chunker import Chunk
from ingest.ids import point_id
from utils.metadata import get_metadata_store
from utils.vectorstore import VectorRecord, get_store


# --- Setup -----------------------------------------------------------------------------
def setup() -> None:
    """Make sure the vector store is ready (collection, indexes). Safe to call every time."""
    get_store().setup()


def where() -> str:
    """Where chunks are stored, for log messages, e.g. 'stocks_rag_chunks'."""
    return get_store().stats().get("where", repr(get_store()))


# --- Filing records: the duplicate check -----------------------------------------------
def get_document(doc_id: str) -> dict | None:
    """Returns this PDF's filing record, or None if it was never ingested."""
    return get_metadata_store().get_filing(doc_id)


def is_ingested(doc_id: str) -> bool:
    """True only if this PDF was ingested completely (a half-finished run doesn't count)."""
    record = get_document(doc_id)
    return bool(record) and record.get("status") == "complete"


def save_document(doc_id: str, **fields) -> None:
    """Creates or updates this PDF's filing record, e.g. save_document(doc_id, status="complete", ...)."""
    get_metadata_store().save_filing(doc_id, fields)


def list_documents() -> list[dict]:
    """Every filing record, newest first."""
    return get_metadata_store().list_filings()


# --- Chunks --------------------------------------------------------------------------------
def store_chunks(doc_id: str, file_name: str, meta: dict,
                 chunks: list[Chunk], vectors: list[list[float]]) -> int:
    """
    Replaces this PDF's chunks in the vector store and returns how many were stored.
    meta = fields from pipeline.describe(): company_id, company,
    fiscal_year, quarter, period_end, period, doc_type.
    Old chunks are deleted first, so a re-run with a different chunk count
    leaves nothing stale behind. Raises if not every chunk arrived.
    """
    records = [
        VectorRecord(
            id=point_id(doc_id, chunk.page_start, chunk.chunk_no),
            vector=vector,
            payload={
                "text": chunk.text,              # what the answer step will read
                "doc_id": doc_id,                # links back to the PDF ...
                "file_name": file_name,
                "page_start": chunk.page_start,  # ... and to the exact pages
                "page_end": chunk.page_end,
                **meta,                          # company_id, company, fiscal_year, quarter, period_end, period, doc_type
                "section": chunk.section,
                "kind": chunk.kind,              # prose / table / fact
                "source": chunk.source,          # text / vision / ocr
                "chunk_no": chunk.chunk_no,
            },
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    store = get_store()
    store.delete_chunks(doc_id)
    store.upsert_chunks(records)

    stored = store.count_chunks(doc_id)
    if stored != len(records):
        raise RuntimeError(f"only {stored} of {len(records)} chunks were stored")
    return stored
