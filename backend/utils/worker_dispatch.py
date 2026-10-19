"""
worker_dispatch.py - Starts an ingestion worker as an ECS Fargate task (AWS only).

Settings (environment variables, set by Terraform in Phase 2):
    ECS_CLUSTER              the cluster name
    ECS_TASK_DEFINITION      the task definition running `python -m ingest.worker`
    ECS_SUBNETS              comma-separated private subnet IDs
    ECS_SECURITY_GROUPS      comma-separated security group IDs
    ECS_CONTAINER_NAME       the container name in the task (default "worker")
    ECS_ASSIGN_PUBLIC_IP     ENABLED or DISABLED (default DISABLED; ENABLED for public subnets without NAT)

The job's details are passed to the task as environment variables (see ingest/worker.py main()).
Pay as you go: the task runs only while the file is being processed.
"""

# --- Imports -----------------------------------------------------------------
# os: reads the ECS settings.
import os


def dispatch_worker(job_id: str, upload_key: str, file_name: str, company: str, period: str,
                    doc_type: str | None, force: bool, client=None) -> str:
    """Starts one Fargate task for this job. Returns the task ARN. Raises RuntimeError if AWS refuses."""
    if client is None:
        import boto3                       # imported only when AWS is used
        client = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "ap-south-1"))
    settings = {
        "JOB_ID": job_id, "UPLOAD_KEY": upload_key, "FILE_NAME": file_name, "COMPANY": company,
        "PERIOD": period, "DOC_TYPE": doc_type or "", "FORCE": "true" if force else "false",
    }
    response = client.run_task(
        cluster=os.environ["ECS_CLUSTER"],
        taskDefinition=os.environ["ECS_TASK_DEFINITION"],
        launchType="FARGATE",
        count=1,
        networkConfiguration={"awsvpcConfiguration": {
            "subnets": [s.strip() for s in os.environ["ECS_SUBNETS"].split(",") if s.strip()],
            "securityGroups": [s.strip() for s in os.environ["ECS_SECURITY_GROUPS"].split(",") if s.strip()],
            # ENABLED lets the task reach Gemini, Qdrant and Supabase without a NAT gateway (set by Terraform).
            "assignPublicIp": os.getenv("ECS_ASSIGN_PUBLIC_IP", "DISABLED"),
        }},
        overrides={"containerOverrides": [{
            "name": os.getenv("ECS_CONTAINER_NAME", "worker"),
            "environment": [{"name": k, "value": v} for k, v in settings.items()],
        }]},
    )
    if response.get("failures"):
        reasons = "; ".join(f.get("reason", "unknown") for f in response["failures"])
        raise RuntimeError(f"ECS did not start the worker: {reasons}")
    return response["tasks"][0]["taskArn"]
