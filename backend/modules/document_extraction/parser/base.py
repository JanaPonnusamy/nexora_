"""Invoice Parser abstraction (pre-Chunk-7). Engine-agnostic parser
interface.

Business logic (Supplier Detection, Header Extraction, Product Extraction —
Chunks 7-9) must depend only on InvoiceParser and parser.models, never on a
specific parser implementation. GenericInvoiceParser is the only concrete
implementation today; document-type-specific parsers (medicine invoice,
credit note, delivery challan) are added the same way — a new InvoiceParser
subclass plus a parser_factory.py registry entry.

A parser must never:
  * read the database or call repository.py
  * call supplier/product matching (SupplierProductMapping, doc_product_mapping)
  * generate or resolve a ProductCode
  * write to the database
It is a pure function: OCRDocument in, InvoiceDocument out.
"""

from abc import ABC, abstractmethod

from modules.document_extraction.ocr.models import OCRDocument
from modules.document_extraction.parser.models import InvoiceDocument


class InvoiceParser(ABC):
    @abstractmethod
    def parse(self, document: OCRDocument) -> InvoiceDocument:
        """Pure transform: one OCRDocument in, one InvoiceDocument out. No
        side effects, no I/O beyond reading the input object."""
        raise NotImplementedError

    @abstractmethod
    def parser_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def parser_version(self) -> str:
        raise NotImplementedError
