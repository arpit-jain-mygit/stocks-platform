"""
test_figures.py - Figure check on answers, one rewrite when a figure is unverified, and
more sources for comparison questions. Offline: the models are stubbed, no calls are made.

Run (from backend/):   python -m pytest
"""

# --- Imports -----------------------------------------------------------------
import pytest

from query import answer as answer_module
from query.figures import figure_problems
from query.search import Hit

SOURCES = ["Revenue 77,673 65,585 Net income 27,747 24,667 Growth 18% 12% 1,234.5 and 57,167"]


@pytest.mark.parametrize("text, found", [
    ("Revenue was $77.7 billion [S2].", True),                 # 77,673 million, rounded
    ("Revenue was $65.6 billion [S2].", True),                 # 65,585 million, rounded
    ("Revenue was $66 billion [S2].", True),                   # 65.585 billion rounds to 66
    ("Revenue was $90 billion [S2].", False),                  # not in the sources
    ("Net income was $27,700 million [S2].", False),           # not printed (27,747 is)
    ("Net income was $27.7 billion [S2].", True),
    ("Revenue grew 18% [S2].", True),
    ("Revenue grew 25% [S2].", False),
    ("In 2025 revenue grew 18% [S2].", True),                  # the year is not a figure
    ("Revenue grew 18% (calculated: 12% on $24,667 million [S2]).", True),   # calculated line skipped
])
def test_figure_is_found_in_the_sources(text, found):
    problems = figure_problems(text, SOURCES)
    assert (problems == []) == found, problems


def test_badly_formatted_figure_is_reported_once():
    problems = figure_problems("Revenue was $77,7 billion [S2].", SOURCES)
    assert problems == ["77,7"]


# --- answer(): one rewrite, then report -----------------------------------------------
class StubModel:
    """Returns the given replies one after another, and records each prompt."""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def hit(text="Revenue 77,673 million", company="MSFT", location=""):
    return Hit(score=0.9, text=text, file_name="deck.pdf", page_start=4, page_end=4, section="Summary",
               kind="table", chunk_no=0, doc_id="d", company_id=company, location=location)


def test_unverified_figure_gets_one_rewrite_then_is_accepted(monkeypatch):
    model = StubModel("Revenue was $90 billion [S1].", "Revenue was $77.7 billion [S1].")
    monkeypatch.setattr(answer_module, "get_llm", lambda role: model)
    monkeypatch.setattr(answer_module, "search", lambda *a, **k: [hit()])
    result = answer_module.answer("What was revenue?")
    assert len(model.prompts) == 2                                      # one rewrite
    assert "not printed in the sources" in model.prompts[1]
    assert result["unverified_figures"] == []
    assert result["answer"] == "Revenue was $77.7 billion [S1]."


def test_figure_still_unverified_after_rewrite_is_reported(monkeypatch):
    model = StubModel("Revenue was $90 billion [S1].", "Revenue was $91 billion [S1].")
    monkeypatch.setattr(answer_module, "get_llm", lambda role: model)
    monkeypatch.setattr(answer_module, "search", lambda *a, **k: [hit()])
    result = answer_module.answer("What was revenue?")
    assert len(model.prompts) == 2
    assert result["unverified_figures"] == ["$91 billion"]


def test_no_rewrite_when_every_figure_is_found(monkeypatch):
    model = StubModel("Revenue was $77.7 billion [S1].")
    monkeypatch.setattr(answer_module, "get_llm", lambda role: model)
    monkeypatch.setattr(answer_module, "search", lambda *a, **k: [hit()])
    result = answer_module.answer("What was revenue?")
    assert len(model.prompts) == 1 and result["unverified_figures"] == []


# --- Comparison questions retrieve more sources ----------------------------------------
@pytest.mark.parametrize("question, comparison", [
    ("How did revenue change compared with last year?", True),
    ("What was the year on year growth?", True),
    ("What were the segment results?", False),
])
def test_comparison_questions_are_detected(question, comparison):
    assert answer_module.wants_comparison(question) is comparison


def test_comparison_question_retrieves_at_least_12_sources(monkeypatch):
    seen = {}

    def fake_search(question, company=None, period=None, doc_type=None, top_k=6):
        seen["top_k"] = top_k
        return []

    monkeypatch.setattr(answer_module, "search", fake_search)
    answer_module.answer("How did revenue change compared with last year?")
    assert seen["top_k"] == answer_module.COMPARISON_TOP_K == 12
    answer_module.answer("What were the segment results?")
    assert seen["top_k"] == 6
