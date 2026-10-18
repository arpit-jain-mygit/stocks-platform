"""
embeddings.py - Turns chunks into vectors (lists of numbers that capture meaning).

Steps:
  1. Look up each chunk's text in the vector cache (free).
  2. Send only the missing ones to the configured embedding model (get_llm("embed")),
     EMBED_BATCH_SIZE chunks at a time, pausing EMBED_PAUSE_SECONDS between batches
     so free-tier per-minute limits aren't hit.
  3. Save each batch's vectors to the cache AS SOON AS it returns (checkpoint):
     if batch 9 fails, batches 1-8 are kept and a re-run only embeds from 9 on.
Returns one vector per chunk, in the same order as the chunks.
"""

# --- Imports -----------------------------------------------------------------
# os / time:     batch settings from .env, pause between batches.
# Chunk:         one card from chunker.py.
# llm:           the configured embedding model (utils/llm).
# vector_cache:  disk cache for vectors (utils/vector_cache.py).
import os
import time

from ingest.chunker import Chunk
from utils import vector_cache
from utils.llm import DOCUMENT, QUERY, get_llm

# --- Settings ----------------------------------------------------------------
# Smaller batches + a pause = gentler on free-tier quotas; each finished batch is saved.
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "20"))
EMBED_PAUSE_SECONDS = float(os.getenv("EMBED_PAUSE_SECONDS", "2"))


# --- Main entry point ------------------------------------------------------------------
def embed_chunks(chunks: list[Chunk]) -> list[list[float]]:
    """Returns one vector per chunk. Only uncached chunks are sent to the model."""
    embedder = get_llm("embed")
    model, dim, task = embedder.model, embedder.embed_dim, DOCUMENT
    texts = [chunk.text for chunk in chunks]

    # 1. Cache first.
    vectors = [vector_cache.load(model, dim, task, text) for text in texts]
    missing = [i for i, vector in enumerate(vectors) if vector is None]
    print(f"embeddings: {len(texts) - len(missing)} from cache, {len(missing)} to embed ({model}, {dim} dims)")

    # 2. Embed the rest batch by batch; 3. save each batch straight away.
    batches = [missing[start:start + EMBED_BATCH_SIZE] for start in range(0, len(missing), EMBED_BATCH_SIZE)]
    for number, batch in enumerate(batches, start=1):
        if number > 1 and EMBED_PAUSE_SECONDS:
            time.sleep(EMBED_PAUSE_SECONDS)
        new_vectors = embedder.embed_texts([texts[i] for i in batch], DOCUMENT)
        for i, vector in zip(batch, new_vectors):
            vector_cache.save(model, dim, task, texts[i], vector)
            vectors[i] = vector
        print(f"  batch {number}/{len(batches)}: {len(batch)} embedded and saved")

    return vectors


# --- Quick manual test -------------------------------------------------------
# Run:  python -m ingest.embeddings data/<file>.pdf VIDEOIND "Q3 FY25" ["your question"]
#       company + period are validated like the pipeline (same chunk labels).
# Reads + chunks the PDF (from cache), embeds the chunks, then does a tiny
# in-memory search: embeds the question and prints the 5 closest chunks.
# (Qdrant will do this search for real later - this just shows the idea.)
if __name__ == "__main__":
    import math
    import sys
    from pathlib import Path

    from ingest.chunker import chunk_pages
    from ingest.pdf_reader import read_pdf
    from ingest.pipeline import describe

    pdf_path = Path(sys.argv[1])
    meta = describe(sys.argv[2], sys.argv[3])
    question = sys.argv[4] if len(sys.argv) > 4 else "How much interest did the company pay this quarter?"

    chunks = chunk_pages(read_pdf(pdf_path.read_bytes()), meta["company"], meta["period"])
    vectors = embed_chunks(chunks)
    print(f"{len(vectors)} vectors of {len(vectors[0])} numbers, e.g. {[round(x, 3) for x in vectors[0][:4]]} ...")

    # Cosine similarity: 1.0 = same meaning, 0 = unrelated.
    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))

    [question_vector] = get_llm("embed").embed_texts([question], QUERY)
    ranked = sorted(zip(chunks, vectors), key=lambda cv: cosine(question_vector, cv[1]), reverse=True)

    # Show the top 5: full text for facts and prose (so the actual values are
    # visible), first 400 characters for big tables.
    print(f'\nQ: "{question}"\nTop 5 chunks:')
    for chunk, vector in ranked[:5]:
        body = chunk.text.split("\n\n", 1)[1].replace("\n", " ")
        if chunk.kind == "table" and len(body) > 400:
            body = body[:400] + " ..."
        print(f"\n  {cosine(question_vector, vector):.3f}  #{chunk.chunk_no} {chunk.kind} "
              f"(pages {chunk.page_start}-{chunk.page_end})")
        for part in body.split("; "):         # one column per line for facts
            print(f"      {part}")
