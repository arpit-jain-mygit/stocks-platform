// chat.spec.ts - Unit tests for the chat window (run with: npm test).
// The backend is faked with HttpTestingController: no network, no model calls.

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Chat, SUGGESTED_QUESTIONS } from './chat';
import { AskResponse, Company } from '../../services/stocks-api';

const OFSS: Company = {
  company_id: 'OFSS', name: 'Oracle Financial Services Software Ltd', country: 'IN',
  identifiers: [{ type: 'ticker', exchange: 'NSE', value: 'OFSS' }],
  nse_symbol: 'OFSS', bse_code: '', cin: '', isin: '', aliases: [], sector: '', fy_end_month: 3, status: 'active',
};
const ANSWER: AskResponse = {
  answer: 'Basic EPS was **303.54** [S1].\n<script>alert(1)</script>',
  sources: [{ ref: 'S1', file_name: 'ofss-ar.pdf', pages: '91', location: '', citation: 'page 91', section: 'Note 23', kind: 'table', score: 0.74,
              doc_id: 'abc', company_id: 'OFSS' }],
};

describe('Chat', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());   // fails on any unexpected request

  // Creates the chat (with OFSS selected on the home view) and opens the window.
  async function openChat(selected: string | null = 'OFSS') {
    const fixture = TestBed.createComponent(Chat);
    document.body.appendChild(fixture.nativeElement);   // attached, so focus can be checked
    fixture.componentRef.setInput('companies', [OFSS]);
    fixture.componentRef.setInput('companyId', selected);
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    (page.querySelector('.launcher') as HTMLButtonElement).click();
    await fixture.whenStable();
    return { fixture, page };
  }

  // Types a question and presses Enter.
  async function ask(fixture: { whenStable(): Promise<unknown> }, page: HTMLElement, text: string) {
    const box = page.querySelector('textarea') as HTMLTextAreaElement;
    box.value = text;
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await fixture.whenStable();
  }

  it('starts closed, opens from the button, picker follows the selected company', async () => {
    const { page } = await openChat();
    expect(page.querySelector('.notice')?.textContent).toContain('does not provide investment');   // disclaimer first
    expect(page.querySelector('[role="dialog"]')).not.toBeNull();
    expect((page.querySelector('select') as HTMLSelectElement).value).toBe('OFSS');
    expect(document.activeElement).toBe(page.querySelector('textarea'));   // ready to type
  });

  it('sends the question with the company and shows the answer with its sources', async () => {
    const { fixture, page } = await openChat();
    await ask(fixture, page, 'What is the EPS?');

    const request = backend.expectOne('/api/ask');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ question: 'What is the EPS?', company: 'OFSS' });
    expect(page.textContent).toContain('What is the EPS?');            // the user's bubble
    expect(page.textContent).toContain('Thinking');

    request.flush(ANSWER);
    await fixture.whenStable();
    const answer = page.querySelector('.assistant p') as HTMLElement;
    expect(answer.querySelector('strong')?.textContent).toBe('303.54');   // **bold** rendered
    expect(answer.querySelector('.cite')?.textContent).toBe('S1');       // [S1] as a tag
    expect(answer.querySelector('script')).toBeNull();                   // model text can't inject HTML
    expect(page.querySelector('.sources')?.textContent).toContain('ofss-ar.pdf, page 91');
    expect(page.textContent).not.toContain('Thinking');
  });

  it('always shows 5 suggested questions; clicking one sends it for the picked company', async () => {
    const { fixture, page } = await openChat();
    const buttons = page.querySelectorAll<HTMLButtonElement>('.suggestions button');
    expect(buttons.length).toBe(9);
    expect(SUGGESTED_QUESTIONS.length).toBe(9);

    buttons[1].click();
    await fixture.whenStable();
    const request = backend.expectOne('/api/ask');
    expect(buttons[1].textContent?.trim()).toBe(SUGGESTED_QUESTIONS[1].label);      // short label on the chip
    expect(request.request.body).toEqual({ question: SUGGESTED_QUESTIONS[1].question, company: 'OFSS' });   // full question sent
    expect(buttons[0].disabled).toBe(true);                              // no second question while waiting

    request.flush({ answer: 'ok', sources: [] });
    await fixture.whenStable();
    const after = page.querySelectorAll<HTMLButtonElement>('.suggestions button');
    expect(after.length).toBe(9);                                        // still shown after an answer
    expect(after[0].disabled).toBe(false);
  });

  it('a spreadsheet source shows its sheet and rows, not a page number', async () => {
    const { fixture, page } = await openChat();
    await ask(fixture, page, 'What was revenue?');
    backend.expectOne('/api/ask').flush({ answer: 'Revenue was 57,167 [S1].', sources: [{ ref: 'S1',
      file_name: 'statements.xlsx', pages: '', location: "sheet 'Income Statements', rows 2-61",
      citation: "sheet 'Income Statements', rows 2-61", section: 'Income Statements', kind: 'table', score: 0.8,
      doc_id: 'd', company_id: 'OFSS' }] });
    await fixture.whenStable();
    const sources = page.querySelector('.sources')?.textContent ?? '';
    expect(sources).toContain("sheet 'Income Statements', rows 2-61");
    expect(sources).not.toContain('page ');
  });

  it('"All companies" sends no company', async () => {
    const { fixture, page } = await openChat(null);
    await ask(fixture, page, 'Which company had the highest revenue?');
    expect(backend.expectOne('/api/ask').request.body).toEqual({ question: 'Which company had the highest revenue?' });
  });

  it('does not send questions shorter than 3 characters', async () => {
    const { fixture, page } = await openChat();
    await ask(fixture, page, 'hi');
    backend.expectNone('/api/ask');
  });

  it('shows a friendly error when the model is out of quota', async () => {
    const { fixture, page } = await openChat();
    await ask(fixture, page, 'What is the EPS?');
    backend.expectOne('/api/ask').flush({ detail: 'quota' }, { status: 429, statusText: 'Too Many Requests' });
    await fixture.whenStable();
    expect(page.querySelector('[role="alert"]')?.textContent).toContain('out of quota');
  });
});
