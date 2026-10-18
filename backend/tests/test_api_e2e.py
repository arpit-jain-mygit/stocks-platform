"""
test_api_e2e.py - End-to-end tests of the backend API: the safety net for refactoring.

Each test goes through the real HTTP API (FastAPI TestClient) and the real
pipeline, chunker, search and answer code. Only Gemini, Qdrant and Postgres
are fakes (tests/fakes.py), so the tests are free, take seconds and never
touch real data. If a refactor breaks a flow, one of these fails.

Run (from backend/):   python -m pytest
"""

# --- Imports -----------------------------------------------------------------
import gzip
import importlib
import json
import os

import pytest
from fastapi.testclient import TestClient

import api.main
from tests.conftest import ADMIN_KEY, APP_KEY
from tests.fakes import FAKE_ANSWER
from utils import prompts

ADMIN = {"X-API-Key": APP_KEY, "X-Admin-Key": ADMIN_KEY}


# =====================================================================================
# 1. Server basics and security
# =====================================================================================
def test_health_needs_no_key(client):
    assert client.get("/health", headers={"X-API-Key": ""}).json() == {"status": "ok"}


@pytest.mark.parametrize("method, path", [
    ("get", "/companies"), ("get", "/doc-types"), ("get", "/documents"), ("get", "/documents/abc"),
    ("get", "/jobs/abc"), ("post", "/ask"), ("post", "/ingest"),
])
def test_every_endpoint_but_health_needs_the_api_key(client, method, path):
    for headers in ({"X-API-Key": ""}, {"X-API-Key": "wrong"}):
        assert getattr(client, method)(path, headers=headers).status_code == 401


def test_companies_and_doc_types(client):
    companies = {c["company_id"]: c for c in client.get("/companies").json()}
    assert set(companies) == {"VIDEOIND", "OFSS"}
    assert "Videocon" in companies["VIDEOIND"]["aliases"]
    types = client.get("/doc-types").json()
    assert types["default"] == "quarterly_results"
    assert "annual_report" in {t["code"] for t in types["doc_types"]}


def test_companies_ingested_filter_lists_only_companies_with_data(client, make_pdf, ingest):
    assert client.get("/companies", params={"ingested": "true"}).json() == []      # nothing ingested yet
    ingest(make_pdf())                                                             # Videocon only
    assert [c["company_id"] for c in client.get("/companies", params={"ingested": "true"}).json()] == ["VIDEOIND"]
    assert len(client.get("/companies").json()) == 2                               # default: every company


# =====================================================================================
# 2. Ingestion
# =====================================================================================
@pytest.mark.parametrize("form, file, expected", [
    ({"company": "NOPE", "period": "Q3 FY25"}, b"%PDF-1.4", "Unknown company"),
    ({"company": "VIDEOIND", "period": "someday"}, b"%PDF-1.4", ""),
    ({"company": "VIDEOIND", "period": "Q3 FY25", "doc_type": "blog post"}, b"%PDF-1.4", "Unknown doc_type"),
    ({"company": "VIDEOIND", "period": "Q3 FY25"}, b"hello, not a pdf", "not a PDF"),
])
def test_ingest_rejects_bad_input_before_any_work(client, llm, form, file, expected):
    reply = client.post("/ingest", files={"file": ("x.pdf", file, "application/pdf")}, data=form)
    assert reply.status_code == 400 and expected in reply.json()["detail"]
    assert all(n == 0 for model in llm.values() for n in model.calls.values())    # no model call


def test_ingest_stores_chunks_and_filing(client, llm, vectors, make_pdf, ingest):
    status, body = ingest(make_pdf(), company="Videocon", period="Q3 FY25", name="q3.pdf")   # alias works
    assert status == 200 and body["status"] == "queued"
    job = body["job"]
    assert job["status"] == "complete", job.get("error")
    assert job["company_id"] == "VIDEOIND" and job["doc_type"] == "quarterly_results"

    # Table page + image-only page went to vision; the prose page did not.
    assert llm["vision"].calls["describe_image"] == 2
    result = job["result"]
    assert result["pages"] == 3 and result["chunks"] == vectors.count_chunks(body["doc_id"]) > 0

    # Every chunk carries the fields search and citations depend on.
    payloads = [p.payload for p in vectors.points.values()]
    for p in payloads:
        assert {"text", "doc_id", "file_name", "page_start", "page_end", "company_id", "fiscal_year",
                "quarter", "doc_type", "section", "kind", "source", "chunk_no"} <= p.keys()
        assert p["company_id"] == "VIDEOIND" and p["fiscal_year"] == 2025 and p["quarter"] == 3
    kinds = {p["kind"] for p in payloads}
    assert "fact" in kinds, "table rows from the vision page should become fact cards"
    assert any("1,234.5" in p["text"] and "Revenue from operations" in p["text"] for p in payloads)

    # The filing record is visible through the API.
    record = client.get(f"/documents/{body['doc_id']}").json()
    assert record["status"] == "complete" and record["file_name"] == "q3.pdf"
    assert [d["doc_id"] for d in client.get("/documents", params={"company": "VIDEOIND"}).json()] == [body["doc_id"]]
    assert client.get("/documents", params={"company": "OFSS"}).json() == []
    assert client.get("/documents/unknown").status_code == 404


