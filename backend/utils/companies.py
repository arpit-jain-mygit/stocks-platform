"""
companies.py - The companies the app knows, and how to look one up.

The list lives in Postgres (companies + company_aliases), read through the
metadata store (utils/metadata). Add companies with db/samples/add_company.sql.
Each company has one canonical company_id (Postgres: companies.code) plus a
display name, exchange codes and aliases. Everything stored in the vector
store uses company_id, so "Videocon Industries Ltd" and "Videocon Industries
Limited" can never become two different companies.

    find_company("Videocon")      -> Company(company_id="VIDEOIND", ...)
    find_company("511389")        -> same company (BSE ticker; also "BSE:511389")
    find_company("NASDAQ:MSFT")   -> Microsoft (a ticker with its exchange is always unique)
    require_company("XYZ")        -> ValueError listing the known companies
"""

# --- Imports -----------------------------------------------------------------
# Company:            the company record (utils/metadata/base.py).
# get_metadata_store: the configured metadata store (JSON files or Postgres).
from utils.metadata import Company, get_metadata_store

__all__ = ["Company", "load_companies", "find_company", "require_company", "company_dict"]


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
    The company matching this text (case-insensitive, exact match), or None:
      1. its ID, name, alias, ISIN / CIN / LEI ..., or a ticker with its exchange ("NASDAQ:MSFT")
      2. otherwise a bare ticker ("MSFT", "532540") - if exactly one company has it.
    Raises ValueError if a bare ticker belongs to several companies (on different
    exchanges): the caller must then write EXCHANGE:TICKER.
    """
    if not text:
        return None
    wanted = text.strip().lower()
    companies = load_companies()
    for company in companies:
        if wanted in (n.lower() for n in company.names()):
            return company

    by_ticker = [c for c in companies if wanted in (t.lower() for t in c.tickers())]
    if len(by_ticker) > 1:
        choices = ", ".join(f"{i.label()} ({c.name})" for c in by_ticker
                            for i in c.identifiers if i.type == "ticker" and i.value.lower() == wanted)
        raise ValueError(f"{text!r} is a ticker of several companies: {choices}. Write it as EXCHANGE:TICKER.")
    return by_ticker[0] if by_ticker else None


def company_dict(company: Company) -> dict:
    """
    A company as JSON for the API. "identifiers" is the general list; nse_symbol,
    bse_code, isin and cin are kept (filled from it) so older callers keep working.
    """
    return {
        "company_id": company.company_id, "name": company.name, "country": company.country,
        "sector": company.sector, "fy_end_month": company.fy_end_month, "status": company.status,
        "aliases": list(company.aliases),
        "identifiers": [{"type": i.type, "exchange": i.exchange, "value": i.value} for i in company.identifiers],
        # Older fields (same data as "identifiers"):
        "nse_symbol": company.identifier("ticker", "NSE"), "bse_code": company.identifier("ticker", "BSE"),
        "isin": company.identifier("isin"), "cin": company.identifier("cin"),
    }


def require_company(text: str) -> Company:
    """Like find_company(), but raises ValueError (listing known IDs) if not found."""
    company = find_company(text)
    if company is None:
        known = ", ".join(f"{c.company_id} ({c.name})" for c in load_companies())
        raise ValueError(f"Unknown company {text!r}. Known: {known}")
    return company
