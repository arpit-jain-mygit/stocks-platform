// home.ts - The home view, shown at "/" (see app.routes.ts). The address never changes.
//
// Wide screens (900px+): company cards on the left, the selected company's details in a
// panel on the right, so the rest of the list stays visible.
// Narrow screens (phones): no room for two columns - details open under the card instead.
// The chat window ("Ask a question", bottom-right) asks about the selected company or all of them.

import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { Chat } from '../../components/chat/chat';
import { CompanyDetails } from '../../components/company-details/company-details';
import { DISCLAIMER, MOTTO } from '../../disclaimer';
import { Company, StocksApi } from '../../services/stocks-api';

/** Screen width from which the details move into the right-hand panel. */
export const WIDE_SCREEN = '(min-width: 900px)';

@Component({
  selector: 'app-home',
  imports: [CompanyDetails, Chat],   // <app-company-details> (panel / under a card), <app-chat> (chat window)
  templateUrl: './home.html',
  styleUrl: './home.css',
})
export class Home {
  private readonly api = inject(StocksApi);

  // The platform's promise and disclaimer (text lives in disclaimer.ts).
  protected readonly motto = MOTTO;
  protected readonly disclaimer = DISCLAIMER;

  // State as signals: when one changes, the template updates by itself.
  protected readonly companies = signal<Company[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  /** The selected company's code, or null. One at a time. */
  protected readonly openId = signal<string | null>(null);
  /** The selected company's record (for the panel heading). */
  protected readonly openCompany = computed(() => this.companies().find((c) => c.company_id === this.openId()) ?? null);
  /** true = two columns (panel on the right); false = details under the card. */
  protected readonly wide = signal(true);

  constructor() {
    this.watchScreenWidth();
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

  /** Selects a company, or unselects it if it is already selected. */
  protected toggle(id: string): void {
    this.openId.update((current) => (current === id ? null : id));
  }

  /** Keeps `wide` in step with the window width (e.g. rotating a tablet, resizing a window). */
  private watchScreenWidth(): void {
    if (typeof window === 'undefined' || !window.matchMedia) return;   // e.g. some test browsers
    const query = window.matchMedia(WIDE_SCREEN);
    const update = () => this.wide.set(query.matches);
    update();
    query.addEventListener('change', update);
    inject(DestroyRef).onDestroy(() => query.removeEventListener('change', update));
  }
}
