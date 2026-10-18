"""
vectorstore - database-independent storage and search of chunk vectors.

    from utils.vectorstore import get_store, VectorRecord
    store = get_store()                  # whatever VECTOR_STORE in .env configures
    store.upsert_chunks([VectorRecord(id, vector, payload)])
    store.search(question_vector, limit=6, company="Videocon Industries Ltd")

Files: base.py (interface + records) - qdrant.py (Qdrant) - factory.py (picks the class).
Status:  python -m utils.vectorstore ["question"]
"""

from utils.vectorstore.base import SearchResult, VectorRecord, VectorStore
from utils.vectorstore.factory import create_store, get_store

__all__ = ["SearchResult", "VectorRecord", "VectorStore", "create_store", "get_store"]
