// company.ts - One company's page, shown at /companies/<code> (see app.routes.ts).
// Shows every detail the backend stores about the company, its aliases and its filings.

import { Component, effect, inject, input, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { Title } from '@angular/platform-browser';
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { CompanyDetail, StocksApi } from '../../services/stocks-api';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                'September', 'October', 'November', 'December'];

@Component({
  selector: 'app-company',
  imports: [RouterLink, DatePipe, DecimalPipe],   // back link, date and number formatting
  templateUrl: './company.html',
  styleUrl: './company.css',
})
export class CompanyPage {
  private readonly api = inject(StocksApi);
  private readonly title = inject(Title);       // the browser tab's title

  /** The :id part of the URL, e.g. "OFSS" (filled in by the router). */
  readonly id = input.required<string>();

  // Page state as signals: when one changes, the template updates by itself.
  protected readonly company = signal<CompanyDetail | null>(null);
  protected readonly docTypeNames = signal<Record<string, string>>({});
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  protected readonly canRetry = signal(false);   // false for "no such company" - retrying won't help

  constructor() {
    // Runs now and again whenever the URL's id changes (e.g. moving between companies).
    effect(() => this.load(this.id()));
  }

  /** Fetches the company (with filings) and the doc type names together. */
  protected load(id: string): void {
    this.loading.set(true);
    this.error.set('');
    forkJoin({ company: this.api.company(id), types: this.api.docTypes() }).subscribe({
      next: ({ company, types }) => {
        this.company.set(company);
        this.title.setTitle(`${company.name} - Stocks Platform`);
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

  /** 3 -> "March". */
  protected monthName(month: number): string {
    return MONTHS[month - 1] ?? String(month);
  }

  /** "annual_report" -> "Annual report" (falls back to the code). */
  protected docTypeName(code: string): string {
    return this.docTypeNames()[code] ?? code;
  }
}
