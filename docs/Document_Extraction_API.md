# Document Extraction Engine — API Design (V1, simplified)

Status: Draft — frozen before coding begins (Chunk 1/2 deliverable)
Router: `backend/modules/document_extraction/router.py`
Prefix: `/api/document-extraction` (matches the existing convention — `/api/product-mapping`, `/api/procurement`)
Auth: reuses the platform's existing auth/acting-user mechanism unchanged — no new auth logic is introduced by this module.

All endpoints operate on `import_id` (the `doc_import` PK) as the primary resource identifier — the schema is 6 tables (Database doc), and `doc_import` is the root of all of them.

---

## Conventions

- JSON in/out except upload (`multipart/form-data`) and export download (binary file response).
- Every response includes the resource's current `status` where applicable, so the frontend can poll without a second call.
- Errors use the platform's standard error envelope (unchanged) — `{ "detail": "..." }` on 4xx/5xx, consistent with existing modules.
- Pagination on list endpoints: `page`, `page_size` query params, capped `page_size` (default 25, max 100) — same shape as `product_mapping`'s list endpoints.

---

## 1. Upload

`POST /api/document-extraction/imports`

Multipart upload of one or more files (PDF/JPG/PNG/TIFF) that together represent one invoice, or a batch of independent invoices.

Request (multipart):
- `files`: one or more files
- `store_id` (optional): UNIQUEIDENTIFIER
- `group_as_single_invoice` (bool, default `true` when >1 file uploaded together): if true, all files become one `doc_import` row (`original_file_path` stores a JSON array of paths); if false, each file becomes its own `doc_import` row.

Response `201`:
```json
{ "imports": [ { "import_id": 1042, "status": "UPLOADED", "source_type": "PDF", "page_count": null } ] }
```

Side effects: creates `doc_import` row(s) and immediately kicks off the background pipeline (Upload → Image Processing → OCR → Extraction → Validation — see Workflow doc § execution model). Duplicate-file detection via checksum runs here and sets `is_duplicate` / `duplicate_of_import_id` if a match is found against a recent upload for the same store, but upload is never rejected — duplicates are flagged, not blocked.

---

## 2. OCR

`POST /api/document-extraction/imports/{import_id}/ocr`

Manually (re-)trigger OCR for an import. Normally invoked automatically by the pipeline; exposed explicitly to support reprocessing (§ Reprocess).

Response `202`: `{ "import_id": 1042, "status": "OCR_RUNNING" }`

`GET /api/document-extraction/imports/{import_id}/ocr-raw`

Returns the raw `ocr_json` payload for the document. Used by the Review UI's "show source" trace view, not by the normal review flow.

---

## 3. Extract

`POST /api/document-extraction/imports/{import_id}/extract`

Runs supplier detection + header extraction + item extraction against the stored `ocr_json`. Idempotent — always re-derives the header fields, supplier match, and `doc_import_item` rows from `ocr_json`, never from a previous extraction result, so it is safe to call again after a `doc_supplier_layout` mapping change.

Response `202`: `{ "import_id": 1042, "status": "EXTRACTED" }`

`GET /api/document-extraction/imports/{import_id}/extraction`

Returns the current extraction result: header fields + item rows + supplier match, exactly what the Review UI hydrates on load.

```json
{
  "import_id": 1042,
  "status": "REVIEW_PENDING",
  "supplier": { "matched_supplier_code": "NATHAN-MED-C", "supplier_name": "NATHAN MEDICALS -C", "supplier_match_method": "GST", "supplier_match_confidence": 98.5, "is_supplier_unknown": false },
  "header": { "invoice_number": "26-27D1312", "invoice_date": "2026-07-01", "net_amount": 2152.00, "ocr_confidence": 91.2, "...": "..." },
  "items": [ { "item_id": 9001, "line_number": 1, "product_code": "DOC000004821", "ocr_product_name": "ACILOC 150", "batch_number": "LD26003", "expiry_raw": "06/28", "quantity": 2, "amount": 69.13, "confidence": 88.0 } ]
}
```

