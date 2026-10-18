# ui - Stocks Platform web app (Angular single page app)

The browser app for stocks-platform. Today: a Hello World home page. Next: ask questions against the
backend API (see "UI support" in [../docs/features.md](../docs/features.md)).

Angular 22, standalone components, router, plain CSS, no server-side rendering (a pure SPA: Vercel serves
static files). Generated with `ng new` (Angular CLI 22.2.3).

## Layout

| Path | What |
|---|---|
| `src/index.html` | The one HTML page; Angular draws everything inside `<app-root>` |
| `src/main.ts` | Starts the app |
| `src/app/app.ts` / `app.html` | Root frame: only `<router-outlet>`, where the current page goes |
| `src/app/app.routes.ts` | URL -> page (`/` = home, anything else -> home) |
| `src/app/app.config.ts` | App-wide providers (router, error listener) |
| `src/app/pages/home/` | Home page: `home.ts` (logic), `home.html` (markup), `home.css` (styles), `home.spec.ts` (test) |
| `src/styles.css` | Global styles + light / dark colour tokens |
| `public/` | Files copied as-is (favicon) |
| `vercel.json` | Sends every URL to `index.html`, so refreshing a deep link works on Vercel |

## Run (from `ui/`)

Needs Node.js (tested with 26) and npm.

```bash
npm install
```
```bash
npm start
```

Open http://localhost:4200 - the page reloads on every save.

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
- Never put `APP_API_KEY` in this code - everything here is visible to visitors. Call the backend
  through a Vercel server route (or user login) instead.
