"""
doc_types.py - The fixed list of document types, and how to check one.

The list lives in Postgres (doc_types), read through the metadata store
(utils/metadata). Add types with db/samples/add_company.sql (Block 2).
A fixed list keeps free text out: "Annual Report", "annual-report" and
"annual_report" all become the one code "annual_report", so filters never
split a type in two.

    require_doc_type("Annual Report")  -> "annual_report"
    require_doc_type(None)             -> "quarterly_results"  (the default)
    require_doc_type("blog post")      -> ValueError listing the allowed codes
"""

# --- Imports -----------------------------------------------------------------
# get_metadata_store: the configured metadata store (JSON files or Postgres).
from utils.metadata import get_metadata_store


def load_doc_types() -> dict:
    """The whole list: {"default": code, "doc_types": [{"code", "name"}, ...]}."""
    return get_metadata_store().doc_types()


def normalise(text: str) -> str:
    """'Annual Report' / 'annual-report' -> 'annual_report'."""
    return "_".join(text.strip().lower().replace("-", " ").split())


def require_doc_type(text: str | None) -> str:
    """
    The canonical code for this document type. Empty -> the default.
    Raises ValueError (listing the allowed codes) for anything else.
    """
    config = load_doc_types()
    if not text:
        return config["default"]
    code = normalise(text)
    codes = [t["code"] for t in config["doc_types"]]
    if code not in codes:
        raise ValueError(f"Unknown doc_type {text!r}. Allowed: {', '.join(codes)}")
    return code
