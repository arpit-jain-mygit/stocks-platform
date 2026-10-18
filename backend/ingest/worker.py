"""
worker.py - Runs one ingestion job.

Two ways it runs:
  - locally: the API starts run_job() in the background (FastAPI BackgroundTasks)
  - on AWS:  the API starts an ECS Fargate task (utils/worker_dispatch.py), which runs
             this file as `python -m ingest.worker`, reading its settings from environment
             variables. Background work would stop when a Lambda response is sent, so the
             long ingestion has to run in its own task.
"""

# --- Imports -----------------------------------------------------------------
# os:        reads the task's environment variables.
# datetime:  timestamps on the job.
# ingest_pdf: the full ingestion pipeline (ingest/pipeline.py).
# job_store:  where job progress is recorded (utils/jobs.py).
# read_upload: fetches an uploaded file from S3 (utils/uploads.py).
import os
from datetime import datetime, timezone

from ingest.pipeline import ingest_pdf
from utils.jobs import job_store
from utils.uploads import read_upload


def run_job(job_id: str, pdf_bytes: bytes, file_name: str, company: str, period: str,
            doc_type: str | None, force: bool) -> None:
    """Runs the pipeline for one job and records the outcome on the job."""
    jobs = job_store()
    jobs.update(job_id, status="running")
    try:
        result = ingest_pdf(pdf_bytes, file_name, company, period, doc_type=doc_type, force=force)
        jobs.update(job_id, status=result["status"], result=result)
    except Exception as error:                      # any failure is reported on the job
        jobs.update(job_id, status="failed", error=str(error))
    jobs.update(job_id, finished_at=datetime.now(timezone.utc).isoformat())


def main() -> None:
    """Entry point for the ECS task: every setting comes from environment variables."""
    env = os.environ
    run_job(
        job_id=env["JOB_ID"],
        pdf_bytes=read_upload(env["UPLOAD_KEY"]),
        file_name=env["FILE_NAME"],
        company=env["COMPANY"],
        period=env["PERIOD"],
        doc_type=env.get("DOC_TYPE") or None,
        force=env.get("FORCE", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
