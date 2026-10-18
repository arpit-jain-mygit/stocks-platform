"""
ingest/formats - one reader per file type (PDF, CSV, Excel, PowerPoint, Word, text, Markdown).

Use the factory: from ingest.formats import read_document, check_format, SUPPORTED
"""
from ingest.formats.factory import SUPPORTED, check_format, get_reader, read_document

__all__ = ["SUPPORTED", "check_format", "get_reader", "read_document"]
