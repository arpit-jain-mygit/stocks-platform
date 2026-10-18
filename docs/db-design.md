# Data design

Two stores, each holding what it is good at:

| Store | Holds | Status |
|---|---|---|
| **Postgres** (Supabase) | Companies, aliases, document types, **filings** (one row per PDF, the dedup check) | **Live** – the only source of truth |
| **Qdrant** | **Chunks only** (vector + payload) | Live |

Financial figures are **not** stored in Postgres (only inside chunk text in Qdrant).

---

## Postgres

Created by `db/migrations/` (`python db/migrate.py`): `001_init.sql` tables, `002_filings.sql` filings, `003_seed_reference_data.sql` starting companies + doc types. New companies / doc types: `db/samples/add_company.sql`. Filings are written by the ingestion pipeline. Row level security is on for every table, so Supabase's public REST API can't read them; the app connects as the database owner.

```sql
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE companies (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          TEXT    NOT NULL UNIQUE,      -- 'VIDEOIND' = company_id in Qdrant; never changes
    name          TEXT    NOT NULL,             -- 'Videocon Industries Ltd'
    cin           TEXT    UNIQUE,
    isin          TEXT    UNIQUE,
    nse_symbol    TEXT    UNIQUE,
    bse_code      TEXT    UNIQUE,
    sector        TEXT,
    fy_end_month  SMALLINT NOT NULL DEFAULT 3 CHECK (fy_end_month BETWEEN 1 AND 12),
    status        TEXT    NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'suspended', 'delisted', 'insolvency')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE company_aliases (
    company_id  BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    alias       CITEXT NOT NULL UNIQUE,         -- one alias can never belong to two companies
    PRIMARY KEY (company_id, alias)
);

CREATE TABLE doc_types (
    code        TEXT PRIMARY KEY,               -- 'quarterly_results' = doc_type in Qdrant
    name        TEXT NOT NULL,
    is_default  BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX doc_types_one_default ON doc_types (is_default) WHERE is_default;

CREATE TABLE filings (
    doc_id        TEXT PRIMARY KEY,                       -- SHA-256 of the PDF (= doc_id in Qdrant)
    company_id    BIGINT   NOT NULL REFERENCES companies(id),
    doc_type      TEXT     NOT NULL REFERENCES doc_types(code),
    fiscal_year   SMALLINT NOT NULL,
    quarter       SMALLINT CHECK (quarter BETWEEN 1 AND 4),   -- NULL = full year
    period_end    DATE     NOT NULL,
    period_label  TEXT     NOT NULL,
    file_name     TEXT     NOT NULL,
    storage_url   TEXT,
    filed_on      DATE,
    pages         SMALLINT,
    ocr_pages     SMALLINT[] NOT NULL DEFAULT '{}',
    chunks        INT,
    status        TEXT     NOT NULL DEFAULT 'processing'
                  CHECK (status IN ('processing', 'complete', 'failed', 'superseded')),
    error         TEXT,
    superseded_by TEXT     REFERENCES filings(doc_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- At most one live filing per company + doc type + period; a newer one marks the older 'superseded'.
CREATE UNIQUE INDEX filings_one_live
    ON filings (company_id, doc_type, fiscal_year, COALESCE(quarter, 0)) WHERE status = 'complete';
```

### Sample data (Videocon)

`companies`

| id | code | name | cin | nse_symbol | bse_code | fy_end_month | status |
|---|---|---|---|---|---|---|---|
| 1 | VIDEOIND | Videocon Industries Ltd | L99999MH1986PLC103624 | VIDEOIND | 511389 | 3 | insolvency |

`company_aliases`

| company_id | alias |
|---|---|
| 1 | Videocon Industries Limited |
| 1 | Videocon Industries |
| 1 | Videocon |

`doc_types`

| code | name | is_default |
|---|---|---|
| quarterly_results | Quarterly financial results | true |
| annual_report | Annual report | false |
| investor_presentation | Investor / analyst presentation | false |
| earnings_call_transcript | Earnings call transcript | false |
| shareholding_pattern | Shareholding pattern | false |
| announcement | Corporate announcement | false |

`filings`

| doc_id | company_id | doc_type | fiscal_year | quarter | period_end | period_label | file_name | pages | ocr_pages | chunks | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bcb05762… | 1 | quarterly_results | 2025 | 3 | 2024-12-31 | Q3 FY25 (quarter ended 31-Dec-2024) | Videocon-Financial_Results_Dec-24.pdf | 13 | {6,10} | 84 | complete |

Companies and doc types come from migration 003 and `db/samples/add_company.sql`.

---

## Qdrant

### `stocks_rag_chunks` – one point per chunk (768-dim vector, cosine)

| Payload field | Example | Indexed |
|---|---|---|
| `text` | label line + chunk body | – |
| `doc_id` | `bcb05762…` (SHA-256 of PDF) | keyword |
| `file_name` | `Videocon-Financial_Results_Dec-24.pdf` | – |
| `company_id` | `VIDEOIND` → `companies.code` | keyword |
| `company` | `Videocon Industries Ltd` | keyword |
| `doc_type` | `quarterly_results` → `doc_types.code` | keyword |
| `fiscal_year` / `quarter` | `2025` / `3` | integer |
| `period_end` / `period` | `2024-12-31` / `Q3 FY25 (quarter ended 31-Dec-2024)` | `period` keyword |
| `page_start` / `page_end` | `11` / `11` | integer |
| `section` | `STATEMENT OF STANDALONE …` | – |
| `kind` | `prose` · `table` · `fact` | keyword |
| `source` | `text` · `vision` · `ocr` | keyword |
| `chunk_no` | `37` | – |

Videocon: 84 points.

---

## Links between the stores

```
Postgres                         Qdrant (stocks_rag_chunks)
companies.code   ─────────────►  company_id
doc_types.code   ─────────────►  doc_type
filings.doc_id   ─────────────►  doc_id
```

## Later

- Postgres: `users` (Google `sub` as key), `ingestion_jobs` (survive restarts)
- Superseded filings: their chunks are still searchable in Qdrant - delete or filter them
- Structured financial figures: location to be decided (not Postgres for now)
