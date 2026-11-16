// chat.spec.ts - Unit tests for the chat window (run with: npm test).
// The backend is faked with HttpTestingController: no network, no model calls.
// Saved chats live in a fake database (the `saved` map) that answers the /api/chats requests.

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Chat, SUGGESTED_QUESTIONS, sessionName } from './chat';
import { AskResponse, ChatSession, Company } from '../../services/stocks-api';

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
  let saved: Map<string, ChatSession>;   // the fake database: saved chats by id

  beforeEach(() => {
    localStorage.clear();                // the window size and owner id start fresh
    saved = new Map();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    serveChats();                        // answer any save still waiting, so nothing is left unexpected
    backend.verify();                    // fails on any unexpected request
  });

  /** Answers every pending /api/chats request from the fake database (list, get one, save). */
  function serveChats() {
    let pending = backend.match((r) => r.url.startsWith('/api/chats'));
    while (pending.length) {
      for (const req of pending) {
        const id = req.request.url.split('/').pop() ?? '';
        if (req.request.method === 'GET' && req.request.url === '/api/chats') {
          req.flush([...saved.values()].map(({ messages: _messages, ...summary }) => ({ ...summary, updated_at: '2026-11-16T00:00:00Z' })));
        } else if (req.request.method === 'GET') {
          const session = saved.get(id);
          if (session) req.flush(session);
          else req.flush({ detail: 'No chat with this id' }, { status: 404, statusText: 'Not Found' });
        } else {
          saved.set(id, { id, ...req.request.body });
          req.flush({ id, updated_at: '2026-11-16T00:00:00Z' });
        }
      }
      pending = backend.match((r) => r.url.startsWith('/api/chats'));
    }
  }

  // Creates the chat (with OFSS selected on the home view) and opens the window.
  async function openChat(selected: string | null = 'OFSS') {
    const fixture = TestBed.createComponent(Chat);
    document.body.appendChild(fixture.nativeElement);   // attached, so focus can be checked
    fixture.componentRef.setInput('companies', [OFSS]);
    fixture.componentRef.setInput('companyId', selected);
    serveChats();                        // the saved-chat list the window loads on start
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    (page.querySelector('.launcher') as HTMLButtonElement).click();
    await fixture.whenStable();
    return { fixture, page };
  }

  // Types a question and presses Enter. The save of the question is answered from the fake database.
  async function ask(fixture: { whenStable(): Promise<unknown> }, page: HTMLElement, text: string) {
    const box = page.querySelector('textarea') as HTMLTextAreaElement;
    box.value = text;
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await fixture.whenStable();
    serveChats();
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
    serveChats();
    const answer = page.querySelector('.assistant p') as HTMLElement;
    expect(answer.querySelector('strong')?.textContent).toBe('303.54');   // **bold** rendered
    expect(answer.querySelector('.cite')?.textContent).toBe('[S1]');     // [S1] as a tag, brackets shown
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
    serveChats();
    const request = backend.expectOne('/api/ask');
    expect(buttons[1].textContent?.trim()).toBe(SUGGESTED_QUESTIONS[1].label);      // short label on the chip
    expect(request.request.body).toEqual({ question: SUGGESTED_QUESTIONS[1].question, company: 'OFSS' });   // full question sent
    expect(buttons[0].disabled).toBe(true);                              // no second question while waiting

    request.flush({ answer: 'ok', sources: [] });
    await fixture.whenStable();
    serveChats();
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
    serveChats();
    const sources = page.querySelector('.sources')?.textContent ?? '';
    expect(sources).toContain("sheet 'Income Statements', rows 2-61");
    expect(sources).not.toContain('page ');
  });

  it('cannot send until a company is chosen', async () => {
    const { fixture, page } = await openChat(null);
    await ask(fixture, page, 'Which company had the highest revenue?');
    backend.expectNone('/api/ask');                                       // nothing sent without a company
    expect((page.querySelector('.send') as HTMLButtonElement).disabled).toBe(true);
    expect(page.querySelector('.hint')?.textContent).toContain('Choose a company');
    expect(page.querySelector('.suggestions button')?.hasAttribute('disabled')).toBe(true);
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
    serveChats();
    expect(page.querySelector('[role="alert"]')?.textContent).toContain('out of quota');
  });

  it('names a session after the first six words of its first question, and saves that name', async () => {
    const { fixture, page } = await openChat();
    await ask(fixture, page, 'What were the revenue and net profit for the latest period?');
    backend.expectOne('/api/ask').flush(ANSWER);
    await fixture.whenStable();
    serveChats();
    (page.querySelector('.sessions-toggle') as HTMLButtonElement).click();
    await fixture.whenStable();
    expect(page.querySelector('.session-name')?.textContent?.trim()).toBe('What were the revenue and net…');
    expect([...saved.values()][0].name).toBe('What were the revenue and net…');   // the server has the name too
    expect(sessionName('What is the EPS?')).toBe('What is the EPS?');   // short questions get no "…"
  });

  it('renames a session, and the name is still there after a reload', async () => {
    const { fixture, page } = await openChat();
    await ask(fixture, page, 'What is the EPS?');
    backend.expectOne('/api/ask').flush(ANSWER);
    await fixture.whenStable();
    serveChats();
    (page.querySelector('.sessions-toggle') as HTMLButtonElement).click();
    await fixture.whenStable();
    (page.querySelector('.rename-session') as HTMLButtonElement).click();
    await fixture.whenStable();
    const input = page.querySelector('.rename') as HTMLInputElement;
    input.value = 'Oracle EPS check';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await fixture.whenStable();
    expect(page.querySelector('.session-name')?.textContent?.trim()).toBe('Oracle EPS check');
    serveChats();                                                        // the rename is saved

    const reloaded = await openChat();                                   // a new component, as after a reload
    (reloaded.page.querySelector('.sessions-toggle') as HTMLButtonElement).click();
    await reloaded.fixture.whenStable();
    expect(reloaded.page.querySelector('.session-name')?.textContent?.trim()).toBe('Oracle EPS check');
    expect(reloaded.page.querySelector('.messages .msg.user')?.textContent).toContain('What is the EPS?');   // the conversation came back
  });

  it('new chat starts an empty chat and keeps the earlier one', async () => {
    const { fixture, page } = await openChat();
    await ask(fixture, page, 'What is the EPS?');
    backend.expectOne('/api/ask').flush(ANSWER);
    await fixture.whenStable();
    serveChats();
    (page.querySelector('.new-chat') as HTMLButtonElement).click();
    await fixture.whenStable();
    expect(page.querySelectorAll('.messages .msg').length).toBe(0);
    (page.querySelector('.sessions-toggle') as HTMLButtonElement).click();
    await fixture.whenStable();
    expect(page.querySelectorAll('.session-name').length).toBe(2);
  });
});
