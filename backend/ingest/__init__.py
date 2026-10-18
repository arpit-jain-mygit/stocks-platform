"""
ingest - turns a results PDF into searchable chunks in the vector store.

One module per step, in the order they run (ingest/pipeline.py runs them all):

    1. ids.py         PDF bytes -> doc_id, plus fixed IDs for chunks
    2. pdf_reader.py  PDF -> pages (text layer / vision model / OCR fallback)
    3. chunker.py     pages -> chunks (clean, cut, label, table facts)
    4. embeddings.py  chunks -> vectors (cached)
    5. store.py       chunks -> vector store (Qdrant); filing record + duplicate check -> metadata store (Postgres)

Next: api/main.py (FastAPI) calls pipeline.ingest_pdf() for each upload.
"""
