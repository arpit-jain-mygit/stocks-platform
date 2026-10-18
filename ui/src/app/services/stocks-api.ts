// stocks-api.ts - The one place the UI talks to the backend.
//
// Every call goes to /api/... on the UI's own address. A proxy adds the secret
// X-API-Key and forwards it to the backend: proxy.conf.mjs locally, api/proxy.ts on Vercel.
// Pages never use HttpClient directly - they call these methods.

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

// --- Shapes of the backend's JSON (same fields as GET /companies) ----------------------
export interface Company {
  company_id: string;   // e.g. "OFSS"
  name: string;         // e.g. "Oracle Financial Services Software Ltd"
  nse_symbol: string;
  bse_code: string;
  cin: string;
  isin: string;
  aliases: string[];
}

@Injectable({ providedIn: 'root' })   // one shared instance for the whole app
export class StocksApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  /** Companies that have ingested filings (GET /companies?ingested=true). */
  ingestedCompanies(): Observable<Company[]> {
    return this.http.get<Company[]>(`${this.base}/companies`, { params: { ingested: true } });
  }
}
