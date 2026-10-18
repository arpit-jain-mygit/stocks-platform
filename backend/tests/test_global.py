"""
test_global.py - Tests that nothing assumes Indian companies: any financial-year end,
any currency and number format, neutral prompts. Offline, no model calls.

Run (from backend/):   python -m pytest
"""

# --- Imports -----------------------------------------------------------------
from datetime import date

import pytest

from ingest.chunker import KEEP_ALWAYS
from ingest.pdf_reader import FIGURE_LINE, is_table_page
from query.answer import company_notes
from query.search import Hit
from tests.fakes import Company
from utils import prompts
from utils.periods import parse_period


# =====================================================================================
# 1. Periods follow each company's own financial-year end
# =====================================================================================
@pytest.mark.parametrize("text, fy_end_month, end, label", [
    # Year ends in March (India, Japan, UK): unchanged from before.
    ("Q3 FY25", 3, date(2024, 12, 31), "Q3 FY25 (quarter ended 31-Dec-2024)"),
    ("FY25", 3, date(2025, 3, 31), "FY25 (year ended 31-Mar-2025)"),
    ("Q1 FY25", 3, date(2024, 6, 30), "Q1 FY25 (quarter ended 30-Jun-2024)"),
    # Year ends in December (most US / EU companies): FY25 = calendar 2025.
    ("Q3 2025", 12, date(2025, 9, 30), "Q3 FY25 (quarter ended 30-Sep-2025)"),
    ("2025", 12, date(2025, 12, 31), "FY25 (year ended 31-Dec-2025)"),
    # Year ends in September (e.g. Apple): Q1 FY25 = Oct-Dec 2024.
    ("Q1 FY2025", 9, date(2024, 12, 31), "Q1 FY25 (quarter ended 31-Dec-2024)"),
    # Year ends in June (Australia), and in February (leap year handled).
    ("Q2 FY25", 6, date(2024, 12, 31), "Q2 FY25 (quarter ended 31-Dec-2024)"),
    ("FY24", 2, date(2024, 2, 29), "FY24 (year ended 29-Feb-2024)"),
])
def test_period_end_depends_on_the_company_year_end(text, fy_end_month, end, label):
    period = parse_period(text, fy_end_month)
    assert period.period_end == end and period.label == label


def test_filters_are_the_same_for_every_year_end():
    """fiscal_year + quarter (what search filters on) never depend on the year-end month."""
    assert {(parse_period("Q3 FY25", m).fiscal_year, parse_period("Q3 FY25", m).quarter) for m in range(1, 13)} == {(2025, 3)}


@pytest.mark.parametrize("bad", ["", "someday", "Q5 FY25", "25"])
def test_unreadable_period_is_rejected(bad):
    with pytest.raises(ValueError):
        parse_period(bad)


def test_ingest_uses_the_company_year_end(client, meta, make_pdf, ingest):
    """A December year-end company: Q3 FY25 is stored as the quarter ended 30-Sep-2025."""
    meta.companies.append(Company(company_id="ACME", name="Acme Inc", fy_end_month=12, status="active"))
    _, body = ingest(make_pdf(), company="ACME", period="Q3 2025")
    assert body["job"]["status"] == "complete", body["job"].get("error")
    record = client.get(f"/documents/{body['doc_id']}").json()
    assert record["period_end"] == "2025-09-30" and record["period"] == "Q3 FY25 (quarter ended 30-Sep-2025)"


# =====================================================================================
# 2. Any currency and number format
# =====================================================================================
@pytest.mark.parametrize("line", ["1,234.5", "(24,898.56)", "$1,234", "€1.234,56", "1,23,456.7", "¥ 1 234",
                                  "34%", "2.1x", "5 times", "-", "—"])
def test_figure_lines_in_any_format(line):
    assert FIGURE_LINE.match(line)


@pytest.mark.parametrize("line", ["Revenue", "Q3 2025", "FY25", "Net income attributable to owners"])
def test_text_lines_are_not_figures(line):
    assert not FIGURE_LINE.match(line)


def test_a_us_dollar_table_page_is_detected():
    rows = ["Revenue", "$1,234", "$1,100", "Cost of sales", "(812)", "(790)", "Net income", "$422", "$310",
            "Diluted EPS", "$1.05", "$0.78", "Shares", "402.1", "401.7", "Margin", "34%", "28%"]
    assert is_table_page("\n".join(rows))


@pytest.mark.parametrize("line", ["(In millions, except per share data)", "Amounts in $ thousands", "€m",
                                  "(₹ in Million)", "Rs. in crore", "in USD", "£bn"])
def test_units_lines_are_never_dropped_as_repeated_boilerplate(line):
    assert KEEP_ALWAYS.search(line)


# =====================================================================================
# 3. Prompts are market-neutral and carry each company's year-end
# =====================================================================================
def test_prompts_do_not_assume_india():
    for prompt in (prompts.TRANSCRIBE_PAGE, prompts.ANSWER_QUESTION):
        assert "Indian" not in prompt and "April to March" not in prompt.split("Example")[0]


def test_answer_prompt_lists_each_company_year_end(meta):
    meta.companies.append(Company(company_id="ACME", name="Acme Inc", fy_end_month=12))
    hit = lambda company: Hit(score=1, text="t", file_name="f.pdf", page_start=1, page_end=1, section="",
                              kind="prose", chunk_no=0, doc_id="d", company_id=company)
    notes = company_notes([hit("OFSS"), hit("ACME"), hit("OFSS")])
    assert notes.splitlines() == [
        "- OFSS (Oracle Financial Services Software Ltd): financial year ends in March",
        "- ACME (Acme Inc): financial year ends in December",
    ]


def test_answer_prompt_sent_to_the_model_includes_the_companies(client, llm, make_pdf, ingest):
    ingest(make_pdf())
    client.post("/ask", json={"question": "What was revenue from operations?", "company": "VIDEOIND"})
    [prompt] = llm["answer"].prompts
    assert "Companies:\n- VIDEOIND (Videocon Industries Ltd): financial year ends in March" in prompt
