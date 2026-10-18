"""
main.py - The web API (FastAPI) in front of the ingestion and question-answering code.

Endpoints:
  GET  /health                 is the server up?
  POST /ingest                 upload a PDF (+ company, period) -> starts ingestion
  GET  /jobs/{job_id}          progress of one ingestion
  GET  /companies              companies the app knows (Postgres); ?ingested=true = only those with data
  GET  /companies/{company}    one company (all its details) + its filings, newest first
  GET  /doc-types              allowed document types (Postgres)
  GET  /documents              every ingested PDF and its status (optional ?company=&doc_type=)
  GET  /documents/{doc_id}     one PDF's record
  POST /ask                    question -> answer with cited sources

company: ID, BSE code, name or alias (e.g. VIDEOIND, 511389, "Videocon")
period:  "Q3 FY25", "FY25" ...
doc_type: code from /doc-types, default quarterly_results
(unknown values -> 400 with a clear message)

Run locally:   uvicorn api.main:app --reload
Then open:     http://127.0.0.1:8000/docs   (interactive page to try every endpoint)

Ingestion can take a minute or more (the vision model reads scanned pages),
so /ingest answers immediately with a job_id and does the work in the
background. Poll /jobs/{job_id} to see when it is done.
"""

# --- Imports -----------------------------------------------------------------
# os:            reads ENABLE_RISKY_DELETE_APIS / ENABLE_BACKUP_APIS.
# uuid:          random IDs for jobs.
# datetime:      timestamps on jobs.
# FastAPI parts: the web framework (routes, uploads, errors, security header).
# BaseModel:     describes the JSON bodies of requests and responses.
# ingest_pdf:     the full ingestion pipeline (ingest/pipeline.py).
# check_existing: the pipeline's duplicate check, used up front for instant replies.
# store:          filing records for GET /documents (ingest/store.py -> Postgres).
# answer:         the question-answering step (query/answer.py).
# describe:       validates company + period for ingestion (ingest/pipeline.py).
# build_filters:  validates company + period for questions (query/search.py).
# companies:      the company registry (utils/companies.py).
import os
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.security import require_api_key

from ingest import store
from ingest.formats import check_format
from ingest.pipeline import check_existing, describe, ingest_pdf
from query.answer import answer
from query.search import build_filters
from utils.companies import company_dict, find_company, load_companies
from utils.doc_types import load_doc_types

# --- Settings ----------------------------------------------------------------
# Largest PDF accepted, in megabytes.
MAX_UPLOAD_MB = 25

app = FastAPI(title="Stocks RAG", description="Ask questions about listed companies' financial filings.")

# Risky delete APIs (api/risky_delete_apis/) exist only when switched on in .env:
# ENABLE_RISKY_DELETE_APIS=true. They also need the X-Admin-Key header (ADMIN_API_KEY).
if os.getenv("ENABLE_RISKY_DELETE_APIS", "").lower() == "true":
    from api.risky_delete_apis import router as risky_delete_router
    app.include_router(risky_delete_router)

# Backup / restore APIs (api/backup_apis/): ENABLE_BACKUP_APIS=true + X-Admin-Key.
if os.getenv("ENABLE_BACKUP_APIS", "").lower() == "true":
    from api.backup_apis import router as backup_router
    app.include_router(backup_router)

# Ingestion jobs, kept in memory: job_id -> details.
# Note: they disappear when the server restarts. That's OK - the lasting
# record of every PDF lives in Qdrant (GET /documents).
jobs: dict[str, dict] = {}


# --- Request / response shapes ------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, examples=["What was the net loss for the nine months?"])
    company: str | None = Field(None, examples=["VIDEOIND"], description="ID, BSE code, name or alias; empty = all companies")
    period: str | None = Field(None, examples=["Q3 FY25"], description="e.g. 'Q3 FY25' or 'FY25'; empty = all periods")
    doc_type: str | None = Field(None, examples=["quarterly_results"], description="code from /doc-types; empty = all types")
    top_k: int = Field(6, ge=1, le=20, description="How many chunks to give the model")


class Source(BaseModel):
    ref: str
    file_name: str
    pages: str
    section: str
    kind: str
    score: float
    doc_id: str
    company_id: str = ""


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]


# --- Background work ---------------------------------------------------------------------
def run_ingestion(job_id: str, pdf_bytes: bytes, file_name: str, company: str, period: str,
                  doc_type: str, force: bool) -> None:
    """Runs the pipeline for one job and records the outcome. Called in the background."""
    jobs[job_id]["status"] = "running"
    try:
        result = ingest_pdf(pdf_bytes, file_name, company, period, doc_type=doc_type, force=force)
        jobs[job_id].update(status=result["status"], result=result)
    except Exception as error:                      # any failure is reported on the job
        jobs[job_id].update(status="failed", error=str(error))
    jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


