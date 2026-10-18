"""
conftest.py - Shared setup for every test (pytest loads this file first).

What it guarantees:
  1. NO real outside calls: Gemini, Qdrant and Postgres are replaced by the
     in-memory fakes in fakes.py. If any code still tries to build a real
     client, it fails loudly ("tripwire") instead of calling the service.
  2. NO real data touched: caches go to a temporary folder, never data/cache.
  3. Every test starts clean: fresh fakes and an empty job list.

Fixtures (ask for them by name in a test function's arguments):
  llm      dict of the three fake models: llm["vision"], llm["answer"], llm["embed"]
  vectors  the fake vector store (FakeVectorStore)
  meta     the fake metadata store (FakeMetadataStore)
  client   a FastAPI TestClient for the real app
  make_pdf builds a small 3-page PDF (prose page, table page, image-only page)
  ingest   uploads a PDF through POST /ingest and returns the finished job
"""

# --- Settings for tests: set BEFORE any app code is imported --------------------------
# load_dotenv() never overrides a variable that is already set, so these win
# over backend/.env. Real connection settings are blanked on purpose.
import os
import sys
import tempfile
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))                      # so "import api", "import ingest" work

APP_KEY, ADMIN_KEY = "test-app-key", "test-admin-key"
os.environ.update({
    "APP_API_KEY": APP_KEY,
    "ADMIN_API_KEY": ADMIN_KEY,
    "ENABLE_RISKY_DELETE_APIS": "true",               # mount the guarded routes so they can be tested
    "ENABLE_BACKUP_APIS": "true",
    "TABLE_PAGES_TO_VISION": "true",
    "PAGE_CACHE_DIR": tempfile.mkdtemp(prefix="stocks-rag-tests-"),
    "EMBED_MODEL": "fake-embed", "EMBED_DIM": "768",
    "VISION_MODEL": "fake-vision", "ANSWER_MODEL": "fake-answer",
    "EMBED_PAUSE_SECONDS": "0",
    # Blank real connection details: nothing can reach a real service.
    "GEMINI_API_KEY": "", "VISION_API_KEY": "", "ANSWER_API_KEY": "", "EMBED_API_KEY": "",
    "QDRANT_URL": "", "QDRANT_API_KEY": "", "DATABASE_URL": "",
})

# --- Imports (after the settings above) -----------------------------------------------------
import pymupdf
import pytest
from fastapi.testclient import TestClient

import api.main
from tests.fakes import FakeLLM, FakeMetadataStore, FakeVectorStore
from utils.llm import factory as llm_factory
from utils.metadata import factory as metadata_factory
from utils.vectorstore import factory as vector_factory


# --- Tripwires: building a REAL client is an error during tests -----------------------------
def _tripwire(name):
    def refuse(*args, **kwargs):
        raise AssertionError(f"Test tried to create a real {name} client - use the fakes")
    return refuse


llm_factory.PROVIDERS["gemini"] = _tripwire("Gemini")
vector_factory.PROVIDERS["qdrant"] = _tripwire("Qdrant")
metadata_factory.PROVIDERS["postgres"] = _tripwire("Postgres")


# --- Fresh fakes for every test -----------------------------------------------------------------
@pytest.fixture(autouse=True)
def fakes():
    """Puts new fakes into the factories' shared slots (get_llm / get_store / get_metadata_store)."""
    models = {"vision": FakeLLM("fake-vision"), "answer": FakeLLM("fake-answer"),
              "embed": FakeLLM("fake-embed", embed_dim=768)}
    llm_factory._clients.clear()
    llm_factory._clients.update(models)
    vector_factory._store = FakeVectorStore(dim=768)
    metadata_factory._store = FakeMetadataStore()
    api.main.jobs.clear()
    yield {"llm": models, "vectors": vector_factory._store, "meta": metadata_factory._store}
    llm_factory._clients.clear()
    vector_factory._store = metadata_factory._store = None


@pytest.fixture
def llm(fakes):
    return fakes["llm"]


@pytest.fixture
def vectors(fakes):
    return fakes["vectors"]


@pytest.fixture
def meta(fakes):
    return fakes["meta"]


@pytest.fixture
def client():
    """The real app. Every request carries the app key unless a test overrides headers."""
    with TestClient(api.main.app, headers={"X-API-Key": APP_KEY}) as test_client:
        yield test_client


# --- Test PDFs -------------------------------------------------------------------------------
PROSE = ("The Board of Directors reviewed the results for the quarter. Revenue grew because of new "
         "contracts with banking customers, while finance costs stayed close to last quarter. "
         "The company continues to invest in product development and in training its employees, "
         "and expects demand from financial institutions to remain steady in the coming year.")


@pytest.fixture
def make_pdf():
    """
    make_pdf() -> PDF bytes with 3 pages:
      1. typed prose (read from the text layer, no model)
      2. typed table, mostly figures (goes to the vision model - TABLE_PAGES_TO_VISION)
      3. image only, no text (a "scanned" page - goes to the vision model)
    Each call adds a random tag, so every PDF has a new doc_id unless `tag` is given.
    """
    def build(tag: str | None = None) -> bytes:
        doc = pymupdf.open()
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800),
                                      f"Notes to the results ({tag or uuid.uuid4().hex})\n\n{PROSE}", fontsize=11)
        rows = ["Particulars", "Q3 FY25", "Q2 FY25"]
        for label, a, b in [("Revenue from operations", "1,234.5", "1,100.0"), ("Other income", "12.0", "10.5"),
                            ("Finance costs", "56.7", "55.1"), ("Depreciation", "20.0", "19.8"),
                            ("Net profit", "300.2", "280.9"), ("Basic EPS", "3.5", "3.2")]:
            rows += [label, a, b]
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), "\n".join(rows), fontsize=10)
        doc.new_page().draw_rect(pymupdf.Rect(100, 100, 300, 200), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
        return doc.tobytes()
    return build


# --- Upload helper ------------------------------------------------------------------------------
@pytest.fixture
def ingest(client):
    """
    ingest(pdf_bytes, company="VIDEOIND", period="Q3 FY25", **form) -> the /ingest reply,
    plus "job" = the finished job (TestClient runs background tasks before returning).
    """
    def upload(pdf: bytes, company: str = "VIDEOIND", period: str = "Q3 FY25", name: str = "results.pdf", **form):
        reply = client.post("/ingest", files={"file": (name, pdf, "application/pdf")},
                            data={"company": company, "period": period, **{k: str(v).lower() if isinstance(v, bool) else v
                                                                            for k, v in form.items()}})
        body = reply.json()
        if reply.status_code == 200 and body.get("job_id"):
            body["job"] = client.get(f"/jobs/{body['job_id']}").json()
        return reply.status_code, body
    return upload
