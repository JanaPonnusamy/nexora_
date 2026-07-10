# Document Extraction Engine — Workflow (V1, simplified)

Status: Draft — frozen before coding begins (Chunk 1/2 deliverable)

This document walks the pipeline stage by stage — what runs and what it reads/writes — against the simplified 6-table schema (Database doc). It replaces an earlier version written against a discarded 18-table draft; the six conceptual stages are unchanged, only what gets persisted at each one is smaller.

```
Upload → Image Processing → OCR → Supplier Detection → Header Extraction
       → Product Extraction → Validation → User Review → Store Database → Excel Export
```

## Execution model

The whole pipeline (Upload through Validation) runs as one background task per import (FastAPI `BackgroundTasks` — no new queue/broker infrastructure). There is no per-stage job table: progress is tracked entirely through `doc_import.status`, which moves `UPLOADED → OCR_RUNNING → EXTRACTED → REVIEW_PENDING` on success, or to `FAILED` (with `failure_reason` set) at whichever step breaks. The Processing Queue UI polls `GET /imports?status=...` to reflect this.

Because there's no separate job-attempt table, "retry" and "reprocess" both mean the same thing here: re-run the pipeline function from a given point using data already on the `doc_import` row (e.g. re-run extraction against the stored `ocr_json` without calling PaddleOCR again). See § Reprocess.

## Stage 1 — Upload

Input: one or more files (§ API doc). Creates one `doc_import` row: `status = 'UPLOADED'`, `original_file_path` (single path, or a JSON array string for a multi-file invoice), `source_type`, `uploaded_by`/`uploaded_at`. A checksum of the uploaded file(s) is compared against recent `doc_import` rows for the same `store_id` to set `is_duplicate`/`duplicate_of_import_id` — a soft flag, never a rejection.

Failure handling: an unsupported file type or unreadable upload creates the row with `status = 'FAILED'` and a `failure_reason`, rather than rejecting the whole request when a batch contains one bad file among several good ones.

## Stage 2 — Image Processing

Runs in-process, not persisted stage-by-stage: for PDFs, split into page images; then for each page, detect orientation → rotate → deskew → crop borders → shadow removal → noise removal → contrast enhancement → adaptive threshold. Only the final result is written back to the `doc_import` row: `preview_image_path` and `page_count`.

This step exists because both sample invoices needed it in practice — Sample B's pages arrive rotated ~90° and scanned at an angle; Sample A has visible paper texture/shadow that would otherwise degrade OCR confidence on the numeric columns. It just no longer produces a row-per-page audit trail; if a page is unreadable, the pipeline either proceeds with whatever pages did preprocess successfully or fails the whole import (`status = 'FAILED'`) if none did — the difference is a note in `failure_reason`, not a database row.

## Stage 3 — OCR

Runs PaddleOCR against the preprocessed pages and writes the full result to `doc_import.ocr_json` (one JSON payload covering every page) plus `ocr_confidence` (aggregate). This is a single write, not one row per block — bounding-box-level detail is available inside the JSON if extraction logic needs it, but there's no separate queryable block table in V1.

Total OCR failure across all pages → `status = 'FAILED'`. Partial failure (some pages produced no text) is reflected as lower `ocr_confidence` and gaps in `ocr_json`, not a per-page failure record.

## Stage 4 — Supplier Detection

Reads `ocr_json` (header region, page 1) and runs the priority chain **GST → DL → Phone → Name** against the existing supplier master (`supplier_detect.py`, in-process — the same code the Supplier Lookup API endpoint calls). Writes directly onto the `doc_import` row: `ocr_supplier_name`, `matched_supplier_code`, `supplier_match_method`, `supplier_match_confidence`, `is_supplier_unknown`.

No match clearing the confidence threshold does **not** fail the pipeline — `is_supplier_unknown = 1` is set and extraction continues, so the user still gets header/item data to review; supplier assignment becomes a manual step in Review (`PATCH` supplier fields).

## Stage 5 — Header Extraction

Reads `ocr_json`, applies the label mapping from `doc_supplier_layout.layout_json` (keyed by the detected `matched_supplier_code`, falling back to the global-default row) to interpret field labels, and writes the header fields directly onto the same `doc_import` row (`invoice_number`, `invoice_date`, all the amount fields, `gst_slab_breakup_json`, etc.). Both suppliers' completely different footer/GST layouts (single CGST/SGST pair for Sample A, multi-slab rows for Sample B) normalize into the same `gst_slab_breakup_json` shape.

## Stage 6 — Product Extraction

