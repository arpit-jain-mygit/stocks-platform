"""
backup_apis - RISKY endpoints: download a full backup, restore one (Postgres + Qdrant).

Mounted by api/main.py only when ENABLE_BACKUP_APIS=true; every call also needs
the X-Admin-Key header. See routes.py for the locks.
"""

from api.backup_apis.routes import router

__all__ = ["router"]
