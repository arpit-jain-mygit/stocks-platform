"""
base.py - The common shape every vector database must follow.

Why this file exists:
The rest of the app (ingest/store.py, query/search.py) only talks to a
VectorStore. It never knows whether Qdrant, Pinecone or something else is
behind it. Each database is one class that fills in these methods (see
qdrant.py), and factory.py picks the right class from VECTOR_STORE in .env.

What a store holds: chunks only - one vector + payload (text, company,
period, page ...) per chunk. This is what questions search.
Records about each PDF (status, page count ...) live in the metadata store
(utils/metadata), not here.

Data goes in and out as the plain records below - never as a database's
own types - so callers don't change when the database does.
"""

# --- Imports -----------------------------------------------------------------
# dataclass: simple record classes.
from dataclasses import dataclass


# --- Records passed in and out ---------------------------------------------------------
@dataclass
class VectorRecord:
    """One chunk to store: a unique ID, its vector and its details."""
    id: str
    vector: list[float]
    payload: dict


@dataclass
class SearchResult:
    """One chunk found by search: its ID, similarity score (higher = closer) and details."""
    id: str
    score: float
    payload: dict


# --- The interface -----------------------------------------------------------------------
class VectorStore:
    """
    One vector database. Every method below must be implemented by each provider.
    `dim` is the vector size of the embedding model - the store must match it.
    """

    provider = "base"   # set by each subclass, e.g. "qdrant"

    def __init__(self, dim: int):
        self.dim = dim

    # --- Setup -------------------------------------------------------------------
    def setup(self) -> None:
        """Create whatever the store needs (collections, indexes). Safe to call every time."""
        raise NotImplementedError

    # --- Chunks ------------------------------------------------------------------------
    def upsert_chunks(self, records: list[VectorRecord]) -> None:
        """Store chunks. Same ID = overwrite, never a duplicate."""
        raise NotImplementedError

    def delete_chunks(self, doc_id: str) -> None:
        """Remove every chunk whose payload has this doc_id."""
        raise NotImplementedError

    def count_where(self, **filters) -> int:
        """How many chunks match ALL these exact payload values, e.g. company_id="OFSS"."""
        raise NotImplementedError

    def delete_where(self, **filters) -> None:
        """Delete every chunk matching ALL these exact payload values (at least one filter)."""
        raise NotImplementedError

    def count_chunks(self, doc_id: str) -> int:
        """How many chunks with this doc_id are stored."""
        raise NotImplementedError

    def search(self, vector: list[float], limit: int = 6, **filters) -> list[SearchResult]:
        """
        The `limit` chunks closest to `vector`, best first.
        Optional exact-match filters on payload fields, e.g. company="Videocon Industries Ltd".
        Filters whose value is None are ignored.
        """
        raise NotImplementedError

    # --- Backup / restore -------------------------------------------------------------
    def export_points(self) -> list[VectorRecord]:
        """Every chunk with its vector and payload (for backups)."""
        raise NotImplementedError

    def clear(self) -> None:
        """Remove EVERY chunk this store holds, then set it up empty again (restore 'replace')."""
        raise NotImplementedError

    # --- Status -----------------------------------------------------------------------
    def stats(self) -> dict:
        """A short summary for humans, e.g. {"chunks": 84, "where": "..."}."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(dim={self.dim})"