---

## 4. Validate

`POST /api/document-extraction/imports/{import_id}/validate`

Runs the validation rule set (Design doc § 13) against the current header/items and writes the result to `doc_import.validation_json` / `validation_status`. Called automatically after extraction and again after every save, but also exposed so the Review UI can re-check after a manual edit without a full save round-trip.

`GET /api/document-extraction/imports/{import_id}/validation`

```json
{ "import_id": 1042, "validation_status": "WARNING", "findings": [ { "rule_code": "MISSING_EXPIRY", "severity": "WARNING", "item_id": 9008, "message": "Expiry date missing for line 8" } ] }
```

(This reads straight out of `doc_import.validation_json` — there is no separate validation table to join.)

---

## 5. Review

`GET /api/document-extraction/imports/{import_id}/review`

Returns everything the Review page needs in one call: extraction result (§3) + validation findings (§4) + preview image URL(s). Avoids the Review UI making several separate round-trips on load.

`PATCH /api/document-extraction/imports/{import_id}/header`

Body: partial header field updates, e.g. `{ "invoice_number": "26-27D1312", "net_amount": 2152.00 }`. Writes the new values directly onto `doc_import`, inserts one `doc_import_review` row per changed field (`item_id = NULL`, old/new value, `corrected_by`), and re-runs validation.

`PATCH /api/document-extraction/imports/{import_id}/items/{item_id}`

Body: partial item field updates, e.g. `{ "batch_number": "LD26003", "expiry_raw": "06/28" }`. Same `doc_import_review` logging + re-validate behavior as header PATCH.

`POST /api/document-extraction/imports/{import_id}/items/{item_id}/exclude`

Marks a line as `is_excluded = 1` (for OCR-mis-captured rows — banners, bank details, "Pending Order" rows per the Sample B artifacts). Does not delete the row, so it stays visible but drops out of validation totals and Excel export.

`POST /api/document-extraction/imports/{import_id}/supplier`

Manual supplier assignment/override when `is_supplier_unknown = true` or the auto-match is wrong. Body: `{ "matched_supplier_code": "NATHAN-MED-C" }` or a free-text override of the detected supplier fields. Sets `supplier_match_method = "MANUAL"`, logs to `doc_import_review`.

---

## 6. Save

`POST /api/document-extraction/imports/{import_id}/save`

Sets `reviewed_by`/`reviewed_at`/`saved_at`, advances `doc_import.status = "SAVED"`. Requires `validation_status != 'FAILED'` unless the caller explicitly passes `force: true` (`WARNING` never blocks save; a `FAILED` validation status requires an explicit override, logged as a `doc_import_review` entry with `field_name = 'validation_override'`).

Request body: `{ "force": false }`
Response: `{ "import_id": 1042, "status": "SAVED" }`

---

## 7. Export Excel

`POST /api/document-extraction/exports`

Body: `{ "import_ids": [1042, 1043], "file_format": "xlsx" }` (single or multi-invoice batch export — one `export_batch_id` groups the whole call, per `doc_export_history`).

Response `201`: `{ "export_batch_id": "…", "download_url": "/api/document-extraction/exports/{export_batch_id}/download", "row_count": 143 }`

`GET /api/document-extraction/exports/{export_batch_id}/download`

Streams the generated `.xlsx` (or `.csv` for the Products-only case) binary. File was already generated and persisted at export time; this endpoint just serves it from storage, it does not regenerate on every download.

`csv` format constraint: since CSV is single-table, `file_format: "csv"` exports **Sheet 2 (Products)** only — documented explicitly so the frontend can grey out CSV when the user needs the GST/header sheets.

---

## 8. History

`GET /api/document-extraction/imports`

