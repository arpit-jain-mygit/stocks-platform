"""
risky_delete_apis - RISKY endpoints that delete ingested data (Postgres + Qdrant).

Mounted by api/main.py only when ENABLE_RISKY_DELETE_APIS=true; every call
also needs the X-Admin-Key header. See routes.py for the full set of locks.
(Folder uses "_" because Python can't import names with "-"; the URLs are /risky-delete/...)
"""

from api.risky_delete_apis.routes import router

__all__ = ["router"]
