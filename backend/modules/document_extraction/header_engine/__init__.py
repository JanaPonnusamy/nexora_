"""Header Extraction Engine (Chunk 8).

Business logic must import from here (or header_engine.models) and never
reach into header_extraction_engine.py's module-level helpers or patterns.py
directly. Build a HeaderExtractionEngine, call .extract(invoice_document),
and consume the returned HeaderExtractionResult.
"""

from modules.document_extraction.header_engine.header_extraction_engine import (
    HeaderExtractionEngine,
)
from modules.document_extraction.header_engine.models import (
    ExtractedHeader,
    HeaderExtractionResult,
    HeaderIssue,
)

__all__ = [
    "HeaderExtractionEngine",
    "HeaderExtractionResult",
    "ExtractedHeader",
    "HeaderIssue",
]
