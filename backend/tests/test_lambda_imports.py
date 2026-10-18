"""
test_lambda_imports.py - The Lambda API must import without the ingestion-only libraries.

build_lambda.sh leaves pymupdf, python-pptx, python-docx, openpyxl and uvicorn out of the zip.
This runs the import in a fresh Python process where those modules are blocked, so a new
top-level import of one of them fails here instead of at Lambda startup.

Run (from backend/):   python -m pytest
"""

# --- Imports -----------------------------------------------------------------
import subprocess
import sys

BLOCKED = ["pymupdf", "pptx", "docx", "openpyxl", "uvicorn"]


def test_api_imports_without_ingestion_only_libraries():
    code = (
        "import sys\n"
        f"for name in {BLOCKED!r}:\n"
        "    sys.modules[name] = None\n"          # any import of these now raises ImportError
        "import api.main\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-2000:]
