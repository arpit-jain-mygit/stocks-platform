// stocks-api.ts - The one place the UI talks to the backend.
//
// Every call goes to /api/... on the UI's own address. A proxy adds the secret
// X-API-Key and forwards it to the backend: proxy.conf.mjs locally, api/proxy.ts on Vercel.
// Pages never use HttpClient directly - they call these methods.

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

// --- Shapes of the backend's JSON -------------------------------------------------------

/** One company (GET /companies). */
export interface Company {
  company_id: string;     // e.g. "OFSS"
  name: string;           // e.g. "Oracle Financial Services Software Ltd"
  nse_symbol: string;
  bse_code: string;
  cin: string;
  isin: string;
  aliases: string[];
  sector: string;
  fy_end_month: number;   // 3 = financial year ends in March
  status: string;         // active / suspended / delisted / insolvency
}

/** One ingested PDF (a "filing"). */
export interface Filing {
  doc_id: string;                 // SHA-256 of the PDF
  file_name: string;
  doc_type: string;               // code, e.g. "annual_report" (names come from docTypes())
  fiscal_year: number;
  quarter: number | null;         // null = full year
  period: string;                 // e.g. "Q3 FY25 (quarter ended 31-Dec-2024)"
  period_end: string;             // "YYYY-MM-DD"
  status: string;                 // processing / complete / failed / superseded
  pages: number | null;
  ocr_pages: number[];
  chunks: number | null;
  error: string | null;
  superseded_by: string | null;
  created_at: string;             // ISO time of first ingestion
  updated_at: string;
}

/** One company with its filings (GET /companies/{id}). */
export interface CompanyDetail extends Company {
  filings: Filing[];
}

/** Allowed document types (GET /doc-types). */
export interface DocTypes {
  default: string;
  doc_types: { code: string; name: string }[];
}

@Injectable({ providedIn: 'root' })   // one shared instance for the whole app
export class StocksApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  /** Companies that have ingested filings (GET /companies?ingested=true). */
  ingestedCompanies(): Observable<Company[]> {
    return this.http.get<Company[]>(`${this.base}/companies`, { params: { ingested: true } });
  }

  /** One company and its filings. id = company code, e.g. "OFSS". */
  company(id: string): Observable<CompanyDetail> {
    return this.http.get<CompanyDetail>(`${this.base}/companies/${encodeURIComponent(id)}`);
  }

  /** Document type codes and their display names. */
  docTypes(): Observable<DocTypes> {
    return this.http.get<DocTypes>(`${this.base}/doc-types`);
  }
}
