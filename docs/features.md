# Features

## Done

- [x] PDF ingestion: typed pages, scanned pages (vision model), OCR fallback
- [x] Chunking: tables whole, row facts, sections, page ranges
- [x] Embeddings + vector store (Qdrant) with dedup and caches
- [x] Question answering with page citations
- [x] FastAPI: `/ingest`, `/jobs`, `/documents`, `/companies`, `/ask`, API key
- [x] LLM factory (per role) and vector store factory
- [x] Company registry (Postgres) + structured periods (`Q3 FY25`)
- [x] Document types (Postgres): stored on chunks/records, filter on search, `/doc-types`
- [x] Eval set (41 cases) + runner
- [x] Docs: architecture, README
- [x] Guarded delete APIs (cascade across Postgres + Qdrant) and backup / restore APIs

## To do

- [ ] **UI support** (Angular single page app in `ui/`, see `ui/README.md`; UX ideas: [UX.md](UX.md))
  - [x] Angular 22 app, router, Hello World home page, unit tests
  - [x] Chat window ("Ask a question"): question + company -> answer with cited sources (`POST /ask`)
  - [ ] Chat: keep the conversation across reloads; send earlier turns for follow-up questions
  - [x] Home page lists companies with ingested filings (`GET /companies?ingested=true`)
  - [x] API key kept server-side: dev proxy (`proxy.conf.mjs`) + Vercel function (`api/proxy.ts`, allowlisted endpoints)
  - [x] Company cards + details panel on the right (phones: under the card; address stays `/`): status, code, NSE, BSE, FY end; aliases; filings with type, file, ingested date (`GET /companies/{company}`)
- [ ] **Create the project in Git** (GitHub repo, private)
  - [ ] `.gitignore` before the first commit: `.env`, `.venv/`, caches, `data/` PDFs, `eval/results/`, backups (`*.json.gz`), `__pycache__/`
  - [ ] Check no secrets are in any file to be committed (keys only in `.env`; `.env.example` has placeholders)
  - [ ] First commit + push; `main` as the default branch
  - [ ] Railway and Vercel deploy from this repo
- [x] **Deploy APIs to Railway** (FastAPI backend) - live at `stocks-platform-production.up.railway.app`
  - [x] Dockerfile with Tesseract (OCR fallback) + `uvicorn api.main:app` (`backend/Dockerfile`, `backend/railway.json`)
  - [x] Secrets as Railway variables (Gemini, Qdrant, Supabase, `APP_API_KEY`, `ADMIN_API_KEY`); risky delete / backup APIs stay off
  - [x] Page + vector caches on a Railway volume (or cloud storage) so restarts don't re-call models (volume at `/data`, survives redeploys)
  - [x] `/health` as the health check; run `db/migrate.py` on deploy (pre-deploy command)
- [ ] **Deploy UI to Vercel**
  - [x] UI calls the Railway API through `ui/api/proxy.ts` (`STOCKS_API_URL` / `STOCKS_API_KEY` on Vercel)
  - [x] CORS: not needed - the browser only calls the Vercel site; the proxy calls Railway server-to-server
  - [x] Never put `APP_API_KEY` in browser code – Vercel server function `api/proxy.ts` (allowlisted endpoints)
- [ ] **Users support** (Google login)
- [ ] **10 companies support**
- [x] **No investment advice** (motto: "Insights from the filings, not tips for the market.")
  - [x] Answer prompt rule 0 + exact reply `NO_ADVICE` (`utils/prompts.py`); eval cases `no_advice` (OFSS 2, VIDEOIND 1)
  - [x] UI: motto under the title, full disclaimer in the page footer and in the chat before the first question (`ui/src/app/disclaimer.ts`)
- [ ] **Global companies** (any market; English filings for now)
  - [x] Periods follow each company's financial-year end (`fy_end_month`): `Q3 FY25`, `FY25`, `Q3 2025`, `2025`
  - [x] Market-neutral prompts; the answer prompt lists each cited company's year-end
  - [x] Any currency and number format in table detection and units lines ($ € £ ¥ ₹; 1,234.5 / 1.234,5 / 1,23,456)
  - [ ] Filing sources per market (e.g. US EDGAR 10-K / 10-Q, UK / EU ESEF) and per-market eval sets - later
  - [x] Company identifiers for any market: `company_identifiers` (ticker per exchange, ISIN, LEI, CIK, CIN …) + `country` (migration 004); lookup by `EXCHANGE:TICKER`
  - [ ] Drop the old `nse_symbol` / `bse_code` / `cin` / `isin` columns (later migration, once 004 is deployed)
  - [ ] Per-filing currency, units and accounting standard (Ind AS / IFRS / US GAAP) in Postgres
  - [ ] Non-English filings (OCR language packs, multilingual questions)
