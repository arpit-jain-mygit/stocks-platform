"""
routes.py - RISKY: deletes ingested data from Postgres (metadata) AND Qdrant (chunks).

  POST /risky-delete/filing           one PDF by doc_id
  POST /risky-delete/company-filings  a company's PDFs (optionally one period / doc type)
  POST /risky-delete/company          a company completely: chunks, filings, aliases, company row

Five locks, all required for a real delete:
  1. Mounted only if ENABLE_RISKY_DELETE_APIS=true in .env (otherwise 404).
  2. X-API-Key header (same as every endpoint).
  3. X-Admin-Key header = ADMIN_API_KEY (if ADMIN_API_KEY is empty: always 403).
  4. dry_run defaults to true: the reply shows what WOULD be removed; nothing changes.
  5. With dry_run=false, "confirm" must repeat the target exactly
     (the doc_id, or the company code like "OFSS") - otherwise 400.

The work itself is in ingest/remove.py (chunks first, then records). No model calls.
"""

# --- Imports -----------------------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.security import require_admin_key, require_api_key
from ingest import remove
from utils.companies import require_company

router = APIRouter(
    prefix="/risky-delete",
    tags=["RISKY delete"],
    dependencies=[Depends(require_api_key), Depends(require_admin_key)],
)


# --- Request bodies ---------------------------------------------------------------------
class FilingDelete(BaseModel):
    doc_id: str = Field(..., min_length=8, description="Full doc_id (SHA-256 of the PDF)")
    dry_run: bool = Field(True, description="true = only report what would be removed")
    confirm: str | None = Field(None, description="With dry_run=false: repeat the doc_id")


class CompanyFilingsDelete(BaseModel):
    company: str = Field(..., examples=["OFSS"], description="ID, BSE code, name or alias")
    period: str | None = Field(None, examples=["FY26"], description="'Q3 FY25' or 'FY26'; empty = all periods")
    doc_type: str | None = Field(None, examples=["financial_statements"], description="empty = all types")
    dry_run: bool = Field(True, description="true = only report what would be removed")
    confirm: str | None = Field(None, description="With dry_run=false: repeat the company code, e.g. OFSS")


class CompanyDelete(BaseModel):
    company: str = Field(..., examples=["OFSS"], description="ID, BSE code, name or alias")
    dry_run: bool = Field(True, description="true = only report what would be removed")
    confirm: str | None = Field(None, description="With dry_run=false: repeat the company code, e.g. OFSS")


# --- Helpers ----------------------------------------------------------------------------
def check_confirm(dry_run: bool, confirm: str | None, expected: str) -> None:
    """A real delete needs confirm == the exact target (doc_id or company code)."""
    if not dry_run and confirm != expected:
        raise HTTPException(status_code=400,
                            detail=f"Real delete needs \"confirm\": \"{expected}\" (exactly). Nothing was deleted.")


def company_code(company: str) -> str:
    try:
        return require_company(company).company_id
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


def run(action, *args, **kwargs) -> dict:
    """Calls the remove step and turns its errors into HTTP replies."""
    try:
        return action(*args, **kwargs)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


# --- Endpoints ---------------------------------------------------------------------------
@router.post("/filing")
def delete_filing(body: FilingDelete) -> dict:
    """One PDF: its chunks (Qdrant) and its filing record (Postgres)."""
    check_confirm(body.dry_run, body.confirm, body.doc_id)
    return run(remove.remove_filing, body.doc_id, dry_run=body.dry_run)


@router.post("/company-filings")
def delete_company_filings(body: CompanyFilingsDelete) -> dict:
    """A company's PDFs (chunks + filing records). The company and its aliases stay."""
    check_confirm(body.dry_run, body.confirm, company_code(body.company))
    return run(remove.remove_company_filings, body.company, period=body.period,
               doc_type=body.doc_type, dry_run=body.dry_run)


@router.post("/company")
def delete_company(body: CompanyDelete) -> dict:
    """Everything about a company: all its chunks, filings, aliases and the company row."""
    check_confirm(body.dry_run, body.confirm, company_code(body.company))
    return run(remove.remove_company, body.company, dry_run=body.dry_run)
