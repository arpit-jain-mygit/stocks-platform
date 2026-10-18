-- add_company.sql - PL/pgSQL blocks for the Supabase SQL editor.
--
--   Block 1: add a company (+ aliases)
--   Block 2: add a document type
--
-- Postgres is the only place companies and doc types live. The API sees
-- changes within 60 seconds (cache). Set the values at the top of ONE block,
-- select it, Run. Each block is all-or-nothing.
--
-- v_dry_run = true (default): checks everything, reports, then undoes it
--   (ends with an error "DRY RUN ..." on purpose). false = really add.


-- =====================================================================================
-- Block 1: add a company (+ aliases)
-- =====================================================================================
DO $$
DECLARE
    v_code        TEXT     := 'TCS';                        -- stable key used everywhere (NSE symbol recommended)
    v_name        TEXT     := 'Tata Consultancy Services Ltd';
    v_nse_symbol  TEXT     := 'TCS';
    v_bse_code    TEXT     := NULL;                         -- e.g. '532540'
    v_isin        TEXT     := NULL;                         -- e.g. 'INE467B01029'
    v_cin         TEXT     := NULL;
    v_sector      TEXT     := NULL;
    v_status      TEXT     := 'active';                     -- active / suspended / delisted / insolvency
    v_aliases     TEXT[]   := ARRAY['Tata Consultancy Services Limited', 'Tata Consultancy Services'];
    v_dry_run     BOOLEAN  := true;                         -- false = really add

    v_company_id  BIGINT;
    v_alias       TEXT;
    v_taken_by    TEXT;
BEGIN
    IF EXISTS (SELECT 1 FROM companies WHERE code = v_code) THEN
        RAISE EXCEPTION 'Company % already exists', v_code;
    END IF;

    -- Every identifier must be new: an alias, code or exchange id that already
    -- belongs to another company would make lookups ambiguous.
    FOREACH v_alias IN ARRAY array_remove(ARRAY[v_code, v_name, v_nse_symbol, v_bse_code, v_isin, v_cin] || v_aliases, NULL)
    LOOP
        SELECT c.code INTO v_taken_by
        FROM companies c LEFT JOIN company_aliases a ON a.company_id = c.id
        WHERE lower(v_alias) IN (lower(c.code), lower(c.name), lower(c.nse_symbol), lower(c.bse_code),
                                 lower(c.isin), lower(c.cin), lower(a.alias::text))
        LIMIT 1;
        IF v_taken_by IS NOT NULL THEN
            RAISE EXCEPTION '"%" already identifies company %', v_alias, v_taken_by;
        END IF;
    END LOOP;

    INSERT INTO companies (code, name, nse_symbol, bse_code, isin, cin, sector, status)
    VALUES (v_code, v_name, v_nse_symbol, v_bse_code, v_isin, v_cin, v_sector, v_status)
    RETURNING id INTO v_company_id;

    INSERT INTO company_aliases (company_id, alias)
    SELECT v_company_id, unnest(v_aliases);

    RAISE NOTICE 'Added company % (%) with % alias(es)', v_code, v_name, cardinality(v_aliases);

    IF v_dry_run THEN
        RAISE EXCEPTION 'DRY RUN - nothing kept. Company % (%) with % alias(es) would be added. Set v_dry_run := false to add.',
            v_code, v_name, cardinality(v_aliases);
    END IF;
END $$;


-- =====================================================================================
-- Block 2: add a document type
-- =====================================================================================
DO $$
DECLARE
    v_code     TEXT    := 'credit_rating';                  -- lowercase_with_underscores
    v_name     TEXT    := 'Credit rating report';
    v_dry_run  BOOLEAN := true;
BEGIN
    IF v_code !~ '^[a-z][a-z0-9_]*$' THEN
        RAISE EXCEPTION 'Code % must be lowercase letters, digits and underscores', v_code;
    END IF;
    IF EXISTS (SELECT 1 FROM doc_types WHERE code = v_code) THEN
        RAISE EXCEPTION 'Doc type % already exists', v_code;
    END IF;

    INSERT INTO doc_types (code, name) VALUES (v_code, v_name);
    RAISE NOTICE 'Added doc type %', v_code;

    IF v_dry_run THEN
        RAISE EXCEPTION 'DRY RUN - nothing kept. Doc type % (%) would be added. Set v_dry_run := false to add.', v_code, v_name;
    END IF;
END $$;
