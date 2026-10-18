"""
postgres.py - Metadata in Postgres (Supabase): companies, aliases, doc types and filings.

Tables and starting data come from db/migrations (python db/migrate.py).
Add companies / doc types with db/samples/add_company.sql.
Companies and doc types are cached for CACHE_SECONDS (they rarely change);
filings are never cached, because the "already ingested?" check must be current.
"""

# --- Imports -----------------------------------------------------------------
# time:    cache expiry.
# psycopg: Postgres driver.
import time

import psycopg

from utils.metadata.base import Company, MetadataStore

CACHE_SECONDS = 60

COMPANIES_SQL = """
    SELECT c.code, c.name, COALESCE(c.nse_symbol, ''), COALESCE(c.bse_code, ''), COALESCE(c.cin, ''),
           COALESCE(c.isin, ''),
           COALESCE(array_agg(a.alias::text ORDER BY a.alias) FILTER (WHERE a.alias IS NOT NULL), '{}'),
           COALESCE(c.sector, ''), c.fy_end_month, c.status
    FROM companies c
    LEFT JOIN company_aliases a ON a.company_id = c.id
    GROUP BY c.id
    ORDER BY c.code
"""

# Filing record keys (see base.py) -> filings columns. "company_id" (the code)
# becomes the companies.id foreign key; "company" (the name) comes from the join.
FILING_COLUMNS = {
    "file_name": "file_name", "doc_type": "doc_type", "fiscal_year": "fiscal_year", "quarter": "quarter",
    "period_end": "period_end", "period": "period_label", "status": "status", "pages": "pages",
    "ocr_pages": "ocr_pages", "chunks": "chunks", "error": "error", "superseded_by": "superseded_by",
    "storage_url": "storage_url", "filed_on": "filed_on",
}
FILING_SELECT = """
    SELECT f.doc_id, f.file_name, c.code, c.name, f.doc_type, f.fiscal_year, f.quarter, f.period_end,
           f.period_label, f.status, f.pages, f.ocr_pages, f.chunks, f.error, f.superseded_by, f.created_at,
           f.updated_at
    FROM filings f JOIN companies c ON c.id = f.company_id
"""
FILING_KEYS = ["doc_id", "file_name", "company_id", "company", "doc_type", "fiscal_year", "quarter", "period_end",
               "period", "status", "pages", "ocr_pages", "chunks", "error", "superseded_by", "created_at", "updated_at"]


# Columns copied as-is by backups (ids are never copied; links go by company code).
COMPANY_COLUMNS = ["code", "name", "cin", "isin", "nse_symbol", "bse_code", "sector", "fy_end_month", "status"]
FILING_EXPORT_COLUMNS = ["doc_id", "doc_type", "fiscal_year", "quarter", "period_end", "period_label", "file_name",
                         "storage_url", "filed_on", "pages", "ocr_pages", "chunks", "status", "error",
                         "superseded_by", "created_at", "updated_at"]


def filing_dict(row) -> dict:
    """One SELECT row -> the plain record dict (dates as ISO strings, so it is JSON-ready)."""
    record = dict(zip(FILING_KEYS, row))
    record["period_end"] = record["period_end"].isoformat()
    record["created_at"] = record["created_at"].isoformat()
    record["updated_at"] = record["updated_at"].isoformat()
    record["ocr_pages"] = list(record["ocr_pages"] or [])
    return record


