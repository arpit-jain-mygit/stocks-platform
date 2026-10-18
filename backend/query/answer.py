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
import re

from query.search import TOP_K, Hit, search
from utils import prompts
from utils.llm import get_llm


# --- Build the "Sources" part of the prompt -----------------------------------------
def format_sources(hits: list[Hit]) -> str:
    """
    Numbers each chunk so the model can cite it:
        [S1] Videocon-Financial_Results_Dec-24.pdf, page 11
        Videocon Industries Ltd | Q3 FY25 | ... (chunk text)
    """
    return "\n\n".join(
        f"[S{n}] {hit.file_name}, page {hit.pages}\n{hit.text}"
        for n, hit in enumerate(hits, start=1)
    )


# --- Main entry point ------------------------------------------------------------
def answer(question: str, company: str | None = None, period: str | None = None,
           doc_type: str | None = None, top_k: int = TOP_K) -> dict:
    """
    Returns {"answer": str, "sources": [...]}.
    sources lists only the chunks the answer actually cites, each with
    file, pages, section, kind and search score.
    """
    hits = search(question, company=company, period=period, doc_type=doc_type, top_k=top_k)
    if not hits:                                   # nothing stored (or filters too strict)
        return {"answer": prompts.NOT_FOUND, "sources": []}

    prompt = prompts.ANSWER_QUESTION.format(question=question, sources=format_sources(hits))
    reply = get_llm("answer").generate_text(prompt)

    # Keep only the sources the answer refers to, in the order they were found.
    # Handles "[S1]" as well as grouped citations like "[S1, S4]".
    cited = {int(n) for group in re.findall(r"\[(S[^\]]*)\]", reply) for n in re.findall(r"S(\d+)", group)}
    sources = [
        {
            "ref": f"S{n}",
            "file_name": hit.file_name,
            "pages": hit.pages,
            "section": hit.section,
            "kind": hit.kind,
            "score": round(hit.score, 3),
            "doc_id": hit.doc_id,
            "company_id": hit.company_id,
        }
        for n, hit in enumerate(hits, start=1) if n in cited
    ]
    return {"answer": reply, "sources": sources}


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
