// company-details.ts - Everything about one company, shown inside its card on the home page
// when the card is opened: key details, aliases and filings. The page address never changes.

import { Component, effect, inject, input, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { forkJoin } from 'rxjs';
import { CompanyDetail, Identifier, StocksApi } from '../../services/stocks-api';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                'September', 'October', 'November', 'December'];

@Component({
  selector: 'app-company-details',
  imports: [DatePipe],   // date formatting in the template
  templateUrl: './company-details.html',
  styleUrl: './company-details.css',
})
export class CompanyDetails {
  private readonly api = inject(StocksApi);

  /** Which company to show, e.g. "OFSS" (set by the home page's card). */
  readonly companyId = input.required<string>();

  // State as signals: when one changes, the template updates by itself.
  protected readonly company = signal<CompanyDetail | null>(null);
  protected readonly docTypeNames = signal<Record<string, string>>({});
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  protected readonly canRetry = signal(false);   // false for "no such company" - retrying won't help

  constructor() {
    // Runs when the card opens, and again if the company id ever changes.
    effect(() => this.load(this.companyId()));
  }

  /** Fetches the company (with filings) and the doc type names together. */
  protected load(id: string): void {
    this.loading.set(true);
    this.error.set('');
    forkJoin({ company: this.api.company(id), types: this.api.docTypes() }).subscribe({
      next: ({ company, types }) => {
        this.company.set(company);
        this.docTypeNames.set(Object.fromEntries(types.doc_types.map((t) => [t.code, t.name])));
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.status === 404 ? `No company "${id}".` : 'Could not load this company. Is the backend running?');
        this.canRetry.set(err.status !== 404);
        this.loading.set(false);
      },
    });
  }

  /** The company's tickers on every exchange it is listed on. */
  protected tickers(company: CompanyDetail): Identifier[] {
    return company.identifiers.filter((id) => id.type === 'ticker');
  }

  /** 3 -> "March". */
  protected monthName(month: number): string {
    return MONTHS[month - 1] ?? String(month);
  }

  /** "annual_report" -> "Annual report" (falls back to the code). */
  protected docTypeName(code: string): string {
    return this.docTypeNames()[code] ?? code;
  }
}
