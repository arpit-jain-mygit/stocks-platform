"""
test_aws.py - The AWS pieces, tested with fake clients (no AWS calls, no cost).

Covers: local and S3 storage, the cache choice, DynamoDB and memory job stores, presigned
uploads, the ECS worker dispatch, and the worker running a job.

Run (from backend/):   python -m pytest
"""

# --- Imports -----------------------------------------------------------------
import pytest

from ingest import worker
from utils import storage, uploads, worker_dispatch
from utils.jobs import DynamoJobStore, MemoryJobStore
from utils.storage import LocalStorage, S3Storage


# --- Fakes ----------------------------------------------------------------------------
class FakeClientError(Exception):
    """Like botocore's ClientError: carries an error code in .response."""
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self, size=10):
        self.objects, self.size = {}, size

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise FakeClientError("NoSuchKey")
        import io
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, Bucket, Key):
        return {"ContentLength": self.size}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://example.invalid/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"


class FakeDynamoTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[Item["job_id"]] = Item

    def get_item(self, Key):
        item = self.items.get(Key["job_id"])
        return {"Item": item} if item else {}


class FakeDynamo:
    def __init__(self):
        self.table_obj = FakeDynamoTable()

    def Table(self, name):
        return self.table_obj


class FakeEcs:
    def __init__(self, failures=None):
        self.calls, self.failures = [], failures or []

    def run_task(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures:
            return {"failures": self.failures, "tasks": []}
        return {"tasks": [{"taskArn": "arn:aws:ecs:ap-south-1:1:task/x"}], "failures": []}


@pytest.fixture
def reset_settings(monkeypatch):
    """Each test starts with the local settings and fresh singletons."""
    for name in ("CACHE_BACKEND", "CACHE_BUCKET", "JOB_BACKEND", "JOBS_TABLE", "UPLOAD_BUCKET", "INGEST_MODE"):
        monkeypatch.delenv(name, raising=False)
    storage.cache_storage.cache_clear()          # job store is NOT cleared: the API holds that instance
    yield monkeypatch
    storage.cache_storage.cache_clear()


# --- Storage ------------------------------------------------------------------------------
def test_local_storage_round_trip(tmp_path):
    local = LocalStorage(tmp_path)
    assert local.get_text("a/b.md") is None
    local.put_text("a/b.md", "hello")
    assert local.get_text("a/b.md") == "hello"
    assert not list(tmp_path.rglob("*.tmp"))            # no half-written files left behind


def test_s3_storage_round_trip_and_prefix():
    client = FakeS3()
    s3 = S3Storage("bucket", prefix="cache", client=client)
    assert s3.get_text("doc/page_001.md") is None        # missing object reads as None
    s3.put_text("doc/page_001.md", "text")
    assert s3.get_text("doc/page_001.md") == "text"
    assert ("bucket", "cache/doc/page_001.md") in client.objects


def test_cache_storage_is_chosen_by_setting(reset_settings, tmp_path):
    reset_settings.setenv("PAGE_CACHE_DIR", str(tmp_path))
    assert isinstance(storage.cache_storage(), LocalStorage)
    storage.cache_storage.cache_clear()
    reset_settings.setenv("CACHE_BACKEND", "s3")
    with pytest.raises(RuntimeError, match="CACHE_BUCKET"):
        storage.cache_storage()
    storage.cache_storage.cache_clear()
    reset_settings.setenv("CACHE_BUCKET", "my-bucket")
    reset_settings.setattr(storage, "S3Storage", lambda bucket, prefix: S3Storage(bucket, prefix, client=FakeS3()))
    assert storage.cache_storage().bucket == "my-bucket"


# --- Job stores -------------------------------------------------------------------------------
def test_memory_job_store_update_merges_and_missing_raises():
    store = MemoryJobStore()
    store.create("j1", {"job_id": "j1", "status": "queued"})
    store.update("j1", status="running")
    assert store.get("j1") == {"job_id": "j1", "status": "running"}
    with pytest.raises(KeyError):
        store.update("nope", status="failed")


def test_dynamo_job_store_round_trip_keeps_nested_results():
    store = DynamoJobStore("jobs", resource=FakeDynamo())
    store.create("j2", {"job_id": "j2", "status": "queued"})
    store.update("j2", status="complete", result={"chunks": 84, "ocr_pages": [3, 9], "pages": 13})
    job = store.get("j2")
    assert job["status"] == "complete" and job["result"] == {"chunks": 84, "ocr_pages": [3, 9], "pages": 13}
    assert store.get("missing") is None


# --- Uploads ---------------------------------------------------------------------------------
def test_create_upload_gives_a_presigned_link_under_uploads(reset_settings):
    reset_settings.setenv("UPLOAD_BUCKET", "uploads-bucket")
    result = uploads.create_upload("Report 2025 (final).pdf", client=FakeS3())
    assert result["upload_key"].startswith("uploads/") and result["upload_key"].endswith("Report_2025__final_.pdf")
    assert result["upload_url"].startswith("https://example.invalid/uploads-bucket/")
    assert result["expires_in"] == uploads.UPLOAD_URL_SECONDS


def test_uploads_need_a_bucket_and_refuse_other_keys(reset_settings):
    with pytest.raises(RuntimeError, match="UPLOAD_BUCKET"):
        uploads.create_upload("a.pdf", client=FakeS3())
    reset_settings.setenv("UPLOAD_BUCKET", "uploads-bucket")
    with pytest.raises(ValueError, match="POST /uploads"):
        uploads.read_upload("caches/secret.md", client=FakeS3())
    with pytest.raises(ValueError, match="larger"):
        uploads.read_upload("uploads/x/a.pdf", client=FakeS3(size=uploads.MAX_UPLOAD_BYTES + 1))


def test_post_uploads_is_not_available_locally(client):
    reply = client.post("/uploads", data={"file_name": "report.pdf"})
    assert reply.status_code == 501 and "UPLOAD_BUCKET" in reply.json()["detail"]


def test_post_uploads_refuses_unsupported_types(reset_settings, client):
    reset_settings.setenv("UPLOAD_BUCKET", "uploads-bucket")
    assert client.post("/uploads", data={"file_name": "virus.exe"}).status_code == 400


# --- Worker dispatch (ECS) ----------------------------------------------------------------------
def test_dispatch_worker_passes_the_job_as_environment_variables(reset_settings):
    reset_settings.setenv("ECS_CLUSTER", "stocks")
    reset_settings.setenv("ECS_TASK_DEFINITION", "worker:1")
    reset_settings.setenv("ECS_SUBNETS", "subnet-a, subnet-b")
    reset_settings.setenv("ECS_SECURITY_GROUPS", "sg-1")
    ecs = FakeEcs()
    arn = worker_dispatch.dispatch_worker("job1", "uploads/x/a.csv", "a.csv", "MSFT", "Q1 FY26",
                                          "financial_statements", True, client=ecs)
    assert arn.endswith("task/x")
    call = ecs.calls[0]
    assert call["launchType"] == "FARGATE" and call["networkConfiguration"]["awsvpcConfiguration"]["subnets"] == ["subnet-a", "subnet-b"]
    env = {item["name"]: item["value"] for item in call["overrides"]["containerOverrides"][0]["environment"]}
    assert env["JOB_ID"] == "job1" and env["UPLOAD_KEY"] == "uploads/x/a.csv" and env["FORCE"] == "true"


def test_dispatch_worker_reports_aws_failures(reset_settings):
    reset_settings.setenv("ECS_CLUSTER", "stocks")
    reset_settings.setenv("ECS_TASK_DEFINITION", "worker:1")
    reset_settings.setenv("ECS_SUBNETS", "subnet-a")
    reset_settings.setenv("ECS_SECURITY_GROUPS", "sg-1")
    with pytest.raises(RuntimeError, match="did not start"):
        worker_dispatch.dispatch_worker("j", "uploads/x/a.csv", "a.csv", "MSFT", "Q1 FY26", None, False,
                                        client=FakeEcs(failures=[{"reason": "CAPACITY"}]))


def test_worker_mode_needs_an_upload_and_starts_a_task(reset_settings, client, monkeypatch):
    reset_settings.setenv("INGEST_MODE", "worker")
    reply = client.post("/ingest", data={"company": "VIDEOIND", "period": "Q3 FY25"},
                        files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert reply.status_code == 400 and "POST /uploads" in reply.json()["detail"]

    started = {}
    import api.main as api_main
    monkeypatch.setattr(api_main, "read_upload", lambda key: b"Particulars,Q3 FY25\nRevenue,1234.5\n")
    monkeypatch.setattr(api_main, "dispatch_worker",
                        lambda job_id, key, *args, **kwargs: started.update(job_id=job_id, key=key) or "arn")
    reply = client.post("/ingest", data={"company": "VIDEOIND", "period": "Q3 FY25",
                                         "upload_key": "uploads/x/a.csv", "file_name": "a.csv"})
    assert reply.status_code == 200 and reply.json()["status"] == "queued"
    assert started["key"] == "uploads/x/a.csv" and started["job_id"] == reply.json()["job_id"]


# --- The worker ------------------------------------------------------------------------------------
def test_worker_main_runs_the_job_from_environment_variables(reset_settings, client, monkeypatch):
    """What the ECS task does: read the upload, run the pipeline, record the result on the job."""
    import api.main as api_main
    csv_bytes = b"Particulars,Q3 FY25,Q2 FY25\nRevenue,1234.5,1100\n"
    monkeypatch.setattr(worker, "read_upload", lambda key: csv_bytes)
    api_main.jobs.create("job-w", {"job_id": "job-w", "status": "queued"})
    for name, value in {"JOB_ID": "job-w", "UPLOAD_KEY": "uploads/x/a.csv", "FILE_NAME": "a.csv",
                        "COMPANY": "VIDEOIND", "PERIOD": "Q3 FY25", "DOC_TYPE": "", "FORCE": "false"}.items():
        reset_settings.setenv(name, value)
    worker.main()
    job = api_main.jobs.get("job-w")
    assert job["status"] == "complete" and job["result"]["chunks"] > 0 and job["finished_at"]
