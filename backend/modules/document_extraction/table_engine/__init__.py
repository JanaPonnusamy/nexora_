"""Product Table Understanding Engine (Chunk 7).

Business logic must import from here (or table_engine.models) and never
reach into column_detector.py / row_reconstructor.py / patterns.py
directly. Build a TableUnderstandingEngine, call .understand(invoice_document),
and consume the returned TableUnderstandingResult.
"""

from modules.document_extraction.table_engine.models import (
    ColumnType,
    DetectedColumn,
    OUTPUT_COLUMN_TYPES,
    RowIssue,
    StructuredProductRow,
    TableLayout,
    TableUnderstandingResult,
)
from modules.document_extraction.table_engine.table_understanding_engine import (
    TableUnderstandingEngine,
)

__all__ = [
    "TableUnderstandingEngine",
    "TableUnderstandingResult",
    "TableLayout",
    "StructuredProductRow",
    "DetectedColumn",
    "ColumnType",
    "RowIssue",
    "OUTPUT_COLUMN_TYPES",
]
