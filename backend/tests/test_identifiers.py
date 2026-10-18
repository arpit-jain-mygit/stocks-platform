"""
test_identifiers.py - Company identifiers for any market: tickers per exchange, ISIN, CIN ...
Offline, no model calls (fakes from conftest.py).

Run (from backend/):   python -m pytest
"""

# --- Imports -----------------------------------------------------------------
import gzip
import json

import pytest

from tests.conftest import ADMIN_KEY, APP_KEY
from utils.companies import find_company
from utils.metadata.base import Company, Identifier
from utils.metadata.postgres import backup_identifiers

ADMIN = {"X-API-Key": APP_KEY, "X-Admin-Key": ADMIN_KEY}

MSFT = Company(company_id="MSFT", name="Microsoft Corporation", country="US", fy_end_month=6,
               aliases=("Microsoft",),
               identifiers=(Identifier("ticker", "MSFT", "NASDAQ"), Identifier("isin", "US5949181045"),
                            Identifier("cik", "0000789019")))


# --- The model ---------------------------------------------------------------------------
def test_ticker_label_includes_its_exchange():
    assert Identifier("ticker", "MSFT", "NASDAQ").label() == "NASDAQ:MSFT"
    assert Identifier("isin", "US5949181045").label() == "US5949181045"


def test_bare_tickers_are_not_unique_names():
    """names() holds only what identifies ONE company - a bare ticker can be shared across exchanges."""
    assert "NASDAQ:MSFT" in MSFT.names() and "MSFT" in MSFT.names()          # "MSFT" via the code, not the ticker
    other = Company(company_id="ZZ", name="Zz plc", identifiers=(Identifier("ticker", "ABC", "LSE"),))
    assert "ABC" not in other.names() and "LSE:ABC" in other.names()


# --- Lookup --------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["MSFT", "msft", "NASDAQ:MSFT", "US5949181045", "0000789019", "Microsoft",
                                  "Microsoft Corporation"])
def test_find_a_us_company_by_any_identifier(meta, text):
    meta.companies.append(MSFT)
    assert find_company(text).company_id == "MSFT"


@pytest.mark.parametrize("text, company_id", [("532466", "OFSS"), ("BSE:532466", "OFSS"), ("NSE:VIDEOIND", "VIDEOIND"),
                                              ("INE881D01027", "OFSS"), ("L99999MH1986PLC103624", "VIDEOIND")])
def test_indian_identifiers_still_work(text, company_id):
    assert find_company(text).company_id == company_id


def test_a_bare_ticker_shared_by_two_companies_needs_the_exchange(client, meta):
    meta.companies += [Company(company_id="ABC1", name="Abc India Ltd", identifiers=(Identifier("ticker", "ABC", "NSE"),)),
                       Company(company_id="ABC2", name="Abc plc", identifiers=(Identifier("ticker", "ABC", "LSE"),))]
    with pytest.raises(ValueError, match="several companies"):
        find_company("ABC")
    assert find_company("LSE:ABC").company_id == "ABC2"
    reply = client.get("/companies/ABC")                                     # API: 400 with the choices
    assert reply.status_code == 400 and "NSE:ABC" in reply.json()["detail"] and "LSE:ABC" in reply.json()["detail"]
    assert client.post("/ask", json={"question": "Revenue?", "company": "ABC"}).status_code == 400
    assert client.get("/companies/NSE:ABC").json()["company_id"] == "ABC1"


# --- API -------------------------------------------------------------------------------------
def test_api_returns_identifiers_country_and_the_older_fields(client):
    ofss = next(c for c in client.get("/companies").json() if c["company_id"] == "OFSS")
    assert ofss["country"] == "IN"
    assert {"type": "ticker", "exchange": "NSE", "value": "OFSS"} in ofss["identifiers"]
    assert {"type": "isin", "exchange": "", "value": "INE881D01027"} in ofss["identifiers"]
    # Older fields, filled from the identifiers.
    assert (ofss["nse_symbol"], ofss["bse_code"], ofss["isin"], ofss["cin"]) == ("OFSS", "532466", "INE881D01027", "")


def test_api_shows_a_us_company(client, meta):
    meta.companies.append(MSFT)
    detail = client.get("/companies/NASDAQ:MSFT").json()
    assert detail["company_id"] == "MSFT" and detail["country"] == "US" and detail["fy_end_month"] == 6
    assert detail["nse_symbol"] == "" and detail["filings"] == []


def test_backup_round_trip_keeps_identifiers(client, meta, make_pdf, ingest):
    ingest(make_pdf())
    backup = client.post("/backup/create", headers=ADMIN).content
    saved = json.loads(gzip.decompress(backup))["metadata"]["companies"]
    assert any(i["value"] == "532466" for c in saved for i in c["identifiers"])
    client.post("/backup/restore", files={"file": ("b.json.gz", backup, "application/gzip")},
                data={"mode": "replace", "dry_run": "false", "confirm": "RESTORE"}, headers=ADMIN)
    assert find_company("BSE:532466").company_id == "OFSS"


def test_backups_from_before_migration_004_are_converted():
    """Old backups have nse_symbol / bse_code / isin / cin instead of "identifiers"."""
    old = {"code": "OFSS", "nse_symbol": "OFSS", "bse_code": "532466", "isin": "INE881D01027", "cin": None}
    assert backup_identifiers(old) == [("ticker", "NSE", "OFSS"), ("ticker", "BSE", "532466"), ("isin", None, "INE881D01027")]
