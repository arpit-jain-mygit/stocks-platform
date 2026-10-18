// home.spec.ts - Unit tests for the home page (run with: npm test).
// The backend is faked with HttpTestingController: no network calls.

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Home } from './home';
import { Company } from '../../services/stocks-api';

const OFSS: Company = {
  company_id: 'OFSS', name: 'Oracle Financial Services Software Ltd', nse_symbol: 'OFSS',
  bse_code: '532466', cin: '', isin: 'INE881D01027', aliases: [],
};

describe('Home', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());   // fails if the page made a call the test didn't expect

  // Builds the page and returns its HTML plus the (still unanswered) companies request.
  async function open() {
    const fixture = TestBed.createComponent(Home);
    const request = backend.expectOne((r) => r.url === '/api/companies');
    expect(request.request.params.get('ingested')).toBe('true');
    return { fixture, request, page: fixture.nativeElement as HTMLElement };
  }

  it('shows the companies returned by the backend', async () => {
    const { fixture, request, page } = await open();
    request.flush([OFSS]);
    await fixture.whenStable();
    expect(page.querySelector('h1')?.textContent).toContain('Stocks Platform');
    expect(page.querySelectorAll('article.company').length).toBe(1);
    expect(page.textContent).toContain('Oracle Financial Services Software Ltd');
    expect(page.textContent).toContain('532466');
  });

  it('says so when no company has data', async () => {
    const { fixture, request, page } = await open();
    request.flush([]);
    await fixture.whenStable();
    expect(page.textContent).toContain('No companies with ingested filings yet');
  });

  it('shows an error with a retry button when the backend fails', async () => {
    const { fixture, request, page } = await open();
    request.flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    expect(page.querySelector('[role="alert"]')?.textContent).toContain('Could not load companies');

    (page.querySelector('button') as HTMLButtonElement).click();       // retry -> a new request
    backend.expectOne((r) => r.url === '/api/companies').flush([OFSS]);
    await fixture.whenStable();
    expect(page.textContent).toContain('Oracle Financial Services Software Ltd');
  });
});
