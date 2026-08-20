"""Supplier Identification Engine (Chunk 9).

Business logic must import from here (or supplier_engine.models) and never
reach into supplier_master_repository.py directly. Build a
SupplierIdentificationEngine, call .identify(tenant_id, store_id,
supplier_block, header), and consume the returned SupplierMatch.
"""

from modules.document_extraction.supplier_engine.models import MatchField, SupplierMatch
from modules.document_extraction.supplier_engine.supplier_identification_engine import (
    SupplierIdentificationEngine,
)

__all__ = ["SupplierIdentificationEngine", "SupplierMatch", "MatchField"]
