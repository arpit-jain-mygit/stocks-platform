# ui - Stocks Platform web app (Angular single page app)

The browser app for stocks-platform. Today: a home page with a card per company that has ingested
filings; a card opens that company's page (details, aliases, filings). Next: ask questions (see "UI support" in [../docs/features.md](../docs/features.md)).

Angular 22, standalone components, router, plain CSS, no server-side rendering (a pure SPA: Vercel serves
static files). Generated with `ng new` (Angular CLI 22.2.3).

## Layout

| Path | What |
|---|---|
| `src/index.html` | The one HTML page; Angular draws everything inside `<app-root>` |
| `src/main.ts` | Starts the app |
| `src/app/app.ts` / `app.html` | Root frame: only `<router-outlet>`, where the current page goes |
| `src/app/app.routes.ts` | URL -> page (`/` = home, `/companies/<code>` = company page, anything else -> home) |
| `src/app/app.config.ts` | App-wide providers (router, error listener) |
| `src/app/services/stocks-api.ts` | The only code that calls the backend (`/api/...`) |
| `src/app/pages/company/` | Company page: details, aliases, filings (`GET /api/companies/<code>` + `/api/doc-types`) |
| `src/app/pages/home/` | Home page: company cards. `home.ts` (logic), `home.html` (markup), `home.css` (styles), `home.spec.ts` (tests) |
| `proxy.conf.mjs` | Local dev: forwards `/api/...` to the backend and adds `X-API-Key` |
| `api/proxy.ts` | Vercel server function: same job in production, only for allowed endpoints |
| `src/styles.css` | Global styles + light / dark colour tokens |
| `public/` | Files copied as-is (favicon) |
| `vercel.json` | `/api/...` -> `api/proxy.ts`; every other URL -> `index.html` (deep links work) |

## How the UI reaches the backend (and why the key stays secret)

```
browser --/api/companies--> proxy (adds X-API-Key) --/companies--> backend (FastAPI)
```

The browser never sees `APP_API_KEY`: everything in Angular code is downloadable by any visitor. The proxy
is `proxy.conf.mjs` locally and `api/proxy.ts` on Vercel. `api/proxy.ts` forwards only
`GET companies`, `GET companies/<code>`, `GET doc-types`, `GET documents` and `POST ask` - the risky delete and backup APIs are unreachable
from the UI even if they are switched on.

## Run (from `ui/`)

Needs Node.js (tested with 26) and npm, and the backend running (default: local on port 8000).

1. Start the backend (other terminal, from `backend/` with the venv active):
   ```bash
   uvicorn api.main:app --reload
   ```
2. Start the UI:
   ```bash
   npm install
   ```
   ```bash
   npm start
   ```
3. Open http://localhost:4200 - the page reloads on every save.

The proxy uses `APP_API_KEY` from `../backend/.env` automatically. To use the Railway backend instead:

```bash
STOCKS_API_URL=https://stocks-platform-production.up.railway.app STOCKS_API_KEY=<railway APP_API_KEY> npm start
```

Restart `npm start` after changing `proxy.conf.mjs` or `angular.json` (they are read once at start).

```bash
npm test -- --watch=false
```
```bash
npm run build
```

The build goes to `dist/stocks-ui/browser/` (what Vercel serves).

## Deploy to Vercel (later)

- Import the GitHub repo `stocks-platform`, **Root Directory = `ui`**, framework preset **Angular**.
- Output directory: `dist/stocks-ui/browser`.
- Environment variables: `STOCKS_API_URL` (Railway URL) and `STOCKS_API_KEY` (Railway `APP_API_KEY`) -
  read only by `api/proxy.ts` on the server.
- Never put `APP_API_KEY` in this code - everything here is visible to visitors. Call the backend
  through a Vercel server route (or user login) instead.
