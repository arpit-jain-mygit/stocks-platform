// chat.ts - The chat window: ask questions about the filings, get answers with sources.
//
// A floating "Ask a question" button opens it (bottom-right; full screen on phones).
// Each question goes to POST /api/ask (services/stocks-api.ts). The company picker
// starts on the company selected on the home view, or "All companies".
// The conversation lives only in memory: it is gone after a page reload.

import { Component, ElementRef, Injector, afterNextRender, effect, inject, input, linkedSignal, signal, viewChild } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { DISCLAIMER } from '../../disclaimer';
import { Company, Source, StocksApi } from '../../services/stocks-api';

/**
 * Suggested questions, always shown above the question box - what most stock researchers
 * ask about any company. Clicking one sends it for the company in the picker.
 */
export const SUGGESTED_QUESTIONS: { label: string; question: string }[] = [
  { label: 'Revenue & profit', question: 'What were the revenue and net profit for the latest period?' },
  { label: 'EPS', question: 'What is the earnings per share (EPS)?' },
  { label: 'Debt & finance costs', question: 'How much debt does the company have, and what are its finance costs?' },
  { label: 'Dividend', question: 'Has the company declared a dividend? How much?' },
  { label: 'Risks & legal', question: 'What key risks, auditor qualifications or legal cases are mentioned?' },
];

/** One bubble in the conversation. */
export interface ChatMessage {
  role: 'user' | 'assistant' | 'error';
  text: string;
  company: string;          // company code asked about ("" = all companies)
  sources?: Source[];       // assistant answers only
}

@Component({
  selector: 'app-chat',
  imports: [FormsModule],             // [(ngModel)] on the text box and company picker
  templateUrl: './chat.html',
  styleUrl: './chat.css',
  host: { '(document:keydown.escape)': 'close()' },   // Esc closes the window
})
export class Chat {
  private readonly api = inject(StocksApi);
  private readonly injector = inject(Injector);

  /** Companies for the picker (from the home view). */
  readonly companies = input<Company[]>([]);
  /** The company selected on the home view, if any. */
  readonly companyId = input<string | null>(null);

  // State as signals: when one changes, the template updates by itself.
  protected readonly open = signal(false);
  protected readonly messages = signal<ChatMessage[]>([]);
  protected readonly waiting = signal(false);
  protected readonly question = signal('');
  protected readonly suggestions = SUGGESTED_QUESTIONS;
  protected readonly disclaimer = DISCLAIMER;   // shown before the first question
  /** The picker's value: follows the home view's selection until the user changes it. */
  protected readonly company = linkedSignal(() => this.companyId() ?? '');

  // Elements the code needs to touch: the message list (scrolling) and the text box (focus).
  private readonly list = viewChild<ElementRef<HTMLElement>>('list');
  private readonly box = viewChild<ElementRef<HTMLTextAreaElement>>('box');

  constructor() {
    // After every new message (or the "thinking" line), scroll to the bottom.
    effect(() => {
      this.messages();
      this.waiting();
      const el = this.list()?.nativeElement;
      if (el) queueMicrotask(() => (el.scrollTop = el.scrollHeight));
    });
  }

  protected toggle(): void {
    this.open.update((v) => !v);
    // Put the cursor in the question box once the window has been drawn.
    if (this.open()) afterNextRender(() => this.box()?.nativeElement.focus(), { injector: this.injector });
  }

  protected close(): void {
    this.open.set(false);
  }

  /** Enter sends; Shift+Enter makes a new line. */
  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  /** Sends a suggested question as if it had been typed. */
  protected ask(text: string): void {
    this.question.set(text);
    this.send();
  }

  /** Sends the question (3+ characters) and adds the answer or an error to the conversation. */
  protected send(): void {
    const text = this.question().trim();
    if (text.length < 3 || this.waiting()) return;
    const company = this.company();

    this.messages.update((m) => [...m, { role: 'user', text, company }]);
    this.question.set('');
    this.waiting.set(true);

    this.api.ask({ question: text, ...(company ? { company } : {}) }).subscribe({
      next: (reply) => {
        this.messages.update((m) => [...m, { role: 'assistant', text: reply.answer, company, sources: reply.sources }]);
        this.waiting.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.messages.update((m) => [...m, { role: 'error', text: errorText(err), company }]);
        this.waiting.set(false);
      },
    });
  }

  protected clear(): void {
    this.messages.set([]);
  }

  /** "OFSS" -> "Oracle Financial Services Software Ltd"; "" -> "All companies". */
  protected companyName(code: string): string {
    return code ? (this.companies().find((c) => c.company_id === code)?.name ?? code) : 'All companies';
  }

  /** The answer as safe HTML: text escaped, **bold** kept, [S1] shown as small citation tags. */
  protected answerHtml(text: string): string {
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\[(S\d+(?:\s*,\s*S\d+)*)\]/g, '<span class="cite">$1</span>')
      .replace(/\n/g, '<br>');
  }
}

/** Makes text safe to put into HTML (no tags from the model can run). */
function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** A short, human message for a failed /ask. */
function errorText(err: HttpErrorResponse): string {
  if (err.status === 0) return 'Could not reach the server. Is the backend running?';
  if (err.status === 429) return 'The AI model is busy or out of quota. Please try again in a minute.';
  const detail = typeof err.error?.detail === 'string' ? err.error.detail : '';
  return detail || `Something went wrong (error ${err.status}). Please try again.`;
}
