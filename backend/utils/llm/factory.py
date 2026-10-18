"""
factory.py - Builds the right LLM client from a provider name + API key + model.

Two ways to get a client:
  create_llm("gemini", api_key, "gemini-3.5-flash")   any provider, any key, directly
  get_llm("vision" | "answer" | "embed")              the client configured in .env for that job

Per-role settings in .env (each role can use a different provider):
  VISION_PROVIDER / VISION_MODEL / VISION_API_KEY     reads scanned pages
  ANSWER_PROVIDER / ANSWER_MODEL / ANSWER_API_KEY     writes answers
  EMBED_PROVIDER  / EMBED_MODEL  / EMBED_API_KEY      turns text into vectors
  EMBED_DIM                                           vector size
If a role's API key is empty, the provider's shared key is used
(e.g. GEMINI_API_KEY), so one key can serve every role.

Adding a provider: write one LLMClient subclass (like gemini.py) and add it
to PROVIDERS below. Nothing else in the app changes.
"""

# --- Imports -----------------------------------------------------------------
# os:           reads the per-role settings.
# LLMClient:    the common interface (utils/llm/base.py).
# GeminiClient: Gemini implementation (utils/llm/gemini.py).
import os

from utils.llm.base import LLMClient
from utils.llm.gemini import GeminiClient

# --- Registry: provider name -> class ------------------------------------------------
PROVIDERS: dict[str, type[LLMClient]] = {
    "gemini": GeminiClient,
}

# --- Defaults per role (used when .env doesn't set them) ---------------------------------
ROLES = {
    "vision": {"provider": "gemini", "model": "gemini-3.5-flash"},
    "answer": {"provider": "gemini", "model": "gemini-3.5-flash"},
    "embed":  {"provider": "gemini", "model": "gemini-embedding-001"},
}
DEFAULT_EMBED_DIM = 768

# One client per role, created on first use, then reused.
_clients: dict[str, LLMClient] = {}


# --- Build any client -------------------------------------------------------------------
def create_llm(provider: str, api_key: str, model: str, embed_dim: int | None = None) -> LLMClient:
    """
    Returns a client for this provider, e.g.
        llm = create_llm("gemini", "AIza...", "gemini-3.5-flash")
        llm.generate_text("Hello")
    """
    provider = provider.lower().strip()
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown LLM provider {provider!r}. Available: {', '.join(PROVIDERS)}")
    return PROVIDERS[provider](api_key=api_key, model=model, embed_dim=embed_dim)


# --- The client configured for one job --------------------------------------------------
def role_settings(role: str) -> dict:
    """The provider, model, key and (for embed) vector size for this role, from .env."""
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}. Roles: {', '.join(ROLES)}")
    prefix = role.upper()
    provider = os.getenv(f"{prefix}_PROVIDER") or ROLES[role]["provider"]
    return {
        "provider": provider,
        "model": os.getenv(f"{prefix}_MODEL") or ROLES[role]["model"],
        # Role's own key first, then the provider's shared key (e.g. GEMINI_API_KEY).
        "api_key": os.getenv(f"{prefix}_API_KEY") or os.getenv(f"{provider.upper()}_API_KEY", ""),
        "embed_dim": int(os.getenv("EMBED_DIM", DEFAULT_EMBED_DIM)) if role == "embed" else None,
    }


def get_llm(role: str) -> LLMClient:
    """
    The shared client for "vision", "answer" or "embed", built from .env.
    Fails early with a clear message if the key is missing.
    """
    if role not in _clients:
        settings = role_settings(role)
        if not settings["api_key"]:
            raise RuntimeError(
                f"No API key for role {role!r}: set {role.upper()}_API_KEY or "
                f"{settings['provider'].upper()}_API_KEY in your .env file."
            )
        _clients[role] = create_llm(**settings)
    return _clients[role]
