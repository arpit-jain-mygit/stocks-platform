"""
factory.py - Builds the right vector database client from VECTOR_STORE in .env.

Two ways to get a store:
  get_store()                                   the store configured in .env (shared, reused)
  create_store("qdrant", dim=768, url=..., ...) any store with explicit settings

.env settings:
  VECTOR_STORE=qdrant                           which database to use
  QDRANT_URL / QDRANT_API_KEY                   Qdrant connection
  QDRANT_CHUNKS_COLLECTION
The vector size always comes from the embedding settings (EMBED_DIM), so the
store and the embedding model can never disagree.

Adding a database (e.g. Pinecone): write one VectorStore subclass, add it to
PROVIDERS, and add how to read its settings in SETTINGS_FROM_ENV. Nothing
else in the app changes.
"""

# --- Imports -----------------------------------------------------------------
# os:            reads the store settings.
# role_settings: the embedding model's vector size (utils/llm).
# VectorStore:   the common interface; QdrantStore: Qdrant implementation.
import os

from utils.llm import role_settings
from utils.vectorstore.base import VectorStore
from utils.vectorstore.qdrant import QdrantStore

# --- Registry: provider name -> class ---------------------------------------------------
PROVIDERS: dict[str, type[VectorStore]] = {
    "qdrant": QdrantStore,
}

# --- How to read each provider's settings from .env ---------------------------------------
SETTINGS_FROM_ENV = {
    "qdrant": lambda: {
        "url": os.getenv("QDRANT_URL", ""),
        "api_key": os.getenv("QDRANT_API_KEY") or None,
        "chunks_collection": os.getenv("QDRANT_CHUNKS_COLLECTION", "stocks_rag_chunks"),
    },
}

DEFAULT_STORE = "qdrant"

# The configured store, created on first use, then reused.
_store: VectorStore | None = None


# --- Build any store ----------------------------------------------------------------------
def create_store(provider: str, dim: int, **settings) -> VectorStore:
    """Returns a store for this provider, e.g. create_store("qdrant", dim=768, url="https://...")."""
    provider = provider.lower().strip()
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown vector store {provider!r}. Available: {', '.join(PROVIDERS)}")
    return PROVIDERS[provider](dim=dim, **settings)


# --- The store configured in .env ------------------------------------------------------------
def get_store() -> VectorStore:
    """The shared store from .env (VECTOR_STORE + that store's settings)."""
    global _store
    if _store is None:
        provider = (os.getenv("VECTOR_STORE") or DEFAULT_STORE).lower().strip()
        if provider not in SETTINGS_FROM_ENV:
            raise ValueError(f"Unknown VECTOR_STORE {provider!r}. Available: {', '.join(PROVIDERS)}")
        dim = role_settings("embed")["embed_dim"]
        _store = create_store(provider, dim=dim, **SETTINGS_FROM_ENV[provider]())
    return _store
