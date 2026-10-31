# Architecture

```
                       ┌────────────────────┐
                       │ Client · UI · eval │
                       └──────────┬─────────┘
                                  │
┌─────────────────────────────────▼────────────────────────────────┐
│ api/  FastAPI                                                    │
│ /ingest  /jobs  /documents  /ask  /health                        │
└───────────────┬──────────────────────────────────┬───────────────┘
                │                                  │
┌───────────────▼───────────────┐  ┌───────────────▼───────────────┐
│ ingest/                       │  │ query/                        │
│ 1 ids                         │  │ search                        │
│ 2 pdf_reader                  │  │ answer                        │
│ 3 chunker                     │  │                               │
│ 4 embeddings                  │  │                               │
│ 5 store                       │  │                               │
└───────────────┬───────────────┘  └───────────────┬───────────────┘
                │                                  │
┌───────────────▼──────────────────────────────────▼───────────────┐
│ utils/                                                           │
│ llm factory   vectorstore factory   metadata factory             │
│ prompts       page_cache            vector_cache       ocr       │
└─────┬─────────────┬─────────────┬─────────────┬─────────────┬────┘
      │             │             │             │             │
┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼────┐
│ Gemini    │ │ Qdrant    │ │ Postgres  │ │ Tesseract │ │ Disk     │
└───────────┘ └───────────┘ └───────────┘ └───────────┘ └──────────┘
```

Each layer only calls the one below it.

| Layer | Role |
|---|---|
| `api/` | HTTP endpoints, API-key check, background ingestion jobs |
| `api/risky_delete_apis` | Guarded delete endpoints (off by default; admin key + dry run + confirm) |
| `api/backup_apis` + `ops/backup.py` | Guarded backup / restore of Postgres + Qdrant as one file (off by default) |
| `ingest/` | PDF → pages → chunks → vectors → vector store, with dedup |
| `query/` | Question → search → answer with page citations |
| `utils/llm` | LLM factory; provider per role (vision, answer, embed) set in `.env` |
| `utils/vectorstore` | Vector DB factory; `VECTOR_STORE` set in `.env` |
| `utils/metadata` | Metadata factory (companies, doc types, filings); `METADATA_STORE=postgres` |
| `utils/` (rest) | Prompts, OCR, page and vector caches |

Diagram source: `docs/architecture_diagram.py` (regenerates and checks alignment).

## AWS deployment (aws-serverless)

The diagrams below show the AWS version. Non-AWS services are in their own group. They render on GitHub.

### Architecture

```mermaid
flowchart LR
  user["User browser"]
  subgraph AWS
    cf["CloudFront"]
    s3fe["S3 frontend site"]
    apigw["API Gateway"]
    lambda["Lambda FastAPI API"]
    ecs["ECS Fargate worker"]
    s3up["S3 uploads and cache"]
    ddb["DynamoDB jobs"]
    ssm["SSM secrets"]
    cw["CloudWatch and SNS alerts"]
  end
  subgraph NonAWS["Non-AWS"]
    sb["Supabase Postgres"]
    qd["Qdrant Cloud"]
    gem["Gemini API"]
    gha["GitHub Actions"]
  end
  user --> cf
  cf -->|"site files"| s3fe
  cf -->|"/api"| apigw
  apigw --> lambda
  lambda --> ddb
  lambda --> s3up
  lambda -->|"RunTask"| ecs
  lambda --> sb
  lambda --> qd
  lambda --> gem
  ecs --> s3up
  ecs --> ddb
  ecs --> sb
  ecs --> qd
  ssm -.->|"secrets"| lambda
  ssm -.->|"secrets"| ecs
  cw --> lambda
  gha -.->|"deploys via OIDC"| lambda
```

### End-to-end flow

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant CF as CloudFront
  participant AG as API Gateway
  participant L as Lambda API
  participant S3 as S3
  participant D as DynamoDB
  participant W as Fargate worker
  participant Q as Qdrant Cloud
  participant SB as Supabase
  participant G as Gemini API
  B->>CF: GET site
  CF->>S3: fetch Angular files
  S3-->>B: app
  B->>CF: POST /api/uploads
  CF->>AG: forward
  AG->>L: create presigned link
  L-->>B: upload_url and upload_key
  B->>S3: PUT file using presigned link
  B->>AG: POST /ingest with upload_key
  AG->>L: ingest
  L->>S3: check size and type
  L->>SB: duplicate check
  L->>Q: duplicate check
  L->>D: create job queued
  L->>W: RunTask with job_id and upload_key
  L-->>B: queued and job_id
  W->>D: status running
  W->>S3: read PDF
  W->>W: OCR, chunk and embed
  W->>Q: store vectors
  W->>SB: store metadata
  W->>D: status complete
  B->>CF: GET /api/jobs/id
  CF->>AG: forward
  AG->>L: read job
  L->>D: get job
  L-->>B: status
  B->>CF: POST /api/ask
  CF->>AG: forward
  AG->>L: ask
  L->>Q: search chunks
  L->>G: generate answer
  L-->>B: answer with citations
```
