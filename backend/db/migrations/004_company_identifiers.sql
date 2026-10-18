-- 004_company_identifiers.sql - company identifiers for any market, plus country.
-- Applied by db/migrate.py (runs once; recorded in schema_migrations).
--
-- Before: four fixed columns on companies - nse_symbol, bse_code (two Indian
-- exchanges), cin (Indian registry number) and isin.
-- After: one row per identifier, any type and any exchange:
--     ticker  NSE     TCS            ticker  NASDAQ  MSFT
--     ticker  BSE     532540         isin            US5949181045
--     isin            INE467B01029   cik             0000789019
--
-- Rules:
--   - a ticker always has an exchange (the same symbol can mean different
--     companies on different exchanges); other types never do
--   - one (type, exchange, value) belongs to one company only
--
-- The old columns are copied here and then no longer read or written by the
-- app. They stay for now so the version still running during a deploy keeps
-- working; a later migration drops them.

CREATE TABLE company_identifiers (
    company_id  BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    type        TEXT   NOT NULL CHECK (type IN ('ticker', 'isin', 'lei', 'cik', 'cin', 'figi', 'registry')),
    exchange    TEXT   CHECK (exchange = upper(exchange)),       -- e.g. 'NSE', 'BSE', 'NASDAQ', 'NYSE', 'LSE'
    value       TEXT   NOT NULL CHECK (value <> ''),
    CHECK ((type = 'ticker') = (exchange IS NOT NULL))           -- tickers need an exchange; nothing else has one
);

-- Unique per type + exchange + value (case-insensitive).
CREATE UNIQUE INDEX company_identifiers_unique
    ON company_identifiers (type, COALESCE(exchange, ''), upper(value));
CREATE INDEX company_identifiers_company ON company_identifiers (company_id);

-- Country of the company (ISO 3166-1 alpha-2, e.g. 'IN', 'US', 'GB').
ALTER TABLE companies ADD COLUMN country TEXT CHECK (country ~ '^[A-Z]{2}$');

-- Copy what the old columns hold.
INSERT INTO company_identifiers (company_id, type, exchange, value)
SELECT id, 'ticker', 'NSE', nse_symbol FROM companies WHERE nse_symbol IS NOT NULL AND nse_symbol <> ''
UNION ALL
SELECT id, 'ticker', 'BSE', bse_code   FROM companies WHERE bse_code   IS NOT NULL AND bse_code   <> ''
UNION ALL
SELECT id, 'isin',   NULL,  isin       FROM companies WHERE isin       IS NOT NULL AND isin       <> ''
UNION ALL
SELECT id, 'cin',    NULL,  cin        FROM companies WHERE cin        IS NOT NULL AND cin        <> '';

-- Companies listed on NSE / BSE or with a CIN are Indian.
UPDATE companies SET country = 'IN'
WHERE country IS NULL AND (nse_symbol IS NOT NULL OR bse_code IS NOT NULL OR cin IS NOT NULL);

-- Same protection as the other tables (see 001_init.sql).
ALTER TABLE company_identifiers ENABLE ROW LEVEL SECURITY;
