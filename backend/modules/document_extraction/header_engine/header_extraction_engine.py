"""Chunk 8 — Header Extraction Engine.

Converts InvoiceDocument (header/totals/gst_summary/supplier_block, all
populated by Chunk 6's GenericInvoiceParser as an unvalidated best-effort
single pass) into a HeaderExtractionResult: a consolidated, validated header
with per-field confidence, missing-required-field tracking, and
reconciliation warnings. This is the sole entry point downstream code
(Chunk 9's supplier identification, a future Review UI header panel) should
use.

Pure transform, no I/O:

  1. consolidate  — pull supplier identity (SupplierBlock), transactional
                     fields (InvoiceHeader), money fields (InvoiceTotals),
                     and e-invoice fields onto one ExtractedHeader.
  2. validate      — data-pattern checks per field (GSTIN format, DL number
                      plausibility, date parseability) rather than trusting
                      Chunk 6's flat capture at face value.
  3. neighbour-fill — Item Count has no reliable "label: value" line on most
                      invoices; when Chunk 6 found no such label, the number
                      of extracted product rows is used as a stand-in
                      (documented, lower-confidence, never silent).
  4. reconcile     — cross-check Gross/Taxable/Net/GST-slab-summary amounts
                      against each other; a mismatch beyond OCR-rounding
                      tolerance becomes a warning, not a silent correction.

Never: writes a database, knows a specific supplier's layout, calls a
repository (models.py docstring).
"""

from statistics import mean
from typing import Dict, List, Optional

from modules.document_extraction.header_engine.models import (
    ExtractedHeader,
    HeaderExtractionResult,
    HeaderIssue,
)
from modules.document_extraction.header_engine.patterns import (
    is_plausible_dl_number,
    is_valid_gstin,
    parse_invoice_date,
    values_reconcile,
)
from modules.document_extraction.ocr.models import Confidence
from modules.document_extraction.parser.models import InvoiceDocument

# The only fields a real, usable invoice header cannot do without. Everything
# else (Transport, Salesman, Credit Days, IRN/Ack/QR, ...) is genuinely
# optional on many suppliers' invoices — see Document_Extraction_Design.md
# §10 ("Optional e-invoice fields ... captured when present, never
# required").
_REQUIRED_FIELDS = ["supplier_name", "gst_number", "invoice_number", "invoice_date", "net_amount"]

_PRESENT_STRING_CONFIDENCE = 0.75
_PRESENT_NUMERIC_CONFIDENCE = 0.8
_DERIVED_ITEM_COUNT_CONFIDENCE = 0.45


class HeaderExtractionEngine:
    def extract(self, document: InvoiceDocument) -> HeaderExtractionResult:
        header = ExtractedHeader()
        field_confidence: Dict[str, float] = {}
        warnings: List[HeaderIssue] = []

        _apply_supplier_block(document, header, field_confidence, warnings)
        _apply_header_fields(document, header, field_confidence)
        _apply_totals(document, header, field_confidence)
        _apply_item_count(document, header, field_confidence, warnings)
        _apply_einvoice_fields(document, header, field_confidence)
        _validate_invoice_date(header, field_confidence, warnings)
        _reconcile_totals(document, header, warnings)

        missing_fields = [f for f in _REQUIRED_FIELDS if getattr(header, f) is None]
        confidence = _overall_confidence(document, field_confidence, missing_fields)

        return HeaderExtractionResult(
            header=header,
            confidence=confidence,
            field_confidence=field_confidence,
            missing_fields=missing_fields,
            warnings=warnings,
        )


def _apply_supplier_block(document, header: ExtractedHeader, field_confidence, warnings) -> None:
    block = document.supplier_block
    if block is None:
        warnings.append(HeaderIssue(
            code="NO_SUPPLIER_BLOCK_DETECTED",
            detail="No letterhead block found on page 1 before the first header field/table start.",
        ))
        return

    if block.candidate_name:
        header.supplier_name = block.candidate_name
        field_confidence["supplier_name"] = _PRESENT_STRING_CONFIDENCE

    if block.candidate_gst_number:
        header.gst_number = block.candidate_gst_number
        if is_valid_gstin(block.candidate_gst_number):
            field_confidence["gst_number"] = 0.95
        else:
            field_confidence["gst_number"] = 0.4
            warnings.append(HeaderIssue(
                code="INVALID_GST_FORMAT",
                detail=f"'{block.candidate_gst_number}' does not match the 15-character GSTIN pattern.",
            ))

    if block.candidate_dl_number:
        header.dl_number = block.candidate_dl_number
        if is_plausible_dl_number(block.candidate_dl_number):
            field_confidence["dl_number"] = 0.7
        else:
            field_confidence["dl_number"] = 0.4
            warnings.append(HeaderIssue(
                code="SUSPECT_DL_NUMBER",
                detail=f"'{block.candidate_dl_number}' is too short/irregular to be confident this is a real DL number.",
            ))


_HEADER_STRING_FIELDS = [
    "invoice_number", "invoice_date", "invoice_type", "credit_days",
    "transport", "order_number", "salesman",
]


def _apply_header_fields(document, header: ExtractedHeader, field_confidence) -> None:
    for field_name in _HEADER_STRING_FIELDS:
        value = getattr(document.header, field_name)
        if value:
            setattr(header, field_name, value)
            field_confidence[field_name] = _PRESENT_STRING_CONFIDENCE


