// api/proxy.ts - Vercel server function: the browser's only way to reach the backend.
//
// The browser calls /api/<path> on the Vercel site; vercel.json sends that here as
// /api/proxy?path=<path>. This function runs on Vercel's servers (never in the browser),
// adds the secret X-API-Key and forwards the call to the backend on Railway.
//
// Only the endpoints in ALLOWED can be reached - never the risky delete or backup APIs.
// Settings (Vercel project -> Settings -> Environment Variables):
//   STOCKS_API_URL   backend address, e.g. https://stocks-platform-production.up.railway.app
//   STOCKS_API_KEY   the backend's APP_API_KEY
// Locally, proxy.conf.mjs does the same job for `npm start`.

// --- Which calls the UI may make: "METHOD path" ------------------------------------------
const ALLOWED = new Set(['GET companies', 'GET doc-types', 'GET documents', 'POST ask']);

// --- Forward one request -----------------------------------------------------------------
export async function forward(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const path = (url.searchParams.get('path') ?? '').replace(/^\/+|\/+$/g, '');

  if (!ALLOWED.has(`${request.method} ${path}`)) {
    return Response.json({ detail: 'Not available' }, { status: 404 });
  }
  const backend = process.env.STOCKS_API_URL;
  const apiKey = process.env.STOCKS_API_KEY;
  if (!backend || !apiKey) {
    return Response.json({ detail: 'Server is missing STOCKS_API_URL / STOCKS_API_KEY' }, { status: 500 });
  }

  // Keep the browser's query string (e.g. ?ingested=true), minus our own "path".
  url.searchParams.delete('path');
  const query = url.searchParams.toString();
  const target = `${backend.replace(/\/+$/, '')}/${path}${query ? `?${query}` : ''}`;

  const reply = await fetch(target, {
    method: request.method,
    headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
    body: request.method === 'POST' ? await request.text() : undefined,
  });
  // Pass the backend's answer through as it is (status + JSON body).
  return new Response(reply.body, {
    status: reply.status,
    headers: { 'Content-Type': reply.headers.get('Content-Type') ?? 'application/json' },
  });
}

// Vercel calls the function named after the HTTP method.
export const GET = forward;
export const POST = forward;