def test_same_pdf_is_skipped_and_force_reingests_without_duplicates(client, llm, vectors, make_pdf, ingest):
    pdf = make_pdf()
    _, first = ingest(pdf)
    chunks = vectors.count_chunks(first["doc_id"])

    _, again = ingest(pdf)                                   # same bytes -> instant skip, no job
    assert again["status"] == "skipped" and "job_id" not in again

    embeds_before = llm["embed"].calls["embed_texts"]
    _, forced = ingest(pdf, force=True)
    assert forced["job"]["status"] == "complete"
    assert vectors.count_chunks(first["doc_id"]) == chunks  # replaced, not doubled
    assert llm["vision"].calls["describe_image"] == 2       # pages came from the page cache
    assert llm["embed"].calls["embed_texts"] == embeds_before   # vectors came from the vector cache


def test_pipeline_itself_skips_duplicates(make_pdf, llm):
    """The command-line path (python -m ingest.pipeline) has its own duplicate check."""
    from ingest.pipeline import ingest_pdf
    pdf = make_pdf()
    assert ingest_pdf(pdf, "q3.pdf", "VIDEOIND", "Q3 FY25")["status"] == "complete"
    embeds = llm["embed"].calls["embed_texts"]
    assert ingest_pdf(pdf, "q3.pdf", "VIDEOIND", "Q3 FY25")["status"] == "skipped"
    assert llm["embed"].calls["embed_texts"] == embeds        # no work done the second time


def test_new_version_supersedes_old_filing(client, make_pdf, ingest):
    _, old = ingest(make_pdf())
    _, new = ingest(make_pdf())                              # different PDF, same company + period + type
    assert client.get(f"/documents/{old['doc_id']}").json()["status"] == "superseded"
    assert client.get(f"/documents/{new['doc_id']}").json()["status"] == "complete"


def test_unknown_job_is_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


# =====================================================================================
# 3. Questions
# =====================================================================================
def test_ask_answers_from_ingested_chunks_with_sources(client, llm, make_pdf, ingest):
    _, body = ingest(make_pdf(), name="q3.pdf")
    reply = client.post("/ask", json={"question": "What was revenue from operations?", "company": "VIDEOIND",
                                      "period": "Q3 FY25"})
    assert reply.status_code == 200
    result = reply.json()
    assert result["answer"] == FAKE_ANSWER
    assert [s["ref"] for s in result["sources"]] == ["S1"]                 # only cited sources are returned
    source = result["sources"][0]
    assert source["file_name"] == "q3.pdf" and source["doc_id"] == body["doc_id"] and source["company_id"] == "VIDEOIND"

    # The answer model saw the question and the retrieved figure.
    [prompt] = llm["answer"].prompts
    assert "What was revenue from operations?" in prompt and "1,234.5" in prompt


def test_ask_with_no_matching_data_says_not_found_without_answer_call(client, llm, make_pdf, ingest):
    ingest(make_pdf())                                       # Videocon data only
    result = client.post("/ask", json={"question": "What was revenue?", "company": "OFSS"}).json()
    assert result == {"answer": prompts.NOT_FOUND, "sources": []}
    assert llm["answer"].calls["generate_text"] == 0


@pytest.mark.parametrize("body, status", [
    ({"question": "Revenue?", "company": "NOPE"}, 400),
    ({"question": "Revenue?", "period": "someday"}, 400),
    ({"question": "Revenue?", "doc_type": "blog post"}, 400),
    ({"question": "a"}, 422),                                # too short
    ({"question": "Revenue?", "top_k": 99}, 422),           # above the limit
])
def test_ask_rejects_bad_input_before_any_model_call(client, llm, body, status):
    assert client.post("/ask", json=body).status_code == status
    assert llm["embed"].calls["embed_texts"] == 0 and llm["answer"].calls["generate_text"] == 0


# =====================================================================================
# 4. Risky delete APIs (guarded, cascading)
# =====================================================================================
def test_delete_apis_need_the_admin_key(client):
    for headers in ({"X-API-Key": APP_KEY}, {"X-API-Key": APP_KEY, "X-Admin-Key": "wrong"}):
        assert client.post("/risky-delete/company", json={"company": "OFSS"}, headers=headers).status_code == 403


