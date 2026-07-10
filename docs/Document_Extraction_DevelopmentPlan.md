# Document Extraction Engine — Development Plan (V1)

Status: Draft — frozen before coding begins. This is the authoritative chunk breakdown; work proceeds strictly in this order, one chunk at a time, stopping after each per the token-saving/build rules.

**Reordering note (2026-07-10):** Chunk 6 was delivered as OCR Abstraction (`ocr/`) plus an Invoice Parser layer (`parser/`, `GenericInvoiceParser`) not originally broken out as its own chunk — both approved. The owner then moved Supplier Detection (originally Chunk 7) out of the immediate sequence and pulled table/column understanding forward in its place: **Chunk 7 is now the Product Table Understanding Engine** (`table_engine/`, this doc's Chunk 7 section below). Supplier Detection is deferred — see the "Chunk 7 (deferred)" section — its exact new position in the sequence is owner-directed when work resumes on it. Chunks 8+ keep their original numbers/scope; Chunk 9 (Product Extraction) now builds directly on the Chunk 7 engine's `StructuredProductRow` output rather than re-deriving column mapping itself.

Testing rule (per module brief): do **not** run the full test suite after every chunk. Each chunk only needs to compile/import cleanly. Integration testing, end-to-end testing, performance testing, and regression testing happen once, after Chunk 18, and repeat until production-ready.

---

## Chunk 1 — Documentation (this chunk)

Deliverables: `Document_Extraction_Design.md`, `Document_Extraction_Database.md`, `Document_Extraction_API.md`, `Document_Extraction_UI.md`, `Document_Extraction_Workflow.md`, `Document_Extraction_DevelopmentPlan.md` (all in `docs/`). Frozen before any code is written. No code changes in this chunk.

## Chunk 2 — Database (done, simplified)

`backend/modules/document_extraction/sql/0001_document_extraction_tables.sql` implements the 6 tables specified in `Document_Extraction_Database.md` (`doc_import`, `doc_product_mapping`, `doc_import_item`, `doc_import_review`, `doc_export_history`, `doc_supplier_layout`) — columns, PKs, FKs, indexes. An earlier 18-table draft was built, reviewed as over-engineered, and discarded before being applied anywhere; this is the schema actually in place.

## Chunk 3 — Backend Skeleton

Create `backend/modules/document_extraction/` package: `__init__.py`, `router.py` (routes stubbed), `schemas.py` (Pydantic models matching the API doc's request/response shapes), `repository.py` (SQLAlchemy/pyodbc data access over the 6 Chunk 2 tables), `service.py` (orchestration skeleton). Mount the router in the main FastAPI app the same way `product_mapping`'s router is mounted — no new mounting pattern. Add new dependencies to `backend/requirements.txt` (§ Dependencies below) but don't wire the heavy libraries in yet.

## Chunk 4 — Upload Engine

Implement `POST /imports` for real: multipart handling, file validation (type/size), storage write per the `data/document_extraction/{import_id}/original/` layout, `doc_import` row creation (`original_file_path`, `source_type`, `status = 'UPLOADED'`), checksum-based duplicate flagging. Stage 1 of the Workflow doc only — no processing kicked off yet.

## Chunk 5 — Image Processing

Implement `preprocessing.py`: PDF page splitting, orientation detection, rotate, deskew, crop, denoise, shadow removal, contrast enhancement, adaptive threshold — run in-process, writing only the final `preview_image_path` and `page_count` back onto `doc_import` (no per-page table). Wire it to run after Upload (Workflow Stage 2). Introduces the OpenCV/Pillow/PDF-splitting dependencies.

## Chunk 6 — OCR Engine

Implement `ocr_engine.py`: PaddleOCR wrapper, writes the whole-document result to `doc_import.ocr_json` + `ocr_confidence`. Wire it to run after Image Processing (Workflow Stage 3). This is the heaviest new dependency (`paddleocr` + `paddlepaddle`) — isolate it behind a thin interface (`ocr_engine.run(page_image_paths) -> dict`) so a future engine swap doesn't ripple into extraction code.

## Chunk 7 — Product Table Understanding Engine (current)

Implement `table_engine/` (`models.py`, `patterns.py`, `column_detector.py`, `row_reconstructor.py`, `table_understanding_engine.py`): converts `InvoiceDocument.products` into `StructuredProductRow`, the canonical per-line-item shape (Product Name, Pack, HSN, Batch, Expiry, Qty, Free Qty, PTR, Purchase Rate, MRP, GST%, Discount%, Amount, Confidence). Generic column detection only — header-keyword, token-position, data-pattern, and neighbour-column signals, never a per-supplier hardcoded layout. Row reconstruction handles merged OCR row-groups, wrapped/multi-line product names, and missing/blank cells. Every row carries self-validation output (row confidence, per-column confidence, missing columns, ambiguous columns). Pure transform: no database, no repository, no ProductCode resolution, no `SupplierProductMapping` lookup — Chunk 9 applies those on top of this engine's output.

## Chunk 7 (deferred) — Supplier Detection

Implement `supplier_detect.py`: GST → DL → Phone → Name priority matching against the existing supplier master, using `rapidfuzz` (already a dependency). Writes the supplier fields directly onto `doc_import` (`matched_supplier_code`, `supplier_match_method`, `supplier_match_confidence`, `is_supplier_unknown`). Also backs the `GET /suppliers/lookup` endpoint (§ API doc §11) since both use the same matching code in-process. Deferred per the 2026-07-10 reordering note above — resume when directed.

## Chunk 8 — Header Extraction

Implement `header_extract.py` + the normalization/column-mapping layer (`normalization.py`) reading `doc_supplier_layout.layout_json`. Writes the header fields directly onto `doc_import`, including `gst_slab_breakup_json`. Seed `doc_supplier_layout` with the global-default mapping plus the two layouts already known from the sample invoices (Sample A / Nathan Medicals style, Sample B / Thanthai Pharma style), so Chunk 16 integration testing has real coverage from day one.

## Chunk 9 — Product Extraction

Implement `item_extract.py`: consumes the Chunk 7 `table_engine`'s `StructuredProductRow` list (instead of re-deriving column mapping from `ocr_json` itself), adds multi-page stitching and the non-item row classifier (banners/bank-details/footer rows) where not already handled by Chunk 7's row reconstruction, and performs product resolution (normalize OCR name → look up/insert `doc_product_mapping` → write `product_code`/`product_guid` onto each `doc_import_item` row). Writes `doc_import_item`.

## Chunk 10 — Validation

Implement `validation.py`: the fixed rule set (invoice/GST/item total reconciliation, duplicate invoice, missing batch/expiry, low confidence). Writes `doc_import.validation_json` + `validation_status`. Wire `POST /validate` and auto-run after extraction (Workflow Stage 7).

## Chunk 11 — Review UI

Frontend: `frontend/src/pages/document-extraction/ReviewPage.tsx` (three-pane layout per UI doc §4 — page preview, header panel, item grid, validation panel), plus the shared Upload, Processing Queue pages needed to reach Review in a real click-path (Upload → Queue → Review is the minimum path to test anything end to end). Wires `PATCH /header`, `PATCH /items/{id}`, exclude, supplier reassignment, keyboard shortcuts — each edit writes a `doc_import_review` row.

## Chunk 12 — Save

Wire `POST /save`: `validation_status != 'FAILED'` gate (or explicit force), sets `reviewed_by`/`reviewed_at`/`saved_at`, `doc_import.status = 'SAVED'`. (Note: per Workflow doc § Stage 9, the actual field persistence already happens live during Review edits in Chunk 11 — this chunk is specifically the finalize/gate step.)

## Chunk 13 — Excel Export

Implement `export_excel.py` (openpyxl): 5-sheet workbook builder (Invoice Header, Products, GST Summary, Validation Errors, OCR Metadata), `xlsx`/`csv` support, `doc_export_history` writes. Wire `POST /exports` + download endpoint. Frontend: Export page.

## Chunk 14 — History

Implement `GET /imports` (list/search/filter/paginate) + `GET /imports/{id}` detail. Frontend: History page + detail drawer, per UI doc §5.

## Chunk 15 — Corrections

Wire `GET /imports/{id}/corrections` reading `doc_import_review` (already being written since Chunk 11). Add the correction-log view to the History detail drawer. This chunk is mostly a read-endpoint + UI panel — the writes exist already, there's no separate audit-table plumbing to build.

## Chunk 16 — Integration

Wire the full stage-to-stage automatic progression (Upload → … → `REVIEW_PENDING`) as one background pipeline per Workflow doc's execution model, replacing the chunk-by-chunk manual-trigger endpoints used during Chunks 4–10 development with the real automatic flow. Implement `POST /reprocess`. Implement `DELETE /imports/{id}` (soft delete). Settings page (supplier-layout JSON editor, confidence threshold) — the last UI page, since it edits the config the earlier chunks now depend on. This is the first point the module is feature-complete end to end.

## Chunk 17 — Performance Optimization

Only after Chunk 16 is functionally complete: index/query tuning against realistic volume, OCR/preprocessing throughput (batching, avoiding redundant page re-reads), pagination/N+1 checks on History and the Processing Queue polling endpoint. Apply the same discipline already used elsewhere in this codebase (see prior Procurement N+1 and debounce/LRU-cache work) — profile before changing, don't guess.

## Chunk 18 — Bug Fixing

Fix whatever Integration/E2E/Performance testing (§ below) surfaces. Last chunk before calling V1 done.

---

## Dependencies introduced (new — none of these exist in `backend/requirements.txt` today)

| Package | Used by | Chunk |
|---|---|---|
| `paddleocr`, `paddlepaddle` | OCR engine | 6 |
| `opencv-python` | Image preprocessing (rotate/deskew/denoise/threshold) | 5 |
| `Pillow` | Image I/O | 5 |
| `pymupdf` (fitz) | PDF page splitting | 5 |
| `openpyxl` | Excel export | 13 |

No changes to existing dependencies (`fastapi`, `sqlalchemy`, `pyodbc`, `pydantic`, `python-dotenv`, `rapidfuzz` are reused as-is).

## Testing — after Chunk 18 only

1. **Integration testing** — full pipeline against both real sample invoices (`assects/sample invoice/*.jpeg`) plus synthetic edge cases (corrupted PDF, rotated-only image, missing GSTIN, duplicate invoice number).
2. **End-to-end testing** — Upload → Review → Save → Export through the actual UI, verifying the exported `.xlsx` opens and matches what was reviewed.
3. **Performance testing** — bulk upload (batch of 20+ files), Processing Queue polling under load, History search over a large `doc_import` table.
4. **Bug fixing** — triage and fix findings from the above.
5. **Regression testing** — re-run 1–3 after fixes; repeat the cycle until clean.

## Explicit exclusions carried through every chunk

No purchase posting, no ERP integration, no accounting, no inventory update, no changes to authentication, no changes to the existing logging pipeline, no modification of `procurement.*`/`sync.*` or any other existing module.
