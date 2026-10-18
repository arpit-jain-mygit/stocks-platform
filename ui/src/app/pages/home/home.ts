// home.ts - The home page, shown at "/" (see app.routes.ts).
// Lists the companies that have ingested filings, loaded from the backend.

import { Component, inject, signal } from '@angular/core';
import { Company, StocksApi } from '../../services/stocks-api';

@Component({
  selector: 'app-home',
  templateUrl: './home.html',
  styleUrl: './home.css',
})
export class Home {
  private readonly api = inject(StocksApi);

  // Page state as signals: when one changes, the template updates by itself.
  protected readonly companies = signal<Company[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal('');

  constructor() {
    this.load();
  }

  /** Fetches the company list. Also used by the "Try again" button. */
  protected load(): void {
    this.loading.set(true);
    this.error.set('');
    this.api.ingestedCompanies().subscribe({
      next: (list) => {
        this.companies.set(list);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Could not load companies. Is the backend running?');
        this.loading.set(false);
      },
    });
  }
}
