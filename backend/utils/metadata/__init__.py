"""
metadata - where companies, doc types and filing records live (Postgres).

    from utils.metadata import get_metadata_store
    get_metadata_store().list_companies()

Files: base.py (interface + Company) - postgres.py - factory.py.
"""

from utils.metadata.base import IDENTIFIER_TYPES, Company, Identifier, MetadataStore
from utils.metadata.factory import get_metadata_store

__all__ = ["IDENTIFIER_TYPES", "Company", "Identifier", "MetadataStore", "get_metadata_store"]
