# stocks-platform

Ask questions about Indian listed companies' financial filings (results, annual reports).
RAG over the filing PDFs: Gemini (vision, answers, embeddings), Qdrant (chunks), Supabase Postgres (metadata).

## Layout

| Folder | What | Deployed to |
|---|---|---|
| [`backend/`](backend/) | FastAPI app, PDF ingestion, query, eval sets, SQL migrations | Railway (root directory `backend`) |
| [`ui/`](ui/) | Web UI (not built yet) | Vercel (root directory `ui`) |
| [`docs/`](docs/) | How to run, architecture, data design, roadmap | – |

Start here: [docs/README.md](docs/README.md) (setup and commands) · [docs/features.md](docs/features.md) (roadmap)

Secrets live only in `backend/.env` locally (copy `backend/.env.example`) and in Railway / Vercel variables. Never commit them.
