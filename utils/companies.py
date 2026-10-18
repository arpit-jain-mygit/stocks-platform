"""
companies.py - The companies the app knows, and how to look one up.

The list lives in Postgres (companies + company_aliases), read through the
metadata store (utils/metadata). Add companies with db/samples/add_company.sql.
Each company has one canonical company_id (Postgres: companies.code) plus a
display name, exchange codes and aliases. Everything stored in the vector
store uses company_id, so "Videocon Industries Ltd" and "Videocon Industries
Limited" can never become two different companies.

    find_company("Videocon")      -> Company(company_id="VIDEOIND", ...)
    find_company("511389")        -> same company (BSE code)
    require_company("XYZ")        -> ValueError listing the known companies
"""

# --- Imports -----------------------------------------------------------------
# Company:            the company record (utils/metadata/base.py).
# get_metadata_store: the configured metadata store (JSON files or Postgres).
from utils.metadata import Company, get_metadata_store

__all__ = ["Company", "load_companies", "find_company", "require_company"]


# --- Loading -------------------------------------------------------------------------
def load_companies() -> list[Company]:
    """Every company. Stops with a clear error if two companies share an ID, code or alias."""
    companies = get_metadata_store().list_companies()
    seen: dict[str, str] = {}
    for company in companies:
        for name in company.names():
            key = name.lower()
            if key in seen and seen[key] != company.company_id:
                raise ValueError(f"{name!r} is used by both {seen[key]} and {company.company_id}")
            seen[key] = company.company_id
    return companies


# --- Lookup --------------------------------------------------------------------------
def find_company(text: str | None) -> Company | None:
    """
    The company matching this ID, exchange code, CIN, ISIN, name or alias
    (case-insensitive, exact match), or None.
    """
    if not text:
        return None
    wanted = text.strip().lower()
    for company in load_companies():
        if wanted in (n.lower() for n in company.names()):
            return company
    return None


def require_company(text: str) -> Company:
    """Like find_company(), but raises ValueError (listing known IDs) if not found."""
    company = find_company(text)
    if company is None:
        known = ", ".join(f"{c.company_id} ({c.name})" for c in load_companies())
        raise ValueError(f"Unknown company {text!r}. Known: {known}")
    return company
