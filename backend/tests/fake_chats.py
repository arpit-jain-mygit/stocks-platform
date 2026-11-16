"""
fake_chats.py - An in-memory stand-in for the chat store (utils/chats.py), for the tests.

Same three methods as ChatStore, kept in a dict keyed by (owner, session id).
"""

from datetime import datetime, timezone


class FakeChatStore:
    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}

    def list_sessions(self, owner: str, limit: int = 30) -> list[dict]:
        mine = [(key, row) for key, row in self.rows.items() if key[0] == owner]
        mine.sort(key=lambda item: item[1]["updated_at"], reverse=True)
        return [{"id": key[1], "name": row["name"], "renamed": row["renamed"], "company": row["company"],
                 "updated_at": row["updated_at"]} for key, row in mine[:limit]]

    def get_session(self, owner: str, session_id: str) -> dict | None:
        row = self.rows.get((owner, session_id))
        return None if row is None else {"id": session_id, **row}

    def save_session(self, owner: str, session_id: str, session: dict) -> str:
        updated_at = datetime.now(timezone.utc).isoformat()
        self.rows[(owner, session_id)] = {"name": session["name"], "renamed": session["renamed"],
                                          "company": session["company"], "messages": session["messages"],
                                          "updated_at": updated_at}
        return updated_at

    def delete_session(self, owner: str, session_id: str) -> bool:
        return self.rows.pop((owner, session_id), None) is not None
