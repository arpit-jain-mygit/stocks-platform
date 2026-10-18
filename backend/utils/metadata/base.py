"""
base.py - The common shape every metadata store must follow.

Metadata = facts ABOUT companies and documents (not the documents' text):
the company list with aliases and identifiers, and the allowed document types.
utils/companies.py and utils/doc_types.py only talk to a MetadataStore, so
where the data lives (Postgres today, something else later) is decided by
METADATA_STORE in .env - see factory.py.
"""

# --- Imports -----------------------------------------------------------------
# dataclass: simple record class (Company).
from dataclasses import dataclass, field


# --- Records -------------------------------------------------------------------------
# Identifier types (Postgres: company_identifiers.type). Only tickers have an exchange.
IDENTIFIER_TYPES = ("ticker", "isin", "lei", "cik", "cin", "figi", "registry")


@dataclass(frozen=True)
class Identifier:
    """
    One way to identify a company, for any market, e.g.
        Identifier("ticker", "TCS", "NSE")      Identifier("ticker", "MSFT", "NASDAQ")
        Identifier("isin", "US5949181045")      Identifier("cin", "L22210MH1995PLC084781")
    """
    type: str                       # one of IDENTIFIER_TYPES
    value: str
    exchange: str = ""              # tickers only, e.g. "NSE", "BSE", "NASDAQ", "NYSE", "LSE"

    def label(self) -> str:
        """How users write it: "NASDAQ:MSFT" for a ticker, the value itself otherwise."""
        return f"{self.exchange}:{self.value}" if self.exchange else self.value


@dataclass(frozen=True)
class Company:
    company_id: str                 # canonical key, e.g. "VIDEOIND" (Postgres: companies.code)
    name: str                       # display name, e.g. "Videocon Industries Ltd"
    country: str = ""               # ISO code, e.g. "IN", "US" (optional)
    aliases: tuple[str, ...] = field(default_factory=tuple)
    identifiers: tuple[Identifier, ...] = field(default_factory=tuple)
    sector: str = ""                # e.g. "IT services" (optional)
    fy_end_month: int = 3           # month the financial year ends (3 = March, 6 = June, 12 = December)
    status: str = "active"          # active / suspended / delisted / insolvency

    def identifier(self, type: str, exchange: str = "") -> str:
        """The first identifier of this type (and exchange), e.g. identifier("ticker", "NSE") -> "TCS"; "" if none."""
        return next((i.value for i in self.identifiers
                     if i.type == type and (not exchange or i.exchange == exchange)), "")

    def tickers(self) -> list[str]:
        """Bare ticker symbols on any exchange, e.g. ["TCS", "532540"]."""
        return [i.value for i in self.identifiers if i.type == "ticker"]

    def names(self) -> list[str]:
        """
        Every string that identifies ONLY this company: ID, name, aliases, ISIN / CIN / LEI ...
        and tickers written with their exchange ("NSE:TCS"). A bare ticker ("TCS") is
        not here, because the same symbol can belong to companies on different exchanges -
        utils/companies.find_company() handles bare tickers.
        """
        return [n for n in (self.company_id, self.name, *self.aliases,
                            *(i.label() for i in self.identifiers)) if n]


# --- The interface -----------------------------------------------------------------------
class MetadataStore:
    """One place company and document-type metadata is read from."""

    provider = "base"   # set by each subclass, e.g. "postgres"

    def list_companies(self) -> list[Company]:
        """Every company, with its aliases."""
        raise NotImplementedError(f"{self.provider} store must implement list_companies")

    def doc_types(self) -> dict:
        """{"default": "<code>", "doc_types": [{"code": ..., "name": ...}, ...]}"""
        raise NotImplementedError(f"{self.provider} store must implement doc_types")

    # --- Filings: one record per ingested PDF (the "already ingested?" check) ------------
    # A filing record is a plain dict with these keys:
    #   doc_id, file_name, company_id (code), company (name), doc_type,
    #   fiscal_year, quarter, period_end ("YYYY-MM-DD"), period (label),
    #   status (processing / complete / failed / superseded), pages, ocr_pages,
    #   chunks, error, superseded_by, created_at, updated_at (ISO times)

    def get_filing(self, doc_id: str) -> dict | None:
        """One filing record, or None if this PDF was never seen."""
        raise NotImplementedError(f"{self.provider} store must implement get_filing")

    def save_filing(self, doc_id: str, fields: dict) -> None:
        """
        Create or update a filing with the given fields (others keep their value).
        Saving status="complete" marks any other complete filing for the same
        company + doc_type + period as "superseded" by this one.
        """
        raise NotImplementedError(f"{self.provider} store must implement save_filing")

    def list_filings(self) -> list[dict]:
        """Every filing record, newest first."""
        raise NotImplementedError(f"{self.provider} store must implement list_filings")

    # --- Deletes (used only by the guarded risky-delete APIs) ---------------------------
    def delete_filing(self, doc_id: str) -> bool:
        """
        Remove one filing record. Returns True if it existed. Filings it had
        superseded stay "superseded" but lose the link. Chunks are NOT touched here.
        """
        raise NotImplementedError(f"{self.provider} store must implement delete_filing")

    def delete_company(self, company_id: str) -> bool:
        """
        Remove a company and its aliases. Its filings must be deleted first.
        Returns True if it existed.
        """
        raise NotImplementedError(f"{self.provider} store must implement delete_company")

    # --- Backup / restore -------------------------------------------------------------
    def export_data(self) -> dict:
        """
        Everything this store holds, as plain JSON-ready data:
        {"migrations": [...], "doc_types": [...], "companies": [... with "aliases"],
         "filings": [... with "company_code" instead of internal ids]}
        """
        raise NotImplementedError(f"{self.provider} store must implement export_data")

    def import_data(self, data: dict, mode: str) -> dict:
        """
        Load export_data() output, all-or-nothing. mode:
          "replace" - wipe doc types, companies, aliases and filings first
          "merge"   - add new rows and update existing ones (by code / doc_id)
        Returns row counts.
        """
        raise NotImplementedError(f"{self.provider} store must implement import_data")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"
