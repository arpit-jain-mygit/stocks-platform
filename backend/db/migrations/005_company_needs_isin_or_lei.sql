-- 005_company_needs_isin_or_lei.sql - every company must have an ISIN or an LEI.
-- Applied by db/migrate.py (runs once; recorded in schema_migrations).
--
-- Why: ISIN (securities) and LEI (legal entities) are global ISO standards that
-- identify a company in any country. Tickers are exchange-specific and national
-- registry numbers (CIN, CIK ...) only work in one country, so they are optional.
--
-- How: a DEFERRED constraint trigger. It runs at COMMIT, not per statement, so a
-- company and its identifiers can be inserted in one transaction (add_company.sql,
-- backup restore) in any order. A row that breaks the rule is refused at commit.
--
-- Existing rows are NOT re-checked when this migration runs. A company that has
-- neither an ISIN nor an LEI (Videocon, until one is verified and added) can be
-- read, but cannot be changed or deleted-and-re-added without one.

CREATE FUNCTION company_has_isin_or_lei(p_company_id BIGINT) RETURNS void AS $$
BEGIN
    -- The company may already be gone (cascade delete): nothing to check then.
    IF NOT EXISTS (SELECT 1 FROM companies WHERE id = p_company_id) THEN
        RETURN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM company_identifiers
                   WHERE company_id = p_company_id AND type IN ('isin', 'lei')) THEN
        RAISE EXCEPTION 'company id % needs at least one ISIN or LEI identifier', p_company_id
            USING HINT = 'Add one with an identifier of type isin or lei (see db/samples/add_company.sql).';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- A company row is inserted or changed: it must end the transaction with an ISIN or LEI.
CREATE FUNCTION trg_company_needs_isin_or_lei() RETURNS trigger AS $$
BEGIN
    PERFORM company_has_isin_or_lei(NEW.id);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- An identifier is removed or moved: the company it leaves must still have an ISIN or LEI.
CREATE FUNCTION trg_identifier_keeps_isin_or_lei() RETURNS trigger AS $$
BEGIN
    PERFORM company_has_isin_or_lei(OLD.company_id);
    IF TG_OP = 'UPDATE' AND NEW.company_id IS DISTINCT FROM OLD.company_id THEN
        PERFORM company_has_isin_or_lei(NEW.company_id);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER companies_need_isin_or_lei
    AFTER INSERT OR UPDATE ON companies
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION trg_company_needs_isin_or_lei();

CREATE CONSTRAINT TRIGGER identifiers_keep_isin_or_lei
    AFTER DELETE OR UPDATE OF company_id, type ON company_identifiers
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION trg_identifier_keeps_isin_or_lei();
