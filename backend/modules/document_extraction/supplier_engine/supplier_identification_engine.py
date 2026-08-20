"""Chunk 9 — Supplier Identification Engine.

Matches SupplierBlock candidates (raw, unresolved OCR read of the invoice's
letterhead — see parser/models.py) against the existing supplier master
(sync.Suppliers), in priority order GST -> DL -> Phone -> Name. First match
wins; never creates a supplier automatically — an invoice with no match
beyond the confidence bar comes back Unknown Supplier (is_unknown=True),
routed to manual assignment in the Review UI (Chunk 11), same as the
Workflow doc's own "no match does not fail the pipeline" rule.

Store-scoped: sync.Suppliers has no tenant-wide identity, only
(store_id, suppliercode) — see supplier_master_repository.py — so tenant_id
and store_id are required inputs here even though the chunk brief's own
Input list (SupplierBlock, InvoiceHeader) doesn't name them; a document-
extraction import is always uploaded against one store (Procurement store
context precedent), so this isn't scope creep, it's the same scoping every
other query in this platform already requires.

DL number never matches today — sync.Suppliers carries no DL column (see
supplier_master_repository.py's docstring) — but the step stays in the
chain so a future schema fix (syncing dbo.Suppliers.Dlnumber) only requires
changing find_by_dl_number(), not this priority logic.
"""

from typing import List, Optional

from modules.document_extraction.ocr.models import Confidence
from modules.document_extraction.parser.models import InvoiceHeader, SupplierBlock
from modules.document_extraction.supplier_engine import supplier_master_repository as repo
from modules.document_extraction.supplier_engine.models import SupplierMatch

_NAME_MATCH_THRESHOLD = 80.0
_GST_CONFIDENCE = 0.95
_DL_CONFIDENCE = 0.9
_PHONE_CONFIDENCE = 0.7
_AMBIGUOUS_PENALTY = 0.15


class SupplierIdentificationEngine:
    def identify(
        self, tenant_id, store_id, supplier_block: Optional[SupplierBlock],
        header: InvoiceHeader,
    ) -> SupplierMatch:
        if supplier_block is None:
            return _unknown("No supplier block was extracted from the invoice (no letterhead detected).")

        if supplier_block.candidate_gst_number:
            rows = repo.find_by_gst(tenant_id, store_id, supplier_block.candidate_gst_number)
            if rows:
                return _matched(rows, "GST", _GST_CONFIDENCE, f"GST number '{supplier_block.candidate_gst_number}' matched the supplier master.")

        if supplier_block.candidate_dl_number:
            rows = repo.find_by_dl_number(tenant_id, store_id, supplier_block.candidate_dl_number)
            if rows:
                return _matched(rows, "DL", _DL_CONFIDENCE, f"DL number '{supplier_block.candidate_dl_number}' matched the supplier master.")

        if supplier_block.candidate_phone:
            rows = repo.find_by_phone(tenant_id, store_id, supplier_block.candidate_phone)
            if rows:
                return _matched(rows, "PHONE", _PHONE_CONFIDENCE, f"Phone number '{supplier_block.candidate_phone}' matched the supplier master.")

        if supplier_block.candidate_name:
            match = _match_by_name(tenant_id, store_id, supplier_block.candidate_name)
            if match:
                return match

        return _unknown(
            "No GST, DL, phone, or name candidate from the invoice matched an active "
            "supplier in the supplier master."
        )


def _matched(rows: List[dict], field: str, base_confidence: float, reason: str) -> SupplierMatch:
    row = rows[0]
    confidence = base_confidence
    if len(rows) > 1:
        confidence = max(0.1, base_confidence - _AMBIGUOUS_PENALTY)
        reason += f" ({len(rows)} suppliers matched; the first was used.)"
    return SupplierMatch(
        is_unknown=False,
        matched_supplier_code=row["supplier_code"],
        matched_supplier_name=row["supplier_name"],
        matched_field=field,
        confidence=Confidence(score=round(confidence, 4)),
        reason=reason,
    )


def _match_by_name(tenant_id, store_id, candidate_name: str) -> Optional[SupplierMatch]:
    candidates = repo.search_by_name(tenant_id, store_id, candidate_name)
    if not candidates:
        return None

    try:
        from rapidfuzz import fuzz
    except ImportError:  # pragma: no cover - dependency optional at runtime
        scored = [(c, 100.0 if c["supplier_name"].strip().lower() == candidate_name.strip().lower() else 0.0) for c in candidates]
    else:
        scored = [(c, fuzz.token_set_ratio(candidate_name, c["supplier_name"] or "")) for c in candidates]

    best_row, best_score = max(scored, key=lambda pair: pair[1])
    if best_score < _NAME_MATCH_THRESHOLD:
        return None

    return SupplierMatch(
        is_unknown=False,
        matched_supplier_code=best_row["supplier_code"],
        matched_supplier_name=best_row["supplier_name"],
        matched_field="NAME",
        confidence=Confidence(score=round(min(0.85, best_score / 100 * 0.9), 4)),
        reason=f"Supplier name '{candidate_name}' fuzzy-matched '{best_row['supplier_name']}' (score {best_score:.0f}/100).",
    )


def _unknown(reason: str) -> SupplierMatch:
    return SupplierMatch(
        is_unknown=True, matched_supplier_code=None, matched_supplier_name=None,
        matched_field=None, confidence=Confidence(score=0.0), reason=reason,
    )
