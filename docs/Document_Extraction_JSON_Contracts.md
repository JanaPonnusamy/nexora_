# Document Extraction Engine — JSON Contracts (frozen)

Status: Frozen before Chunk 5 (Image Processing) begins.
Code mirror: `backend/modules/document_extraction/json_contracts.py` (Pydantic models — keep this doc and that file in sync; the models are the enforceable source of truth, this doc is the human-readable reference).

Every JSON value stored in a `doc_import` column (or returned by the API as a composed structure) must match one of the six contracts below. **Future code must not invent a new JSON shape for a concept already covered here** — extend the model instead.

---

## 1. OriginalFiles — `doc_import.original_files_json`

The authoritative, ordered page list for the import, written once at upload time. This is what makes "one invoice, multiple JPGs / multiple PDF pages / mixed uploads" a single `doc_import` row with proper page order, instead of a separate `doc_page` table.

```json
{
  "files": [
    {
      "page_no": 1,
      "original_file_name": "invoice_page1.jpg",
      "storage_path": "1042/original/invoice_page1.jpg",
      "display_order": 1,
      "rotation": 0,
      "processing_status": "PENDING"
    },
    {
      "page_no": 2,
      "original_file_name": "invoice_page2.jpg",
      "storage_path": "1042/original/invoice_page2.jpg",
      "display_order": 2,
      "rotation": 0,
      "processing_status": "PENDING"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `page_no` | int | 1-based, stable identifier for this page across the whole pipeline |
| `original_file_name` | string | as uploaded by the client |
| `storage_path` | string | relative to the storage root (§ Design doc File storage) |
| `display_order` | int | render order in the Review UI's page navigator — normally equals `page_no`, but lets a user reorder pages later without renumbering |
| `rotation` | int | degrees; `0` at upload time, only ever changed by Chunk 5 |
| `processing_status` | `PENDING`\|`PROCESSING`\|`DONE`\|`FAILED` | `PENDING` at upload; advanced by Chunk 5 |

`original_file_path` (the plain string column) always holds `files[0].storage_path` — a quick-access convenience, not a second source of truth.

---

## 2. ProcessedFiles — `doc_import.processed_files_json`

Written by Chunk 5 (Image Processing). `NULL` until then. One entry per page, produced from the matching `OriginalFiles` entry.

```json
{
  "files": [
    {
      "page_no": 1,
      "processed_storage_path": "1042/preview/page_1.jpg",
      "rotation_degrees": 90,
      "deskew_angle": -1.2,
      "width_px": 1654,
      "height_px": 2339,
      "processing_status": "DONE",
      "processing_notes": null
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `page_no` | int | matches the `OriginalFiles` entry it was derived from |
| `processed_storage_path` | string\|null | the preview/processed image actually shown in Review — see UI doc §4. `null` when `processing_status = "FAILED"` (nothing was produced for that page) |
| `rotation_degrees` | int | applied correction (0/90/180/270) |
| `deskew_angle` | float\|null | fine-angle correction in degrees |
| `width_px` / `height_px` | int\|null | processed image dimensions |
| `processing_status` | `PENDING`\|`PROCESSING`\|`DONE`\|`FAILED` | |
| `processing_notes` | string\|null | set on `FAILED` (or a partial-success caveat) |

---

## 3. OCRResult — `doc_import.ocr_json`

**The normalized OCR model — never the raw PaddleOCR response.** This is the mandatory intermediate layer between the OCR engine and everything downstream (§ OCR output contract, Design doc):

```
PaddleOCR raw response → normalize → OCRResult (this contract, stored in ocr_json)
                                    → Invoice Parser (header_extract.py / item_extract.py)
                                    → Business Model (doc_import header fields / doc_import_item rows)
```

Header/item extraction reads only `OCRResult`. It never touches a raw engine payload — that separation is what lets extraction be re-run (reprocessed) without re-invoking OCR, and lets a human compare "what OCR saw" against "what got interpreted."

```json
{
  "engine_name": "PaddleOCR",
  "engine_version": "2.7.0",
  "average_confidence": 91.2,
  "pages": [
    {
      "page_no": 1,
      "lines": [
        {
          "line_no": 1,
          "text": "NATHAN MEDICALS -C",
          "confidence": 97.5,
          "bbox": { "x1": 120, "y1": 30, "x2": 640, "y2": 70 },
          "words": [
            { "text": "NATHAN", "confidence": 98.1, "bbox": { "x1": 120, "y1": 30, "x2": 230, "y2": 70 } },
            { "text": "MEDICALS", "confidence": 97.0, "bbox": { "x1": 235, "y1": 30, "x2": 420, "y2": 70 } }
          ]
        }
      ]
    }
  ]
}
```

Any OCR engine swap (Chunk 6 uses PaddleOCR; a future engine could differ) only has to produce this shape — extraction code never depends on engine-specific output.

---

## 4. SupplierMatch — API response shape (not stored as its own JSON blob)

Composed on read from `doc_import`'s flat supplier columns (`gst_number`, `dl_number`, `matched_supplier_code`, `supplier_match_method`, `supplier_match_confidence`, `is_supplier_unknown`, ...) by `service.get_extraction()`.

```json
{
  "ocr_supplier_name": "NATHAN MEDICALS -C",
  "matched_supplier_name": "NATHAN MEDICALS -C",
  "matched_supplier_code": "NATHAN-MED-C",
  "gst_number": "33AATFN2362D1ZC",
  "dl_number": "CBP/7464/20/21",
  "supplier_phone": null,
  "supplier_address": null,
  "match_method": "GST",
  "match_confidence": 98.5,
  "is_unknown": false
}
```

**Deliberately not stored as JSON**, unlike the other five contracts: `gst_number`, `dl_number`, and `matched_supplier_code` are indexed (`IX_doc_import_gst_invoice_dup`, `IX_doc_import_supplier_code`) for duplicate-invoice detection and supplier lookup — folding them into a JSON blob would make those indexes impossible. The contract still applies to the *shape callers receive*, just not to storage.

---

## 5. Validation — `doc_import.validation_json`

A **bare JSON array** (not wrapped in an object) of findings:

```json
[
  {
    "rule_code": "MISSING_EXPIRY",
    "severity": "WARNING",
    "field": "items[7].expiry_date",
    "item_id": 9008,
    "message": "Expiry date missing for line 8",
    "expected_value": null,
    "actual_value": null
  },
  {
    "rule_code": "INVOICE_TOTAL_MISMATCH",
    "severity": "ERROR",
    "field": "net_amount",
    "item_id": null,
    "message": "Sum of line amounts (2148.63) does not match net_amount (2152.00)",
    "expected_value": "2152.00",
    "actual_value": "2148.63"
  }
]
```

`item_id = null` means a header/invoice-level finding. `doc_import.validation_status` (`PENDING`\|`PASSED`\|`WARNING`\|`FAILED`) is the summary derived from this array's severities.

---

## 6. ExportInfo — `doc_import.latest_export_json`

A denormalized copy of the most recent `doc_export_history` row for this import — lets Review/History show "last exported" without a join. `doc_export_history` stays the authoritative full list; this is a read-optimization cache only, overwritten (not appended) on every export.

```json
{
  "export_batch_id": "3f2a1e4b-9c3d-4e2a-8f1b-7a6c5d4e3f2a",
  "file_format": "XLSX",
  "storage_path": "_exports/3f2a1e4b-9c3d-4e2a-8f1b-7a6c5d4e3f2a.xlsx",
  "row_count": 143,
  "exported_by": "b6b6c1e2-...",
  "exported_at": "2026-07-09T10:15:00Z"
}
```

---

## Enforcement

`json_contracts.py` defines these six shapes as Pydantic models. Any service-layer code that writes to `original_files_json`, `processed_files_json`, `ocr_json`, `validation_json`, or `latest_export_json` should construct the value via the matching model (`.model_dump()` before handing to `repository.py`) rather than building a raw dict inline — that's what makes "future code must not invent new JSON formats" actually enforceable instead of aspirational.
