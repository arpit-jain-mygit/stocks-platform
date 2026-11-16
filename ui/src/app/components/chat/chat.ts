// chat.ts - The chat window: ask questions about the filings, get answers with sources.
//
// A floating "Ask a question" button opens it (bottom-right; full screen on phones).
// Each question goes to POST /api/ask (services/stocks-api.ts). The company picker
// starts on the company selected on the home view. A company must be chosen before
// a question can be sent (one company per question: its figures and citations belong together).
//
// Conversations are sessions, saved in the database through /api/chats. A session is named after
// the first words of its first question (or renamed by the user). The browser only remembers
// the window size, and its owner id (see chatOwnerId in services/stocks-api.ts).

import { Component, ElementRef, Injector, afterNextRender, effect, inject, input, linkedSignal, signal, viewChild } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { DISCLAIMER } from '../../disclaimer';
import { ChatMessage, ChatSession, ChatSummary, Company, StocksApi } from '../../services/stocks-api';

/**
 * Suggested questions, always shown above the question box - what most stock researchers
 * ask about the company in the picker. Clicking one sends it for that company.
 */
export const SUGGESTED_QUESTIONS: { label: string; question: string }[] = [
  { label: 'Revenue & profit', question: 'What were the revenue and net profit for the latest period?' },
  { label: 'EPS', question: 'What is the earnings per share (EPS)?' },
  { label: 'Debt & finance costs', question: 'How much debt does the company have, and what are its finance costs?' },
  { label: 'Cash flow', question: 'What were the operating cash flow and free cash flow?' },
  { label: 'Year on year', question: 'How did revenue and profit change compared with the same period last year?' },
  { label: 'Segments', question: 'How did each business segment perform?' },
  { label: 'Dividends & buybacks', question: 'What dividends and share buybacks were declared or paid?' },
  { label: 'Outlook', question: 'What outlook or guidance did management give?' },
  { label: 'Risks & legal', question: 'What key risks, auditor qualifications or legal cases are mentioned?' },
];

