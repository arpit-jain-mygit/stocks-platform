-- add_company.sql - PL/pgSQL blocks for the Supabase SQL editor.
--
--   Block 1: add a company (+ aliases and identifiers)
--   Block 2: add a document type
--
-- Postgres is the only place companies and doc types live. The API sees
-- changes within 60 seconds (cache). Set the values at the top of ONE block,
-- select it, Run. Each block is all-or-nothing.
--
-- v_dry_run = true (default): checks everything, reports, then undoes it
--   (ends with an error "DRY RUN ..." on purpose). false = really add.
--
-- Block 1: replace every ? with the company's value (in quotes, e.g. 'TCS') or
-- with NULL if it has none. A ? left behind is a syntax error, so the block
-- cannot run with a value missing. The comments show two filled-in examples:
-- TCS (India, year ends in March) and Microsoft (US, year ends in June).
--
-- Identifiers (needs migration 004): one text per identifier, any market -
--   'ticker:<EXCHANGE>:<SYMBOL>'   e.g. 'ticker:NSE:TCS', 'ticker:BSE:532540', 'ticker:NASDAQ:MSFT'
--   '<type>:<value>'               e.g. 'isin:US5949181045', 'cin:L22210MH1995PLC084781', 'lei:...', 'cik:...'
-- Types: ticker, isin, lei, cik, cin, figi, registry. A ticker's symbol only has
-- to be new on its own exchange; every other identifier must be new everywhere.


-- =====================================================================================
-- Block 1: add a company (+ aliases and identifiers)
-- =====================================================================================
DO $$
DECLARE
    v_code         TEXT     := ?;        -- stable key used everywhere, e.g. 'TCS' / 'MSFT' (ticker recommended)
    v_name         TEXT     := ?;        -- e.g. 'Tata Consultancy Services Ltd' / 'Microsoft Corporation'
    v_country      TEXT     := ?;        -- ISO code, e.g. 'IN' / 'US'
    v_sector       TEXT     := ?;        -- e.g. 'IT services' / 'Software' / NULL
    v_fy_end_month SMALLINT := ?;        -- month the financial year ends: 3 (March, e.g. TCS) / 6 (June, e.g. Microsoft) / 12 (December)
    v_status       TEXT     := ?;        -- active / suspended / delisted / insolvency, e.g. 'active'
    v_identifiers  TEXT[]   := ?;        -- e.g. ARRAY['ticker:NSE:TCS', 'ticker:BSE:532540', 'isin:INE467B01029', 'cin:L22210MH1995PLC084781']
                                         --      ARRAY['ticker:NASDAQ:MSFT', 'isin:US5949181045']
    v_aliases      TEXT[]   := ?;        -- e.g. ARRAY['Tata Consultancy Services Limited', 'Tata Consultancy Services']
                                         --      ARRAY['Microsoft', 'Microsoft Corp']
    v_dry_run      BOOLEAN  := true;     -- false = really add

    v_company_id  BIGINT;
    v_alias       TEXT;
    v_item        TEXT;
    v_type        TEXT;
    v_exchange    TEXT;
    v_value       TEXT;
    v_taken_by    TEXT;
BEGIN
    -- These cannot be NULL.
    IF v_code IS NULL OR v_name IS NULL OR v_status IS NULL THEN
        RAISE EXCEPTION 'v_code, v_name and v_status are required';
    END IF;
    IF v_fy_end_month IS NULL OR v_fy_end_month NOT BETWEEN 1 AND 12 THEN
        RAISE EXCEPTION 'Set v_fy_end_month (1-12): the month the financial year ends, e.g. 3 = March, 6 = June';
    END IF;
    v_aliases := coalesce(v_aliases, ARRAY[]::TEXT[]);
    v_identifiers := coalesce(v_identifiers, ARRAY[]::TEXT[]);

    IF EXISTS (SELECT 1 FROM companies WHERE code = v_code) THEN
        RAISE EXCEPTION 'Company % already exists', v_code;
    END IF;

    -- Code, name and aliases must be new: one that already belongs to another
    -- company (as its code, name, alias or a non-ticker identifier) makes lookups ambiguous.
    FOREACH v_alias IN ARRAY ARRAY[v_code, v_name] || v_aliases
    LOOP
        SELECT c.code INTO v_taken_by
        FROM companies c
        WHERE lower(v_alias) IN (lower(c.code), lower(c.name))
           OR EXISTS (SELECT 1 FROM company_aliases a WHERE a.company_id = c.id AND lower(a.alias::text) = lower(v_alias))
           OR EXISTS (SELECT 1 FROM company_identifiers i WHERE i.company_id = c.id AND i.type <> 'ticker'
                      AND upper(i.value) = upper(v_alias))
        LIMIT 1;
        IF v_taken_by IS NOT NULL THEN
            RAISE EXCEPTION '"%" already identifies company %', v_alias, v_taken_by;
        END IF;
    END LOOP;

    INSERT INTO companies (code, name, country, sector, fy_end_month, status)
    VALUES (v_code, v_name, upper(v_country), v_sector, v_fy_end_month, v_status)
    RETURNING id INTO v_company_id;

    INSERT INTO company_aliases (company_id, alias)
    SELECT v_company_id, unnest(v_aliases);

    -- Identifiers: 'ticker:EXCHANGE:SYMBOL' or 'type:value'.
    FOREACH v_item IN ARRAY v_identifiers
    LOOP
        v_type := lower(split_part(v_item, ':', 1));
        IF v_type = 'ticker' THEN
            v_exchange := upper(split_part(v_item, ':', 2));
            v_value    := split_part(v_item, ':', 3);
            IF v_exchange = '' OR v_value = '' THEN
                RAISE EXCEPTION 'Ticker "%" must be written ticker:EXCHANGE:SYMBOL, e.g. ticker:NASDAQ:MSFT', v_item;
            END IF;
        ELSE
            v_exchange := NULL;
            v_value    := substr(v_item, length(split_part(v_item, ':', 1)) + 2);
        END IF;

        SELECT c.code INTO v_taken_by
        FROM company_identifiers i JOIN companies c ON c.id = i.company_id
        WHERE i.type = v_type AND COALESCE(i.exchange, '') = COALESCE(v_exchange, '') AND upper(i.value) = upper(v_value)
        LIMIT 1;
        IF v_taken_by IS NOT NULL THEN
            RAISE EXCEPTION 'Identifier "%" already belongs to company %', v_item, v_taken_by;
        END IF;

        -- The table checks the type (ticker, isin, lei, cik, cin, figi, registry).
        INSERT INTO company_identifiers (company_id, type, exchange, value)
        VALUES (v_company_id, v_type, v_exchange, v_value);
    END LOOP;

    -- Rule (migration 005): every company needs an ISIN or an LEI, so it can be identified worldwide.
    IF NOT EXISTS (SELECT 1 FROM company_identifiers WHERE company_id = v_company_id AND type IN ('isin', 'lei')) THEN
        RAISE EXCEPTION 'Add at least one identifier of type isin or lei, e.g. ''isin:US5949181045'' or ''lei:...''';
    END IF;

    RAISE NOTICE 'Added company % (%) with % identifier(s) and % alias(es)',
        v_code, v_name, cardinality(v_identifiers), cardinality(v_aliases);

    IF v_dry_run THEN
        RAISE EXCEPTION 'DRY RUN - nothing kept. Company % (%) with % identifier(s) and % alias(es) would be added. Set v_dry_run := false to add.',
            v_code, v_name, cardinality(v_identifiers), cardinality(v_aliases);
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
