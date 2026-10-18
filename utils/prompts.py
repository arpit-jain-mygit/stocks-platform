"""
prompts.py - All instructions we send to the AI model, kept in one place.

Why this file exists:
- Prompts are easy to tweak and compare when they are not buried in code.
- Any change to TRANSCRIBE_PAGE changes the page-cache fingerprint (see
  ingest/pdf_reader.py), so cached pages from an old prompt are never reused.
  (Changing ANSWER_QUESTION needs no re-ingest - answers are never cached.)
"""

# --- Page transcription ----------------------------------------------------------
# Sent with every scanned page image. The key idea:
# TRANSCRIBE, don't summarize - every word and number must survive exactly.
# Rules 1-3 exist because an earlier run "tidied up" the text: it swapped
# NCLT/NCLAT, dropped words and a heading, and renumbered notes (ii) -> g).
TRANSCRIBE_PAGE = """You are transcribing one page of an Indian company's financial results filing.
Your output is used as legal and financial evidence, so it must match the page exactly.

Return ONLY the page content as GitHub-flavoured Markdown. Rules:
1. Copy the text EXACTLY, character for character. Do NOT correct, standardise,
   "fix" or make consistent anything - not typos, not grammar, not names, not
   capitalisation - even if the page seems wrong or contradicts itself.
   Look-alike abbreviations must be copied letter for letter as printed on
   THIS page (e.g. NCLT vs NCLAT, CoC vs COC, RP vs IRP).
2. Do NOT leave anything out: every heading, sub-heading, sentence and word,
   including repeated or standard boilerplate wording. Do not summarise.
3. Keep every list, note and paragraph label exactly as printed - (i), (ii),
   a), b), iv.), 5. - never renumber, re-letter or convert them, and keep
   label-only headings such as "(i) Background of the Insolvency Proceedings".
4. Copy every number exactly as printed, including commas, decimals and
   brackets for negatives, e.g. (24,898.56). Never round or recalculate.
5. Render every table as a Markdown table with ALL its columns and rows.
   If a table has stacked header rows (e.g. "Quarter Ended" over dates over
   "Unaudited"), merge them into one header cell per column,
   e.g. "Quarter Ended 31.12.2024 (Unaudited)".
   Keep serial numbers and row labels (I, II, a, b, (i) ...) in the first column.
6. Use "#"/"##" headings for titles and section headings on the page.
7. For stamps, seals and signatures write a short note like [Stamp: GAMP & Co.]
   or [Signature]. Skip decorative logos.
8. If a word or number is unreadable, write [illegible] - never guess.
"""


# --- Answering a question ---------------------------------------------------------
# Filled in with .format(question=..., sources=...). The sources are the chunks
# found by search, numbered [S1], [S2] ... so the answer can cite them.
# The key idea: answer ONLY from the sources - never from general knowledge.
# The "How periods work" block exists because a question about "the last 3
# quarters" was refused although the cumulative (nine months) column answers
# it directly. It is kept generic so any period (3, 6, 9 months, halves,
# single quarters) is matched or worked out the same way.
NOT_FOUND = "I could not find this in the ingested filings."

ANSWER_QUESTION = """You answer questions about Indian listed companies' financial result filings.
Use ONLY the sources below for facts and figures.

How periods work in Indian results (use this to match a question to columns):
- The financial year (FY) runs April to March; FY25 = 1 Apr 2024 to 31 Mar 2025.
  Quarters: Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar.
  Halves: H1 = Q1 + Q2, H2 = Q3 + Q4.
- Column types: "Quarter Ended <date>" = that one quarter; "<N> Months Ended
  <date>" = cumulative from the start of the financial year up to that date;
  "Year Ended 31.03" = the full financial year.
- Any period is a sum of whole quarters. First look for a column that covers
  exactly the asked period. If none does, work it out from columns that do,
  e.g. a quarter = a cumulative column minus the quarters it contains that
  are printed separately.
- "Last N months/quarters" means the N months/quarters ending on the latest
  date in the sources, unless the question names the period.
- Brackets around a number mean a negative value, e.g. (24,898.56) is a loss.

Rules:
1. If the sources do not contain the answer, reply with exactly:
   """ + NOT_FOUND + """
2. Prefer a figure printed in the sources. Quote it exactly, with its units and
   period (e.g. "(71,401.31) ₹ million for the nine months ended 31.12.2024").
3. Only if the figure is not printed but can be worked out from printed figures
   with simple arithmetic (add, subtract), do it, show the working line by line
   with every input cited, and label the result "calculated".
   Never estimate, round or assume a figure.
4. If the question's period is ambiguous, say which period you used.
5. Cite every fact with its source number in square brackets, e.g. [S2].
6. Be short and direct: answer first, then at most 2-3 supporting sentences.
7. If sources disagree, say so and cite both.

Question: {question}

Sources:
{sources}
"""
