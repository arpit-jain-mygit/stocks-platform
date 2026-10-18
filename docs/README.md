# Stocks RAG – How to run

Ask questions about listed companies' financial filings (PDFs) - any market; filings in English.
Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · Data design: [db-design.md](db-design.md) · Roadmap: [features.md](features.md) · UX ideas: [UX.md](UX.md)

Repo layout: **`backend/`** = FastAPI app, ingestion, eval, SQL (deployed to Railway) · **`ui/`** = web UI (Vercel) · **`docs/`** = these docs.
Code paths in the docs (e.g. `ingest/chunker.py`, `data/`, `eval/`) are inside `backend/`.

All commands run from **`backend/`** with the virtual environment active (`.env`, `data/` and the caches live there).

---

## Contents

- [1. Setup](#1-setup)
  - [1.1 Prerequisites](#11-prerequisites)
  - [1.2 Install](#12-install)
  - [1.3 The .env file](#13-the-env-file)
  - [1.4 Postgres](#14-postgres)
  - [1.5 Companies, periods and document types](#15-companies-periods-and-document-types)
- [2. Run the whole ingestion pipeline (one command)](#2-run-the-whole-ingestion-pipeline-one-command)
  - [2.1 Ingestion commands by document type](#21-ingestion-commands-by-document-type)
- [3. Run the API](#3-run-the-api)
  - [3.1 Start the server](#31-start-the-server)
  - [3.2 Endpoints](#32-endpoints)
  - [3.3 Way 1 – Browser (Swagger UI)](#33-way-1--browser-swagger-ui)
  - [3.4 Way 2 – curl](#34-way-2--curl)
  - [3.5 Way 3 – Python](#35-way-3--python)
  - [3.6 Way 4 – Postman / Insomnia](#36-way-4--postman--insomnia)
  - [3.7 Way 5 – Eval sets (one per company)](#37-way-5--eval-sets-one-per-company)
  - [3.8 Automated API tests (run before and after every refactor)](#38-automated-api-tests-run-before-and-after-every-refactor)
- [4. Run each piece on its own](#4-run-each-piece-on-its-own)
  - [Examples (Videocon sample)](#examples-videocon-sample)
- [5. Remove ingested data](#5-remove-ingested-data)
  - [5.1 Delete APIs (Postgres + Qdrant together)](#51-delete-apis-postgres--qdrant-together)
  - [5.2 SQL samples (Postgres only)](#52-sql-samples-postgres-only)
  - [5.3 Backup and restore (Postgres + Qdrant)](#53-backup-and-restore-postgres--qdrant)
- [6. Deploy the backend to Railway](#6-deploy-the-backend-to-railway)
- [7. Deploy the UI to Vercel](#7-deploy-the-ui-to-vercel)
- [8. Files the runs create](#8-files-the-runs-create)
- [9. Troubleshooting](#9-troubleshooting)
  - [Checking Railway logs](#checking-railway-logs)
  - [Vercel (UI)](#vercel-ui)
  - [Looking inside the Railway container (SSH)](#looking-inside-the-railway-container-ssh)

---

## 1. Setup

### 1.1 Prerequisites

| Need | Why | Get it |
|---|---|---|
| Python 3.11+ (tested on 3.14) | Runs everything | python.org / Homebrew |
| Tesseract | OCR fallback for pages the vision model refuses | `brew install tesseract` |
| Gemini API key | Vision, answers, embeddings (free tier) | https://aistudio.google.com/apikey |
| Qdrant cluster | Vector store (free 1 GB) | https://cloud.qdrant.io |
| Postgres | Companies, doc types, filing records (Supabase free tier) | https://supabase.com |

### 1.2 Install

```bash
cd /Users/arpit/Documents/my-ai-projects/stocks-rag
```
```bash
python3 -m venv .venv
```
```bash
source .venv/bin/activate
```
```bash
cd backend
```
```bash
pip install -r requirements.txt
```

The virtual environment lives at the repo root (`.venv/`); everything else runs from `backend/`.
In every new terminal: `source .venv/bin/activate` from the repo root, then `cd backend`. A `ModuleNotFoundError` (e.g. `pymupdf`) means it is not active.

### 1.3 The `.env` file

```bash
cp .env.example .env
```

Then fill in the values. `.env` is in `.gitignore` – never commit it.

| Variable | Required | Example / default | Meaning |
|---|---|---|---|
| `GEMINI_API_KEY` | yes | `AIza…` | Shared Gemini key for all roles |
| `VISION_PROVIDER` / `VISION_MODEL` | – | `gemini` / `gemini-3.5-flash-lite` | Model that reads scanned pages |
| `ANSWER_PROVIDER` / `ANSWER_MODEL` | – | `gemini` / `gemini-3.5-flash-lite` | Model that writes answers |
| `EMBED_PROVIDER` / `EMBED_MODEL` | – | `gemini` / `gemini-embedding-001` | Model that turns text into vectors |
| `EMBED_DIM` | – | `768` | Vector size (must match the Qdrant collection) |
| `EMBED_BATCH_SIZE` / `EMBED_PAUSE_SECONDS` | – | `20` / `2` | Chunks per embedding request, pause between requests; each batch is saved as it finishes |
| `TABLE_PAGES_TO_VISION` | – | `true` | Typed pages that are mostly figures (tables) are also read by the vision model so columns stay aligned; text layer is the fallback |
| `VISION_API_KEY` / `ANSWER_API_KEY` / `EMBED_API_KEY` | – | empty | Per-role key; empty = use `GEMINI_API_KEY` |
| `VECTOR_STORE` | – | `qdrant` | Which vector database |
| `QDRANT_URL` | yes | `https://xxxx.cloud.qdrant.io:6333` | Qdrant cluster URL |
| `QDRANT_API_KEY` | yes | `…` | Qdrant key |
| `QDRANT_CHUNKS_COLLECTION` | – | `stocks_rag_chunks` | Chunks collection |
| `APP_API_KEY` | recommended | random string | Clients must send it as `X-API-Key` (empty = API open) |
| `METADATA_STORE` | – | `postgres` | Where companies, doc types and filing records (dedup) live |
| `DATABASE_URL` | yes | `postgresql://postgres.<ref>:…@…pooler.supabase.com:5432/postgres` | Supabase → Connect → **Session pooler** URI |

Generate an `APP_API_KEY`:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Changing models:** a new `VISION_MODEL` re-reads scanned pages once; a new `EMBED_MODEL` or `EMBED_DIM` re-embeds everything and needs a new Qdrant collection name. The caches in `data/cache/` handle the rest.

### 1.4 Postgres

Postgres is the **only** place companies, doc types and filing records live. One command creates the tables **and** the starting data (Videocon, OFSS, 7 doc types); only new migrations run:
```bash
python db/migrate.py
```
See what is applied:
```bash
python db/migrate.py --status
```

### 1.5 Companies, periods and document types

Every stored chunk uses the company's canonical **code** (`company_id`, e.g. `VIDEOIND`), so name spellings never split one company in two. Lookups accept the code, name, any alias, any identifier (ISIN, CIN, LEI, CIK…), a ticker with its exchange (`NSE:OFSS`, `NASDAQ:MSFT`) or a bare ticker (`OFSS`, `511389`) when only one company has it - a bare ticker shared by companies on different exchanges returns **400** listing the `EXCHANGE:TICKER` choices.

**Add a company or doc type:** `db/samples/add_company.sql` in the Supabase SQL editor (Block 1 company + aliases, Block 2 doc type). Dry run by default; it refuses identifiers that already belong to another company. The API sees changes within 60 seconds. List them with `GET /companies` and `GET /doc-types`.

**Periods** follow each company's own financial year, which ends in its `fy_end_month` (Postgres `companies`; 3 = March, the Indian default; 12 = December, most US / EU companies). `FY25` = the financial year that ends in 2025; Q4 ends on the year-end. Accepted: `Q3 FY25`, `FY25`, `Q3 2025`, `FY2025`, `2025`. For a March year-end, `Q3 FY25` = quarter ended 31-Dec-2024 and `FY25` = year ended 31-Mar-2025; for a December year-end, `Q3 FY25` = quarter ended 30-Sep-2025. Each chunk stores `fiscal_year`, `quarter`, `period_end` and a label like `Q3 FY25 (quarter ended 31-Dec-2024)`. Filters (`?period=`) use `fiscal_year` + `quarter`, so `Q3 FY25` means each company's own Q3 FY25.

**Languages and currencies:** filings in English (OCR fallback: `OCR_LANGUAGE=eng`). Any currency and scale (₹, $, €, £, ¥; thousands, millions, billions, crore, lakh) - answers keep the currency and units printed in the filing.

**Document types:** `quarterly_results` (default), `annual_report`, `financial_statements`, `investor_presentation`, `earnings_call_transcript`, `shareholding_pattern`, `announcement`. Input is normalised (`Annual Report` → `annual_report`); anything else is rejected. Stored on every chunk and filing record as `doc_type`.

---

## 2. Run the whole ingestion pipeline (one command)

Put the PDF in `data/`, then:

```bash
python -m ingest.pipeline data/Videocon-Financial_Results_Dec-24.pdf VIDEOIND "Q3 FY25"
```

Runs: ids → pdf_reader → chunker → embeddings → store.

Other document type (default `quarterly_results`):
```bash
python -m ingest.pipeline data/<annual-report>.pdf VIDEOIND "FY24" --doc-type=annual_report
```

| Situation | Result |
|---|---|
| New PDF | Reads, chunks, embeds, stores; prints `stored N chunks` |
| Same PDF again (even renamed) | `already ingested … skipping` – no model calls |
| Re-store anyway (e.g. after changing chunking) | add `--force` at the end – uses caches, so usually no model calls |
| A page can't be read | Stops with an error; record marked `failed`; re-run to retry |

### 2.1 Ingestion commands by document type

Run these from `backend/` with the venv active. The syntax is the same for every document type:

```bash
python -m ingest.pipeline <PDF_PATH> <COMPANY> "<PERIOD>" --doc-type=<DOC_TYPE>
```

Add `--force` at the end to re-ingest a file that's already stored.

**Placeholders**

| Placeholder | Meaning | Examples |
|---|---|---|
| `<PDF_PATH>` | Path to the PDF (only PDFs are accepted today) | `/Users/arpit/Downloads/report.pdf` |
| `<COMPANY>` | Company code, name, alias, ISIN, or `EXCHANGE:TICKER` | `MSFT`, `OFSS`, `NASDAQ:MSFT`, `Videocon` |
| `"<PERIOD>"` | Quarter or year: `Q1 FY26` for a quarter, `FY26` for a full year | `"Q1 FY26"`, `"FY26"`, `"Q3 2025"` for calendar-year companies |
| `<DOC_TYPE>` | One of the codes below | `quarterly_results` |

**Document types**

| Code | Use for |
|---|---|
| `quarterly_results` | Quarterly financial results (the default if you omit `--doc-type`) |
| `annual_report` | Annual report |
| `financial_statements` | Statements such as balance sheet, P&L, cash flow |
| `earnings_call_transcript` | Earnings call transcript |
| `investor_presentation` | Investor or earnings slide deck |
| `announcement` | Corporate announcement, such as a board meeting or insolvency update |
| `shareholding_pattern` | Shareholding pattern |

**Examples**

```bash
# Quarterly results (default type)
python -m ingest.pipeline /Users/arpit/Downloads/Videocon-Financial_Results_Dec-24.pdf VIDEOIND "Q3 FY25"

# Annual report
python -m ingest.pipeline /Users/arpit/Downloads/ofss-software-limited-ar-2025-26.pdf OFSS "FY26" --doc-type=annual_report

# Earnings call transcript
python -m ingest.pipeline /Users/arpit/Downloads/cdn-dynmedia-1.microsoft.com.pdf MSFT "Q1 FY26" --doc-type=earnings_call_transcript

# Investor presentation (export the .pptx to PDF first)
python -m ingest.pipeline /Users/arpit/Downloads/Microsoft-SlidesFY26Q1.pdf MSFT "Q1 FY26" --doc-type=investor_presentation

# Financial statements
python -m ingest.pipeline /Users/arpit/Downloads/MSFT-balance-sheet-Q1-FY26.pdf MSFT "Q1 FY26" --doc-type=financial_statements

# Re-ingest a file that's already stored
python -m ingest.pipeline /Users/arpit/Downloads/Microsoft-SlidesFY26Q1.pdf MSFT "Q1 FY26" --doc-type=investor_presentation --force
```

Things to keep in mind:
- **File types:** PDF, CSV, Excel (`.xlsx`), PowerPoint (`.pptx`), Word (`.docx`), text (`.txt`) and Markdown (`.md`). Each has its own reader class in `backend/ingest/formats/`, picked by a factory (`factory.py`). Pictures in PowerPoint slides with little text go to the vision model; spreadsheets and CSV are read cell by cell with no model calls. Legacy `.xls`, `.ppt` and `.doc` need converting first.
- **Quote the period.** Without quotes, the shell splits `Q1 FY26` into two arguments and the command fails.
- **A new period needs its company's year-end.** `"Q1 FY26"` means the quarter ended 30 Sep 2025 for MSFT (June year-end) but 30 Jun 2025 for a company that ends its year in March.

---

## 3. Run the API

### 3.1 Start the server

```bash
uvicorn api.main:app --reload
```

Server: http://127.0.0.1:8000 · Interactive docs: http://127.0.0.1:8000/docs

Other host/port (e.g. reachable from other devices):
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8080
```

### 3.2 Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | – | `{"status": "ok"}` (no key needed) |
| POST | `/ingest` | form: `file`, `company`, `period` (`Q3 FY25`), `doc_type`, `force` | `skipped`, or `queued` + `job_id` |
| GET | `/jobs/{job_id}` | – | `queued` → `running` → `complete` / `skipped` / `failed` |
| GET | `/companies` | `ingested` (true = only companies with a complete filing) | Known companies and their aliases |
| GET | `/companies/{company}` | – | One company (codes, sector, FY end month, status, aliases) + its filings, newest first; 404 if unknown |
| GET | `/doc-types` | – | Allowed document types + default |
| GET | `/documents` | optional `?company=` `&doc_type=` | Every ingested PDF and its status |
| GET | `/documents/{doc_id}` | – | One PDF's record |
| POST | `/ask` | JSON: `question`, `company?`, `period?`, `doc_type?`, `top_k?` | `answer` + cited `sources` |

All except `/health` need header `X-API-Key: <APP_API_KEY>`.

`company` accepts the company ID, name, alias, ISIN / CIN, `EXCHANGE:TICKER` or a unique bare ticker (`VIDEOIND`, `BSE:511389`, `511389`, `Videocon`). `period` accepts `Q3 FY25`, `FY25` etc. `doc_type` is a code from `/doc-types`. Unknown values return **400** with the allowed values.

### 3.3 Way 1 – Browser (Swagger UI)

1. Open http://127.0.0.1:8000/docs
2. **Authorize** → paste `APP_API_KEY` → Authorize → Close
3. Pick an endpoint → **Try it out** → **Execute**

For `/ask`, delete the `"period": "string"` placeholder or set it to `null`.

### 3.4 Way 2 – curl

Load the key into the terminal once:
```bash
export APP_API_KEY=$(grep '^APP_API_KEY=' .env | cut -d= -f2)
```

Health:
```bash
curl -s http://127.0.0.1:8000/health
```

Ingest a PDF:
```bash
curl -s -X POST http://127.0.0.1:8000/ingest -H "X-API-Key: $APP_API_KEY" -F "file=@data/Videocon-Financial_Results_Dec-24.pdf" -F "company=VIDEOIND" -F "period=Q3 FY25"
```

Re-ingest anyway (add `force`):
```bash
curl -s -X POST http://127.0.0.1:8000/ingest -H "X-API-Key: $APP_API_KEY" -F "file=@data/Videocon-Financial_Results_Dec-24.pdf" -F "company=VIDEOIND" -F "period=Q3 FY25" -F "force=true"
```

Job progress (use the `job_id` from the ingest reply):
```bash
curl -s http://127.0.0.1:8000/jobs/JOB_ID -H "X-API-Key: $APP_API_KEY"
```

List companies:
```bash
curl -s http://127.0.0.1:8000/companies -H "X-API-Key: $APP_API_KEY"
```

List documents (all, or one company):
```bash
curl -s http://127.0.0.1:8000/documents -H "X-API-Key: $APP_API_KEY"
```
```bash
curl -s "http://127.0.0.1:8000/documents?company=VIDEOIND" -H "X-API-Key: $APP_API_KEY"
```

Ask a question:
```bash
curl -s -X POST http://127.0.0.1:8000/ask -H "X-API-Key: $APP_API_KEY" -H "Content-Type: application/json" -d '{"question": "What was the net loss for the nine months?", "company": "VIDEOIND", "period": "Q3 FY25"}'
```

### 3.5 Way 3 – Python

```python
import json, os, urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8000/ask",
    data=json.dumps({"question": "What were the finance costs in Q3 FY25?",
                     "company": "Videocon Industries Ltd"}).encode(),
    headers={"Content-Type": "application/json", "X-API-Key": os.environ["APP_API_KEY"]},
    method="POST",
)
print(json.loads(urllib.request.urlopen(req).read())["answer"])
```

### 3.6 Way 4 – Postman / Insomnia

Import http://127.0.0.1:8000/openapi.json, then add header `X-API-Key` to the collection.

### 3.7 Way 5 – Eval sets (one per company)

| Company | Eval set | Cases | Source document |
|---|---|---|---|
| VIDEOIND | `eval/companies/VIDEOIND/eval_set.json` | 41 | Q3 FY25 results |
| OFSS | `eval/companies/OFSS/eval_set.json` | 23 | Annual Report 2025-26 |

Every case: the `/ask` request, a hand-written expected response (from the PDF, not from the app), and deterministic checks. Add a company: create `eval/companies/<COMPANY_ID>/eval_set.json` in the same format.

With the server running – every company:
```bash
python eval/run_eval.py
```
One company / some cases:
```bash
python eval/run_eval.py --company OFSS --only ofss-01 ofss-10
```
Check the eval files themselves (no API, no model calls):
```bash
python eval/run_eval.py --self-test
```
Each company's run is saved to **`eval/results/<COMPANY_ID>/run-<time>.json`**: summary, then per case the request, expected response, actual response, checks and failures – ready for an LLM judge to compare expected vs actual. Each question costs 1 embedding + 1 answer call.

### 3.8 Automated API tests (run before and after every refactor)

`backend/tests/` holds end-to-end tests: real API, pipeline, chunker, search and answer code, with in-memory
fakes for Gemini, Qdrant and Postgres (`tests/fakes.py`). **Free, about 2 seconds, no network, never touches
your data** (caches go to a temp folder; building a real Gemini / Qdrant / Postgres client fails the test).

```bash
pip install -r requirements-dev.txt
```
```bash
python -m pytest
```

| Area | What is checked |
|---|---|
| Security | `/health` open; every other endpoint 401 without / with a wrong `X-API-Key`; risky APIs 403 without `X-Admin-Key`, 404 when switched off |
| Ingestion | bad company / period / doc type / non-PDF → 400 with no model call; 3-page PDF → table + scanned pages to vision, fact cards, full chunk payload, filing record; duplicate → skipped; `force` → no duplicate chunks, caches reused; new version → old one superseded |
| Questions | answer cites only used sources with file / doc_id; retrieved figure reaches the prompt; no data → not-found with no answer call; bad input → 400/422 with no model call |
| Deletes | dry run changes nothing; real delete needs `confirm`; filing / company-filings / company cascade across both stores; other companies untouched |
| Backup | create → wipe → restore (`replace`) brings back chunks, filings, company; dry run and missing `confirm` change nothing; bad file → 400 |

These test the app's flow, not answer quality (that is the eval sets, 3.7) and not the real Qdrant /
Postgres adapters.

---

## 4. Run each piece on its own

Every step has a test entry point. Each reuses the caches, so repeated runs are cheap.

| # | Module | Command | Model calls | Output |
|---|---|---|---|---|
| 1 | `ingest/ids.py` | `python -m ingest.ids <pdf>` | none | doc_id + sample point_id |
| 2 | `ingest/pdf_reader.py` | `python -m ingest.pdf_reader <pdf>` | vision, only for uncached scanned pages | `data/<file>.pages.md` |
| 3 | `ingest/chunker.py` | `python -m ingest.chunker <pdf> <company> "<period>"` | none if pages cached | `data/<file>.chunks.md` |
| 4 | `ingest/embeddings.py` | `python -m ingest.embeddings <pdf> <company> "<period>" ["question"]` | embed: uncached chunks + 1 for the test question | top 5 chunks (in memory) |
| 5 | `ingest/pipeline.py` | `python -m ingest.pipeline <pdf> <company> "<period>" [--doc-type=…] [--force]` | as steps 2–4 | stored in vector store |
| – | `utils/vectorstore` | `python -m utils.vectorstore ["question"]` | none; 1 embed if a question is given | stats, documents, search hits |
| – | `query/search.py` | `python -m query.search "question" [company]` | 1 embed | top 6 chunks |
| – | `query/answer.py` | `python -m query.answer "question" [company]` | 1 embed + 1 answer | answer + sources |
| – | `eval/run_eval.py` | `python eval/run_eval.py [--company X] [--self-test]` | via the API (none with `--self-test`) | pass/fail per company |
| – | `docs/architecture_diagram.py` | `python docs/architecture_diagram.py` | none | ASCII diagram + alignment check |
| – | `db/migrate.py` | `python db/migrate.py [--status]` | none | Creates / updates Postgres tables |

`ingest/store.py`, `utils/llm/`, `utils/ocr.py`, `utils/prompts.py` and the caches have no entry point; they are used by the steps above.

### Examples (Videocon sample)

```bash
python -m ingest.ids data/Videocon-Financial_Results_Dec-24.pdf
```
```bash
python -m ingest.pdf_reader data/Videocon-Financial_Results_Dec-24.pdf
```
```bash
python -m ingest.pdf_reader data/Videocon-Financial_Results_Dec-24.pdf --refresh
```
```bash
python -m ingest.chunker data/Videocon-Financial_Results_Dec-24.pdf VIDEOIND "Q3 FY25"
```
```bash
python -m ingest.embeddings data/Videocon-Financial_Results_Dec-24.pdf VIDEOIND "Q3 FY25" "What were finance costs?"
```
```bash
python -m utils.vectorstore
```
```bash
python -m query.search "What were finance costs?" VIDEOIND
```
```bash
python -m query.answer "What was the net loss for the nine months?" Videocon
```

`--refresh` on `pdf_reader` ignores the page cache and calls the vision model for every scanned page again.

---

## 5. Remove ingested data

Sample SQL for the Supabase SQL editor: **`db/samples/remove_ingested.sql`**. It covers: preview, delete by `doc_id`, by company, by company + period (+ doc type), by file name, failed/stuck ingestions, and delete everything. Companies and doc types are never touched.

### 5.1 Delete APIs (Postgres + Qdrant together)

`api/risky_delete_apis/` – removes chunks (Qdrant) **and** records (Postgres) in one call. Five locks:

1. Off unless `.env` has `ENABLE_RISKY_DELETE_APIS=true` (restart the API; otherwise 404).
2. `X-API-Key` header, as for every endpoint.
3. `X-Admin-Key` header = `ADMIN_API_KEY` (if that is empty, always 403).
4. `dry_run` defaults to `true` – the reply shows what **would** be removed.
5. A real delete needs `"confirm"` repeating the target exactly (the `doc_id` or company code).

| POST | Body | Removes |
|---|---|---|
| `/risky-delete/filing` | `doc_id` | One PDF (also clears chunks left without a record) |
| `/risky-delete/company-filings` | `company`, `period?`, `doc_type?` | A company's PDFs; company and aliases stay |
| `/risky-delete/company` | `company` | Chunks, filings, aliases and the company row |

Load the keys once:
```bash
export APP_API_KEY=$(grep '^APP_API_KEY=' .env | cut -d= -f2) ADMIN_API_KEY=$(grep '^ADMIN_API_KEY=' .env | cut -d= -f2)
```
Preview:
```bash
curl -s -X POST http://127.0.0.1:8000/risky-delete/company-filings -H "X-API-Key: $APP_API_KEY" -H "X-Admin-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" -d '{"company": "OFSS", "period": "FY26"}'
```
Delete:
```bash
curl -s -X POST http://127.0.0.1:8000/risky-delete/company-filings -H "X-API-Key: $APP_API_KEY" -H "X-Admin-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" -d '{"company": "OFSS", "period": "FY26", "dry_run": false, "confirm": "OFSS"}'
```
`/risky-delete/company` leaves no trace of the company in Postgres or Qdrant.

### 5.2 SQL samples (Postgres only)

PL/pgSQL blocks for whole companies: **`db/samples/delete_company.sql`**
- **Block 1** – delete a company completely (filings + aliases + company row).
- **Block 2** – delete a company's filings only (optionally one fiscal year / quarter / doc type); company and aliases stay.

Set `v_code` at the top of the block. `v_dry_run := true` (default) shows the counts and changes nothing; set it to `false` to delete.

A PDF lives in **two** places, and SQL only reaches the first:

| Where | Remove with |
|---|---|
| Postgres `filings` (record, dedup) | The SQL file |
| Qdrant `stocks_rag_chunks` (searchable chunks) | Qdrant console – requests at the bottom of the same file |

Order: run the preview query → delete the chunks in the Qdrant console for those `doc_id`s → run the matching SQL delete. Skipping the Qdrant step leaves chunks that answers can still use.

### 5.3 Backup and restore (Postgres + Qdrant)

`api/backup_apis/` – one `.json.gz` file with every Postgres row (doc types, companies, aliases, filings, applied migrations) and every Qdrant chunk (id, vector, payload). No model calls.

Locks: `ENABLE_BACKUP_APIS=true` in `.env` (restart the API), plus `X-API-Key` **and** `X-Admin-Key`. Restore: `dry_run` defaults to true; a real restore needs `confirm=RESTORE`.

| POST | Sends | Does |
|---|---|---|
| `/backup/create` | – | Downloads `stocks-rag-backup-<time>.json.gz` (≈370 KB today). Changes nothing |
| `/backup/restore` | form: `file`, `mode`, `dry_run`, `confirm` | `merge` (default) adds / updates rows and chunks; `replace` wipes both stores first, then loads |

Restore refuses a file whose embedding model / vector size differs from `.env`, or that needs migrations this database doesn't have (run `python db/migrate.py` first). Postgres loads in one transaction; Qdrant loads after it succeeds.

Load the keys once:
```bash
export APP_API_KEY=$(grep '^APP_API_KEY=' .env | cut -d= -f2) ADMIN_API_KEY=$(grep '^ADMIN_API_KEY=' .env | cut -d= -f2)
```
Take a backup:
```bash
curl -s -OJ -X POST http://127.0.0.1:8000/backup/create -H "X-API-Key: $APP_API_KEY" -H "X-Admin-Key: $ADMIN_API_KEY"
```
Check a backup file (dry run):
```bash
curl -s -X POST http://127.0.0.1:8000/backup/restore -H "X-API-Key: $APP_API_KEY" -H "X-Admin-Key: $ADMIN_API_KEY" -F "file=@stocks-rag-backup-YYYYMMDD-HHMMSS.json.gz"
```
Restore it, wiping current data:
```bash
curl -s -X POST http://127.0.0.1:8000/backup/restore -H "X-API-Key: $APP_API_KEY" -H "X-Admin-Key: $ADMIN_API_KEY" -F "file=@stocks-rag-backup-YYYYMMDD-HHMMSS.json.gz" -F "mode=replace" -F "dry_run=false" -F "confirm=RESTORE"
```
Backup files contain all your data: keep them out of git (`.gitignore` covers `backups/` and `stocks-rag-backup-*.json.gz`).

---

## 6. Deploy the backend to Railway

Files: `backend/Dockerfile` (Python + Tesseract + code), `backend/.dockerignore` (keeps `.env`, PDFs, caches,
tests out of the image), `backend/railway.json` (build with the Dockerfile, run `python db/migrate.py` before
each deploy, health check `/health`).

Qdrant and Supabase are already in the cloud, so the Railway API sees the same companies, filings and chunks
as your machine - nothing needs re-ingesting.

1. **New project:** railway.com → New Project → Deploy from GitHub repo → `stocks-platform`.
2. **Service → Settings:**
   - Source → **Root Directory** = `/backend`
   - **Config file path** = `/backend/railway.json` (the config file does not follow the root directory)
   - Build → **Watch Paths** = `/backend/**` (a docs or UI change does not redeploy the API)
3. **Service → Variables** (Raw Editor; names as in `.env.example`, values your own):
   - `GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_CHUNKS_COLLECTION`, `DATABASE_URL`
   - `APP_API_KEY`, `ADMIN_API_KEY` - **new values**, not the ones in your local `.env`
   - model / batch settings you changed from the defaults (`VISION_MODEL`, `ANSWER_MODEL`, `EMBED_MODEL`,
     `EMBED_DIM`, `EMBED_BATCH_SIZE`, `EMBED_PAUSE_SECONDS`, `TABLE_PAGES_TO_VISION`, `METADATA_STORE`)
   - `ENABLE_RISKY_DELETE_APIS=false`, `ENABLE_BACKUP_APIS=false`
   - `DATABASE_URL`: use Supabase's **Session pooler** string (the direct one is IPv6-only)
   - do **not** set `PORT` or `PAGE_CACHE_DIR` (Railway / the Dockerfile set them)
4. **Volume:** right-click the service → Attach Volume → mount path **`/data`** (page + vector caches survive redeploys).
5. **Networking → Generate Domain**, then **Deploy**.
6. **Check the logs:** pre-deploy shows `0 applied, 3 already up to date`; the deploy turns green once `/health` answers.

Test (replace the domain and key):

```bash
curl -s https://<your-app>.up.railway.app/health
```
```bash
curl -s https://<your-app>.up.railway.app/companies -H "X-API-Key: <railway APP_API_KEY>"
```

Notes: one process only (ingestion jobs live in memory, so `/jobs` is lost on restart - the filing records in
Postgres are not). Every push to `main` that touches `backend/` redeploys; run `python -m pytest` first.

---

## 7. Deploy the UI to Vercel

Files (in `ui/`): the Angular app, `api/proxy.ts` (Vercel server function: forwards `/api/...` to the
Railway backend and adds `X-API-Key`; only `GET companies`, `GET companies/<code>`, `GET doc-types`,
`GET documents`, `POST ask` are allowed) and `vercel.json` (`/api/...` -> the proxy, every other URL ->
`index.html`).

The browser only ever talks to the Vercel site, so the API key never reaches it and the backend needs no
CORS settings. Deploy the backend (section 6) first - the UI needs its URL and key.

1. **New project:** vercel.com → Add New → Project → Import Git Repository → `stocks-platform`
   (first time: allow Vercel to access the GitHub repo).
2. **Configure Project** (before the first deploy):
   - **Root Directory** = `ui` (click Edit next to it)
   - **Framework Preset** = Angular (detected)
   - **Build Command** = `npm run build` (default)
   - **Output Directory** = `dist/stocks-ui/browser` (override the default)
   - **Install Command** = `npm install` (default)
3. **Environment Variables** (same screen, or later: Settings → Environment Variables; read only by
   `api/proxy.ts` on Vercel's servers, never sent to the browser):
   - `STOCKS_API_URL` = your Railway domain, e.g. `https://stocks-platform-production.up.railway.app`
     (no trailing slash)
   - `STOCKS_API_KEY` = the Railway service's `APP_API_KEY`
4. **Deploy.** The build takes about a minute; Vercel shows the site address (`https://<project>.vercel.app`).
5. **Only rebuild the UI when `ui/` changes:** Settings → Git → Ignored Build Step → "Only build if there
   are changes in a folder" → `ui`. (Backend and docs pushes then skip the UI build.)

Test (replace the domain):

```bash
curl -s "https://<your-app>.vercel.app/api/companies?ingested=true"
```
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<your-app>.vercel.app/api/backup/create
```

The first lists the companies without any key (the proxy adds it); the second must print `404` (not
allowed through the proxy). Then open the site: company cards, details panel, and the chat
(a chat question costs 1 embedding + 1 answer model call on the backend's Gemini key).

Notes: every push to `main` that changes `ui/` redeploys (preview deployments for other branches).
Changing a variable needs a **Redeploy** (Deployments → latest → ⋮ → Redeploy) - variables apply only
to new deployments.

---

## 8. Files the runs create

| Path | What | Safe to delete? |
|---|---|---|
| `data/cache/<doc_id>/<variant>/page_NNN.md` | Vision/OCR result per scanned page | Yes – but re-reading costs model calls |
| `data/cache/vectors/<model>-<dim>/` | One cached vector per chunk text | Yes – but re-embedding costs model calls |
| `data/<file>.pages.md` | All pages as text (from `pdf_reader`) | Yes |
| `data/<file>.chunks.md` | All chunks (from `chunker`) | Yes |
| `eval/results/<COMPANY_ID>/run-*.json` | Eval runs per company | Yes |

---

## 9. Troubleshooting

| Message | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'pymupdf'` | `source .venv/bin/activate` |
| `No API key for role …` | Set `GEMINI_API_KEY` (or the role's key) in `.env` |
| `QDRANT_URL is not set` / `a URL is required` | Set `QDRANT_URL` in `.env` |
| `429 RESOURCE_EXHAUSTED` while embedding | Free-tier quota hit. Finished batches are already cached: wait (per-minute limit) or try tomorrow (daily limit), then re-run the same command - it continues where it stopped. Check usage at https://ai.dev/rate-limit; lower `EMBED_BATCH_SIZE` / raise `EMBED_PAUSE_SECONDS` |
| `Gemini … error 503, retrying` | Model overloaded; retries automatically. If it keeps failing, use a `-lite` model in `.env` |
| `refused (RECITATION) -> local OCR` | Normal for standard legal text; Tesseract reads it |
| `Tesseract is not installed` | `brew install tesseract` |
| `… stores 768-number vectors but EMBED_DIM is …` | Set `EMBED_DIM` back, or use a new `QDRANT_CHUNKS_COLLECTION` |
| `401 Missing or wrong X-API-Key header` | Send header `X-API-Key` with the value from `.env` |
| `{"detail":"Not Found"}` in the browser | Use `/docs`; `/ask` only accepts POST |
| Postgres connection times out / `Network is unreachable` | Use the Supabase **Session pooler** URI (direct connection is IPv6-only) |
| `relation "companies" does not exist` | Run `python db/migrate.py` |
| Railway: `Application not found` (404) | No domain on the service yet: Settings → Networking → Public Networking → Generate Domain, then use that URL |
| Railway: `Internal Server Error` (500) | Read the Railway logs (below); the last line of the traceback names the cause |

### Checking Railway logs

1. Click the service card, open the **Deployments** tab, click the active deployment (the green one), then open **Deploy Logs**. The error appears there at the moment you run the curl.
2. Or use the left sidebar of the project and open **Observability** (Logs), which lets you search all logs. Try searching for `Traceback` or `error`.

Build problems are in the deployment's **Build Logs**; migration problems in its **Pre-deploy** step.

### Vercel (UI)

| Message | Fix |
|---|---|
| `{"detail":"Server is missing STOCKS_API_URL / STOCKS_API_KEY"}` (500) | Add both variables (section 7), then Redeploy |
| `{"detail":"Missing or wrong X-API-Key header"}` (401) | `STOCKS_API_KEY` differs from Railway's `APP_API_KEY` - fix it, Redeploy |
| `{"detail":"Not available"}` (404) on `/api/...` | Endpoint not allowed by `ui/api/proxy.ts` (by design for risky / backup APIs) |
| Page shows "Could not load companies" | Open `https://<your-app>.vercel.app/api/companies` to see the real error (one of the rows above) |
| Build fails: "No Output Directory named … found" | Output Directory must be `dist/stocks-ui/browser`; Root Directory `ui` |
| Refreshing the page gives 404 | `vercel.json` missing from `ui/` (it sends every URL to `index.html`) |
| Logs: `Failed to load the ES module: /var/task/ui/api/proxy.js … set "type": "module"` then `SyntaxError: Unexpected token 'export'`; every `/api/...` call fails | Vercel compiles `api/proxy.ts` to `proxy.js` with `export` syntax, and Node only accepts that when the nearest `package.json` says `"type": "module"`. Fixed in `ui/package.json` (`"type": "module"`) - push, Vercel redeploys. Keep that line |

Logs: Vercel project → **Logs** (runtime, filter `/api/proxy`) or Deployments → a deployment → **Build Logs**.

### Looking inside the Railway container (SSH)

Use it to check files on the volume, e.g. that the caches survive a redeploy.

1. Install and log in to the Railway CLI (once):
   ```bash
   brew install railway
   ```
   ```bash
   railway login
   ```
   `railway ssh` also needs an SSH key on your Mac. If it says `No SSH keys found`, create one (press Enter
   for the default location; the private key never leaves your Mac), then run the SSH command again:
   ```bash
   ssh-keygen -t ed25519 -C "<your email>"
   ```
2. Right-click the service card (or its **⋮** menu) → **Copy SSH Command**, paste it in your terminal
   (`railway ssh --project=… --environment=… --service=…`). You are now inside the running container.
3. Look at the caches:
   ```bash
   ls -la /data/cache
   ```
   Expect one folder per `doc_id` plus `vectors/`. Missing or empty = nothing ingested on Railway yet
   (the folder is created by the first ingestion). Leave with `exit`.

Your prompt shows where commands run: `arpit@…-iMac backend %` = your Mac, `root@<container-id>:/app#` =
inside Railway. `ls /data` showing only `lost+found` = the volume is mounted and still empty.

**Check that the volume survives a redeploy** (no model calls):

1. Inside the container, write a marker file:
   ```bash
   mkdir -p /data/cache && echo ok > /data/cache/volume-test.txt
   ```
2. `exit`, then in Railway: **Deployments** → latest deployment's **⋮** → **Redeploy**.
3. When it is green, SSH in again:
   ```bash
   cat /data/cache/volume-test.txt
   ```
   `ok` = the volume persists (so the caches will too). Nothing / error = check Volume mount path is `/data`.
4. Clean up:
   ```bash
   rm /data/cache/volume-test.txt
   ```

Re-uploading a PDF that is already ingested does not fill the cache - the API skips it before reading any page.

The Railway cache is separate from your local `data/cache`: a `force=true` re-ingest on Railway calls the
vision and embedding models again. Run big forced re-ingests locally, where the cache already exists.
