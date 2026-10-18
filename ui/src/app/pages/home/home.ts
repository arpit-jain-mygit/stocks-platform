// home.ts - The home view, shown at "/" (see app.routes.ts).
// One card per company with ingested filings. Clicking a card opens its details
// (company-details component) right under it; clicking again closes it.
// The page address never changes.

import { Component, inject, signal } from '@angular/core';
import { CompanyDetails } from '../../components/company-details/company-details';
import { Company, StocksApi } from '../../services/stocks-api';

@Component({
  selector: 'app-home',
  imports: [CompanyDetails],     // <app-company-details> inside an opened card
  templateUrl: './home.html',
  styleUrl: './home.css',
})
export class Home {
  private readonly api = inject(StocksApi);

  // State as signals: when one changes, the template updates by itself.
  protected readonly companies = signal<Company[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  /** The company whose card is open, or null. One card is open at a time. */
  protected readonly openId = signal<string | null>(null);

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

  /** Opens a card, or closes it if it is already open. */
  protected toggle(id: string): void {
    this.openId.update((current) => (current === id ? null : id));
  }
}
