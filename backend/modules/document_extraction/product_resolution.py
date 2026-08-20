"""Product Resolution Engine (Chunk 10).

Resolves an OCR-extracted product name (scoped to a supplier) to a stable
ProductCode, per docs/Document_Extraction_Design.md § Normalization.
doc_import_item.product_code/product_guid depend on this contract —
item_extract.py is the only intended caller.

Resolution order (first match wins, never creates a supplier/product outside
this module's own mapping table — dbo.doc_product_mapping):

  1. EXISTING_MAPPING — already resolved by a prior invoice, found in
     dbo.doc_product_mapping via (supplier_code, normalized_product_key).
     Reuses the existing DOC-style product_code.
     (repository.find_existing_mapping)
  2. MASTER_PRODUCT — this exact supplier already has a known product in the
     platform's real product master, via sync.SupplierProductMatch (the
     "SupplierProductMapping" the module brief refers to) joined to
     sync.Products. Returns the *real* store ProductCode — deliberately not
     a DOC-style code, since a real one already exists — so product_guid is
     None (sync.Products has no GUID identity).
     (product_resolution_repository.find_master_product)
  3. NEW_MAPPING — neither above matched; a new dbo.doc_product_mapping row
     is created (mints the next DOC000000001-style code).
     (repository.create_mapping)

Never creates duplicate mappings — enforced at the DB layer by
doc_product_mapping's filtered unique indexes (Database doc) as well as this
function's own EXISTING_MAPPING-first order.
"""

from typing import Literal, Optional

from pydantic import BaseModel

from modules.document_extraction import product_resolution_repository as _master_repo
from modules.document_extraction import repository as _repo
from modules.product_mapping.normalization import normalize_product_name

ProductResolutionSource = Literal["EXISTING_MAPPING", "MASTER_PRODUCT", "NEW_MAPPING"]

_EXISTING_MAPPING_CONFIDENCE = 1.0
_MASTER_PRODUCT_CONFIDENCE = 0.9
_NEW_MAPPING_CONFIDENCE = 0.5

# ProductCode Integrity Rule — enforced here (service layer), not by a SQL
# FK: doc_import_item.product_code was never able to carry a single FK,
# because a resolved code legitimately lives in one of two different tables
# depending on how it was resolved (sql/0001_document_extraction_tables.sql's
# original FK to doc_product_mapping alone was both un-creatable, due to a
# computed-column length mismatch, and wrong, since MASTER_PRODUCT codes
# never belong in that table).
#
#   product_code_source            bucket      must exist in
#   EXISTING_MAPPING / NEW_MAPPING  DOCUMENT    dbo.doc_product_mapping
#   MASTER_PRODUCT                  MASTER      sync.Products
_DOCUMENT_SOURCES = {"EXISTING_MAPPING", "NEW_MAPPING"}
_MASTER_SOURCES = {"MASTER_PRODUCT"}


class ProductCodeIntegrityError(ValueError):
    """A resolved product_code does not exist in the table its
    product_code_source claims it comes from. Should never happen if this
    module's own resolve_product() is the only writer — signals either a
    resolution-engine bug or a write path that bypassed it."""


def validate_product_code_integrity(tenant_id, store_id, product_code, source: str) -> None:
    if source in _DOCUMENT_SOURCES:
        if not _repo.mapping_code_exists(tenant_id, product_code):
            raise ProductCodeIntegrityError(
                f"ProductCode {product_code!r} (source={source}) not found in doc_product_mapping"
            )
    elif source in _MASTER_SOURCES:
        if not _master_repo.master_product_code_exists(tenant_id, store_id, product_code):
            raise ProductCodeIntegrityError(
                f"ProductCode {product_code!r} (source={source}) not found in sync.Products"
            )
    else:
        raise ProductCodeIntegrityError(f"Unknown product_code_source {source!r}")


class ProductResolutionRequest(BaseModel):
    tenant_id: str
    store_id: Optional[str] = None  # required to consult the store's own master (source 2)
    ocr_product_name: str
    supplier_code: Optional[str] = None  # None = global fallback bucket


class ProductResolutionResult(BaseModel):
    product_code: str
    product_guid: Optional[str] = None  # None for MASTER_PRODUCT — no internal mapping row exists
    confidence: float
    source: ProductResolutionSource


def resolve_product(request: ProductResolutionRequest) -> ProductResolutionResult:
    normalized_key = normalize_product_name(request.ocr_product_name)
    normalized_name = " ".join(request.ocr_product_name.strip().upper().split())

    existing = _repo.find_existing_mapping(request.tenant_id, request.supplier_code, normalized_key)
    if existing:
        return ProductResolutionResult(
            product_code=existing["product_code"], product_guid=existing["product_guid"],
            confidence=_EXISTING_MAPPING_CONFIDENCE, source="EXISTING_MAPPING",
        )

    if request.store_id and request.supplier_code:
        master = _master_repo.find_master_product(
            request.tenant_id, request.store_id, request.supplier_code, normalized_key,
        )
        if master:
            return ProductResolutionResult(
                product_code=master["product_code"], product_guid=None,
                confidence=_MASTER_PRODUCT_CONFIDENCE, source="MASTER_PRODUCT",
            )

    product_code, product_guid = _repo.create_mapping(
        request.tenant_id, request.supplier_code, request.ocr_product_name,
        normalized_name, normalized_key,
    )
    return ProductResolutionResult(
        product_code=product_code, product_guid=product_guid,
        confidence=_NEW_MAPPING_CONFIDENCE, source="NEW_MAPPING",
    )
