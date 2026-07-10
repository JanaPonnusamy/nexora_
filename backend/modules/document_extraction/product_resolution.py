"""Product Resolution — interface only (Chunk 9 implements the matching).

Resolves an OCR-extracted product name (scoped to a supplier) to a stable
internal ProductCode, per the module brief's Product Resolution workflow and
docs/Document_Extraction_Design.md § Normalization. Defined now, ahead of
OCR/extraction, because doc_import_item.product_code/product_guid already
depend on this contract existing — item_extract.py (Chunk 9) will call
`resolve_product()` for every line, it must not invent its own shape later.

Resolution order (documented now, implemented in Chunk 9):
  1. EXISTING_MAPPING — already resolved before, found in
     dbo.doc_product_mapping via (supplier_code, normalized_product_key).
     Reuses the existing product_code. Backed by
     repository.resolve_product_code()'s lookup half.
  2. MASTER_PRODUCT — matches an existing product in the platform's product
     master / Product Mapping module (the "SupplierProductMapping" the
     module brief refers to) — a real ProductCode already exists outside
     this module for this supplier+product. Not yet wired to anything;
     Chunk 9 decides whether/how to call into modules.product_mapping.
  3. NEW_MAPPING — neither above matched; a new dbo.doc_product_mapping row
     is created (mints the next DOC000000001-style code). Backed by
     repository.resolve_product_code()'s insert half.

Never creates duplicate mappings for (2) or (3) — enforced at the DB layer by
doc_product_mapping's filtered unique indexes (Database doc), not only by
this interface's contract.
"""

from typing import Literal, Optional

from pydantic import BaseModel

ProductResolutionSource = Literal["EXISTING_MAPPING", "MASTER_PRODUCT", "NEW_MAPPING"]


class ProductResolutionRequest(BaseModel):
    tenant_id: str
    ocr_product_name: str
    supplier_code: Optional[str] = None  # None = global fallback bucket


class ProductResolutionResult(BaseModel):
    product_code: str
    product_guid: str
    confidence: float
    source: ProductResolutionSource


def resolve_product(request: ProductResolutionRequest) -> ProductResolutionResult:
    """Interface only. Matching/normalization logic (including the
    MASTER_PRODUCT lookup) lands in Chunk 9 (Product Extraction). Do not
    call from Chunk 5/6/7/8 code paths — item_extract.py is the only
    intended caller."""
    raise NotImplementedError(
        "Product resolution matching is implemented in Chunk 9 (Product Extraction)"
    )