class PostgresMetadataStore(MetadataStore):
    provider = "postgres"

    def __init__(self, url: str):
        if not url:
            raise ValueError("postgres: DATABASE_URL is required (in .env)")
        self.url = url
        self._cache: dict[str, tuple[float, object]] = {}    # key -> (time stored, value)

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self.url, connect_timeout=10)

    def _cached(self, key: str, load):
        """Returns the cached value if fresh, else calls load() and caches it."""
        stored = self._cache.get(key)
        if stored and time.monotonic() - stored[0] < CACHE_SECONDS:
            return stored[1]
        value = load()
        self._cache[key] = (time.monotonic(), value)
        return value

    def clear_cache(self) -> None:
        """Forget cached companies / doc types (e.g. right after seeding)."""
        self._cache.clear()

    # --- Companies and doc types (cached) ---------------------------------------------
    def list_companies(self) -> list[Company]:
        def load():
            with self.connect() as conn:
                rows = conn.execute(COMPANIES_SQL).fetchall()
            return [Company(company_id=code, name=name, nse_symbol=nse, bse_code=bse, cin=cin, isin=isin,
                            aliases=tuple(aliases), sector=sector, fy_end_month=fy_end, status=status)
                    for code, name, nse, bse, cin, isin, aliases, sector, fy_end, status in rows]
        return self._cached("companies", load)

    def doc_types(self) -> dict:
        def load():
            with self.connect() as conn:
                rows = conn.execute("SELECT code, name, is_default FROM doc_types ORDER BY code").fetchall()
            default = next((code for code, _, is_default in rows if is_default), None)
            return {"default": default, "doc_types": [{"code": code, "name": name} for code, name, _ in rows]}
        return self._cached("doc_types", load)

    # --- Filings (never cached) ---------------------------------------------------------
    def get_filing(self, doc_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(FILING_SELECT + " WHERE f.doc_id = %s", (doc_id,)).fetchone()
        return filing_dict(row) if row else None

    def list_filings(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(FILING_SELECT + " ORDER BY f.updated_at DESC").fetchall()
        return [filing_dict(r) for r in rows]

    def save_filing(self, doc_id: str, fields: dict) -> None:
        """
        Upsert in one transaction:
          1. write every given field except status = "complete"
          2. if completing: mark the previous complete filing for the same
             company + doc_type + period "superseded" (pointing to this one)
          3. then set this one to "complete"
        This order keeps both the foreign key (superseded_by) and the
        "one live filing per slot" rule satisfied at every step.
        """
        columns = {FILING_COLUMNS[k]: v for k, v in fields.items() if k in FILING_COLUMNS}
        completing = columns.get("status") == "complete"
        if completing:
            del columns["status"]

        with self.connect() as conn, conn.transaction():
            if "company_id" in fields:
                found = conn.execute("SELECT id FROM companies WHERE code = %s", (fields["company_id"],)).fetchone()
                if not found:
                    raise ValueError(f"Unknown company {fields['company_id']!r} - add it to companies first")
                columns["company_id"] = found[0]

            # 1. Create or update the row.
            names = list(columns)
            if names:
                conn.execute(
                    f"""INSERT INTO filings (doc_id, {", ".join(names)})
                        VALUES (%s, {", ".join(["%s"] * len(names))})
                        ON CONFLICT (doc_id) DO UPDATE SET {", ".join(f"{n} = EXCLUDED.{n}" for n in names)}""",
                    (doc_id, *columns.values()),
                )

            if completing:
                # 2. Retire the previous live filing for the same slot.
                conn.execute(
                    """UPDATE filings old SET status = 'superseded', superseded_by = new.doc_id
                       FROM filings new
                       WHERE new.doc_id = %s AND old.doc_id <> new.doc_id AND old.status = 'complete'
                         AND old.company_id = new.company_id AND old.doc_type = new.doc_type
                         AND old.fiscal_year = new.fiscal_year
                         AND COALESCE(old.quarter, 0) = COALESCE(new.quarter, 0)""",
                    (doc_id,),
                )
                # 3. Mark this one complete.
                conn.execute("UPDATE filings SET status = 'complete', error = NULL WHERE doc_id = %s", (doc_id,))

    def delete_filing(self, doc_id: str) -> bool:
        with self.connect() as conn, conn.transaction():
            # Clear links first, or the foreign key on superseded_by blocks the delete.
            conn.execute("UPDATE filings SET superseded_by = NULL WHERE superseded_by = %s", (doc_id,))
            return conn.execute("DELETE FROM filings WHERE doc_id = %s", (doc_id,)).rowcount > 0

    def delete_company(self, company_id: str) -> bool:
        with self.connect() as conn, conn.transaction():
            row = conn.execute("SELECT id FROM companies WHERE code = %s", (company_id,)).fetchone()
            if not row:
                return False
            left = conn.execute("SELECT count(*) FROM filings WHERE company_id = %s", row).fetchone()[0]
            if left:
                raise ValueError(f"{company_id} still has {left} filing(s) - delete them first")
            conn.execute("DELETE FROM company_aliases WHERE company_id = %s", row)
            conn.execute("DELETE FROM companies WHERE id = %s", row)
        self.clear_cache()                                    # lookups must stop finding it now
        return True

    # --- Backup / restore -------------------------------------------------------------
    def export_data(self) -> dict:
        def rows(conn, sql):
            cur = conn.execute(sql)
            names = [c.name for c in cur.description]
            return [{n: (v.isoformat() if hasattr(v, "isoformat") else v) for n, v in zip(names, r)} for r in cur]
        with self.connect() as conn:
            return {
                "migrations": [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")],
                "doc_types": rows(conn, "SELECT code, name, is_default FROM doc_types ORDER BY code"),
                "companies": rows(conn, f"""
                    SELECT {", ".join("c." + col for col in COMPANY_COLUMNS)},
                           COALESCE(array_agg(a.alias::text ORDER BY a.alias)
                                    FILTER (WHERE a.alias IS NOT NULL), '{{}}') AS aliases
                    FROM companies c LEFT JOIN company_aliases a ON a.company_id = c.id
                    GROUP BY c.id ORDER BY c.code"""),
                "filings": rows(conn, f"""
                    SELECT c.code AS company_code, {", ".join("f." + col for col in FILING_EXPORT_COLUMNS)}
                    FROM filings f JOIN companies c ON c.id = f.company_id ORDER BY f.created_at"""),
            }

    def import_data(self, data: dict, mode: str) -> dict:
        if mode not in ("replace", "merge"):
            raise ValueError("mode must be 'replace' or 'merge'")
        with self.connect() as conn, conn.transaction():          # all or nothing
            applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            missing = [m for m in data["migrations"] if m not in applied]
            if missing:
                raise ValueError(f"Backup needs migrations {missing} - run python db/migrate.py first")

            if mode == "replace":                                   # children first (foreign keys)
                conn.execute("DELETE FROM filings")
                conn.execute("DELETE FROM company_aliases")
                conn.execute("DELETE FROM companies")
                conn.execute("DELETE FROM doc_types")

            # Doc types: clear the default first - only one row may have it.
            if any(t["is_default"] for t in data["doc_types"]):
                conn.execute("UPDATE doc_types SET is_default = false")
            for t in data["doc_types"]:
                conn.execute("""INSERT INTO doc_types (code, name, is_default) VALUES (%(code)s, %(name)s, %(is_default)s)
                                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_default = EXCLUDED.is_default""", t)

            # Companies (by code) + their aliases.
            for c in data["companies"]:
                company_id = conn.execute(
                    f"""INSERT INTO companies ({", ".join(COMPANY_COLUMNS)})
                        VALUES ({", ".join("%(" + col + ")s" for col in COMPANY_COLUMNS)})
                        ON CONFLICT (code) DO UPDATE SET
                        {", ".join(f"{col} = EXCLUDED.{col}" for col in COMPANY_COLUMNS if col != "code")}
                        RETURNING id""", c).fetchone()[0]
                for alias in c["aliases"]:
                    conn.execute("INSERT INTO company_aliases (company_id, alias) VALUES (%s, %s) "
                                 "ON CONFLICT (alias) DO NOTHING", (company_id, alias))

            # Filings: insert without superseded_by first, then add the links,
            # so a link never points at a row that isn't loaded yet.
            cols = [col for col in FILING_EXPORT_COLUMNS if col != "superseded_by"]
            for f in data["filings"]:
                conn.execute(
                    f"""INSERT INTO filings (company_id, {", ".join(cols)})
                        VALUES ((SELECT id FROM companies WHERE code = %(company_code)s),
                                {", ".join("%(" + col + ")s" for col in cols)})
                        ON CONFLICT (doc_id) DO UPDATE SET
                        {", ".join(f"{col} = EXCLUDED.{col}" for col in ["company_id"] + cols if col != "doc_id")}""", f)
            for f in data["filings"]:
                if f.get("superseded_by"):
                    conn.execute("UPDATE filings SET superseded_by = %s WHERE doc_id = %s", (f["superseded_by"], f["doc_id"]))

            counts = {name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                      for name in ("doc_types", "companies", "company_aliases", "filings")}
        self.clear_cache()
        return counts

    def __repr__(self) -> str:
        host = self.url.split("@")[-1].split("/")[0]       # never show the password
        return f"PostgresMetadataStore({host})"
