-- 001_init.sql - company metadata and document types.
-- Applied by db/migrate.py (runs once; recorded in schema_migrations).

CREATE EXTENSION IF NOT EXISTS citext;      -- case-insensitive text (aliases)

-- Companies: one row per company. `code` is the stable key used everywhere
-- else (Qdrant payload company_id); exchange codes may change, code never does.
CREATE TABLE companies (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
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

-- Other names a company is known by. UNIQUE on alias: one alias can never
-- point to two companies (case-insensitive thanks to CITEXT).
CREATE TABLE company_aliases (
    company_id  BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    alias       CITEXT NOT NULL UNIQUE,
    PRIMARY KEY (company_id, alias)
);

-- Allowed document types; exactly one is the default.
CREATE TABLE doc_types (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    is_default  BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX doc_types_one_default ON doc_types (is_default) WHERE is_default;

-- Keep updated_at current on every change to a company.
CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER companies_updated_at BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Supabase exposes tables in "public" through its REST API. Row level
-- security with no policies blocks that API; the app connects as the
-- database owner and is not affected.
ALTER TABLE companies       ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE doc_types       ENABLE ROW LEVEL SECURITY;
