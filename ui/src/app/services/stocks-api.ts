// stocks-api.ts - The one place the UI talks to the backend.
//
// Every call goes to /api/... on the UI's own address. A proxy adds the secret
// X-API-Key and forwards it to the backend: proxy.conf.mjs locally, api/proxy.ts on Vercel.
// Pages never use HttpClient directly - they call these methods.

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

// --- Shapes of the backend's JSON -------------------------------------------------------

/** One way to identify a company: a ticker on an exchange, an ISIN, a CIN ... */
export interface Identifier {
  type: string;           // ticker / isin / lei / cik / cin / figi / registry
  exchange: string;       // tickers only, e.g. "NSE", "NASDAQ"; "" otherwise
  value: string;          // e.g. "OFSS", "US5949181045"
}

/** One company (GET /companies). */
export interface Company {
  company_id: string;     // e.g. "OFSS"
  name: string;           // e.g. "Oracle Financial Services Software Ltd"
  country: string;        // ISO code, e.g. "IN", "US"; "" if not recorded
  identifiers: Identifier[];   // tickers first, then ISIN, CIN ...
  aliases: string[];
  sector: string;
  fy_end_month: number;   // 3 = financial year ends in March
  status: string;         // active / suspended / delisted / insolvency
  // Older fields, filled from identifiers by the backend (not used by the UI):
  nse_symbol: string;
  bse_code: string;
  cin: string;
  isin: string;
}

/** "NSE OFSS" for a ticker, "ISIN INE881D01027" otherwise - how identifiers are shown. */
export function identifierLabel(id: Identifier): { label: string; value: string } {
  return { label: id.type === 'ticker' ? id.exchange : id.type.toUpperCase(), value: id.value };
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

/** A question for POST /ask. Empty company = search every company. */
export interface AskRequest {
  question: string;       // at least 3 characters
  company?: string;       // company code, e.g. "OFSS"
}

/** One chunk the answer cites, e.g. [S1]. */
export interface Source {
  ref: string;            // "S1"
  file_name: string;
  pages: string;          // "91" or "6-7"; "" for spreadsheets and CSV
  location: string;       // e.g. "sheet 'Income Statements', rows 2-61"; "" for pages
  citation: string;       // what to show: the location, or "page N"
  section: string;
  kind: string;           // prose / table / fact
  score: number;          // search similarity (higher = closer)
  doc_id: string;
  company_id: string;
}

/** The answer from POST /ask, with the sources it cites. */
export interface AskResponse {
  answer: string;
  sources: Source[];
  unverified_figures?: string[];   // optional: figures in the answer not found in the sources (empty = all found)
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

  /** Asks a question; the answer cites its sources. Costs 1 embedding + 1 answer model call. */
  ask(request: AskRequest): Observable<AskResponse> {
    return this.http.post<AskResponse>(`${this.base}/ask`, request);
  }

  /** Document type codes and their display names. */
  docTypes(): Observable<DocTypes> {
    return this.http.get<DocTypes>(`${this.base}/doc-types`);
  }
}
