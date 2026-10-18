"""
gemini.py - Google Gemini, behind the common LLMClient interface.

Supports all three abilities: images, text and embeddings.
Created by the factory, e.g. create_llm("gemini", api_key, "gemini-3.5-flash").
"""

# --- Imports -----------------------------------------------------------------
# genai/types/errors: Google's official Gemini SDK (package name: google-genai).
# base:               the common interface, errors and retry helper.
from google import genai
from google.genai import errors, types

from utils.llm.base import DOCUMENT, QUERY, LLMBlocked, LLMClient, RecitationBlocked, call_with_retries

# --- Settings ----------------------------------------------------------------
# 429 = too many requests (free-tier limit), 500/503 = Google's side is busy.
RETRYABLE_CODES = {429, 500, 503}

# How many texts go to Gemini in one embedding request.
EMBED_BATCH_SIZE = 50

# Our task names -> Gemini's names. Gemini tunes the vector slightly for each.
TASK_TYPES = {DOCUMENT: "RETRIEVAL_DOCUMENT", QUERY: "RETRIEVAL_QUERY"}


def retryable_code(error: Exception) -> int | None:
    """The HTTP code if this Gemini error is temporary (worth retrying), else None."""
    if isinstance(error, errors.APIError) and error.code in RETRYABLE_CODES:
        return error.code
    return None


class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(self, api_key: str, model: str, embed_dim: int | None = None):
        super().__init__(api_key, model, embed_dim)
        self._sdk: genai.Client | None = None    # created on first call, then reused

    @property
    def sdk(self) -> genai.Client:
        if self._sdk is None:
            self._sdk = genai.Client(api_key=self.api_key)
        return self._sdk

    def _call(self, request):
        return call_with_retries(request, retryable_code, label=f"Gemini {self.model}")

    # --- Image + instruction -> text ---------------------------------------------
    def describe_image(self, png: bytes, prompt: str) -> str:
        response = self._call(lambda: self.sdk.models.generate_content(
            model=self.model,
            contents=[types.Part.from_bytes(data=png, mime_type="image/png"), prompt],
        ))
        return checked_text(response)

    # --- Text prompt -> text -----------------------------------------------------
    def generate_text(self, prompt: str) -> str:
        response = self._call(lambda: self.sdk.models.generate_content(model=self.model, contents=prompt))
        return checked_text(response)

    # --- Texts -> vectors --------------------------------------------------------
    def embed_texts(self, texts: list[str], task: str = DOCUMENT) -> list[list[float]]:
        config = types.EmbedContentConfig(task_type=TASK_TYPES[task], output_dimensionality=self.embed_dim)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[start:start + EMBED_BATCH_SIZE]
            response = self._call(lambda: self.sdk.models.embed_content(
                model=self.model, contents=batch, config=config,
            ))
            vectors.extend(embedding.values for embedding in response.embeddings)

        # Safety check: one vector per text, each of the right size.
        if len(vectors) != len(texts) or any(len(v) != self.embed_dim for v in vectors):
            raise RuntimeError(f"Expected {len(texts)} vectors of size {self.embed_dim} from {self.model}")
        return vectors


# --- Check WHY Gemini stopped, not just whether text came back -------------------
def checked_text(response) -> str:
    """
    Returns the reply text if Gemini finished normally (STOP).
    Anything else (RECITATION, MAX_TOKENS, SAFETY ...) means the text is
    missing or incomplete, so we raise instead of passing it on as complete.
    """
    candidate = response.candidates[0] if response.candidates else None
    reason = candidate.finish_reason if candidate else None
    text = (response.text or "").strip()

    if reason == types.FinishReason.RECITATION:
        raise RecitationBlocked("Gemini refused: text matches published material (RECITATION)")
    if reason not in (types.FinishReason.STOP, None) or not text:
        raise LLMBlocked(f"Gemini gave no usable text (finish_reason={reason}, "
                         f"prompt_feedback={response.prompt_feedback})")
    return text
