# Metadata database design (Postgres / Supabase)

What lives in Postgres: **companies, their aliases and identifiers, document types and filings**
(one row per ingested PDF). The filing *text* does not live here – it is chunked into Qdrant.
Tables come from `db/migrations/` (`python db/migrate.py`), in order:

| Migration | Adds |
|---|---|
| `001_init.sql` | `companies`, `company_aliases`, `doc_types`, `updated_at` trigger, row level security |
| `002_filings.sql` | `filings` (one per PDF), "one live filing per slot" rule |
| `003_seed_reference_data.sql` | starting doc types and companies (OFSS, VIDEOIND) |
| `004_company_identifiers.sql` | `company_identifiers` (any market), `companies.country` |

---

## Diagram

```
┌──────────────────────────────────┐
│ schema_migrations                │   which migration files ran (db/migrate.py)
├──────────────────────────────────┤
│ PK version     TEXT  '004_...'   │
│    applied_at  TIMESTAMPTZ       │
└──────────────────────────────────┘

┌────────────────────────────────────┐         ┌────────────────────────────────────────────────┐
│ company_aliases                    │         │ companies                                      │
├────────────────────────────────────┤         ├────────────────────────────────────────────────┤
│ PK,FK company_id  BIGINT           │────────►│ PK id            BIGINT (identity)             │
│ PK,UQ alias       CITEXT           │  N : 1  │ UQ code          TEXT   'OFSS'                 │  ◄── Qdrant chunk payload company_id
│   e.g. 'Oracle Financial Services' │         │      = company_id on Qdrant chunks;            │
└────────────────────────────────────┘         │      never changes                             │
                                               │    name          TEXT                          │
┌────────────────────────────────────┐         │    country       TEXT   'IN' / 'US'  (004)     │
│ company_identifiers   (004)        │         │    sector        TEXT                          │
├────────────────────────────────────┤         │    fy_end_month  SMALLINT 1-12 (3 = March)     │
│ FK company_id  BIGINT              │────────►│    status        TEXT   active / suspended /   │
│    type        TEXT                │  N : 1  │                         delisted / insolvency  │
│      ticker / isin / lei / cik /   │         │    created_at, updated_at                      │
│      cin / figi / registry         │         │    (old cin, isin, nse_symbol, bse_code:       │
│    exchange    TEXT                │         │     copied by 004, unused, to be dropped)      │
│      tickers only: NSE, BSE,       │         └────────────────────────────────────────────────┘
│      NASDAQ, NYSE, LSE ...         │                                  │
│    value       TEXT                │                                  │
│ UQ (type, exchange, upper(value))  │                                  │
└────────────────────────────────────┘                                  │
                                                                        │ 1 : N
                                                                        ▼
┌────────────────────────────────────┐         ┌────────────────────────────────────────────────┐
│ doc_types                          │         │ filings                                        │
├────────────────────────────────────┤         ├────────────────────────────────────────────────┤
│ PK code        TEXT                │◄────────│ PK doc_id        TEXT   SHA-256 of the PDF     │  ◄── Qdrant chunk payload doc_id
│      e.g. 'annual_report'          │  1 : N  │                         (= doc_id on chunks)   │
│    name        TEXT                │         │ FK company_id    BIGINT -> companies.id        │
│    is_default  BOOLEAN             │         │ FK doc_type      TEXT   -> doc_types.code      │
│ UQ only one default                │         │    fiscal_year   SMALLINT 2025 = FY25          │
└────────────────────────────────────┘         │    quarter       SMALLINT 1-4, NULL = year     │
                                               │    period_end    DATE                          │
                                               │    period_label  TEXT 'Q3 FY25 (quarter ...)'  │
                                               │    file_name, storage_url, filed_on            │
                                               │    pages, ocr_pages[], chunks                  │
                                               │    status        processing / complete /       │
                                               │                  failed / superseded           │
                                               │    error         TEXT                          │
                                               │ FK superseded_by TEXT   -> filings.doc_id      │──┐ self link: the newer filing
                                               │    created_at, updated_at                      │  │ that replaced this one
                                               └────────────────────────────────────────────────┘◄─┘

```

`PK` primary key · `FK` foreign key · `UQ` unique · `N : 1` many rows point to one row · arrows point at the referenced table.

---

## The rules the design enforces