Reads `ocr_json` for all pages, groups OCR text into table rows using line/position geometry, and applies the item-column mapping (also from `doc_supplier_layout.layout_json`) to map whatever column headers the supplier used onto the canonical `doc_import_item` schema. Writes one `doc_import_item` row per line.

**Product resolution** happens per line as part of this stage: normalize the OCR product name → look up `doc_product_mapping` by `(matched_supplier_code, normalized_product_key)` → reuse `product_code` if found, otherwise insert a new `doc_product_mapping` row (which mints the next `DOC000000001`-style code) → write `product_code`/`product_guid` onto the `doc_import_item` row. This is what makes "future invoices reuse the same ProductCode" true without any extra reconciliation step later.

Multi-page stitching: rows accumulate across all pages of the import in page order; a row classifier filters out non-item content — banner/watermark text ("EXPIRY STOCK DO NOT RETURN BACK", "Rapid News"), bank-details blocks, footer/summary rows already captured by header extraction — before they're persisted as `doc_import_item` rows. Rows the classifier is unsure about are still persisted (never silently dropped) but flagged with low `confidence` and left for the user to `is_excluded` in Review if they're not real line items.

## Stage 7 — Validation

Reads the just-written `doc_import` header fields + `doc_import_item` rows, runs the fixed rule set (Design doc § 13), and writes the findings as a JSON array to `doc_import.validation_json`, with `validation_status` summarizing to `PASSED`/`WARNING`/`FAILED`. Always runs to completion — a rule that can't compute (e.g. a null amount) produces a finding, it never throws and aborts the stage. Sets `status = 'REVIEW_PENDING'` when done.

## Stage 8 — User Review

Human-in-the-loop, driven through the Review API/UI. Every field edit (header or item) writes one row to `doc_import_review` (field name, old value, new value, who, when) and updates the field directly on `doc_import`/`doc_import_item` — edits are applied immediately, not batched, so `doc_import_review` is a change log, not the source of truth for current values.

Re-running validation after edits (same Stage 7 logic, callable on demand) is the review loop: edit → re-validate → see remaining findings → edit again → Save.

## Stage 9 — Store Database

"Store" here means finalizing review (`POST .../save`): by this point `doc_import`/`doc_import_item` already hold the current data, since Review edits are written immediately. Save's job is only to: (a) enforce the no-unresolved-`FAILED`-findings gate (unless the caller forces it), (b) set `reviewed_by`/`reviewed_at`/`saved_at`, (c) advance `status = 'SAVED'`.

## Stage 10 — Excel Export

Reads `doc_import` (header + `gst_slab_breakup_json` + `validation_json`) and `doc_import_item` (excluding `is_excluded = 1`) for one or more `SAVED` imports, builds the 5-sheet workbook (Design doc § 15), writes it to `export/{export_batch_id}.xlsx`, and inserts one `doc_export_history` row per import in the batch. Re-export is always allowed and always produces a new `export_batch_id` — history is additive.

---

## Logging

Each stage emits one structured log entry through the platform's existing logging pipeline (unmodified) containing: Start Time, End Time, Duration, Pages, Products, Confidence, Errors. This is a logging concern, not a database table — it backs the Dashboard's aggregate metrics and gives ops a per-stage timing breakdown without a `doc_processing_job`-style table to maintain.

## Reprocess

`POST /imports/{id}/reprocess` with `from_stage: 'ocr' | 'extraction' | 'validation'` resets `doc_import.status` to the matching pre-stage value and re-invokes the pipeline from that point:
- `from_stage: 'ocr'` re-runs OCR through validation (re-populates `ocr_json` from scratch).
- `from_stage: 'extraction'` reuses the existing `ocr_json` and re-runs supplier detection through validation — the common case after a `doc_supplier_layout` mapping fix, and why OCR output is kept separately from the derived header/item fields.
- `from_stage: 'validation'` just re-runs the rule set against current data.

## Error handling summary

| Failure | Handling |
|---|---|
| Corrupted PDF | Import → `FAILED`, reason recorded, other files in the same batch unaffected |
| Unreadable image / OCR failure on some pages | Pipeline continues with whatever pages did produce text; `ocr_confidence` reflects the gap |
| Total OCR failure | Import → `FAILED` |
| Missing header field | Field left NULL with low `ocr_confidence`; surfaced in Review, not a pipeline failure |
| Broken table (product extraction) | Uncertain rows persisted with low confidence rather than dropped |
| Invalid invoice (fails validation) | Never blocks save by itself — `validation_status = 'WARNING'`/`'FAILED'` surfaced in Review, user decides (or forces save) |
| Database failure mid-stage | Each stage's write is a single row update, so a failure leaves `doc_import` at its last successfully completed `status` — safe to retry/reprocess from there |
