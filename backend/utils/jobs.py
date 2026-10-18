"""
jobs.py - Where ingestion jobs are remembered: in this process's memory, or in DynamoDB.

    JOB_BACKEND=memory (default)  a dictionary; forgotten when the server restarts
    JOB_BACKEND=dynamodb          a DynamoDB table (JOBS_TABLE), shared by every Lambda instance

Each job is a dictionary with a "job_id". DynamoDB stores the whole job as one JSON text
attribute ("body"), so any job fields (nested results, lists, numbers) are saved unchanged.
"""

# --- Imports -----------------------------------------------------------------
# functools: keeps one job store for the whole process.
# json:      the DynamoDB body is one JSON text.
# os:        reads JOB_BACKEND and JOBS_TABLE.
import functools
import json
import os


class JobStore:
    """Create, read, update and clear ingestion jobs by job_id."""

    name = "base"

    def create(self, job_id: str, job: dict) -> None:
        raise NotImplementedError(f"{self.name} job store must implement create")

    def get(self, job_id: str) -> dict | None:
        raise NotImplementedError(f"{self.name} job store must implement get")

    def update(self, job_id: str, **fields) -> None:
        """Merges the given fields into the job (other fields keep their value)."""
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        job.update(fields)
        self._save(job_id, job)

    def _save(self, job_id: str, job: dict) -> None:
        raise NotImplementedError(f"{self.name} job store must implement _save")

    def clear(self) -> None:
        raise NotImplementedError(f"{self.name} job store must implement clear")


class MemoryJobStore(JobStore):
    """Jobs in a dictionary. Single process only."""

    name = "memory"

    def __init__(self):
        self._jobs: dict[str, dict] = {}

    def create(self, job_id: str, job: dict) -> None:
        self._jobs[job_id] = dict(job)

    def get(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        return dict(job) if job is not None else None

    def _save(self, job_id: str, job: dict) -> None:
        self._jobs[job_id] = job

    def clear(self) -> None:
        self._jobs.clear()


class DynamoJobStore(JobStore):
    """Jobs in a DynamoDB table with partition key "job_id" and a text attribute "body"."""

    name = "dynamodb"

    def __init__(self, table_name: str, resource=None):
        if resource is None:
            import boto3                     # imported only when DynamoDB is used
            resource = boto3.resource("dynamodb")
        self.table = resource.Table(table_name)

    def create(self, job_id: str, job: dict) -> None:
        self._save(job_id, dict(job))

    def get(self, job_id: str) -> dict | None:
        item = self.table.get_item(Key={"job_id": job_id}).get("Item")
        return json.loads(item["body"]) if item else None

    def _save(self, job_id: str, job: dict) -> None:
        self.table.put_item(Item={"job_id": job_id, "body": json.dumps(job)})

    def clear(self) -> None:
        raise NotImplementedError("clear is not used on DynamoDB (jobs expire by table TTL)")


@functools.lru_cache(maxsize=None)
def job_store() -> JobStore:
    """The job store chosen by JOB_BACKEND (created once)."""
    backend = os.getenv("JOB_BACKEND", "memory").lower().strip()
    if backend == "dynamodb":
        table = os.getenv("JOBS_TABLE", "")
        if not table:
            raise RuntimeError("JOB_BACKEND=dynamodb needs JOBS_TABLE")
        return DynamoJobStore(table)
    if backend == "memory":
        return MemoryJobStore()
    raise ValueError(f"Unknown JOB_BACKEND {backend!r}. Use memory or dynamodb.")
