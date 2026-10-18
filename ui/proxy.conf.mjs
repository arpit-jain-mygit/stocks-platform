// proxy.conf.mjs - Local development only (npm start).
//
// The browser calls /api/... on localhost:4200. This proxy forwards the call to the
// backend and adds the X-API-Key header there, so the key never reaches the browser.
//   /api/companies  ->  <backend>/companies   (+ X-API-Key)
//
// Which backend and key:
//   1. STOCKS_API_URL / STOCKS_API_KEY environment variables, if set
//      (e.g. to try the UI against Railway), otherwise
//   2. http://localhost:8000 and APP_API_KEY from ../backend/.env (the local backend).
// On Vercel the same job is done by api/proxy.ts.

import { existsSync, readFileSync } from 'node:fs';

// Reads one KEY=value line from ../backend/.env (no extra package needed).
function fromBackendEnv(name) {
  const file = new URL('../backend/.env', import.meta.url);
  if (!existsSync(file)) return '';
  const line = readFileSync(file, 'utf8').split('\n').find((l) => l.startsWith(`${name}=`));
  return line ? line.slice(name.length + 1).trim().replace(/^["']|["']$/g, '') : '';
}

const target = process.env.STOCKS_API_URL || 'http://localhost:8000';
const apiKey = process.env.STOCKS_API_KEY || fromBackendEnv('APP_API_KEY');

export default {
  '/api': {
    target,
    changeOrigin: true,                       // send the backend's own host name (needed for Railway)
    pathRewrite: { '^/api': '' },             // /api/companies -> /companies
    headers: { 'X-API-Key': apiKey },         // added here, on your machine - never in the browser
  },
};
