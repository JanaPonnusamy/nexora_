"""Chunk 12 — Excel Export.

Builds the 5-sheet workbook exactly as frozen in
docs/Document_Extraction_Excel_Contract.md — column order/labels/types there
are binding; this module must not invent its own layout. Pure: takes
already-fetched rows (repository.get_imports_by_ids /
list_items_by_import_ids), returns bytes. No DB access, no file I/O — the
caller (service.py) owns persisting the result via storage.export_path().

`csv` format is Sheet 2 (Products) only, per the contract's own constraint
(a single table can't represent five sheets).
"""

import csv
import io
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

_DATE_FMT = "%Y-%m-%d"
_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def _slab_get(slab: dict, *keys):
    """gst_slab_breakup_json's exact key names aren't written by any chunk
    yet (Chunk 14/Integration is first) — tolerate either the Excel
    contract doc's short names (rate/taxable/cgst/...) or the GSTSummary
    model's names (gst_percent/taxable_amount/...) so this module works
    whichever one Integration ends up emitting."""
    for key in keys:
        if key in slab and slab[key] is not None:
            return slab[key]
    return None


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.strftime(_DATE_FMT)
    return str(value)[:10]


def _as_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime(_DATETIME_FMT)
    return str(value)


def _write_header_row(ws, headers):
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"


def _autosize(ws, headers):
    for col_idx, header in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = max(12, len(header) + 2)


# --------------------------------------------------------------------------
# Sheet 1 — Invoice Header
# --------------------------------------------------------------------------

_HEADER_COLUMNS = [
    "Import ID", "Supplier Name", "GST Number", "DL Number", "Invoice Number",
    "Invoice Date", "Invoice Type", "Order Number", "Transport", "Salesman",
    "Credit Days", "Gross Amount", "Discount Amount", "Scheme Discount",
    "Cash Discount", "Taxable Amount", "CGST Amount", "SGST Amount",
    "IGST Amount", "CESS Amount", "Round Off", "Net Amount", "Item Count",
    "Total Quantity", "IRN Number", "Ack Number", "Ack Date", "Validation Status",
]


def _header_row(doc: dict) -> list:
    return [
        doc["import_id"], doc.get("supplier_name"), doc.get("gst_number"), doc.get("dl_number"),
        doc.get("invoice_number"), _as_date(doc.get("invoice_date")), doc.get("invoice_type"),
        doc.get("order_number"), doc.get("transport"), doc.get("salesman"), doc.get("credit_days"),
        doc.get("gross_amount"), doc.get("discount_amount"), doc.get("scheme_discount"),
        doc.get("cash_discount"), doc.get("taxable_amount"), doc.get("cgst_amount"),
        doc.get("sgst_amount"), doc.get("igst_amount"), doc.get("cess_amount"), doc.get("round_off"),
        doc.get("net_amount"), doc.get("item_count"), doc.get("total_quantity"),
        doc.get("irn_number"), doc.get("ack_number"), _as_date(doc.get("ack_date")),
        doc.get("validation_status"),
    ]


# --------------------------------------------------------------------------
# Sheet 2 — Products
# --------------------------------------------------------------------------

_PRODUCT_COLUMNS = [
    "Import ID", "Invoice Number", "Line No", "Product Code", "Product Name", "Pack",
    "HSN Code", "Batch Number", "Expiry Date", "Quantity", "Free Quantity", "PTR",
    "Purchase Rate", "MRP", "GST %", "Discount %", "Discount Amount", "Amount", "Confidence",
]


def _product_row(item: dict, invoice_number) -> list:
    return [
        item["import_id"], invoice_number, item["line_number"], item.get("product_code"),
        item.get("normalized_product_name") or item.get("ocr_product_name"), item.get("pack"),
        item.get("hsn_code"), item.get("batch_number"),
        _as_date(item.get("expiry_date")) or item.get("expiry_raw"),
        item.get("quantity"), item.get("free_quantity"), item.get("ptr"), item.get("purchase_rate"),
        item.get("mrp"), item.get("gst_percent"), item.get("discount_percent"),
        item.get("discount_amount"), item.get("amount"), item.get("confidence"),
    ]


# --------------------------------------------------------------------------
# Sheet 3 — GST Summary
# --------------------------------------------------------------------------

_GST_SUMMARY_COLUMNS = [
    "Import ID", "Invoice Number", "GST Rate %", "Taxable Amount", "CGST Amount",
    "SGST Amount", "IGST Amount", "Total GST Amount", "Net Amount",
]


