-- 003_seed_reference_data.sql - starting reference data (doc types + companies).
-- Generated from the live database when the config JSON files were retired; Postgres is now
-- the only source of truth. ON CONFLICT DO NOTHING: safe on a database that already
-- has these rows (it changes nothing there), and fills a fresh one.
-- Add more companies later with db/samples/add_company.sql (not by editing this file).

INSERT INTO doc_types (code, name, is_default) VALUES
    ('quarterly_results', 'Quarterly financial results (with limited review / audit report)', true),
    ('announcement', 'Corporate announcement (board meeting, insolvency update, etc.)', false),
    ('annual_report', 'Annual report', false),
    ('earnings_call_transcript', 'Earnings call transcript', false),
    ('financial_statements', 'Financial statements (balance sheet, P&L, changes in equity, cash flow)', false),
    ('investor_presentation', 'Investor / analyst presentation', false),
    ('shareholding_pattern', 'Shareholding pattern', false)
ON CONFLICT (code) DO NOTHING;

INSERT INTO companies (code, name, cin, isin, nse_symbol, bse_code, sector, fy_end_month, status) VALUES
    ('OFSS', 'Oracle Financial Services Software Ltd', NULL, 'INE881D01027', 'OFSS', '532466', NULL, 3, 'active'),
    ('VIDEOIND', 'Videocon Industries Ltd', 'L99999MH1986PLC103624', NULL, 'VIDEOIND', '511389', NULL, 3, 'insolvency')
ON CONFLICT (code) DO NOTHING;

INSERT INTO company_aliases (company_id, alias)
SELECT c.id, v.alias
FROM (VALUES
    ('OFSS', 'i-flex solutions'),
    ('OFSS', 'i-flex solutions Limited'),
    ('OFSS', 'Oracle Financial Services'),
    ('OFSS', 'Oracle Financial Services Software'),
    ('OFSS', 'Oracle Financial Services Software Limited'),
    ('VIDEOIND', 'Videocon'),
    ('VIDEOIND', 'Videocon Industries'),
    ('VIDEOIND', 'Videocon Industries Limited')
) AS v(code, alias)
JOIN companies c ON c.code = v.code
ON CONFLICT (alias) DO NOTHING;