// The window size is the only thing kept in this browser's own storage.
const SIZE_KEY = 'stocks-insights.chat.size';
const DEFAULT_WIDTH = 400;               // px, as before
const DEFAULT_HEIGHT = 600;              // px, as before
const MIN_WIDTH = 320;
const MIN_HEIGHT = 360;
const WINDOW_MARGIN = 48;                // px kept clear around the window (24px each side)

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

  // Sessions: the saved list, the one on screen, the rename box, and a save warning.
  protected readonly sessions = signal<ChatSummary[]>([]);
  protected readonly currentId = signal('');
  protected readonly listOpen = signal(false);
  protected readonly editingId = signal('');
  protected readonly saveFailed = signal(false);

  // Window size in px, changed by dragging the corner.
  protected readonly width = signal(DEFAULT_WIDTH);
  protected readonly height = signal(DEFAULT_HEIGHT);

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

    const size = readSize();
    this.width.set(size.width);
    this.height.set(size.height);

    // Load the saved chats. The most recent one comes back on screen; with none, a new chat starts.
    this.api.chats().subscribe({
      next: (list) => {
        if (list.length) {
          this.sessions.set(list);
          this.openSaved(list[0].id);
        } else {
          this.startBlank();
        }
      },
      error: () => this.startBlank(),   // backend unreachable: a new chat still works, it just is not kept
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
    const company = this.company();
    if (text.length < 3 || this.waiting() || !company) return;

    this.messages.update((m) => [...m, { role: 'user', text, company }]);
    this.persist();
    this.question.set('');
    this.waiting.set(true);

    this.api.ask({ question: text, company }).subscribe({
      next: (reply) => {
        this.messages.update((m) => [...m, { role: 'assistant', text: reply.answer, company, sources: reply.sources }]);
        this.waiting.set(false);
        this.persist();
      },
      error: (err: HttpErrorResponse) => {
        this.messages.update((m) => [...m, { role: 'error', text: errorText(err), company }]);
        this.waiting.set(false);
        this.persist();
      },
    });
  }

  // --- Sessions ----------------------------------------------------------------

  /** Starts a new chat. Nothing is saved until its first question. */
  protected newChat(): void {
    if (this.waiting() || this.messages().length === 0) return;
    this.startBlank();
  }

  /** Opens a saved chat. Not while an answer is still coming in for the current one. */
  protected switchTo(summary: ChatSummary): void {
    if (this.waiting() || summary.id === this.currentId()) return;
    // A new chat that was never asked anything is dropped when the user leaves it.
    this.sessions.update((list) => list.filter((s) => !(s.id === this.currentId() && s.updated_at === '')));
    this.openSaved(summary.id);
  }

  /** The picker changed: keep the company with this chat. */
  protected onCompanyChange(code: string): void {
    this.company.set(code);
    this.sessions.update((list) => list.map((s) => (s.id === this.currentId() ? { ...s, company: code } : s)));
    // A new chat that was never asked anything stays unsaved, so the server gets no empty chats.
    const saved = this.sessions().find((s) => s.id === this.currentId())?.updated_at !== '';
    if (this.messages().length || saved) this.persist();
  }

  /** A chat made here, not yet saved: it has no id on the server until its first question. */
  private startBlank(): void {
    const blank: ChatSummary = {
      id: crypto.randomUUID(), name: 'New chat', renamed: false, company: this.company(), updated_at: '',
    };
    this.sessions.update((list) => [blank, ...list]);
    this.activate({ id: blank.id, name: blank.name, renamed: false, company: blank.company, messages: [] });
  }

  /** Loads a saved chat with its messages and puts it on screen. */
  private openSaved(id: string): void {
    this.currentId.set(id);
    this.api.chat(id).subscribe({
      next: (session) => this.activate(session),
      error: () => this.saveFailed.set(true),
    });
  }

  /** Puts a chat's messages and company on screen. */
  private activate(session: ChatSession): void {
    this.currentId.set(session.id);
    this.messages.set(session.messages);
    this.company.set(session.company || this.companyId() || '');
    this.editingId.set('');
  }

  /** Saves the chat on screen: its name, company and whole conversation. */
  private persist(): void {
    const id = this.currentId();
    const summary = this.sessions().find((s) => s.id === id);
    if (!summary) return;
    const messages = this.messages();
    const firstQuestion = messages.find((m) => m.role === 'user')?.text;
    const name = summary.renamed || !firstQuestion ? summary.name : sessionName(firstQuestion);
    this.sessions.update((list) => list.map((s) => (s.id === id ? { ...s, name } : s)));
    this.save({ id, name, renamed: summary.renamed, company: this.company(), messages });
  }

  /** Sends one chat to the server. The list keeps its time of last save, for the next load. */
  private save(session: ChatSession): void {
    this.api.saveChat(session).subscribe({
      next: (saved) => {
        this.saveFailed.set(false);
        this.sessions.update((list) => list.map((s) => (s.id === saved.id ? { ...s, updated_at: saved.updated_at } : s)));
      },
      error: () => this.saveFailed.set(true),
    });
  }

  /** Double-click or the pencil: the name becomes an editable box, with its text selected. */
  protected startRename(summary: ChatSummary): void {
    this.editingId.set(summary.id);
    afterNextRender(() => document.querySelector<HTMLInputElement>('.rename')?.select(), { injector: this.injector });
  }

  /** Enter or leaving the box saves the new name. An empty name keeps the old one. */
  protected finishRename(summary: ChatSummary, value: string): void {
    if (this.editingId() !== summary.id) return;   // already saved or cancelled (blur runs after Enter and Esc)
    this.editingId.set('');
    const name = value.trim().slice(0, 60);
    if (!name) return;
    this.sessions.update((list) => list.map((s) => (s.id === summary.id ? { ...s, name, renamed: true } : s)));

    if (summary.id === this.currentId()) {
      this.persist();
      return;
    }
    // Another chat: fetch its messages first, so saving the new name does not wipe them.
    this.api.chat(summary.id).subscribe((session) => this.save({ ...session, name, renamed: true }));
  }

  /** Esc: leave the name as it was. */
  protected cancelRename(): void {
    this.editingId.set('');
  }

  /** Deletes a chat after the user confirms. The chat on screen, if it goes, moves to the next one. */
  protected deleteChat(summary: ChatSummary): void {
    if (summary.id === this.currentId() && this.waiting()) return;   // an answer is still coming in for it
    if (!confirm(`Delete "${summary.name}"? This cannot be undone.`)) return;
    if (summary.updated_at === '') {   // never saved, so there is nothing on the server to delete
      this.removeLocal(summary.id);
      return;
    }
    this.api.deleteChat(summary.id).subscribe({
      next: () => this.removeLocal(summary.id),
      error: () => this.saveFailed.set(true),
    });
  }

  /** Takes a chat off the list. If it was on screen, the next saved chat opens, or a new chat if none is left. */
  private removeLocal(id: string): void {
    const wasCurrent = id === this.currentId();
    this.sessions.update((list) => list.filter((s) => s.id !== id));
    if (!wasCurrent) return;
    const next = this.sessions().find((s) => s.updated_at !== '');
    if (next) this.openSaved(next.id);
    else this.startBlank();
  }

  protected toggleList(): void {
    this.listOpen.update((v) => !v);
  }

  // --- Resize ------------------------------------------------------------------

  /** Drag the top-left corner: the window grows up and left, since it stays anchored bottom-right. */
  protected startResize(event: PointerEvent): void {
    event.preventDefault();
    const grip = event.currentTarget as HTMLElement;
    grip.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const startY = event.clientY;
    const startWidth = this.width();
    const startHeight = this.height();

    const move = (e: PointerEvent) => {
      this.width.set(clamp(startWidth + (startX - e.clientX), MIN_WIDTH, window.innerWidth - WINDOW_MARGIN));
      this.height.set(clamp(startHeight + (startY - e.clientY), MIN_HEIGHT, window.innerHeight - WINDOW_MARGIN));
    };
    const stop = () => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', stop);
      grip.removeEventListener('pointercancel', stop);
      this.saveSize();
    };
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', stop);
    grip.addEventListener('pointercancel', stop);
  }

  private saveSize(): void {
    try {
      localStorage.setItem(SIZE_KEY, JSON.stringify({ width: this.width(), height: this.height() }));
    } catch {
      // Storage blocked: the size just is not remembered.
    }
  }

  // --- Display -----------------------------------------------------------------

  /** "OFSS" -> "Oracle Financial Services Software Ltd"; "" -> "Choose a company". */
  protected companyName(code: string): string {
    return code ? (this.companies().find((c) => c.company_id === code)?.name ?? code) : 'Choose a company';
  }

  /** The answer as safe HTML: text escaped, **bold** kept, [S1] shown as a small tag with its brackets. */
  protected answerHtml(text: string): string {
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\[(S\d+(?:\s*,\s*S\d+)*)\]/g, '<span class="cite">[$1]</span>')
      .replace(/\n/g, '<br>');
  }
}

/**
 * The name for a chat: the first six words of its first question, cut to 40 characters.
 * "What were the revenue and net profit for the latest period?" -> "What were the revenue and net…"
 */
export function sessionName(question: string): string {
  const words = question.trim().split(/\s+/);
  let name = words.slice(0, 6).join(' ');
  if (name.length > 40) name = name.slice(0, 40).trimEnd();
  return name !== question.trim() ? name + '…' : name;
}

/** Reads the saved window size, or the defaults. */
function readSize(): { width: number; height: number } {
  try {
    const parsed = JSON.parse(localStorage.getItem(SIZE_KEY) ?? 'null');
    if (parsed && typeof parsed.width === 'number' && typeof parsed.height === 'number') {
      return { width: parsed.width, height: parsed.height };
    }
  } catch {
    // Not readable: use the defaults.
  }
  return { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
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
