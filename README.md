# stocks-platform

Ask questions about listed companies' financial filings (results, annual reports) - any market, English filings.
RAG over the filing PDFs: Gemini (vision, answers, embeddings), Qdrant (chunks), Supabase Postgres (metadata).

## Layout

| Folder | What | Deployed to |
|---|---|---|
| [`backend/`](backend/) | FastAPI app, PDF ingestion, query, eval sets, SQL migrations | Railway (root directory `backend`) |
| [`ui/`](ui/) | Angular web UI: company cards, details panel, chat (`/ask`) | Vercel (root directory `ui`) |
| [`docs/`](docs/) | How to run, architecture, data design, roadmap | – |

Start here: [docs/README.md](docs/README.md) (setup and commands) · [docs/features.md](docs/features.md) (roadmap)

Secrets live only in `backend/.env` locally (copy `backend/.env.example`) and in Railway / Vercel variables. Never commit them.
