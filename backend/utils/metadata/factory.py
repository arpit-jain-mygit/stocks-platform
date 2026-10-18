"""
factory.py - Picks the metadata store from METADATA_STORE in .env.

    METADATA_STORE=postgres   Postgres at DATABASE_URL (default; tables + starting
                              data come from python db/migrate.py)

Adding another store: write one MetadataStore subclass and add it to PROVIDERS.
"""

# --- Imports -----------------------------------------------------------------
import os

from utils.metadata.base import MetadataStore
from utils.metadata.postgres import PostgresMetadataStore

# --- Registry: name -> how to build it from .env ----------------------------------------
PROVIDERS = {
    "postgres": lambda: PostgresMetadataStore(os.getenv("DATABASE_URL", "")),
}
DEFAULT_STORE = "postgres"

_store: MetadataStore | None = None


def get_metadata_store() -> MetadataStore:
    """The shared metadata store from .env, created on first use."""
    global _store
    if _store is None:
        name = (os.getenv("METADATA_STORE") or DEFAULT_STORE).lower().strip()
        if name not in PROVIDERS:
            raise ValueError(f"Unknown METADATA_STORE {name!r}. Available: {', '.join(PROVIDERS)}")
        _store = PROVIDERS[name]()
    return _store
