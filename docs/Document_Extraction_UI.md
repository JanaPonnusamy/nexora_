# Document Extraction Engine — UI Design (V1)

Status: Draft — frozen before coding begins (Chunk 1 deliverable)
Location: `frontend/src/pages/document-extraction/` (new folder, mirrors `pages/mapping/`, `pages/procurement/`)
Route root: `/document-extraction/*`
Layout: desktop-first (matches the platform's existing desktop-first modules — Purchase Manager, Product Mapping). No mobile layout in V1; mobile is only a **capture** source (camera photo upload), not a review surface.

---

## Pages

### 1. Dashboard (`/document-extraction`)

At-a-glance module home. Cards: documents uploaded today/this week, pending review count, failed count, average confidence, recent activity feed (last N imports with status chips). Entry points to Upload and Processing Queue. No editing here — pure summary, same role as other modules' landing dashboards.

### 2. Upload (`/document-extraction/upload`)

- Drag-and-drop zone (full-width drop target) + a standard file picker button, accepting `.pdf .jpg .jpeg .png .tiff`.
- Multi-file selection with a per-file thumbnail strip before submit.
- A toggle: **"These files are pages of one invoice"** vs **"Each file is a separate invoice"** — maps directly to the `group_as_single_invoice` upload flag (API doc §1). Defaults on when ≥2 files of the same apparent supplier/batch are dropped together (heuristic, not blocking).
- Optional store selector (only shown if the acting user has access to more than one store — same store-scoping pattern as Procurement).
- Submit shows per-file upload progress, then redirects to Processing Queue filtered to the just-created imports.
- Camera capture on touch/mobile browsers uses the native `<input capture>` file picker — no custom camera UI in V1.

### 3. Processing Queue (`/document-extraction/queue`)

Live-updating table of in-flight imports: thumbnail, supplier (or "Unknown Supplier" badge), file name, current stage (chip matching the `doc_import.status` state machine), progress, confidence once available, error indicator. Row actions: **Retry stage** (calls the relevant single-stage endpoint — OCR/Extract/Validate, not a full restart), **View** (jumps to Review once `REVIEW_PENDING`), **Cancel/Delete**.

Polling: short-interval GET on `/imports?status=...` while any row is non-terminal; stops polling once all visible rows reach `REVIEW_PENDING`, `SAVED`, or `FAILED`.

### 4. Review (`/document-extraction/review/{import_id}`)

The core workspace — three-pane desktop layout:

```
┌───────────────┬─────────────────────────────┬──────────────┐
│  Page Preview │        Header Panel          │  Validation  │
│  (image, zoom,│  Supplier / Invoice No /     │  panel (list │
│  page nav)    │  Date / Amount / Status /    │  of errors + │
│               │  Confidence — editable       │  warnings,   │
│               ├─────────────────────────────┤  click to    │
│               │        Item Grid             │  jump to the │
│               │  Product/Batch/Expiry/Qty/   │  offending   │
│               │  Free/PTR/MRP/GST/Amount/    │  row/field)  │
│               │  Confidence — editable rows  │              │
└───────────────┴─────────────────────────────┴──────────────┘
```

- **Page Preview**: shows the preview rendition (`preview_image_path`), not the raw original, so what the user reviews matches what OCR actually saw. Page navigation for multi-page invoices (Sample B pattern — items span pages 1–3, banners/bank-details pages must still be viewable even though they contribute no items).
- **Header Panel**: every header field on `doc_import` inline-editable; supplier row shows the detected match + confidence, with a "Change supplier" action opening the Supplier Lookup search (API §11) when `is_supplier_unknown` or the match looks wrong.
- **Item Grid**: dense editable grid (one row per `doc_import_item` row). Each cell shows OCR confidence via a subtle background tint (see § Highlighting). Row-level "Exclude" action for OCR-mis-captured rows (banner/bank-details text a table parser swept up — matches the Sample B artifacts). Adding a row manually is supported for a line the parser missed entirely; deleting is implemented as Exclude, never a hard delete, so the row stays visible/reviewable.
- Bottom bar: validation summary (`validation_status` + finding count), **Save** button (disabled — or confirm-to-force — while `validation_status = FAILED`, per API §6), **Reprocess** dropdown (from OCR / from Extraction).

**Highlighting rules:**
- Missing required field → red outline on the cell/field.
- Confidence below threshold (configurable, default 80%) → amber background tint, darker as confidence drops.
- Field edited by a user → small "edited" dot, distinguishing human corrections from OCR output at a glance.
- Excluded row → dimmed/struck-through, collapsed by default with a "N excluded rows" expander.

**Keyboard shortcuts** (desktop-first requirement):
- `↑`/`↓` — move active row in item grid
- `Tab`/`Shift+Tab` — move field within a row
- `Enter` — commit cell edit
- `Esc` — cancel cell edit
- `Ctrl+S` — Save
- `Ctrl+→`/`Ctrl+←` — next/previous page in preview
- `E` (row focused) — toggle Exclude on the focused row

### 5. History (`/document-extraction/history`)

Searchable/filterable table over all imports (§ API `GET /imports`): date range, supplier, invoice number, status, has-errors. Row click opens a read-mostly detail drawer (header summary, item count, confidence, export history, correction log) with a **Re-open for review** action if further edits are needed (re-enters the Review page even after `SAVED`) and a **Reprocess** action.

### 6. Export (`/document-extraction/export`)

Multi-select from a History-like list (defaults to `SAVED` imports not yet exported, or already-exported ones for re-export) → choose format (`xlsx`/`csv`, CSV disabled when multiple invoices or non-Products sheets are needed — per API §7 constraint) → **Generate** → download link + row count summary. Past exports listed below with re-download links (reads `doc_export_history`).

### 7. Settings (`/document-extraction/settings`)

- **Supplier layout editor**: per-supplier and global-default source-label → canonical-field mappings (Design doc §12), backed by `doc_supplier_layout.layout_json` — add/edit/remove alias rows, e.g. add `"Trade Rate"` as another label for `PURCHASE_RATE`. The editor works on the JSON structure directly (a simple label-list-per-field form), not a relational template builder.
- **Confidence threshold** for the amber-highlight cutoff used in Review.

No user/role management here — that's out of scope, unchanged from platform auth.

---

## Cross-cutting UI notes

- **Confidence display**: always shown as a percentage badge, never a raw score — consistent unit across header fields, item cells, and the Processing Queue.
- **Unknown Supplier**: surfaced as a distinct orange badge everywhere an import is listed (Queue, History, Dashboard activity feed), not just buried in the Review page, since it is the one condition that always needs a human decision.
- **Empty/failed states**: a `FAILED` import shows its `failure_reason` directly in the Queue/History row, not just a generic "Failed" chip — this maps to the graceful-error-handling requirement (Design doc §16).
- No new global nav pattern — the module gets one top-level nav entry ("Document Extraction") linking to the Dashboard, consistent with how Product Mapping and Reports are surfaced today.
