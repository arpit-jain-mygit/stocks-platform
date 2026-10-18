"""
config.py - Small settings shared by the API and the worker.

INGEST_MODE  background (default, local): the API runs the ingestion in the background.
             worker (AWS): the API starts an ECS Fargate task for each ingestion.
"""

# --- Imports -----------------------------------------------------------------
# os: reads environment variables.
import os


def ingest_mode() -> str:
    mode = os.getenv("INGEST_MODE", "background").lower().strip()
    if mode not in ("background", "worker"):
        raise ValueError(f"Unknown INGEST_MODE {mode!r}. Use background or worker.")
    return mode