| Rule | How |
|---|---|
| One stable key per company, used everywhere | `companies.code` (e.g. `OFSS`) is the `company_id` on every Qdrant chunk; exchange codes may change, the code never does |
| An alias belongs to one company | `company_aliases.alias` is `UNIQUE` and case-insensitive (`CITEXT`) |
| Identifiers for any market | `company_identifiers`: a **ticker always has an exchange** (`CHECK`), other types never do; `UNIQUE (type, exchange, upper(value))` – the same symbol may exist on two exchanges, an ISIN only once |
| The same PDF is never stored twice | `filings.doc_id` = SHA-256 of the file bytes (primary key) |
| One live filing per company + type + period | partial unique index `filings_one_live` on `(company_id, doc_type, fiscal_year, COALESCE(quarter, 0)) WHERE status = 'complete'`; a newer PDF marks the old one `superseded` and links it with `superseded_by` |
| Only one default document type | partial unique index on `doc_types (is_default) WHERE is_default` |
| Deleting a company removes its aliases and identifiers | `ON DELETE CASCADE` on both; filings must be deleted first (the delete APIs do chunks → filings → company) |
| Not readable through Supabase's public REST API | row level security on every table, no policies; the app connects as the owner |
| `updated_at` is always current | trigger `set_updated_at()` on `companies` and `filings` |

---

## How Postgres and Qdrant fit together

```
 Postgres (this database)                      Qdrant (vector store)
 ─────────────────────────                     ──────────────────────────────────────────
 companies.code  'OFSS'  ──────────────────►   payload.company_id  'OFSS'
 filings.doc_id  '4a9e8c…' ────────────────►   payload.doc_id      '4a9e8c…'
 filings.fiscal_year / quarter / doc_type ──►  payload.fiscal_year / quarter / doc_type
                                               + vector (768 numbers) + chunk text + pages
```

- **Postgres answers** "which companies exist, which PDFs were ingested, which version is current?"
- **Qdrant answers** "which chunks are closest in meaning to this question?" – filtered by the same
  `company_id`, `fiscal_year`, `quarter` and `doc_type`, so a question about one company never
  retrieves another company's numbers.
- They are kept in step by code, not by a foreign key: deletes remove **chunks first, then
  records**, so a half-finished delete can leave a record without chunks (harmless, a re-run cleans
  it) but never searchable chunks without a record.

---

## Sample rows

`companies`

| id | code | name | country | fy_end_month | status |
|---|---|---|---|---|---|
| 1 | OFSS | Oracle Financial Services Software Ltd | IN | 3 | active |
| 2 | VIDEOIND | Videocon Industries Ltd | IN | 3 | insolvency |

`company_identifiers`

| company_id | type | exchange | value |
|---|---|---|---|
| 1 | ticker | NSE | OFSS |
| 1 | ticker | BSE | 532466 |
| 1 | isin | | INE881D01027 |
| 2 | ticker | NSE | VIDEOIND |
| 2 | ticker | BSE | 511389 |
| 2 | cin | | L99999MH1986PLC103624 |

A US company follows the same shape, e.g. `MSFT`: `ticker NASDAQ MSFT`, `isin US5949181045`,
`cik 0000789019`, `country US`, `fy_end_month 6`.

`filings`

| doc_id | company | doc_type | fiscal_year | quarter | period_label | status | pages | chunks |
|---|---|---|---|---|---|---|---|---|
| 4a9e8c… | OFSS | annual_report | 2026 | – | FY26 (year ended 31-Mar-2026) | complete | 196 | 1193 |
| … | VIDEOIND | quarterly_results | 2025 | 3 | Q3 FY25 (quarter ended 31-Dec-2024) | complete | 13 | 84 |

---

## Where to change things

| Task | Use |
|---|---|
| Add a company (with identifiers, aliases, year-end) | `db/samples/add_company.sql`, Block 1 |
| Add a document type | `db/samples/add_company.sql`, Block 2 |
| Remove filings / a company | `db/samples/delete_company.sql`, or the guarded `/risky-delete/...` APIs (Postgres + Qdrant together) |
| Change the schema | a new numbered file in `db/migrations/`, then `python db/migrate.py` (runs automatically before each Railway deploy) |

More detail on the reasoning: [docs/db-design.md](../../docs/db-design.md).
