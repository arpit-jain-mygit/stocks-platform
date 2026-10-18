# stocks-insights.ai – GenAI Interview Prep

Questions an interviewer is likely to ask about this project, answered in plain words from what was
actually built and the problems actually hit. Read each answer as a story you can retell: what the
problem was, what was tried, what worked, and the trade-off. Numbers are real unless marked "about".

---

## Contents

1. [The 60-second pitch](#1-the-60-second-pitch)
2. [Architecture and design choices](#2-architecture-and-design-choices)
3. [Reading PDFs: text, vision and OCR](#3-reading-pdfs-text-vision-and-ocr)
4. [Chunking](#4-chunking)
5. [Embeddings and the vector store](#5-embeddings-and-the-vector-store)
6. [Retrieval and answering](#6-retrieval-and-answering)
7. [Prompt engineering](#7-prompt-engineering)
8. [Evaluation](#8-evaluation)
9. [Cost, tokens and latency](#9-cost-tokens-and-latency)
10. [Rate limits and reliability](#10-rate-limits-and-reliability)
11. [Guardrails and responsible AI](#11-guardrails-and-responsible-ai)
12. [Security](#12-security)
13. [Data model and lifecycle](#13-data-model-and-lifecycle)
14. [Testing without calling the model](#14-testing-without-calling-the-model)
15. [Deployment and operations](#15-deployment-and-operations)
16. [Frontend for an LLM product](#16-frontend-for-an-llm-product)
17. [Going global and scaling up](#17-going-global-and-scaling-up)
18. [Behavioural questions from this project](#18-behavioural-questions-from-this-project)
19. [Numbers worth remembering](#19-numbers-worth-remembering)

---

## 1. The 60-second pitch

**"Tell me about a GenAI project you built."**

stocks-insights.ai answers questions about listed companies from their own filings – quarterly
results and annual reports – and cites the file and page for every fact. Its motto is "Insights from
the filings, not tips for the market": it never gives buy or sell advice.

A PDF goes through ingestion: typed pages are read from the text layer, scanned and table-heavy pages
are transcribed by a Gemini vision model (with Tesseract OCR as a fallback), the text is cut into
labelled chunks plus one "fact card" per table row, embedded with `gemini-embedding-001` and stored
in Qdrant. Company and filing metadata live in Postgres (Supabase). A question is embedded, the
closest chunks for that company and period are retrieved, and Gemini answers using only those chunks
with `[S1]`-style citations.

The backend is FastAPI on Railway (Docker, with Tesseract); the UI is an Angular single-page app on
Vercel that talks to the backend through a small server-side proxy so the API key never reaches the
browser. Quality is tracked with per-company eval sets, and the whole API is covered by offline
end-to-end tests that never call a model.

The hardest problems were not the LLM call itself: they were reading messy PDFs faithfully, chunking
tables without losing numbers, and proving answers were right.

---

## 2. Architecture and design choices

**Q: Walk me through the architecture.**

Two flows. *Ingestion*: upload → SHA-256 of the bytes becomes the `doc_id` (duplicate check) → read
pages (text layer, vision, or OCR) → chunk → embed → store chunks in Qdrant and a filing record in
Postgres. *Question*: validate company and period → embed the question → filtered vector search
(company, fiscal year, quarter, document type) → number the top chunks `[S1]…[S6]` → answer prompt →
return the answer plus only the sources it actually cited.

```
PDF ─► read pages ─► chunk ─► embed ─► Qdrant (chunks)      Postgres (companies, filings)
                                            ▲                       ▲
question ─► embed ─► filtered search ───────┘   validate company ───┘
                         └─► top chunks ─► Gemini (answer + [S#]) ─► API ─► UI
```

**Q: Why split data between Postgres and Qdrant instead of one database?**

They answer different questions. Qdrant answers "which text is closest in meaning to this
question?" – it only holds chunks (vector + payload). Postgres answers "which companies exist, which
PDFs were ingested, which version is current?" – that needs constraints, foreign keys and
transactions. Keeping both meant deletes had to be careful (see section 13), but each store does what
it is good at, and Qdrant payload filters still use the same `company_id` as Postgres.

**Q: How did you avoid locking yourself into one model or one vector database?**

Three small factories. `get_llm("vision" | "answer" | "embed")` returns a client for that *role*,
configured in `.env` (provider, model, key per role); `get_store()` returns the vector store;
`get_metadata_store()` returns the metadata store. The rest of the code only sees interfaces
(`describe_image`, `generate_text`, `embed_texts`, `search`, `upsert_chunks`…). Swapping Gemini for
another provider for answers only means writing one class and changing `ANSWER_PROVIDER`. Roles
matter: you might want a cheap model for transcription, a stronger one for answers, and the
embedding model must never change without re-embedding everything.

**Q: Why per-role API keys?**

Free-tier quotas are per Google Cloud project. During a large ingestion the embedding quota ran out
while the answer quota was fine, so being able to point only embeddings at a key from another
project (`EMBED_API_KEY`) unblocked it. Empty role keys fall back to `GEMINI_API_KEY`.

**Q: Why not a framework like LangChain or LlamaIndex?**

The pipeline is short and every step needed custom behaviour (table detection, fact cards,
company/period filters, exact refusal text). Plain functions with small interfaces kept it easy to
read, test with fakes and debug. A framework would make sense if many retrievers, tools or agents
had to be composed.

---

## 3. Reading PDFs: text, vision and OCR

**Q: How do you get text out of financial PDFs?**

Page by page. If a page has a real text layer (≥ 50 characters), PyMuPDF reads it for free. Scanned
pages have no text layer, so the page is rendered to an image (200 DPI) and a Gemini vision model
transcribes it to Markdown – tables become Markdown tables. If the vision model refuses, Tesseract OCR
reads it locally.

**Q: Why use a vision LLM instead of plain OCR?**

OCR gives you characters; financial results are tables with stacked headers ("Quarter ended" over a
date over "Unaudited"). The vision model returns a proper table with one header per column, which
the chunker can turn into row facts. OCR is the fallback, not the first choice.

**Q: You said the model "refuses" – what happened?**

Gemini sometimes stops with a `RECITATION` finish reason on standard legal or auditor boilerplate,
because the text looks like something already published. Retrying does not help. The code treats it
as its own error type (`RecitationBlocked`) and falls back to Tesseract for that page, recording the
page as `ocr`.

**Q: The model transcribed pages – did it get them right?**

Not at first. It "tidied up" the text: swapped look-alike abbreviations (NCLT ↔ NCLAT), dropped
words and a heading, and renumbered notes from `(ii)` to `g)`. For legal and financial evidence that
is unacceptable. The fix was a strict transcription prompt: copy character for character, never
correct or standardise, keep every label as printed, copy every number exactly including brackets
for negatives, write `[illegible]` rather than guess. The principle: *transcribe, don't summarise*.

**Q: Typed pages are free – why send some of them to the vision model too?**

Because typed tables lose their structure. In the text layer a table comes out as one number per
line, so you cannot tell which number belongs to which column or year. A page is now treated as a
"table page" when it has at least 15 lines and at least 35% of them are figures, and those pages also
go to the vision model, which returns an aligned table. On a 196-page annual report that was 52
pages; the text layer is kept as a fallback if the vision call fails.

**Q: Vision calls are slow and cost money – how do you avoid paying twice?**

Every page result is cached on disk, keyed by the document and a *fingerprint* of model + DPI +
prompt. Re-running ingestion reuses the cache; changing the prompt or model automatically creates a
new fingerprint, so stale transcriptions are never mixed with new ones. The trade-off: any prompt
change means the next forced re-ingest re-reads those pages once.

---

## 4. Chunking

**Q: How did you chunk the documents?**

Clean the lines, split into paragraphs, join paragraphs that continue across pages, cut at headings
and numbered points, and cap prose chunks at about 400 words (no cut below about 80). Every chunk
starts with a label line – company, period, section – so a chunk still makes sense on its own when
retrieved. Tables become one whole "table" chunk *and* one small "fact" card per row.

**Q: Why fact cards per table row?**

A question like "What were finance costs in Q3?" matches one row, but a whole statement table is a
big, noisy chunk whose embedding is "about everything". A one-row card – label, row name, each
column's value, plus the units caption – embeds close to that exact question and gives the model a
precise, citable figure. Table chunks stay too, for questions that need several rows.

**Q: What went wrong with chunking, and how did you find out?**

The eval showed retrieval misses, so I compared chunks before and after with numbers in hand:

- *Repeated-line cleanup deleted data.* Headers and footers are removed if a line repeats on many
  pages. But financial statements repeat numbers too: the cleanup removed 824 lines from one annual
  report, 363 of them pure figures. Fix: a line is only dropped if it contains letters, repeats on at
  least 20% of pages, and is not a units line ("₹ in million", "in thousands").
- *Bad headings.* Lines like `(45) (45) Other financial assets` (table remnants) and one-word logos
  were treated as section headings, so whole runs of chunks were mislabelled. Fix: lines that start
  with a figure or are mostly figures are never headings, but a numbered title like
  `7. Other Matters` still is.
- *Chunks spanning many pages.* A paragraph that starts on a new page now starts a new chunk.
- *Typed tables.* Sent to the vision model (section 3).

After the fixes, 319 of 363 chunks of the annual report sat on a single page, and the lost figures
were back.

**Q: How do you make sure chunking rules don't overfit one document?**

A rule I was held to: no change may be specific to one question or one document. Every rule is
general (share of figures, repeat threshold, units words), and I re-measured on both test documents
– a typed annual report and a scanned quarterly result – to check the other one didn't regress
(e.g. 81 of 87 chunks of the second document were unchanged, so their cached vectors were reused).

---

## 5. Embeddings and the vector store

**Q: Which embedding model and why?**

`gemini-embedding-001` at 768 dimensions: free tier, good multilingual quality, and it supports
*task types* – chunks are embedded as `document`, questions as `query`, which improves matching. 768
instead of the full size keeps storage small with little quality loss.

**Q: What happens if you change the embedding model?**

All vectors must be recomputed, and old and new vectors must never be searched together. The vector
cache folder is named after model + dimension, so a new model starts a fresh cache; the Qdrant
collection should get a new name; and the backup restore refuses a file whose model or vector size
differs from the current setting.

**Q: How do you avoid re-embedding the same text?**

A disk cache keyed by SHA-256 of (task type + text). Same chunk text → same file, whatever PDF it
came from. After a chunking change, only chunks whose text changed are embedded again.

**Q: Why Qdrant? How do you filter?**

Free cloud tier (1 GB), fast filtered search, and payload indexes. Each point's payload carries
`company_id`, `fiscal_year`, `quarter`, `doc_type`, `doc_id`, pages and section. Questions pass exact
filters, so a question about one company can never retrieve another company's numbers. That is
tested by "leakage" eval cases: asked about OFSS, the answer must not contain Videocon's figures.

**Q: How are point IDs chosen?**

Deterministic: derived from `doc_id` + page + chunk number. Re-ingesting the same PDF overwrites the
same points instead of creating duplicates; old chunks for that `doc_id` are deleted first, and the
stored count is checked against the expected count.

---

## 6. Retrieval and answering

**Q: How does a question become an answer?**

Validate company / period / doc type (400 before any model call if wrong) → embed the question →
search the top 6 chunks with filters → number them `[S1]…[S6]` → answer prompt → parse which `[S#]`
the answer cites → return the answer and only those sources (file, pages, section, score).

**Q: Why return only cited sources?**

Because a source list is a claim: "this answer is based on these pages". Listing chunks the model
didn't use would be misleading, and the UI shows exactly what supports the answer.

**Q: A user asked "What is the P/E ratio?" and got "not found". Is that a bug?**

No – the filing has EPS but not the share price, and P/E = price ÷ EPS. A correct refusal beats a
made-up number. The better answer explains that P/E isn't in filings and offers the EPS with its
page; a deterministic path with market data could compute it later.

**Q: Another answer quoted the right EPS but was still wrong. Why?**

Indian annual reports contain both *consolidated* (group) and *standalone* (parent only) figures,
which differ. The answer quoted consolidated EPS without saying so, and retrieval hadn't brought the
standalone page. Fixes: tag each chunk with its statement type, retrieve both kinds for figure
questions, and a prompt rule to report both, labelled. Lesson: "grounded" isn't enough – the answer
must say *which* figure it is.

**Q: How do you handle periods like "last three quarters"?**

Period columns are confusing: "nine months ended" is cumulative from the start of the financial year.
The prompt explains the column types and says any period is a sum of whole quarters – look for a
column that matches exactly, otherwise compute it (e.g. a quarter = nine months − the two printed
quarters), show the working with every input cited, and label it "calculated". A planned
improvement is to do the arithmetic in code instead of in the model.

---

## 7. Prompt engineering

**Q: What does your answer prompt look like?**

Short role, then the period guide, then numbered rules:

0. Never give investment advice – reply with an exact sentence (section 11).
1. If the sources don't contain the answer, reply with an exact `NOT_FOUND` sentence.
2. Prefer a printed figure; quote it exactly with currency, units and period.
3. Calculate only with simple arithmetic from printed figures, show working, label "calculated".
4. Say which period you used if ambiguous.
5. Cite every fact `[S2]`.
6. Be short: answer first, then at most 2–3 sentences.
7. If sources disagree, say so and cite both.

Plus a "Companies" block listing each cited company's financial-year end.

**Q: Why exact refusal sentences?**

They make behaviour testable. The eval can check "said not found" with a string match instead of an
LLM judge, and the UI can recognise them.

**Q: What prompt problem surprised you?**

A question about "the last 3 quarters" was refused even though the nine-months column answered it
directly. The model didn't know how Indian result columns work. Adding a generic "how periods work"
block (not a rule for that one question) fixed that class of questions.

**Q: How do you version prompts?**

All prompts live in one file. The transcription prompt is part of the page-cache fingerprint, so a
change is automatically tracked; the answer prompt isn't cached, so a change takes effect at once and
is checked by re-running the eval.

---

## 8. Evaluation

**Q: How do you know the system is accurate?**

Per-company eval sets (OFSS 25 cases, Videocon 42), written by hand from the PDF – never by running
the app. Each case has the `/ask` request, an expected answer, and deterministic checks:
`must_contain` (each required fact, with accepted spellings), `must_not_contain` (known wrong values,
e.g. another company's figure), `expected_pages` (a source must cite the right page),
`expect_not_found` and `accept_any_of` for genuinely ambiguous questions. Categories include lookups,
calculations, period mapping, not-in-filing, company leakage and no-advice.

**Q: Your first OFSS run scored 15/23. What did you do?**

Read every failure instead of tuning to the score. Three were over-strict cases (the answer was right
but phrased differently or cited a different correct page) – fixed in the eval, giving 18/23. The
remaining five were retrieval misses, which traced back to the chunking problems in section 4. That
split – "eval bug" vs "system bug" – is the most useful habit.

**Q: Would you use an LLM as a judge?**

For answers that are correct but phrased differently, yes – but only after the cheap deterministic
checks, and with a judge from a *different model family* than the one answering, to avoid
self-preference. Results are saved per run (`eval/results/<company>/run-*.json`) with expected vs
actual, so a judge can grade them later. Spot-check the judge against your own grading on about ten
cases before trusting it.

**Q: How is eval different from tests?**

Tests check the *flow* (does the API, pipeline and citation logic work) and run offline with fake
models. Eval checks *answer quality* and needs real model calls, so it runs deliberately, with a
known cost (one embedding + one answer per case).

---

## 9. Cost, tokens and latency

**Q: Where do the tokens go?**

Mostly input: about 600 tokens of instructions plus 6 chunks, roughly 3–5k tokens per question. The
visible answer is 100–200 tokens. So the levers are fewer or shorter chunks, a tighter answer rule,
and – often overlooked – *thinking tokens*.

**Q: What are thinking tokens and why do they matter?**

Newer Gemini models reason privately before answering. Those hidden tokens are billed as output and
add latency, and can exceed the answer itself. For direct lookups they add little; for calculations
and period mapping they help. The plan: log `prompt_token_count`, `candidates_token_count` and
`thoughts_token_count` per answer, then compare accuracy and latency with a small thinking budget on
the eval. Gotcha: on Gemini, `max_output_tokens` generally covers thinking *and* answer, so a tight cap
can leave an empty answer.

**Q: What did ingestion cost?**

On the paid tier, estimated: embeddings for a ~1,200-chunk annual report about $0.03–0.05; 52
vision pages about $0.30; a question about $0.002. On the free tier the real constraint was quotas,
not money.

**Q: How would you reduce latency?**

Stream the answer (first words in about a second instead of waiting for the full reply), cap or turn
off thinking for simple lookups, cache company metadata (already 60 s), reuse database connections,
and answer simple figure lookups deterministically without the model.

---

## 10. Rate limits and reliability

**Q: You hit 429 RESOURCE_EXHAUSTED during ingestion. How did you handle it?**

Two layers. Every model call retries temporary errors (429, 503) with exponential backoff (2, 4, 8 s…,
up to 5 attempts). Embeddings are sent in small batches with a pause, and *each finished batch is
saved immediately* – so when the daily quota ran out at batch 77 of 120, a re-run started from batch
78 ("774 from cache, 419 to embed"). Changing the API key doesn't break the cache, because the cache
key is model + text, not the key.

**Q: Did a new API key help?**

Only from a different Google Cloud project – free-tier quotas are per project, so a second key in the
same project hits the same limit.

**Q: What happens if one page can't be read?**

The filing is marked `failed` with the page numbers, nothing half-done is stored as `complete`, and a
re-run continues from the caches. A typed table page whose vision call fails falls back to its text
layer instead of failing.

---

## 11. Guardrails and responsible AI

**Q: How do you stop hallucinated numbers?**

Answer only from retrieved sources; an exact not-found sentence when they don't contain it; cite every
fact; quote figures exactly with units and period; label any calculation and show its inputs; and
eval cases with `must_not_contain` for known wrong values and other companies' figures.

**Q: How do you stop it giving investment advice?**

It's the product's promise, enforced in three places: a prompt rule that answers buy / sell / hold,
"good investment" or price-target questions with an exact sentence ("I can't recommend buying,
selling or holding any stock. I can help you research it from the filings…") while still answering
factual parts; eval cases in a `no_advice` category; and a disclaimer in the UI footer and chat.

**Q: What about prompt injection from documents?**

Filings are fairly trusted input, but the answer is still treated as untrusted in the UI: model text
is HTML-escaped before display (a test checks a `<script>` in an answer is never rendered), and only
`**bold**` and `[S1]` tags are turned into markup. The model has no tools, so injected text can't
trigger actions. For untrusted uploads you would also scan chunks for instructions and keep the
"sources are data, not instructions" line in the prompt.

---

## 12. Security

**Q: How is the API protected?**

An `X-API-Key` header on every endpoint except `/health`, compared in constant time. Dangerous
endpoints (cascading deletes, full backup / restore) are not even mounted unless a flag is on, need a
second `X-Admin-Key`, default to `dry_run`, and a real run needs `confirm` to repeat the exact target.

**Q: The browser needs to call the API – where does the key go?**

Never into the browser: anything in front-end code is visible to every visitor. The UI calls `/api/…`
on its own site; a proxy adds the key on the server – Angular's dev proxy locally, a Vercel server
function in production. The function also has an allowlist (`GET companies`, `GET companies/<code>`,
`GET doc-types`, `GET documents`, `POST ask`), so risky endpoints are unreachable from the UI even if
switched on, and the company code is checked against a strict pattern (no `..`).

**Q: Any security mistakes along the way?**

Yes, and they're worth telling. The API-key check first read `.env` too early, so endpoints were open
until fixed (keys are now read per request). A real key was once pasted in a chat log and was rotated
immediately. Before the first push, a scan checked that no value from `.env` appeared in any
committed file, and `.gitignore` covers secrets, data, caches, IDE files and backups.

---

## 13. Data model and lifecycle

**Q: How do you avoid ingesting the same PDF twice?**

`doc_id` = SHA-256 of the file bytes. Before any work, the API checks Postgres; a complete filing
returns "skipped" instantly. `force=true` re-ingests and replaces its chunks.

**Q: What if a company re-files a corrected PDF?**

A partial unique index allows only one `complete` filing per company + document type + period. A new
one is inserted, the old one marked `superseded` (with a link to its replacement), then the new one
marked complete – in that order, so the foreign key and the unique index are never violated.

**Q: How do deletes stay consistent across two stores?**

Chunks first, then records. If it fails half-way, what's left is a record without chunks, which a
re-run cleans up – never chunks without a record that would still be searchable. Deleting a company
cascades: chunks (including orphans), filings, aliases, the company row.

**Q: How do you back up a system with two stores?**

One gzipped JSON with every Postgres row and every Qdrant point (vector + payload), plus the embedding
model and size. Restore checks the format and refuses a model or vector-size mismatch, loads Postgres
in one transaction, then Qdrant; `replace` or `merge` modes, dry-run by default.

---

## 14. Testing without calling the model

**Q: How do you test an LLM app without spending money or getting flaky results?**

The rule on this project: no real model calls during verification. The test suite runs the real
FastAPI app, pipeline, chunker, search and answer code, with in-memory fakes for Gemini (fixed vision
Markdown, a fixed answer, deterministic word-hash "embeddings" so search still finds the right chunk),
Qdrant and Postgres. "Tripwires" replace the real client factories, so any attempt to build a real
client fails the test. Caches go to a temp folder. 75 tests run in about 2 seconds.

**Q: How do you know the tests actually catch bugs?**

By breaking the code on purpose (mutation testing by hand): dropping a payload field, disabling the
duplicate check, returning uncited sources, turning off the API-key check, leaving chunks after a
company delete, ignoring the company filter. Every mutation failed at least one test – and one that
survived revealed a missing test for the command-line ingestion path, which was then added.

**Q: And the UI?**

Unit tests with a faked HTTP backend (17), and browser checks where `/api/ask` was stubbed inside the
page – so the chat was exercised end to end with zero model calls.

---

## 15. Deployment and operations

**Q: How is it deployed?**

Backend: Docker image (Python + Tesseract) on Railway, one Uvicorn process (ingestion jobs are kept in
memory), database migrations as a pre-deploy step, `/health` as the health check, caches on a Railway
volume at `/data`. Frontend: Angular build on Vercel with the proxy function. Postgres on Supabase,
vectors on Qdrant Cloud. Secrets live only in Railway / Vercel variables.

**Q: What broke when you deployed?**

- *Supabase IPv6.* `Network is unreachable` to an IPv6 address: the direct connection string is
  IPv6-only and Railway couldn't reach it. Fix: the Session pooler string.
- *Pooler login.* `password authentication failed for user "postgres"`: the pooler needs the user
  `postgres.<project-ref>`.
- *Migrations.* The migration script only read `.env`, which doesn't exist on Railway – fixed to read
  environment variables too.
- *Vercel function crash.* `SyntaxError: Unexpected token 'export'`: the TypeScript function was
  compiled to ES-module JavaScript but Node loaded it as CommonJS. Fix: `"type": "module"` in
  `package.json`.
- *Caches lost on redeploy* until a volume was attached; verified by writing a marker file,
  redeploying, and reading it back.

**Q: How do you debug in production?**

Railway deploy logs (search for `Traceback`), Railway SSH into the running container (e.g. to inspect
`/data/cache`), and Vercel runtime logs filtered by `/api/proxy`.

---

## 16. Frontend for an LLM product

**Q: What UX decisions mattered for an LLM app?**

- *Show the evidence*: sources under every answer, `[S1]` tags inline.
- *Set expectations*: a "Thinking…" state, disabled input while waiting, friendly messages for quota
  (429) and server errors.
- *Help people start*: five always-visible suggested questions (revenue & profit, EPS, debt & finance
  costs, dividend, risks & legal) as short chips that send the full question.
- *Context*: the chat's company picker follows the company selected in the list.
- *Safety*: model output escaped before display; the disclaimer shown before the first question.
- Next on the list: streaming answers, clickable citations, follow-up questions.

---

## 17. Going global and scaling up

**Q: It started India-only. What did "make it global" involve?**

The core pipeline was already generic; the assumptions were in a few places:

- *Financial years.* India runs April–March, the US mostly January–December, Apple ends in
  September. Periods now follow each company's year-end month: "FY25" = the year ending in 2025, and
  "Q3 FY25" is the quarter ended 31 Dec 2024 for a March year-end but 30 Sep 2025 for December. Filters
  use fiscal year + quarter, which mean "each company's own Q3 FY25".
- *Prompts* no longer say "Indian"; the answer prompt lists each cited company's year-end and keeps
  the filing's own currency and units.
- *Number formats*: `$1,234`, `€1.234,56`, `1,23,456.7`, thousands to billions – table detection
  and units lines handle all of them; detection on the Indian documents stayed identical.

Still to do: filing sources per market (e.g. SEC EDGAR, whose structured XBRL data could replace PDF
parsing for numbers), per-market eval sets, and non-English filings.

**Q: What breaks first at 1,000 companies?**

Storage (the free 1 GB Qdrant tier holds roughly 100–150 annual reports), ingestion throughput (needs
a queue and workers instead of in-memory jobs), vision cost per PDF, and the UI (a company list needs
search). Retrieval quality also needs per-market eval before claiming coverage.

---

## 18. Behavioural questions from this project

**"Tell me about a time you were wrong."**
I treated a Node.js warning ("module type not specified") as harmless in a local test; on Vercel the
same issue crashed the proxy and every API call failed. I fixed it, added the exact error to the
troubleshooting guide, and now read warnings as possible production errors.

**"Tell me about a time you pushed back on a quick fix."**
When an eval case failed, the quick fix was to tweak the chunker until that question passed. The rule
was: no change specific to one question or document. The failures were traced to general causes
(numbers deleted as boilerplate, bad headings, typed tables) and fixed with general rules, verified on
a second document.

**"How do you balance cost and quality?"**
Measure first: caches at every expensive step (pages, vectors), checkpointed batches, and token
logging before tuning thinking budgets. Changes that might reduce accuracy (fewer chunks, less
thinking) are only kept if the eval says accuracy didn't drop.

**"How do you work with an AI coding assistant?"**
Clear constraints up front (no model calls during verification, no secrets in the repo, explain
before risky actions), small verified steps, tests and deliberate bug-injection to check its work,
and reading every diff before pushing.

---

## 19. Numbers worth remembering

| What | Value |
|---|---|
| Embedding model / size | `gemini-embedding-001`, 768 dims, task types document / query |
| Answer and vision model | `gemini-3.5-flash-lite` (configurable per role) |
| Page render for vision | 200 DPI |
| Table-page rule | ≥ 15 lines and ≥ 35% figures |
| Prose chunk size | about 80–400 words, one label line per chunk |
| Chunks retrieved per question | 6 |
| Annual report (OFSS FY26) | 196 pages, 52 table pages to vision, 1,193 chunks |
| Quarterly result (Videocon Q3 FY25) | 13 pages, 84 chunks |
| Repeated-line bug | 824 lines removed, 363 of them numbers |
| Eval | OFSS 25 cases, Videocon 42; first OFSS run 15/23 → 18/23 after fixing eval cases |
| Tests | backend 75 (offline, about 2 s), UI 17 |
| Retries | 5 attempts, backoff 2 s, 4 s, 8 s… |
| Tokens per question | about 3–5k in, 100–200 out (plus any thinking) |
| Paid-tier estimate | about $0.002 per question; about $0.35–1.25 to re-ingest the annual report |