# --- Endpoints ------------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    """Simple check that the server is running (no API key needed)."""
    return {"status": "ok"}


@app.post("/ingest", dependencies=[Depends(require_api_key)])
async def ingest(
    background: BackgroundTasks,
    file: UploadFile = File(..., description="The filing: .pdf, .csv, .xlsx, .pptx, .docx, .txt or .md"),
    company: str = Form(..., examples=["VIDEOIND"], description="ID, BSE code, name or alias from /companies"),
    period: str = Form(..., examples=["Q3 FY25"], description="e.g. 'Q3 FY25' or 'FY25'"),
    doc_type: str = Form("quarterly_results", description="code from /doc-types"),
    force: bool = Form(False, description="Re-ingest even if this PDF was already stored"),
) -> dict:
    """
    Uploads a PDF. Returns straight away:
      - status "skipped" if this exact PDF is already stored (nothing to do), or
      - status "queued" with a job_id - follow it at GET /jobs/{job_id}.
    """
    pdf_bytes = await file.read()     # any supported file type (see ingest/formats/)

    # Basic checks before any work.
    if len(pdf_bytes) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {MAX_UPLOAD_MB} MB")
    try:
        check_format(file.filename, pdf_bytes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    try:
        meta = describe(company, period, doc_type)   # known company? readable period? allowed doc type?
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    # Duplicate check up front (same function the pipeline uses), so a
    # re-upload answers instantly instead of starting a background job.
    doc_id, skipped = check_existing(pdf_bytes)
    if skipped and not force:
        return skipped

    # Otherwise start a background job.
    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "job_id": job_id, "status": "queued", "doc_id": doc_id, "file_name": file.filename,
        "company_id": meta["company_id"], "period": meta["period"], "doc_type": meta["doc_type"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    background.add_task(run_ingestion, job_id, pdf_bytes, file.filename, company, period, meta["doc_type"], force)
    return {"status": "queued", "job_id": job_id, "doc_id": doc_id}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: str) -> dict:
    """Progress of one ingestion: queued -> running -> complete / skipped / failed."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Unknown job_id (jobs are forgotten when the server restarts)")
    return jobs[job_id]


@app.get("/companies", dependencies=[Depends(require_api_key)])
def companies(ingested: bool = False) -> list[dict]:
    """
    Every company (ID, name, country, identifiers - tickers per exchange, ISIN ... - and aliases).
    ?ingested=true -> only companies with at least one completely ingested filing
    (what the UI lists - a company with no data can't answer questions).
    """
    found = load_companies()
    if ingested:
        with_data = {f["company_id"] for f in store.list_documents() if f.get("status") == "complete"}
        found = [c for c in found if c.company_id in with_data]
    return [company_dict(c) for c in found]


@app.get("/companies/{company}", dependencies=[Depends(require_api_key)])
def company_detail(company: str) -> dict:
    """
    One company: every stored detail (country, identifiers, sector, status, aliases ...)
    plus "filings" = its ingested PDFs, newest first. company = ID, name, alias, ISIN,
    "EXCHANGE:TICKER" or a bare ticker that only one company has.
    """
    try:
        found = find_company(company)
    except ValueError as error:                       # a bare ticker used by several companies
        raise HTTPException(status_code=400, detail=str(error))
    if found is None:
        raise HTTPException(status_code=404, detail=f"No company {company!r}")
    filings = [f for f in store.list_documents() if f["company_id"] == found.company_id]
    return {**company_dict(found), "filings": filings}


@app.get("/doc-types", dependencies=[Depends(require_api_key)])
def doc_types() -> dict:
    """Allowed document types and the default."""
    return load_doc_types()


@app.get("/documents", dependencies=[Depends(require_api_key)])
def documents(company: str | None = None, doc_type: str | None = None) -> list[dict]:
    """Every ingested PDF with its status, company, period, pages and chunk count. Optional ?company=&doc_type=."""
    try:
        wanted = build_filters(company=company, doc_type=doc_type)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return [r for r in store.list_documents() if all(r.get(k) == v for k, v in wanted.items())]


@app.get("/documents/{doc_id}", dependencies=[Depends(require_api_key)])
def document(doc_id: str) -> dict:
    """One PDF's record."""
    record = store.get_document(doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No document with this doc_id")
    return record


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(require_api_key)])
def ask(request: AskRequest) -> dict:
    """Answers a question from the ingested filings, citing file and page for every fact."""
    try:
        build_filters(request.company, request.period, request.doc_type)   # 400 before any model call
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return answer(request.question, company=request.company, period=request.period,
                  doc_type=request.doc_type, top_k=request.top_k)