def _gst_summary_rows(doc: dict) -> list:
    slabs = doc.get("gst_slab_breakup_json") or []
    rows = []
    for slab in slabs:
        cgst = _slab_get(slab, "cgst", "cgst_amount") or 0
        sgst = _slab_get(slab, "sgst", "sgst_amount") or 0
        igst = _slab_get(slab, "igst", "igst_amount") or 0
        total = _slab_get(slab, "total", "total_amount")
        if total is None:
            total = cgst + sgst + igst
        rows.append([
            doc["import_id"], doc.get("invoice_number"),
            _slab_get(slab, "rate", "gst_percent"), _slab_get(slab, "taxable", "taxable_amount"),
            _slab_get(slab, "cgst", "cgst_amount"), _slab_get(slab, "sgst", "sgst_amount"),
            _slab_get(slab, "igst", "igst_amount"), total, _slab_get(slab, "net", "net_amount"),
        ])
    return rows


# --------------------------------------------------------------------------
# Sheet 4 — Validation Errors
# --------------------------------------------------------------------------

_VALIDATION_COLUMNS = [
    "Import ID", "Invoice Number", "Rule Code", "Severity", "Field", "Line No",
    "Message", "Expected Value", "Actual Value",
]


def _validation_rows(doc: dict, line_by_item_id: dict) -> list:
    findings = doc.get("validation_json") or []
    rows = []
    for finding in findings:
        item_id = finding.get("item_id")
        rows.append([
            doc["import_id"], doc.get("invoice_number"), finding.get("rule_code"),
            finding.get("severity"), finding.get("field"),
            line_by_item_id.get(item_id) if item_id is not None else None,
            finding.get("message"), finding.get("expected_value"), finding.get("actual_value"),
        ])
    return rows


# --------------------------------------------------------------------------
# Sheet 5 — OCR Metadata
# --------------------------------------------------------------------------

_OCR_METADATA_COLUMNS = [
    "Import ID", "Invoice Number", "Source Type", "Page Count", "OCR Confidence %",
    "Supplier Match Method", "Supplier Match Confidence %", "Uploaded At", "Reviewed At", "Exported At",
]


def _ocr_metadata_row(doc: dict, exported_at: datetime) -> list:
    return [
        doc["import_id"], doc.get("invoice_number"), doc.get("source_type"), doc.get("page_count"),
        doc.get("ocr_confidence"), doc.get("supplier_match_method"), doc.get("supplier_match_confidence"),
        _as_datetime(doc.get("uploaded_at")), _as_datetime(doc.get("reviewed_at")),
        exported_at.strftime(_DATETIME_FMT),
    ]


# --------------------------------------------------------------------------
# Public builders
# --------------------------------------------------------------------------

def build_workbook(imports: list, items: list, exported_at: datetime) -> bytes:
    """`imports`/`items` are raw repository rows (get_imports_by_ids /
    list_items_by_import_ids — the latter WITHOUT excluded rows filtered out,
    since Sheet 4 findings may reference an item that was excluded after the
    finding was raised); this function filters Sheet 2 to non-excluded rows
    itself."""
    imports_by_id = {doc["import_id"]: doc for doc in imports}
    line_by_item_id = {item["item_id"]: item["line_number"] for item in items}

    wb = Workbook()

    ws1 = wb.active
    ws1.title = "Invoice Header"
    _write_header_row(ws1, _HEADER_COLUMNS)
    for doc in imports:
        ws1.append(_header_row(doc))
    _autosize(ws1, _HEADER_COLUMNS)

    ws2 = wb.create_sheet("Products")
    _write_header_row(ws2, _PRODUCT_COLUMNS)
    for item in items:
        if item.get("is_excluded"):
            continue
        doc = imports_by_id.get(item["import_id"], {})
        ws2.append(_product_row(item, doc.get("invoice_number")))
    _autosize(ws2, _PRODUCT_COLUMNS)

    ws3 = wb.create_sheet("GST Summary")
    _write_header_row(ws3, _GST_SUMMARY_COLUMNS)
    for doc in imports:
        for row in _gst_summary_rows(doc):
            ws3.append(row)
    _autosize(ws3, _GST_SUMMARY_COLUMNS)

    ws4 = wb.create_sheet("Validation")
    _write_header_row(ws4, _VALIDATION_COLUMNS)
    for doc in imports:
        for row in _validation_rows(doc, line_by_item_id):
            ws4.append(row)
    _autosize(ws4, _VALIDATION_COLUMNS)

    ws5 = wb.create_sheet("OCR Metadata")
    _write_header_row(ws5, _OCR_METADATA_COLUMNS)
    for doc in imports:
        ws5.append(_ocr_metadata_row(doc, exported_at))
    _autosize(ws5, _OCR_METADATA_COLUMNS)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_products_csv(imports: list, items: list) -> bytes:
    imports_by_id = {doc["import_id"]: doc for doc in imports}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_PRODUCT_COLUMNS)
    for item in items:
        if item.get("is_excluded"):
            continue
        doc = imports_by_id.get(item["import_id"], {})
        writer.writerow(_product_row(item, doc.get("invoice_number")))
    return buffer.getvalue().encode("utf-8-sig")  # BOM so Excel opens UTF-8 CSV correctly
