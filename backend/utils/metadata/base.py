"""
base.py - The common shape every metadata store must follow.

Metadata = facts ABOUT companies and documents (not the documents' text):
the company list with aliases, and the allowed document types.
utils/companies.py and utils/doc_types.py only talk to a MetadataStore, so
where the data lives (Postgres today, something else later) is decided by
METADATA_STORE in .env - see factory.py.
"""

# --- Imports -----------------------------------------------------------------
# dataclass: simple record class (Company).
from dataclasses import dataclass, field


# --- Records -------------------------------------------------------------------------
@dataclass(frozen=True)
class Company:
    company_id: str                 # canonical key, e.g. "VIDEOIND" (Postgres: companies.code)
    name: str                       # display name, e.g. "Videocon Industries Ltd"
    nse_symbol: str = ""
    bse_code: str = ""
    cin: str = ""
    isin: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def names(self) -> list[str]:
        """Every string that identifies this company (ID, codes, name, aliases)."""
        return [n for n in (self.company_id, self.nse_symbol, self.bse_code, self.cin, self.isin,
                            self.name, *self.aliases) if n]


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
    #   chunks, error, superseded_by, updated_at (ISO time)

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
