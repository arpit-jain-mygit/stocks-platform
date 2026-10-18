# ui - Stocks Platform web app (Angular single page app)

The browser app for stocks-platform. Today: one screen with a card per company that has ingested
filings. Clicking a card shows its details (status, codes, aliases, filings) in a panel on the right,
so the list stays visible; on phones (under 900px) the details open under the card instead. The
"Ask a question" button (bottom-right) opens a chat window that asks `POST /ask` about the selected
company or all companies, and shows answers with their cited sources. The address stays `/`.
Roadmap: "UI support" in [../docs/features.md](../docs/features.md).

Angular 22, standalone components, router, plain CSS, no server-side rendering (a pure SPA: Vercel serves
static files). Generated with `ng new` (Angular CLI 22.2.3).

## Layout

| Path | What |
|---|---|
| `src/index.html` | The one HTML page; Angular draws everything inside `<app-root>` |
| `src/main.ts` | Starts the app |
| `src/app/app.ts` / `app.html` | Root frame: only `<router-outlet>`, where the current page goes |
| `src/app/app.routes.ts` | URL -> view (`/` = home; anything else -> home) |
| `src/app/app.config.ts` | App-wide providers (router, error listener) |
| `src/app/services/stocks-api.ts` | The only code that calls the backend (`/api/...`) |
| `src/app/components/chat/` | Chat window: company picker, 5 always-visible suggested questions as short chips (`SUGGESTED_QUESTIONS`: label + full question), conversation (in memory only), answers with `[S1]` tags + sources list; Enter sends, Esc closes; full screen on phones. Each question = 1 embedding + 1 answer model call |
| `src/app/components/company-details/` | Shown inside an opened card: status, code, NSE, BSE, FY end; aliases; filings (type, file, ingested) (`GET /api/companies/<code>` + `/api/doc-types`, loaded on open) |
| `src/app/pages/home/` | Home view: company cards (left) + details panel (right, sticky); phones: details under the card. `home.ts` (logic), `home.html` (markup), `home.css` (styles), `home.spec.ts` (tests) |
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

## Deploy to Vercel

1. vercel.com -> **Add New -> Project** -> import the GitHub repo **`stocks-platform`**.
2. Configure the project:
   - **Root Directory**: `ui` (click Edit next to it)
   - **Framework Preset**: Angular (detected)
   - **Build Command**: `npm run build` (default) - **Output Directory**: `dist/stocks-ui/browser`
3. **Environment Variables** (read only by `api/proxy.ts`, on Vercel's servers - never sent to the browser):
   - `STOCKS_API_URL` = `https://stocks-platform-production.up.railway.app` (no trailing slash)
   - `STOCKS_API_KEY` = the Railway service's `APP_API_KEY`
4. **Deploy**. Every push to `main` that touches `ui/` redeploys (Settings -> Git -> Ignored Build Step:
   "Only build if there are changes in a folder" -> `ui`).

Check (replace the domain):

```bash
curl -s "https://<your-app>.vercel.app/api/companies?ingested=true"
```

Should list the companies (no key needed: the proxy adds it). Then open the site, click a company,
try the chat. `curl -s -X POST https://<your-app>.vercel.app/api/backup/create` must return 404.

Troubleshooting: `500 Server is missing STOCKS_API_URL / STOCKS_API_KEY` = add the variables, then
Redeploy (variables apply to new deployments only). `401` = `STOCKS_API_KEY` differs from Railway's
`APP_API_KEY`. Logs: Vercel project -> **Logs** (filter by `/api/proxy`).
