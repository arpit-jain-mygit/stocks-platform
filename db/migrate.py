"""
migrate.py - Applies the SQL files in db/migrations/ to the Postgres database, in order.

Each file runs once: its name is recorded in the schema_migrations table, so
running this again only applies new files. Each file runs in its own
transaction - if it fails, nothing from that file is kept.

Run:  python db/migrate.py              apply new migrations
      python db/migrate.py --status     list applied / pending, change nothing
"""

# --- Imports -----------------------------------------------------------------
# sys:          command-line flag.
# Path:         finds the migrations folder.
# psycopg:      Postgres driver.
# dotenv_values: reads DATABASE_URL from the project's .env.
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).parent.parent
MIGRATIONS = Path(__file__).parent / "migrations"


def main() -> None:
    url = dotenv_values(ROOT / ".env").get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set in .env")

    with psycopg.connect(url) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                            version    TEXT PRIMARY KEY,
                            applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        conn.commit()
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        files = sorted(MIGRATIONS.glob("*.sql"))

        if "--status" in sys.argv:
            for f in files:
                print(f"{'applied' if f.name in applied else 'PENDING':8} {f.name}")
            return

        pending = [f for f in files if f.name not in applied]
        for f in pending:
            with conn.transaction():                      # all or nothing per file
                conn.execute(f.read_text())
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.name,))
            print(f"applied {f.name}")
        print(f"{len(pending)} applied, {len(files) - len(pending)} already up to date")


if __name__ == "__main__":
    main()