List/search imports for the History page. Filters: `status`, `store_id`, `supplier_name`, `invoice_number`, `date_from`, `date_to`, `has_errors` (bool — `validation_status IN ('WARNING','FAILED')`). Paginated, sortable by `uploaded_at`.

`GET /api/document-extraction/imports/{import_id}`

Full detail for a single import — every `doc_import` column, item list, export history, and the correction log. Backs the History detail drawer.

`GET /api/document-extraction/imports/{import_id}/corrections`

The `doc_import_review` rows for the import, paginated — "what did the user change." This is the closest thing to an audit trail this module has, and it is scoped to manual corrections only (upload/OCR/export are already answered directly by `doc_import.uploaded_by`, `doc_export_history.exported_by`, etc.).

---

## 9. Delete

`DELETE /api/document-extraction/imports/{import_id}`

Soft delete. Sets `is_deleted = 1`, `deleted_by`, `deleted_at`. Returns `204`. Excluded from all list/dashboard queries thereafter but not physically removed, so export history and the correction log stay intact.

---

## 10. Reprocess

`POST /api/document-extraction/imports/{import_id}/reprocess`

Body: `{ "from_stage": "ocr" }` — one of `preprocessing`\|`ocr`\|`extraction`\|`validation`. Resets `doc_import.status` to the matching pre-stage value and re-invokes the pipeline from that point:
- `ocr` re-populates `ocr_json` from scratch.
- `extraction` reuses the existing `ocr_json` without re-running PaddleOCR — the common case after a `doc_supplier_layout` mapping fix.
- `validation` just re-runs the rule set against current data.

---

## 11. Supplier Lookup

`GET /api/document-extraction/suppliers/lookup`

Query params: `gst_number` \| `dl_number` \| `phone` \| `name` (at least one required). Used by (a) the Review UI's manual supplier-assignment search box and (b) the pipeline's own supplier-detection step, calling `supplier_detect.py` in-process (not over HTTP internally — this endpoint exists for the UI).

Response: ranked list of candidate matches from the existing supplier master with match method + confidence, same shape as `doc_import`'s own supplier fields.

---

## 12. Supplier Layout (Settings page)

`GET /api/document-extraction/supplier-layouts`

List `doc_supplier_layout` rows (global default + any per-supplier overrides).

`PUT /api/document-extraction/supplier-layouts/{layout_id}`

Body: `{ "layout_json": { "header_fields": [...], "item_columns": [...] } }` — replaces the whole JSON blob for that layout in one call (the Settings page editor saves the full config at once, not field-by-field).

`POST /api/document-extraction/supplier-layouts`

Create a new per-supplier layout (or the global default if `supplier_code` is omitted).

---

## Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| POST | /imports | Upload |
| POST | /imports/{id}/ocr | Trigger/retry OCR |
| GET | /imports/{id}/ocr-raw | Raw OCR JSON trace |
| POST | /imports/{id}/extract | Run extraction |
| GET | /imports/{id}/extraction | Get extraction result |
| POST | /imports/{id}/validate | Run validation |
| GET | /imports/{id}/validation | Get validation findings |
| GET | /imports/{id}/review | Review page bootstrap |
| PATCH | /imports/{id}/header | Edit header field(s) |
| PATCH | /imports/{id}/items/{item_id} | Edit item field(s) |
| POST | /imports/{id}/items/{item_id}/exclude | Exclude mis-parsed row |
| POST | /imports/{id}/supplier | Manual supplier assignment |
| POST | /imports/{id}/save | Finalize review |
| POST | /exports | Generate Excel/CSV |
| GET | /exports/{batch_id}/download | Download generated file |
| GET | /imports | History list/search |
| GET | /imports/{id} | Import detail |
| GET | /imports/{id}/corrections | Manual-correction log |
| DELETE | /imports/{id} | Soft delete |
| POST | /imports/{id}/reprocess | Reprocess from a stage |
| GET | /suppliers/lookup | Supplier search |
| GET/POST/PUT | /supplier-layouts | Column-mapping config (Settings page) |
