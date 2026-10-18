"""
base.py - The common shape every LLM provider must follow.

Why this file exists:
The rest of the app (pdf_reader, embeddings, answer) only ever talks to an
LLMClient. It never knows whether Gemini, Claude or OpenAI is behind it.
Each provider is one class that fills in these methods (see gemini.py), and
factory.py picks the right class from a provider name + API key.

A provider doesn't have to support everything (e.g. Claude has no embeddings);
the methods it skips raise NotImplementedError with a clear message.
"""

# --- Imports -----------------------------------------------------------------
# time:     waits between retries.
# Callable: type hint for "a function we can call".
import time
from typing import Callable

# --- Shared settings -------------------------------------------------------------
# Retry rule for temporary errors (rate limit, server busy): wait 2s, 4s, 8s ...
MAX_RETRIES = 5

# What a vector is for. Providers that tune vectors per purpose (Gemini does)
# translate these into their own names; others can ignore them.
DOCUMENT = "document"   # a chunk that will be stored and searched
QUERY = "query"         # a question that searches the chunks


# --- Errors every provider raises the same way ---------------------------------------
class LLMBlocked(RuntimeError):
    """
    The model answered but gave no usable text: empty, cut off (max tokens)
    or stopped by a filter. Retrying won't help.
    """


class RecitationBlocked(LLMBlocked):
    """
    The model refused because the text looks like something already published.
    Common for standard legal/auditor wording. Callers can fall back to local OCR.
    """


# --- The interface ---------------------------------------------------------------------
class LLMClient:
    """
    One provider + one model + one API key.
    Subclasses implement whichever of the three abilities their provider has.
    """

    provider = "base"   # set by each subclass, e.g. "gemini"

    def __init__(self, api_key: str, model: str, embed_dim: int | None = None):
        if not api_key:
            raise ValueError(f"{self.provider}: an API key is required")
        self.api_key = api_key
        self.model = model
        self.embed_dim = embed_dim   # only used by embedding models

    def describe_image(self, png: bytes, prompt: str) -> str:
        """Image + instruction -> text. Never returns blank text (raises LLMBlocked instead)."""
        raise NotImplementedError(f"{self.provider} client does not support images")

    def generate_text(self, prompt: str) -> str:
        """Text prompt -> text reply. Never returns blank text (raises LLMBlocked instead)."""
        raise NotImplementedError(f"{self.provider} client does not support text generation")

    def embed_texts(self, texts: list[str], task: str = DOCUMENT) -> list[list[float]]:
        """Texts -> one vector of embed_dim numbers per text, same order."""
        raise NotImplementedError(f"{self.provider} client does not support embeddings")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r})"


# --- Shared retry helper ------------------------------------------------------------------
def call_with_retries(request: Callable, retryable_code: Callable[[Exception], int | None], label: str):
    """
    Runs request() and returns its result. If it fails and retryable_code(error)
    returns an HTTP code (e.g. 429, 503), waits 2s, 4s, 8s ... and tries again,
    up to MAX_RETRIES times. Other errors (bad key, bad model) are raised at once.
    Each provider passes its own retryable_code, because every SDK reports
    errors differently.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return request()
        except Exception as error:
            code = retryable_code(error)
            if code is None or attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            print(f"  {label} error {code}, retrying in {wait}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