def test_delete_filing_dry_run_confirm_and_cascade(client, vectors, make_pdf, ingest):
    _, body = ingest(make_pdf())
    doc_id = body["doc_id"]
    chunks = vectors.count_chunks(doc_id)

    dry = client.post("/risky-delete/filing", json={"doc_id": doc_id}, headers=ADMIN).json()
    assert dry["dry_run"] is True and dry["chunks"] == chunks
    assert vectors.count_chunks(doc_id) == chunks            # dry run changed nothing

    no_confirm = client.post("/risky-delete/filing", json={"doc_id": doc_id, "dry_run": False}, headers=ADMIN)
    assert no_confirm.status_code == 400 and vectors.count_chunks(doc_id) == chunks

    done = client.post("/risky-delete/filing", json={"doc_id": doc_id, "dry_run": False, "confirm": doc_id},
                       headers=ADMIN)
    assert done.status_code == 200
    assert vectors.count_chunks(doc_id) == 0                 # chunks gone ...
    assert client.get(f"/documents/{doc_id}").status_code == 404   # ... and the record


def test_delete_company_filings_keeps_the_company(client, vectors, make_pdf, ingest):
    ingest(make_pdf())
    reply = client.post("/risky-delete/company-filings",
                        json={"company": "VIDEOIND", "dry_run": False, "confirm": "VIDEOIND"}, headers=ADMIN)
    assert reply.status_code == 200
    assert vectors.count_where(company_id="VIDEOIND") == 0 and client.get("/documents").json() == []
    assert "VIDEOIND" in {c["company_id"] for c in client.get("/companies").json()}


def test_delete_company_removes_every_trace(client, vectors, make_pdf, ingest):
    ingest(make_pdf())
    ingest(make_pdf(), company="OFSS", period="FY26", doc_type="annual_report")
    reply = client.post("/risky-delete/company",
                        json={"company": "Videocon", "dry_run": False, "confirm": "VIDEOIND"}, headers=ADMIN)
    assert reply.status_code == 200
    assert vectors.count_where(company_id="VIDEOIND") == 0
    assert all(d["company_id"] != "VIDEOIND" for d in client.get("/documents").json())
    assert "VIDEOIND" not in {c["company_id"] for c in client.get("/companies").json()}
    assert vectors.count_where(company_id="OFSS") > 0        # the other company is untouched


# =====================================================================================
# 5. Backup and restore
# =====================================================================================
def test_backup_then_restore_brings_everything_back(client, vectors, make_pdf, ingest):
    _, body = ingest(make_pdf())
    chunks = vectors.count_where()

    backup = client.post("/backup/create", headers=ADMIN)
    assert backup.status_code == 200
    data = json.loads(gzip.decompress(backup.content))
    assert len(data["vectors"]) == chunks and len(data["metadata"]["filings"]) == 1

    # Wipe the company, then restore the backup.
    client.post("/risky-delete/company", json={"company": "VIDEOIND", "dry_run": False, "confirm": "VIDEOIND"},
                headers=ADMIN)
    upload = {"file": ("backup.json.gz", backup.content, "application/gzip")}
    dry = client.post("/backup/restore", files=upload, data={"mode": "replace"}, headers=ADMIN).json()
    assert dry["dry_run"] is True and vectors.count_where() == 0      # dry run restores nothing

    no_confirm = client.post("/backup/restore", files=upload, data={"mode": "replace", "dry_run": "false"},
                             headers=ADMIN)
    assert no_confirm.status_code == 400

    done = client.post("/backup/restore", files=upload,
                       data={"mode": "replace", "dry_run": "false", "confirm": "RESTORE"}, headers=ADMIN)
    assert done.status_code == 200
    assert vectors.count_where() == chunks
    assert client.get(f"/documents/{body['doc_id']}").json()["status"] == "complete"
    assert "VIDEOIND" in {c["company_id"] for c in client.get("/companies").json()}


def test_restore_refuses_a_file_that_is_not_a_backup(client):
    upload = {"file": ("x.json.gz", gzip.compress(b'{"format": "other"}'), "application/gzip")}
    assert client.post("/backup/restore", files=upload, headers=ADMIN).status_code == 400


# =====================================================================================
# 6. Risky routes are not there unless switched on
# =====================================================================================
def test_risky_routes_do_not_exist_when_switched_off(monkeypatch):
    monkeypatch.setenv("ENABLE_RISKY_DELETE_APIS", "false")
    monkeypatch.setenv("ENABLE_BACKUP_APIS", "false")
    try:
        app = importlib.reload(api.main).app
        with TestClient(app, headers=ADMIN) as off:
            assert off.post("/risky-delete/company", json={"company": "OFSS"}).status_code == 404
            assert off.post("/backup/create").status_code == 404
            assert off.get("/health").status_code == 200
    finally:
        monkeypatch.setenv("ENABLE_RISKY_DELETE_APIS", "true")
        monkeypatch.setenv("ENABLE_BACKUP_APIS", "true")
        importlib.reload(api.main)                            # back to the app the other tests use
        assert os.getenv("ENABLE_BACKUP_APIS") == "true"
