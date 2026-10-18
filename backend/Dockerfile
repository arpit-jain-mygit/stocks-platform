# Dockerfile - builds the backend API image (Railway builds this from backend/).
#
# What ends up in the image: Python, Tesseract (OCR fallback), the packages in
# requirements.txt and the backend code. NOT in the image: .env, PDFs, caches,
# tests (see .dockerignore). Secrets come from Railway service variables.

# --- Base: small official Python image (same version as local development) -------
FROM python:3.14-slim

# --- System package: Tesseract, for pages the vision model refuses (utils/ocr.py) ---
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# --- Settings ----------------------------------------------------------------------
# PYTHONUNBUFFERED: print() output shows up in Railway logs straight away.
# PAGE_CACHE_DIR:   page + vector caches; mount a Railway volume at /data so they
#                   survive redeploys (otherwise every redeploy starts with an empty cache).
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PAGE_CACHE_DIR=/data/cache

WORKDIR /app

# --- Python packages first (this layer is reused while requirements.txt is unchanged) ---
COPY requirements.txt .
RUN pip install -r requirements.txt

# --- The backend code -----------------------------------------------------------------
COPY . .

# --- Start the API ------------------------------------------------------------------------
# Railway sets PORT. One process only: ingestion jobs are kept in memory (api/main.py),
# so several workers would not see each other's /jobs.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
