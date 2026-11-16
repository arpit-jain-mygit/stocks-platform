"""
chats.py - Saved chat sessions (the Ask window's conversations), kept in Postgres.

A session belongs to one browser. The UI sends a random owner id in the X-Chat-Owner header.
There is no login, so the owner id is the only key: it must stay private to the browser.
The table is created by db/migrations/006_chat_sessions.sql.

    from utils.chats import get_chat_store
    get_chat_store().list_sessions(owner)
"""

# --- Imports -----------------------------------------------------------------
# os:      reads DATABASE_URL.
# psycopg: Postgres driver.
# Jsonb:   tells the driver to store the messages as JSON.
import os

import psycopg
from psycopg.types.json import Jsonb


class ChatStore:
    """Reads and writes chat sessions. One short connection per call (same as the metadata store)."""

    def __init__(self, url: str):
        if not url:
            raise ValueError("postgres: DATABASE_URL is required (in .env)")
        self.url = url

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self.url, connect_timeout=10)

    def list_sessions(self, owner: str, limit: int = 30) -> list[dict]:
        """The owner's sessions, newest first. Messages are left out: fetch one session for those."""
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, name, renamed, company, updated_at FROM chat_sessions
                   WHERE owner = %s ORDER BY updated_at DESC LIMIT %s""",
                (owner, limit)).fetchall()
        return [{"id": r[0], "name": r[1], "renamed": r[2], "company": r[3], "updated_at": r[4].isoformat()}
                for r in rows]

    def get_session(self, owner: str, session_id: str) -> dict | None:
        """One session with its messages, or None if this owner has no such session."""
        with self.connect() as conn:
            row = conn.execute(
                """SELECT id, name, renamed, company, messages, updated_at FROM chat_sessions
                   WHERE owner = %s AND id = %s""",
                (owner, session_id)).fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "renamed": row[2], "company": row[3],
                "messages": row[4], "updated_at": row[5].isoformat()}

    def save_session(self, owner: str, session_id: str, session: dict) -> str:
        """Creates the session or replaces its contents. Returns the new updated_at time."""
        with self.connect() as conn:
            row = conn.execute(
                """INSERT INTO chat_sessions (owner, id, name, renamed, company, messages)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (owner, id) DO UPDATE SET
                       name = EXCLUDED.name, renamed = EXCLUDED.renamed, company = EXCLUDED.company,
                       messages = EXCLUDED.messages, updated_at = now()
                   RETURNING updated_at""",
                (owner, session_id, session["name"], session["renamed"], session["company"],
                 Jsonb(session["messages"]))).fetchone()
        return row[0].isoformat()

    def delete_session(self, owner: str, session_id: str) -> bool:
        """Removes one session of this owner. Returns False if there was no such session."""
        with self.connect() as conn:
            result = conn.execute(
                "DELETE FROM chat_sessions WHERE owner = %s AND id = %s", (owner, session_id))
        return result.rowcount > 0


# The store is made once, the first time it is needed. Tests put a fake in this slot.
_store: ChatStore | None = None


def get_chat_store() -> ChatStore:
    global _store
    if _store is None:
        _store = ChatStore(os.getenv("DATABASE_URL", "").strip())
    return _store
