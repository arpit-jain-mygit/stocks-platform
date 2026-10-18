-- 002_filings.sql - one row per ingested PDF (moved here from Qdrant).
-- Qdrant keeps only the chunks; this table is the "already ingested?" check
-- and the record of every filing.

CREATE TABLE filings (
    doc_id        TEXT PRIMARY KEY,                       -- SHA-256 of the PDF (same as Qdrant payload)
    company_id    BIGINT   NOT NULL REFERENCES companies(id),
    doc_type      TEXT     NOT NULL REFERENCES doc_types(code),
    fiscal_year   SMALLINT NOT NULL,
    quarter       SMALLINT CHECK (quarter BETWEEN 1 AND 4),   -- NULL = full year
    period_end    DATE     NOT NULL,
    period_label  TEXT     NOT NULL,                      -- 'Q3 FY25 (quarter ended 31-Dec-2024)'
    file_name     TEXT     NOT NULL,
    storage_url   TEXT,                                   -- where the original PDF lives (later)
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

CREATE INDEX filings_company ON filings (company_id, fiscal_year, quarter);

-- At most one live (complete) filing per company + doc type + period.
-- A newer PDF for the same slot marks the older one 'superseded'.
CREATE UNIQUE INDEX filings_one_live
    ON filings (company_id, doc_type, fiscal_year, COALESCE(quarter, 0))
    WHERE status = 'complete';

CREATE TRIGGER filings_updated_at BEFORE UPDATE ON filings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE filings ENABLE ROW LEVEL SECURITY;