_TOTALS_NUMERIC_FIELDS = [
    "gross_amount", "discount_amount", "scheme_discount", "cash_discount",
    "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount",
    "cess_amount", "round_off", "net_amount",
]


def _apply_totals(document, header: ExtractedHeader, field_confidence) -> None:
    for field_name in _TOTALS_NUMERIC_FIELDS:
        value = getattr(document.totals, field_name)
        if value is not None:
            setattr(header, field_name, value)
            field_confidence[field_name] = _PRESENT_NUMERIC_CONFIDENCE


def _apply_item_count(document, header: ExtractedHeader, field_confidence, warnings) -> None:
    if document.totals.item_count is not None:
        header.item_count = document.totals.item_count
        field_confidence["item_count"] = _PRESENT_NUMERIC_CONFIDENCE
    elif document.products:
        header.item_count = len(document.products)
        field_confidence["item_count"] = _DERIVED_ITEM_COUNT_CONFIDENCE
        warnings.append(HeaderIssue(
            code="ITEM_COUNT_DERIVED_FROM_ROWS",
            detail=(
                f"No 'item count' label found on the invoice; using the "
                f"{len(document.products)} extracted product rows as a stand-in count."
            ),
        ))

    if document.totals.total_quantity is not None:
        header.total_quantity = document.totals.total_quantity
        field_confidence["total_quantity"] = _PRESENT_NUMERIC_CONFIDENCE
        # No row-count-style fallback here: InvoiceProduct.quantity isn't
        # populated until Chunk 10/11 resolve each row's Qty column, so
        # summing it now would silently read as 0.0 instead of an honest
        # "missing" signal.


_EINVOICE_FIELDS = ["irn_number", "ack_number", "ack_date", "qr_data"]


def _apply_einvoice_fields(document, header: ExtractedHeader, field_confidence) -> None:
    for field_name in _EINVOICE_FIELDS:
        value = getattr(document.header, field_name)
        if value:
            setattr(header, field_name, value)
            field_confidence[field_name] = _PRESENT_STRING_CONFIDENCE


def _validate_invoice_date(header: ExtractedHeader, field_confidence, warnings) -> None:
    if not header.invoice_date:
        return
    parsed = parse_invoice_date(header.invoice_date)
    if parsed:
        header.invoice_date = parsed
        field_confidence["invoice_date"] = 0.9
    else:
        field_confidence["invoice_date"] = 0.4
        warnings.append(HeaderIssue(
            code="UNPARSEABLE_INVOICE_DATE",
            detail=f"'{header.invoice_date}' does not match any known invoice date format; kept as raw text.",
        ))

    if header.ack_date:
        normalized_ack = parse_invoice_date(header.ack_date)
        if normalized_ack:
            header.ack_date = normalized_ack


def _reconcile_totals(document, header: ExtractedHeader, warnings: List[HeaderIssue]) -> None:
    if header.gross_amount is not None and header.taxable_amount is not None:
        discounts = sum(
            v for v in (header.discount_amount, header.scheme_discount, header.cash_discount)
            if v is not None
        )
        expected_taxable = header.gross_amount - discounts
        if not values_reconcile(expected_taxable, header.taxable_amount):
            warnings.append(HeaderIssue(
                code="GROSS_TAXABLE_MISMATCH",
                detail=(
                    f"Gross ({header.gross_amount}) minus discounts ({discounts}) = "
                    f"{expected_taxable}, but Taxable Amount is {header.taxable_amount}."
                ),
            ))

    if header.taxable_amount is not None and header.net_amount is not None:
        tax_total = sum(
            v or 0.0 for v in (header.cgst_amount, header.sgst_amount, header.igst_amount, header.cess_amount)
        )
        expected_net = header.taxable_amount + tax_total + (header.round_off or 0.0)
        if not values_reconcile(expected_net, header.net_amount):
            warnings.append(HeaderIssue(
                code="NET_AMOUNT_MISMATCH",
                detail=(
                    f"Taxable ({header.taxable_amount}) + GST ({tax_total}) + Round Off "
                    f"({header.round_off or 0.0}) = {expected_net}, but Net Amount is {header.net_amount}."
                ),
            ))

    if document.gst_summary and header.taxable_amount is not None:
        summed_taxable = sum(
            g.taxable_amount for g in document.gst_summary if g.taxable_amount is not None
        )
        if summed_taxable > 0 and not values_reconcile(header.taxable_amount, summed_taxable):
            warnings.append(HeaderIssue(
                code="GST_SUMMARY_TOTALS_MISMATCH",
                detail=(
                    f"GST slab summary rows sum to {summed_taxable} Taxable Amount, "
                    f"but the header reports {header.taxable_amount}."
                ),
            ))


def _overall_confidence(document, field_confidence: Dict[str, float], missing_fields: List[str]) -> Confidence:
    ocr_score = (
        document.metadata.ocr_average_confidence
        if document.metadata.ocr_average_confidence is not None else 0.5
    )
    mean_field = mean(field_confidence.values()) if field_confidence else 0.0
    completeness = 1.0 - (len(missing_fields) / len(_REQUIRED_FIELDS))
    score = 0.3 * ocr_score + 0.45 * mean_field + 0.25 * completeness
    return Confidence(score=round(max(0.0, min(1.0, score)), 4))
