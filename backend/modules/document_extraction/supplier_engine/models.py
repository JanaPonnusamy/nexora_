"""Chunk 9 — Supplier Identification Engine. Output models.

SupplierMatch is the ONLY shape this engine produces. It is a pure decision
target: SupplierBlock + InvoiceHeader in (candidates a generic, supplier-
agnostic parser already read off the invoice), SupplierMatch out
(supplier_identification_engine.py).

Per the chunk brief, this engine never creates a supplier automatically — an
unmatched invoice comes back with `is_unknown=True` and `matched_field=None`,
never a fabricated supplier record.
"""

from typing import Literal, Optional

from pydantic import BaseModel

from modules.document_extraction.ocr.models import Confidence

MatchField = Literal["GST", "DL", "PHONE", "NAME"]


class SupplierMatch(BaseModel):
    is_unknown: bool
    matched_supplier_code: Optional[str] = None
    matched_supplier_name: Optional[str] = None
    matched_field: Optional[MatchField] = None
    confidence: Confidence
    reason: str
