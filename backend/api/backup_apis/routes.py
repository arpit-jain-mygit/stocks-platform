"""
routes.py - Backup and restore of Postgres (metadata) + Qdrant (chunks) as one file.

  POST /backup/create    downloads stocks-rag-backup-<time>.json.gz (everything)
  POST /backup/restore   uploads that file; mode "merge" (default) or "replace"

Locks:
  1. Mounted only if ENABLE_BACKUP_APIS=true in .env (otherwise 404).
  2. X-API-Key and X-Admin-Key headers (a backup holds ALL your data).
  3. Restore: dry_run defaults to true (only reports); a real restore needs
     confirm = "RESTORE". mode "replace" wipes both stores before loading.

The work itself is in ops/backup.py. No model calls.
"""

# --- Imports -----------------------------------------------------------------
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from api.security import require_admin_key, require_api_key
from ops import backup

MAX_BACKUP_MB = 500

router = APIRouter(
    prefix="/backup",
    tags=["RISKY backup / restore"],
    dependencies=[Depends(require_api_key), Depends(require_admin_key)],
)


@router.post("/create")
def create_backup() -> Response:
    """Downloads a .json.gz with every Postgres row and every Qdrant chunk. Changes nothing."""
    name, data, summary = backup.create_backup()
    return Response(
        content=data,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Backup-Summary": (f"companies={summary['companies']}; filings={summary['filings']}; "
                                 f"chunks={summary['chunks']}; doc_types={summary['doc_types']}"),
        },
    )


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(..., description="A stocks-rag-backup-*.json.gz file from /backup/create"),
    mode: str = Form("merge", description="merge = add / update only; replace = wipe both stores first"),
    dry_run: bool = Form(True, description="true = check the file and report; nothing changes"),
    confirm: str = Form("", description='With dry_run=false: type RESTORE'),
) -> dict:
    """Loads a backup into Postgres (one transaction) and then Qdrant."""
    data = await file.read()
    if len(data) > MAX_BACKUP_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Backup larger than {MAX_BACKUP_MB} MB")
    if not dry_run and confirm != "RESTORE":
        raise HTTPException(status_code=400, detail='Real restore needs confirm = "RESTORE". Nothing was changed.')
    try:
        return backup.restore_backup(data, mode=mode, dry_run=dry_run)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
