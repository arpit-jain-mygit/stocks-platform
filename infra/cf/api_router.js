// api_router.js - CloudFront Function (viewer request). Runs at the edge before every request
// to the site, on both the /api/* behaviour and the site behaviour.
//
// 1. /api/<allowed path>   -> "/api" is removed, so API Gateway gets the real path (/companies ...)
// 2. any other /api/ path  -> 404 (the risky delete and backup APIs are never reachable)
// 3. a site path with no file extension (e.g. /chat) -> /index.html, so Angular routes work on reload
//
// The rules mirror ui/api/proxy.ts (the Vercel path) plus the jobs and uploads routes in docs/AWS.md step 2.11.

// Each rule: which paths and which HTTP methods the UI may use.
var RULES = [
  { path: /^\/companies(\/[^\/]+)?$/, methods: ['GET'] },
  { path: /^\/doc-types$/, methods: ['GET'] },
  { path: /^\/documents(\/[^\/]+)?$/, methods: ['GET'] },
  { path: /^\/jobs\/[^\/]+$/, methods: ['GET'] },
  { path: /^\/ask$/, methods: ['POST'] },
  { path: /^\/uploads$/, methods: ['POST'] }
];

function notAvailable() {
  return {
    statusCode: 404,
    statusDescription: 'Not Found',
    headers: { 'content-type': { value: 'application/json' } },
    body: '{"detail":"Not available"}'
  };
}

function handler(event) {
  var request = event.request;
  var uri = request.uri;

  if (uri === '/api' || uri.indexOf('/api/') === 0) {
    var path = uri.substring(4);            // "/api/companies" -> "/companies"
    for (var i = 0; i < RULES.length; i++) {
      if (RULES[i].path.test(path)) {
        if (RULES[i].methods.indexOf(request.method) !== -1) {
          request.uri = path;
          return request;
        }
        break;                              // right path, wrong method: refuse
      }
    }
    return notAvailable();
  }

  // A file (has an extension) is served as it is; anything else is an Angular route.
  if (!/\.[A-Za-z0-9]+$/.test(uri)) {
    request.uri = '/index.html';
  }
  return request;
}
