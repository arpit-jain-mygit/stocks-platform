"""
Status check for the configured vector store.

Run:  python -m utils.vectorstore                 -> what is stored (no LLM calls)
      python -m utils.vectorstore "question"      -> also searches the chunks
                                                     (1 embedding call for the question)
"""

# --- Imports -----------------------------------------------------------------
import sys

from utils.llm import QUERY, get_llm
from utils.metadata import get_metadata_store
from utils.vectorstore import get_store

store = get_store()

# 1. Which store, and how much is in it?
print(f"store: {store!r}")
for key, value in store.stats().items():
    print(f"  {key}: {value}")

# 2. Every ingested document (from the metadata store), with its live chunk count here.
records = get_metadata_store().list_filings()
print(f"\ndocuments ({len(records)}):")
for d in records:
    print(f"  [{d.get('status')}] {d.get('file_name')} | {d.get('company')} | {d.get('period')}")
    print(f"      doc_id {d['doc_id'][:12]}...  pages {d.get('pages')}  "
          f"chunks {d.get('chunks')} (stored now: {store.count_chunks(d['doc_id'])})  "
          f"ocr pages {d.get('ocr_pages')}  updated {d.get('updated_at', '')[:19]}")

# 3. Optional: search the chunks with a question.
if len(sys.argv) > 1:
    question = sys.argv[1]
    [question_vector] = get_llm("embed").embed_texts([question], QUERY)
    print(f'\nQ: "{question}"')
    for hit in store.search(question_vector, limit=5):
        p = hit.payload
        body = p["text"].split("\n\n", 1)[-1].replace("\n", " ")
        print(f"  {hit.score:.3f}  #{p['chunk_no']} {p['kind']:5} {p['file_name']} p{p['page_start']}  {body[:100]}")
