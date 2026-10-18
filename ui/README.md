# ui

Web UI for stocks-platform - not built yet (see "UI support" and "Deploy UI to Vercel" in [../docs/features.md](../docs/features.md)).

- Deployed to Vercel with Root Directory = `ui`.
- Calls the backend API (Railway URL from an environment variable).
- Never put `APP_API_KEY` in browser code: call the API through a Vercel server route.