- [ ] **Hindi and other languages support**
- [ ] **Move platform to AWS or another cloud** (evaluate options)
- [ ] **Evaluate other embedding models**
  - [ ] FinanceParam (India-focused)
  - [ ] Google embedding model v1 (global)
- [x] **Company metadata in Postgres** (Supabase; no financial figures in Postgres for now)
  - [x] Tables: `companies`, `company_aliases`, `doc_types` (migration + RLS)
  - [x] Postgres is the only source of truth (config JSON files retired; starting data in migration 003)
  - [x] Behind a metadata-store factory (`METADATA_STORE=postgres`)
  - [x] `filings` table (one row per PDF, dedup, superseded rule); Qdrant holds chunks only
  - [ ] Later: users, ingestion jobs
  - [ ] Superseded filings: remove or filter their chunks in Qdrant
- [ ] **Split user queries: deterministic vs LLM** (save cost and latency)
  - [ ] Router: classify each question before calling any model
  - [ ] Deterministic path: direct figure lookups ("finance costs Q3 FY25") answered from stored table rows / facts – no LLM call
  - [ ] Deterministic path: simple arithmetic (Q1 = 9M − Q2 − Q3, QoQ change) computed in code
  - [ ] LLM path: explanations, prose questions, comparisons, anything ambiguous
  - [ ] Store table rows as structured numbers (company, period, line item, value, unit) to enable lookups – where: decide later (not Postgres for now; e.g. numbers on the fact chunks in the vector store)
  - [ ] Track share of questions answered without an LLM; eval both paths
- [ ] **Streaming answer response** (answer appears word by word instead of after the full wait)
  - [ ] `/ask/stream` endpoint using Server-Sent Events (FastAPI `StreamingResponse`); keep `/ask` as is for eval and scripts
  - [ ] Streaming method on the answer role in the LLM factory (Gemini `generate_content_stream`)
  - [ ] Send sources (pages, chunks) as a first or last event, then the answer text
  - [ ] Handle mid-stream errors (quota, blocked) with an error event; respect the API key check
  - [ ] UI shows text as it arrives

## Non-functional

- [ ] **Observability** – structured logs, request IDs, metrics (latency, model calls, tokens, cache hits), tracing per pipeline step
- [ ] **Security** – secrets in a vault, per-user API keys, input validation, prompt-injection guard, HTTPS, CORS
- [ ] **Availability** – health/readiness checks, persistent jobs, retries, Qdrant backups (free cluster deletes after 4 weeks idle)
- [ ] **Performance** – parallel page reading, async API, batch embeddings, response time targets for `/ask`
- [ ] **Caching** – move page/vector caches off local disk (cloud storage), cache frequent answers
- [ ] **CI/CD** – git repo, tests + eval self-test on every push, Docker image (with Tesseract), auto-deploy
- [ ] **Rate limit** – per user/API key limits on `/ask` and `/ingest`; queue to stay within LLM free-tier quotas
- [ ] **Pricing model + cost estimation** for every platform used
  - [ ] Pricing model for users (free tier, paid plans, usage limits)
  - [ ] LLM: vision (pages read), answers (questions), embeddings – per PDF and per question
  - [ ] Vector store: Qdrant free vs paid, Pinecone – by number of companies/filings
  - [ ] Hosting: Railway vs AWS vs others – API, background jobs, storage
  - [ ] Metadata DB (Postgres), auth (Google login), monitoring, domain
  - [ ] Monthly estimate at 10 companies, 100 companies, N users

## Also pending (from earlier work)

- [ ] Detect company from the question; prompt rule: never mix companies
- [ ] Comparison questions across companies (one search per company)
- [ ] Leakage eval cases (ask about A, must not cite B)
- [ ] Metadata store interface → see "Company and user metadata in Postgres"
- [ ] Do calculated answers in code, not by the LLM → see "Split user queries"
- [ ] LLM judge for the 10 `needs_judge` eval cases
- [ ] Standalone vs consolidated statement field; units per chunk
- [ ] Git repo + deployment (Dockerfile with Tesseract) → see "Create the project in Git" and "Deploy APIs to Railway"
