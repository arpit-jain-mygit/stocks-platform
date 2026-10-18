# UX – To do

Ideas to make stocks-insights.ai friendlier and more inviting. Nothing here is built yet.
**Top 3 to start with:** streaming answers (1), clickable citations (2), hero ask box (8).

Related: [features.md](features.md) (roadmap) · [README.md](README.md) (how to run)

---

## Quick wins (small changes, big feel)

- [ ] **1. Streaming answers** – the answer appears word by word instead of after "Thinking…" (same as "Streaming answer response" in features.md).
- [ ] **2. Clickable citations** – tapping `[S1]` highlights its source line; later opens the PDF at that page. The biggest trust signal.
- [ ] **3. Copy button** on each answer (with its sources), for pasting into notes.
- [ ] **4. 👍 / 👎 on answers** – one-click quality signal; thumbs-down answers become new eval cases.
- [ ] **5. "Ask about this company"** button in the details panel – opens the chat with that company already picked.
- [ ] **6. Loading skeletons** – grey placeholder cards instead of "Loading…".
- [ ] **7. Freshness on cards** – e.g. "Latest: FY26 annual report · added 17 Oct", so users know what they can ask about.

## Make it catchy

- [ ] **8. Hero ask box** – on first visit: a big "Ask any filing a question…" box, the motto under it, suggestion chips right there. The chat becomes the front door, not a corner button.
- [ ] **9. Logo and brand colour** for stocks-insights.ai (e.g. a magnifier over a document) – header, browser-tab icon, link previews when shared.
- [ ] **10. Key-figures strip per company** – revenue, net profit, EPS, dividend from the latest filing, each with its source page. Pre-compute once at ingest to keep it cheap.
- [ ] **11. Answer card layout** – headline figure big ("₹303.54 EPS"), one line of context, then sources.
- [ ] **12. Friendlier empty states** – e.g. "Upload a filing to start asking questions" instead of "No companies yet".

## Helpful for real research

- [ ] **13. Follow-up questions** – "and last year?" works; send earlier turns with each question (also in features.md).
- [ ] **14. Compare mode** – pick two companies, "Compare EPS" answered side by side with sources for each.
- [ ] **15. Saved questions / history** per user (after Google login) – "My research on OFSS".
- [ ] **16. Export** a conversation to PDF / Markdown, citations included.
- [ ] **17. "What's new" badge** on a company card when a new filing is ingested, e.g. "New: Q3 FY26 results".

## Polish and trust

- [ ] **18. Keyboard shortcuts** – `/` opens the chat, arrow keys move between companies.
- [ ] **19. Dark-mode toggle** – the page already follows the device setting; add a manual switch.
- [ ] **20. Clearer "not found"** – "Not in the ingested filings. Closest: EPS on page 91" with a link, instead of a bare refusal.
- [ ] **21. "How it works" strip** – Upload filing → Ask → Get cited answer. Explains the motto and builds trust.
