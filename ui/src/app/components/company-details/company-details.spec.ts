// company-details.spec.ts - Unit tests for the company details shown in an opened card (npm test).
// The backend is faked with HttpTestingController: no network calls.

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { CompanyDetails } from './company-details';
import { CompanyDetail, DocTypes } from '../../services/stocks-api';

const OFSS: CompanyDetail = {
  company_id: 'OFSS', name: 'Oracle Financial Services Software Ltd', nse_symbol: 'OFSS', bse_code: '532466',
  cin: '', isin: 'INE881D01027', aliases: ['i-flex solutions', 'Oracle Financial Services'], sector: '',
  fy_end_month: 3, status: 'active',
  filings: [{
    doc_id: '4a9e8ce73533206b361bc60de95dc8114f2fbe93ae648463a5b2a8492973a08d',
    file_name: 'ofss-software-limited-ar-2025-26.pdf', doc_type: 'annual_report', fiscal_year: 2026, quarter: null,
    period: 'FY26 (year ended 31-Mar-2026)', period_end: '2026-03-31', status: 'complete', pages: 236,
    ocr_pages: [], chunks: 1193, error: null, superseded_by: null,
    created_at: '2026-10-17T10:26:34+00:00', updated_at: '2026-10-17T11:02:10+00:00',
  }],
};
const TYPES: DocTypes = { default: 'quarterly_results', doc_types: [{ code: 'annual_report', name: 'Annual report' }] };

describe('CompanyDetails', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());   // fails if the page made a call the test didn't expect

  // Shows the details for one company id; returns them with the two pending requests.
  async function open(id: string) {
    const fixture = TestBed.createComponent(CompanyDetails);
    fixture.componentRef.setInput('companyId', id);   // what the home page's card does
    await fixture.whenStable();
    return {
      fixture,
      page: fixture.nativeElement as HTMLElement,
      company: backend.expectOne(`/api/companies/${id}`),
      types: backend.expectOne('/api/doc-types'),
    };
  }

  it('shows details, aliases and filings', async () => {
    const { fixture, page, company, types } = await open('OFSS');
    company.flush(OFSS);
    types.flush(TYPES);
    await fixture.whenStable();

    expect(page.textContent).toContain('active');                       // status
    expect(page.textContent).toContain('532466');                       // details
    expect(page.textContent).toContain('March');                        // FY end month as a name
    expect(page.querySelectorAll('.chips li').length).toBe(2);          // aliases
    expect(page.textContent).toContain('Filings (1)');
    expect(page.textContent).toContain('FY26 (year ended 31-Mar-2026)');
    expect(page.textContent).toContain('Annual report');                // doc type name, not the code
    expect(page.textContent).toContain('1,193');                        // chunks, formatted
  });

  it('says so for an unknown company', async () => {
    const { fixture, page, company, types } = await open('NOPE');
    company.flush({ detail: 'No company' }, { status: 404, statusText: 'Not Found' });
    expect(types.cancelled).toBe(true);           // the page drops the other request when one fails
    await fixture.whenStable();
    expect(page.querySelector('[role="alert"]')?.textContent).toContain('No company "NOPE"');
    expect(page.querySelector('button')).toBeNull();                    // no pointless "Try again"
  });
});
