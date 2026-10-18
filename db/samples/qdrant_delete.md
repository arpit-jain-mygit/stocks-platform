# Qdrant – delete chunks

Run in the Qdrant console: cloud.qdrant.io → cluster → **Open Dashboard** → **Console**.
Use the **same values** as the matching SQL / PL/pgSQL (`remove_ingested.sql`, `delete_company.sql`).
Run **count** first, then **delete** with the same filter.
Order: delete in Qdrant first, then run the SQL.

| Postgres action | Qdrant filter |
|---|---|
| Delete company completely / all its filings | `company_id` |
| Company + fiscal year + quarter | `company_id` + `fiscal_year` + `quarter` |
| Company + full year | `company_id` + `fiscal_year` + `quarter` is null |
| Company + doc type | `company_id` + `doc_type` |
| One PDF | `doc_id` |
| By file name | not possible (no index) – use `doc_id` |

## Count (template)
```
POST collections/stocks_rag_chunks/points/count
{"filter": {"must": [{"key": "company_id", "match": {"value": "OFSS"}}]}, "exact": true}
```

## 1. Whole company
```
POST collections/stocks_rag_chunks/points/delete
{"filter": {"must": [{"key": "company_id", "match": {"value": "OFSS"}}]}}
```

## 2. Company + one quarter
```
POST collections/stocks_rag_chunks/points/delete
{"filter": {"must": [
  {"key": "company_id",  "match": {"value": "VIDEOIND"}},
  {"key": "fiscal_year", "match": {"value": 2025}},
  {"key": "quarter",     "match": {"value": 3}}
]}}
```

## 3. Company + full year (no quarter)
```
POST collections/stocks_rag_chunks/points/delete
{"filter": {"must": [
  {"key": "company_id",  "match": {"value": "OFSS"}},
  {"key": "fiscal_year", "match": {"value": 2026}},
  {"is_null": {"key": "quarter"}}
]}}
```

## 4. Company + doc type
```
POST collections/stocks_rag_chunks/points/delete
{"filter": {"must": [
  {"key": "company_id", "match": {"value": "OFSS"}},
  {"key": "doc_type",   "match": {"value": "financial_statements"}}
]}}
```

## 5. One PDF (doc_id from the SQL preview)
```
POST collections/stocks_rag_chunks/points/delete
{"filter": {"must": [{"key": "doc_id", "match": {"value": "<doc_id>"}}]}}
```

Never delete the whole collection: it holds every company, and other projects share the cluster.
