"""
qdrant.py - Qdrant, behind the common VectorStore interface.

One collection (Qdrant's word for "table"): one point per chunk = vector +
payload. That is what questions search. Filing records (status, pages ...)
live in the metadata store (utils/metadata), not here.
The collection name is prefixed "stocks_rag_" (from .env) so it never clashes
with other projects' collections on the same cluster.

Created by the factory, e.g. create_store("qdrant", dim=768, url=..., api_key=...).
"""

# --- Imports -----------------------------------------------------------------
# QdrantClient/models: the official Qdrant Python client and its building blocks.
# base:                the common interface and the plain records.
from qdrant_client import QdrantClient, models

from utils.vectorstore.base import SearchResult, VectorRecord, VectorStore

# --- Settings ----------------------------------------------------------------
# Points sent to Qdrant per request when uploading.
UPSERT_BATCH_SIZE = 64

# Payload fields we filter on get an index, so filtering stays fast as data grows.
KEYWORD_INDEXES = ["doc_id", "company_id", "company", "period", "doc_type", "kind", "source"]
INTEGER_INDEXES = ["page_start", "page_end", "fiscal_year", "quarter"]


def match_all(**filters) -> models.Filter | None:
    """Turns company="X", doc_id="Y" ... into a Qdrant filter. None values are skipped."""
    conditions = [
        models.FieldCondition(key=field, match=models.MatchValue(value=value))
        for field, value in filters.items() if value is not None
    ]
    return models.Filter(must=conditions) if conditions else None


class QdrantStore(VectorStore):
    provider = "qdrant"

    def __init__(self, dim: int, url: str, api_key: str | None = None,
                 chunks_collection: str = "stocks_rag_chunks"):
        super().__init__(dim)
        if not url:
            raise ValueError("qdrant: a URL is required (QDRANT_URL in .env)")
        self.url, self.api_key = url, api_key
        self.chunks = chunks_collection
        self._client: QdrantClient | None = None    # created on first call, then reused

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.url, api_key=self.api_key, timeout=60)
        return self._client

    # --- Setup -------------------------------------------------------------------
    def setup(self) -> None:
        """
        Creates the chunks collection if it doesn't exist yet, and adds any payload
        index that is missing (so new filter fields also reach old collections).
        If the chunks collection exists with a different vector size (EMBED_DIM
        changed), it stops with a clear error instead of mixing sizes.
        """
        if not self.client.collection_exists(self.chunks):
            self.client.create_collection(
                self.chunks,
                vectors_config=models.VectorParams(size=self.dim, distance=models.Distance.COSINE),
            )
            print(f"created collection {self.chunks} ({self.dim} dims, cosine)")
        else:
            size = self.client.get_collection(self.chunks).config.params.vectors.size
            if size != self.dim:
                raise RuntimeError(
                    f"{self.chunks} stores {size}-number vectors but EMBED_DIM is {self.dim}. "
                    f"Use a new QDRANT_CHUNKS_COLLECTION name or delete the old collection."
                )

        # Add any missing payload index (cheap; existing ones are left alone).
        existing = set(self.client.get_collection(self.chunks).payload_schema)
        wanted = {**{f: models.PayloadSchemaType.KEYWORD for f in KEYWORD_INDEXES},
                  **{f: models.PayloadSchemaType.INTEGER for f in INTEGER_INDEXES}}
        for field, kind in wanted.items():
            if field not in existing:
                self.client.create_payload_index(self.chunks, field, kind)
                print(f"added index {self.chunks}.{field}")


    # --- Chunks ------------------------------------------------------------------------
    def upsert_chunks(self, records: list[VectorRecord]) -> None:
        points = [models.PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in records]
        for start in range(0, len(points), UPSERT_BATCH_SIZE):
            self.client.upsert(self.chunks, points=points[start:start + UPSERT_BATCH_SIZE], wait=True)

    def delete_chunks(self, doc_id: str) -> None:
        self.client.delete(self.chunks, points_selector=models.FilterSelector(filter=match_all(doc_id=doc_id)))

    def count_where(self, **filters) -> int:
        return self.client.count(self.chunks, count_filter=match_all(**filters), exact=True).count

    def delete_where(self, **filters) -> None:
        if not any(v is not None for v in filters.values()):
            raise ValueError("delete_where needs at least one filter - refusing to delete every chunk")
        self.client.delete(self.chunks, points_selector=models.FilterSelector(filter=match_all(**filters)))

    def count_chunks(self, doc_id: str) -> int:
        return self.client.count(self.chunks, count_filter=match_all(doc_id=doc_id), exact=True).count

    def search(self, vector: list[float], limit: int = 6, **filters) -> list[SearchResult]:
        points = self.client.query_points(
            self.chunks, query=vector, query_filter=match_all(**filters), limit=limit, with_payload=True,
        ).points
        return [SearchResult(id=str(p.id), score=p.score, payload=p.payload) for p in points]

    # --- Status -----------------------------------------------------------------------
    def export_points(self) -> list[VectorRecord]:
        if not self.client.collection_exists(self.chunks):
            return []
        records, offset = [], None
        while True:                                            # page through, 256 at a time
            points, offset = self.client.scroll(self.chunks, limit=256, offset=offset,
                                                with_payload=True, with_vectors=True)
            records += [VectorRecord(id=str(p.id), vector=list(p.vector), payload=p.payload) for p in points]
            if offset is None:
                return records

    def clear(self) -> None:
        # Only OUR collection (QDRANT_CHUNKS_COLLECTION); other projects' collections are untouched.
        if self.client.collection_exists(self.chunks):
            self.client.delete_collection(self.chunks)
        self.setup()                                           # recreate it, with all payload indexes

    def stats(self) -> dict:
        def size(name):
            return self.client.count(name, exact=True).count if self.client.collection_exists(name) else None
        return {
            "store": "qdrant",
            "where": self.chunks,
            "chunks": size(self.chunks),
            "all collections on cluster": [c.name for c in self.client.get_collections().collections],
        }
