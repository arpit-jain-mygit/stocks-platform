-- delete_company.sql - PL/pgSQL blocks for the Supabase SQL editor.
--
--   Block 1: delete a company COMPLETELY  (filings + aliases + the company row)
--   Block 2: delete a company's FILINGS only (company and aliases stay)
--
-- How to use: set v_code (and v_dry_run) at the top of ONE block, select that
-- block, Run. Each block is all-or-nothing: if anything fails, nothing changes.
--
-- v_dry_run = true (default): reports what WOULD be deleted, then undoes it
--   (the block ends with an error "DRY RUN ..." on purpose - that is the undo).
-- v_dry_run = false: really deletes.
--
-- Postgres only. The company's CHUNKS live in Qdrant and stay searchable until
-- removed there - Qdrant console (cloud.qdrant.io -> cluster -> Open Dashboard -> Console):
--   POST collections/stocks_rag_chunks/points/delete
--   {"filter": {"must": [{"key": "company_id", "match": {"value": "OFSS"}}]}}
--
-- Postgres is the only place companies live, so after Block 1 (and the Qdrant
-- delete) no trace of the company is left.


-- =====================================================================================
-- Block 1: delete company data, including filings
-- =====================================================================================
DO $$
DECLARE
    v_code     TEXT    := 'OFSS';   -- company code (companies.code)
    v_dry_run  BOOLEAN := true;     -- false = really delete

    v_company_id BIGINT;
    v_name       TEXT;
    v_filings    INT;
    v_aliases    INT;
    v_unlinked   INT;
BEGIN
    SELECT id, name INTO v_company_id, v_name FROM companies WHERE code = v_code;
    IF v_company_id IS NULL THEN
        RAISE EXCEPTION 'No company with code %', v_code;
    END IF;

    -- Other companies' filings never point at these, but clear any links first
    -- so the superseded_by foreign key can't block the delete.
    UPDATE filings SET superseded_by = NULL
    WHERE superseded_by IN (SELECT doc_id FROM filings WHERE company_id = v_company_id);
    GET DIAGNOSTICS v_unlinked = ROW_COUNT;

    DELETE FROM filings WHERE company_id = v_company_id;
    GET DIAGNOSTICS v_filings = ROW_COUNT;

    DELETE FROM company_aliases WHERE company_id = v_company_id;
    GET DIAGNOSTICS v_aliases = ROW_COUNT;

    DELETE FROM companies WHERE id = v_company_id;

    RAISE NOTICE 'Company % (%): % filing(s), % alias(es), 1 company row deleted (% link(s) cleared)',
        v_code, v_name, v_filings, v_aliases, v_unlinked;

    IF v_dry_run THEN
        RAISE EXCEPTION 'DRY RUN - nothing kept. Would delete % filing(s), % alias(es) and company %. Set v_dry_run := false to delete.',
            v_filings, v_aliases, v_code;
    END IF;
END $$;


-- =====================================================================================
-- Block 2: delete company filings only (company + aliases stay)
-- Optional: limit to one period / doc type with the filters below (NULL = all).
-- =====================================================================================
DO $$
DECLARE
    v_code         TEXT     := 'OFSS';   -- company code (companies.code)
    v_fiscal_year  SMALLINT := NULL;     -- e.g. 2026 for FY26; NULL = every year
    v_quarter      SMALLINT := NULL;     -- 1-4; NULL = any (incl. full-year filings)
    v_doc_type     TEXT     := NULL;     -- e.g. 'financial_statements'; NULL = every type
    v_dry_run      BOOLEAN  := true;     -- false = really delete

    v_company_id BIGINT;
    v_filings    INT;
    v_unlinked   INT;
    v_doc        RECORD;
BEGIN
    SELECT id INTO v_company_id FROM companies WHERE code = v_code;
    IF v_company_id IS NULL THEN
        RAISE EXCEPTION 'No company with code %', v_code;
    END IF;

    -- Show each filing that matches.
    FOR v_doc IN
        SELECT doc_id, period_label, doc_type, status, chunks, file_name
        FROM filings
        WHERE company_id = v_company_id
          AND (v_fiscal_year IS NULL OR fiscal_year = v_fiscal_year)
          AND (v_quarter     IS NULL OR quarter     = v_quarter)
          AND (v_doc_type    IS NULL OR doc_type    = v_doc_type)
    LOOP
        RAISE NOTICE '  % | % | % | % | % chunks | %',
            left(v_doc.doc_id, 12), v_doc.period_label, v_doc.doc_type, v_doc.status, v_doc.chunks, v_doc.file_name;
    END LOOP;

    UPDATE filings SET superseded_by = NULL
    WHERE superseded_by IN (
        SELECT doc_id FROM filings
        WHERE company_id = v_company_id
          AND (v_fiscal_year IS NULL OR fiscal_year = v_fiscal_year)
          AND (v_quarter     IS NULL OR quarter     = v_quarter)
          AND (v_doc_type    IS NULL OR doc_type    = v_doc_type));
    GET DIAGNOSTICS v_unlinked = ROW_COUNT;

    DELETE FROM filings
    WHERE company_id = v_company_id
      AND (v_fiscal_year IS NULL OR fiscal_year = v_fiscal_year)
      AND (v_quarter     IS NULL OR quarter     = v_quarter)
      AND (v_doc_type    IS NULL OR doc_type    = v_doc_type);
    GET DIAGNOSTICS v_filings = ROW_COUNT;

    RAISE NOTICE 'Company %: % filing(s) deleted (% link(s) cleared). Company and aliases kept.',
        v_code, v_filings, v_unlinked;

    IF v_dry_run THEN
        RAISE EXCEPTION 'DRY RUN - nothing kept. Would delete % filing(s) of %. Set v_dry_run := false to delete.',
            v_filings, v_code;
    END IF;
END $$;
