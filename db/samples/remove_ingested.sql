-- remove_ingested.sql - sample queries to remove ingested PDFs (Supabase SQL editor).
--
-- A PDF lives in TWO places:
--   1. Postgres  filings            -> removed by the SQL below
--   2. Qdrant    stocks_rag_chunks  -> NOT reachable from SQL; remove the chunks
--      in the Qdrant console (see "Qdrant" at the bottom), or they stay searchable.
--
-- Safe order: run the PREVIEW query, note the doc_ids, delete the Qdrant
-- chunks for those doc_ids, then run the matching DELETE here.
-- Companies, aliases and doc types are never touched by these queries.


-- =====================================================================================
-- 1. PREVIEW - what is ingested
-- =====================================================================================
SELECT f.doc_id, c.code AS company, f.period_label, f.doc_type, f.status,
       f.chunks, f.file_name, f.updated_at
FROM filings f
JOIN companies c ON c.id = f.company_id
ORDER BY f.updated_at DESC;


-- =====================================================================================
-- 2. DELETE one PDF by doc_id
-- =====================================================================================
BEGIN;
UPDATE filings SET superseded_by = NULL WHERE superseded_by = '<doc_id>';   -- clear links first (foreign key)
DELETE FROM filings WHERE doc_id = '<doc_id>' RETURNING doc_id, file_name;
COMMIT;


-- =====================================================================================
-- 3. DELETE every PDF of one company
-- =====================================================================================
-- preview
SELECT f.doc_id, f.period_label, f.doc_type, f.file_name
FROM filings f JOIN companies c ON c.id = f.company_id
WHERE c.code = 'OFSS';

BEGIN;
UPDATE filings SET superseded_by = NULL
WHERE superseded_by IN (SELECT f.doc_id FROM filings f JOIN companies c ON c.id = f.company_id WHERE c.code = 'OFSS');
DELETE FROM filings
WHERE company_id = (SELECT id FROM companies WHERE code = 'OFSS')
RETURNING doc_id, file_name;
COMMIT;


-- =====================================================================================
-- 4. DELETE one company + period (+ doc type)
--    Period: fiscal_year = 2026 for FY26; quarter 1-4, or IS NULL for a full year.
-- =====================================================================================
BEGIN;
UPDATE filings SET superseded_by = NULL
WHERE superseded_by IN (
    SELECT f.doc_id FROM filings f JOIN companies c ON c.id = f.company_id
    WHERE c.code = 'OFSS' AND f.fiscal_year = 2026 AND f.quarter IS NULL AND f.doc_type = 'financial_statements');
DELETE FROM filings f
USING companies c
WHERE c.id = f.company_id
  AND c.code = 'OFSS' AND f.fiscal_year = 2026 AND f.quarter IS NULL     -- FY26 full year
  AND f.doc_type = 'financial_statements'                               -- remove this line for any doc type
RETURNING f.doc_id, f.file_name;
COMMIT;


-- =====================================================================================
-- 5. DELETE by file name
-- =====================================================================================
BEGIN;
UPDATE filings SET superseded_by = NULL
WHERE superseded_by IN (SELECT doc_id FROM filings WHERE file_name = 'ofss-q4fy26-ind-as-financials-ua.pdf');
DELETE FROM filings WHERE file_name = 'ofss-q4fy26-ind-as-financials-ua.pdf' RETURNING doc_id;
COMMIT;


-- =====================================================================================
-- 6. DELETE failed / stuck ingestions (no chunks to worry about for 'failed')
-- =====================================================================================
DELETE FROM filings
WHERE status = 'failed'
   OR (status = 'processing' AND updated_at < now() - interval '1 hour')
RETURNING doc_id, status, file_name;


-- =====================================================================================
-- 7. DELETE ALL filings (companies and doc types stay)
-- =====================================================================================
-- TRUNCATE filings;


-- =====================================================================================
-- Qdrant - remove the chunks for the same doc_ids
-- (cloud.qdrant.io -> cluster -> Open Dashboard -> Console)
-- =====================================================================================
-- Count first:
--   POST collections/stocks_rag_chunks/points/count
--   {"filter": {"must": [{"key": "doc_id", "match": {"value": "<doc_id>"}}]}, "exact": true}
--
-- Delete one PDF's chunks:
--   POST collections/stocks_rag_chunks/points/delete
--   {"filter": {"must": [{"key": "doc_id", "match": {"value": "<doc_id>"}}]}}
--
-- Delete a whole company's chunks:
--   POST collections/stocks_rag_chunks/points/delete
--   {"filter": {"must": [{"key": "company_id", "match": {"value": "OFSS"}}]}}
--
-- Delete one company + period:
--   POST collections/stocks_rag_chunks/points/delete
--   {"filter": {"must": [{"key": "company_id", "match": {"value": "OFSS"}},
--                        {"key": "fiscal_year", "match": {"value": 2026}}]}}
