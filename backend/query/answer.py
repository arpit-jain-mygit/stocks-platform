"""
answer.py - Answers a question from the ingested filings, with citations.

Steps:
  1. search()  - find the closest chunks in Qdrant (query/search.py).
  2. Number them [S1], [S2] ... and put them in the answer prompt.
  3. The answer model writes the answer using ONLY those chunks, citing [S1] etc.
  4. Return the answer plus the sources it cited (file + page), so every
     fact can be checked against the original PDF.
"""

# --- Imports -----------------------------------------------------------------
# re:      finds the [S1], [S2] citations in the answer.
# search:  question -> closest chunks (query/search.py).
# llm:     the configured answer model (utils/llm).
# prompts: ANSWER_QUESTION and the NOT_FOUND reply.
# calendar / find_company: each company's financial-year end month, by name.
import calendar
import re

from query.figures import figure_problems
from query.search import TOP_K, Hit, search
from utils import prompts
from utils.companies import find_company
from utils.llm import get_llm


# --- Build the "Sources" part of the prompt -----------------------------------------
def format_sources(hits: list[Hit]) -> str:
    """
    Numbers each chunk so the model can cite it:
        [S1] Videocon-Financial_Results_Dec-24.pdf, page 11
        [S2] statements.xlsx, sheet 'Income Statements', rows 2-61
        Videocon Industries Ltd | Q3 FY25 | ... (chunk text)
    """
    return "\n\n".join(
        f"[S{n}] {hit.file_name}, {hit.citation}\n{hit.text}"
        for n, hit in enumerate(hits, start=1)
    )


# --- Build the "Companies" part of the prompt -----------------------------------------
def company_notes(hits: list[Hit]) -> str:
    """
    One line per company in the sources, with its financial-year end, e.g.
        - OFSS (Oracle Financial Services Software Ltd): financial year ends in March
    Periods mean different dates for different companies, so the model needs this.
    """
    lines = []
    for company_id in dict.fromkeys(hit.company_id for hit in hits if hit.company_id):   # unique, in order
        found = find_company(company_id)
        if found:
            lines.append(f"- {found.company_id} ({found.name}): financial year ends in "
                         f"{calendar.month_name[found.fy_end_month]}")
    return "\n".join(lines) or "- (not known)"


# A source list the model writes at the end ("* S2 statements.xlsx, sheet ...") duplicates the
# sources the app already shows, so it is removed. Only lines at the END are removed.
SOURCE_LINE = re.compile(
    r"^\s*(?:[*-]\s*)?S\d+\s+\S+.*(?:\.(?:pdf|xlsx|csv|pptx|docx|txt|md)\b|,\s*(?:page|sheet|rows)\b)",
    re.IGNORECASE)


# A citation written as a bare S2 (not in brackets). Not after a letter or "[", not before "]" or a letter.
BARE_CITATION = re.compile(r"(?<![\w\[])S(\d+)(?![\w\]])")


def clean_reply(reply: str) -> str:
    """
    Tidies the model's answer:
      - removes a trailing list of sources (one line per source)
      - turns a bare citation "S2" into the bracketed "[S2]" the chat shows as a tag
    """
    lines = reply.rstrip().split("\n")
    while lines and (not lines[-1].strip() or SOURCE_LINE.match(lines[-1])):
        lines.pop()
    return BARE_CITATION.sub(r"[S\1]", "\n".join(lines)).strip()


# --- Main entry point ------------------------------------------------------------
# Comparison questions ("change", "compared with", "growth") need the prior-period figures too,
# which are often in other sheets or slides. They get at least this many sources.
COMPARISON_TOP_K = 12
COMPARISON_WORDS = re.compile(
    r"\b(compare|compared|comparison|change|changed|growth|grew|grow|increase|increased|decrease|decreased|"
    r"versus|vs|year on year|quarter on quarter|same period|previous|prior)\b", re.IGNORECASE)


def wants_comparison(question: str) -> bool:
    """True for questions that compare with an earlier period."""
    return bool(COMPARISON_WORDS.search(question))


def answer(question: str, company: str | None = None, period: str | None = None,
           doc_type: str | None = None, top_k: int = TOP_K) -> dict:
    """
    Returns {"answer": str, "sources": [...], "unverified_figures": [...]}.
    sources lists only the chunks the answer actually cites, each with
    file, pages, section, kind and search score.
    unverified_figures lists figures in the answer that are not in the sources, after one
    rewrite. Empty = every figure was found in the sources.
    """
    if wants_comparison(question):
        top_k = max(top_k, COMPARISON_TOP_K)
    hits = search(question, company=company, period=period, doc_type=doc_type, top_k=top_k)
    if not hits:                                   # nothing stored (or filters too strict)
        return {"answer": prompts.NOT_FOUND, "sources": [], "unverified_figures": []}

    texts = [hit.text for hit in hits]
    prompt = prompts.ANSWER_QUESTION.format(question=question, companies=company_notes(hits),
                                            sources=format_sources(hits))
    reply = clean_reply(get_llm("answer").generate_text(prompt))

    # Figures not in the sources (or badly formatted): ask once for a rewrite, then report what is left.
    problems = figure_problems(reply, texts)
    if problems:
        print(f"figures not verified: {problems} - asking for one rewrite")
        rewrite = (prompt + "\n\nYour previous answer used figures that are not printed in the sources "
                   f"or are badly formatted: {', '.join(problems)}. Rewrite the answer. Quote only figures "
                   "printed in the sources, formatted with standard separators (for example 77.7 billion "
                   "or 77,673 million).")
        reply = clean_reply(get_llm("answer").generate_text(rewrite))
        problems = figure_problems(reply, texts)

    # Keep only the sources the answer refers to, in the order they were found.
    # Handles "[S1]" as well as grouped citations like "[S1, S4]".
    cited = {int(n) for n in re.findall(r"\bS(\d+)\b", reply)}      # [S2], [S2, S4] and a bare S2 all count
    sources = [
        {
            "ref": f"S{n}",
            "file_name": hit.file_name,
            "pages": "" if hit.location else hit.pages,
            "location": hit.location,
            "citation": hit.citation,
            "section": hit.section,
            "kind": hit.kind,
            "score": round(hit.score, 3),
            "doc_id": hit.doc_id,
            "company_id": hit.company_id,
        }
        for n, hit in enumerate(hits, start=1) if n in cited
    ]
    return {"answer": reply, "sources": sources, "unverified_figures": problems}


# --- Quick manual test -------------------------------------------------------
# Run:  python -m query.answer "your question" ["company"]
if __name__ == "__main__":
    import sys

    question = sys.argv[1]
    company = sys.argv[2] if len(sys.argv) > 2 else None
    result = answer(question, company=company)

    print(f"Q: {question}\n")
    print(result["answer"])
    print(f"\nSources ({get_llm('answer').model}):")
    for s in result["sources"]:
        print(f"  [{s['ref']}] {s['file_name']}, page {s['pages']} | {s['kind']} | {s['section']} | score {s['score']}")
