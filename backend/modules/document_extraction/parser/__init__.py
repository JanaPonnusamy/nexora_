"""Invoice Parser abstraction (pre-Chunk-7).

Business logic (Supplier Detection, Header Extraction, Product Extraction —
Chunks 7-9) must import from here (or parser.base / parser.models) and
never import a specific parser implementation directly. Get a parser via
ParserFactory.create(), call .parse(ocr_document) on it, and consume the
returned InvoiceDocument.
"""

from modules.document_extraction.parser.base import InvoiceParser
from modules.document_extraction.parser.models import (
    DocumentMetadata,
    GSTSummary,
    InvoiceDocument,
    InvoiceHeader,
    InvoiceProduct,
    InvoiceTotals,
    PageRegion,
    RegionType,
    SupplierBlock,
)
from modules.document_extraction.parser.parser_factory import ParserFactory

__all__ = [
    "InvoiceParser",
    "ParserFactory",
    "InvoiceDocument",
    "DocumentMetadata",
    "SupplierBlock",
    "InvoiceHeader",
    "InvoiceTotals",
    "GSTSummary",
    "InvoiceProduct",
    "PageRegion",
    "RegionType",
]
