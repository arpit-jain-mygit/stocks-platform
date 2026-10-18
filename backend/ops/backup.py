"""
backup.py - One-file backup and restore of BOTH stores:
  - metadata store (Postgres): doc types, companies + aliases, filings, applied migrations
  - vector store (Qdrant):     every chunk - id, vector, payload

The file is gzipped JSON (stocks-rag-backup-<time>.json.gz):
  {"format": "stocks-rag-backup", "version": 1, "created_at": ...,
   "embed_model": ..., "embed_dim": 768,
   "metadata": {...export_data()...},
   "vectors": [{"id": ..., "vector": [...], "payload": {...}}, ...]}

Restore checks the file first (format, embedding model + vector size, migrations)
and refuses a mismatch - vectors from another model can't be searched together.
Modes: "replace" (wipe both stores, then load) or "merge" (add / update only).
Postgres loads in one transaction; Qdrant is loaded after it succeeds.

Used by api/backup_apis. No model calls.
"""

# --- Imports -----------------------------------------------------------------
import gzip
import json
from datetime import datetime, timezone

from utils.llm import role_settings
from utils.metadata import get_metadata_store
from utils.vectorstore import VectorRecord, get_store

FORMAT = "stocks-rag-backup"
VERSION = 1


# --- Create -----------------------------------------------------------------------
def create_backup() -> tuple[str, bytes, dict]:
    """Returns (file name, gzipped bytes, summary)."""
    embed = role_settings("embed")
    points = get_store().export_points()
    backup = {
        "format": FORMAT, "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "embed_model": embed["model"], "embed_dim": embed["embed_dim"],
        "metadata": get_metadata_store().export_data(),
        "vectors": [{"id": p.id, "vector": p.vector, "payload": p.payload} for p in points],
    }
    data = gzip.compress(json.dumps(backup, ensure_ascii=False).encode())
    name = f"stocks-rag-backup-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json.gz"
    return name, data, summarise(backup) | {"file": name, "bytes": len(data)}


# --- Inspect -----------------------------------------------------------------------
def summarise(backup: dict) -> dict:
    """Row / point counts of a backup."""
    m = backup["metadata"]
    return {
        "created_at": backup["created_at"], "embed_model": backup["embed_model"], "embed_dim": backup["embed_dim"],
        "migrations": m["migrations"], "doc_types": len(m["doc_types"]), "companies": len(m["companies"]),
        "company_aliases": sum(len(c["aliases"]) for c in m["companies"]), "filings": len(m["filings"]),
        "chunks": len(backup["vectors"]),
    }


def load_backup(data: bytes) -> dict:
    """Reads and checks a backup file. Raises ValueError if it can't be used here."""
    try:
        backup = json.loads(gzip.decompress(data))
    except (OSError, ValueError) as error:
        raise ValueError(f"Not a readable .json.gz backup: {error}")
    if backup.get("format") != FORMAT or backup.get("version") != VERSION:
        raise ValueError(f"Not a {FORMAT} v{VERSION} file")
    embed = role_settings("embed")
    if (backup["embed_model"], backup["embed_dim"]) != (embed["model"], embed["embed_dim"]):
        raise ValueError(f"Backup vectors are {backup['embed_model']} / {backup['embed_dim']} dims, but this app uses "
                         f"{embed['model']} / {embed['embed_dim']} - they can't be searched together")
    if any(len(v["vector"]) != embed["embed_dim"] for v in backup["vectors"]):
        raise ValueError("Backup contains vectors of the wrong size")
    return backup


# --- Restore ------------------------------------------------------------------------
def restore_backup(data: bytes, mode: str = "replace", dry_run: bool = True) -> dict:
    """
    dry_run=True: checks the file and reports what is in it vs what is stored now.
    Otherwise loads it: Postgres first (one transaction), then Qdrant.
    """
    if mode not in ("replace", "merge"):
        raise ValueError("mode must be 'replace' or 'merge'")
    backup = load_backup(data)
    metadata, vectors = get_metadata_store(), get_store()
    current = metadata.export_data()
    report = {
        "dry_run": dry_run, "mode": mode,
        "backup": summarise(backup),
        "current": {"doc_types": len(current["doc_types"]), "companies": len(current["companies"]),
                    "filings": len(current["filings"]), "chunks": vectors.stats().get("chunks")},
    }
    if dry_run:
        return report

    report["postgres_after"] = metadata.import_data(backup["metadata"], mode)   # all or nothing
    if mode == "replace":
        vectors.clear()
    else:
        vectors.setup()
    records = [VectorRecord(id=v["id"], vector=v["vector"], payload=v["payload"]) for v in backup["vectors"]]
    vectors.upsert_chunks(records)
    report["qdrant_after"] = {"chunks": vectors.stats().get("chunks")}
    return report
