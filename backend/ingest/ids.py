"""
ids.py - Generates stable, unique IDs for documents and their chunks.

Why this file exists:
- doc_id   = SHA-256 hash of the PDF's bytes. Same file -> same ID, every time,
             no matter what the file is named or how often it is uploaded.
- point_id = UUID built from (doc_id, page, chunk_no). Qdrant only accepts
             integers or UUIDs as point IDs, so we turn our string into a UUID.
             Same chunk -> same UUID, so re-ingesting overwrites instead of duplicating.
"""

# --- Imports -----------------------------------------------------------------
# hashlib: Python's built-in hashing library (gives us SHA-256).
# uuid:    Python's built-in UUID library (gives us uuid5 = deterministic UUIDs).
# Path:    a friendly way to work with file paths.
import hashlib
import uuid
from pathlib import Path

# --- Settings ----------------------------------------------------------------
# Read files in 1 MB pieces so a big PDF never has to sit fully in memory.
CHUNK_SIZE = 1024 * 1024

# A fixed "namespace" for uuid5. uuid5(namespace, text) always returns the same
# UUID for the same inputs, so this value must NEVER change once you have data
# in Qdrant - changing it would give every chunk a new ID (= duplicates).
POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "stocks-rag/points")


# --- doc_id from raw bytes ---------------------------------------------------
def doc_id_from_bytes(data: bytes) -> str:
    """
    Use this inside FastAPI, where the uploaded file arrives as bytes:
        pdf_bytes = await file.read()
        doc_id = doc_id_from_bytes(pdf_bytes)
    Returns a 64-character hex string, e.g. '3f9a...c21b'.
    """
    return hashlib.sha256(data).hexdigest()


# --- doc_id from a file on disk ----------------------------------------------
def doc_id_from_file(path: str | Path) -> str:
    """
    Use this in local scripts that read a PDF from disk.
    Reads the file piece by piece and feeds each piece into the hash.
    Gives exactly the same result as doc_id_from_bytes() for the same file.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as f:                      # "rb" = read raw bytes
        for block in iter(lambda: f.read(CHUNK_SIZE), b""):
            hasher.update(block)                     # add this piece to the hash
    return hasher.hexdigest()


# --- point_id for one chunk ----------------------------------------------------
def point_id(doc_id: str, page: int, chunk_no: int) -> str:
    """
    Builds the Qdrant point ID for one chunk.
    Example: point_id(doc_id, page=11, chunk_no=0)
    Same (doc_id, page, chunk_no) -> same UUID, so an upsert overwrites the
    old chunk instead of storing a second copy.
    """
    return str(uuid.uuid5(POINT_NAMESPACE, f"{doc_id}:{page}:{chunk_no}"))



# --- Quick manual test -------------------------------------------------------
# Run:  python -m ingest.ids /path/to/file.pdf
# Prints the doc_id and a sample point_id, and checks both helpers agree.
if __name__ == "__main__":
    import sys

    pdf_path = Path(sys.argv[1])
    from_file = doc_id_from_file(pdf_path)
    from_bytes = doc_id_from_bytes(pdf_path.read_bytes())

    print("doc_id (file) :", from_file)
    print("doc_id (bytes):", from_bytes)
    print("match         :", from_file == from_bytes)
    print("point_id p1 c0:", point_id(from_file, page=1, chunk_no=0))
    print("point_id again:", point_id(from_file, page=1, chunk_no=0))
