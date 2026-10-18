"""
llm - provider-independent access to language models.

    from utils.llm import get_llm, QUERY
    answer_llm = get_llm("answer")          # whatever .env configures for answers
    answer_llm.generate_text("...")

    from utils.llm import create_llm
    create_llm("gemini", api_key, "gemini-3.5-flash")   # any provider + key directly

Files: base.py (interface, errors, retries) - gemini.py (Gemini) - factory.py (picks the class).
"""

from utils.llm.base import DOCUMENT, QUERY, LLMBlocked, LLMClient, RecitationBlocked
from utils.llm.factory import create_llm, get_llm, role_settings

__all__ = ["DOCUMENT", "QUERY", "LLMBlocked", "LLMClient", "RecitationBlocked",
           "create_llm", "get_llm", "role_settings"]
