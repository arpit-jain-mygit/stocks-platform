# Stocks RAG – How to run

Ask questions about Indian listed companies' financial-result PDFs.
Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · Data design: [db-design.md](db-design.md) · Roadmap: [features.md](features.md)

All commands run from the **project root** (`stocks-rag/`) with the virtual environment active.

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
pip install -r requirements.txt
```

Run `source .venv/bin/activate` in every new terminal. A `ModuleNotFoundError` (e.g. `pymupdf`) means it is not active.

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

Every stored chunk uses the company's canonical **code** (`company_id`, e.g. `VIDEOIND`), so name spellings never split one company in two. Lookups accept the code, NSE symbol, BSE code, ISIN, CIN, name or any alias.

**Add a company or doc type:** `db/samples/add_company.sql` in the Supabase SQL editor (Block 1 company + aliases, Block 2 doc type). Dry run by default; it refuses identifiers that already belong to another company. The API sees changes within 60 seconds. List them with `GET /companies` and `GET /doc-types`.

**Periods** use the Indian financial year (April–March): `Q3 FY25` = quarter ended 31-Dec-2024, `FY25` = year ended 31-Mar-2025. Each chunk stores `fiscal_year`, `quarter`, `period_end` and the label `Q3 FY25 (quarter ended 31-Dec-2024)`.

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
| GET | `/companies` | – | Known companies and their aliases |
| GET | `/doc-types` | – | Allowed document types + default |
| GET | `/documents` | optional `?company=` `&doc_type=` | Every ingested PDF and its status |
| GET | `/documents/{doc_id}` | – | One PDF's record |
| POST | `/ask` | JSON: `question`, `company?`, `period?`, `doc_type?`, `top_k?` | `answer` + cited `sources` |

All except `/health` need header `X-API-Key: <APP_API_KEY>`.

`company` accepts the company ID, BSE code, name or any alias (`VIDEOIND`, `511389`, `Videocon`). `period` accepts `Q3 FY25`, `FY25` etc. `doc_type` is a code from `/doc-types`. Unknown values return **400** with the allowed values.

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

## 6. Files the runs create

| Path | What | Safe to delete? |
|---|---|---|
| `data/cache/<doc_id>/<variant>/page_NNN.md` | Vision/OCR result per scanned page | Yes – but re-reading costs model calls |
| `data/cache/vectors/<model>-<dim>/` | One cached vector per chunk text | Yes – but re-embedding costs model calls |
| `data/<file>.pages.md` | All pages as text (from `pdf_reader`) | Yes |
| `data/<file>.chunks.md` | All chunks (from `chunker`) | Yes |
| `eval/results/<COMPANY_ID>/run-*.json` | Eval runs per company | Yes |

---

## 7. Troubleshooting

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
