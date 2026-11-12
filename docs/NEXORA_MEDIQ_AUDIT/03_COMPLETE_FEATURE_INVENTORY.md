# 03 — Complete Feature Inventory
**NEXORA MEDIQ Unification — Phase 0 Audit**

All 17 entries below come directly from the `screens` array in `desktop/supplier-stock-client/src/App.jsx` (lines 69-86) — the single source of truth for what's actually navigable in the app today. Every screen maps to a real, present component file; **no stub/placeholder screens were found in the navigation.**

Classification legend: **(1)** Existing & working · **(2)** Existing but incomplete · **(3)** Duplicate functionality · **(4)** Missing integration · **(5)** Broken · **(6)** Planned, not implemented.

| Screen (nav id) | Component | Backend dependency | Class | Notes |
|---|---|---|---|---|
| Stock Availability | `App.jsx` (inline) | `/api/stock-availability/*` | (1) | View-only stock lookup, per prior project memory |
| Stock (Vertical) | `App.jsx` (inline) | same as above | (1) | Alternate layout of the same data |
| Network Stock | `App.jsx` (inline) | stock-availability variant | (1) | All-store view |
| Procurement | `ProcurementWorkspace.jsx` | `pm_router.py` (1193 lines) | (1), actively developed | Supplier queue/assignment, GRN, pending adjust, abnormal-sales review, shelf-sort AI, export-defaults (in-flight) |
| Order Workspace | `App.jsx` (inline, ~`OW_*` constants) | `pm_router.py` shared logic | (1) but (3)-adjacent | Order Workspace logic lives inside `App.jsx` rather than a separate module — overlaps/shares code with Procurement without a clean boundary |
| Order Entry | `PmOrderEntry.jsx` | `pm_router.py` | (1) | |
| Legacy Order | `LegacyOrderGeneration.jsx` | `/api/legacy-order/*` | (1), actively developed | Most recently touched module in git history (tenant-aware warehouse stock fix, commit `799ea15`) |
| Sync Live | `SyncLive.jsx` | `/api/sync/*` | (1) | |
| Supplier Stock Analysis | `supplierCompare.jsx` | `supplier_stock_analysis/repository.py` | (1) | Warehouse-store-scoped per prior memory |
| Rate Analysis | `RateAnalysis.jsx` | `/api/rate-analysis/*` | (1), not re-verified this pass | |
| Non-Moving Stock | `NonMovingStock.jsx` | `/api/non-moving/*` (inferred) | (1) | |
| NMW Sales Report | (reports screen) | `/api/nmw-sales-report/*`, not re-verified | (1) inferred | |
| Time Report | `TimeReport.jsx` | `/api/time-report/*`, not re-verified | (1) inferred | COSEC attendance reporting, ported from standalone Flask app per prior memory |
| Label Exporter | (tools screen) | — | (1) | Merged letter-wise review per prior memory |
| WhatsApp | `storeWhatsApp.jsx` / `supplierWhatsApp.jsx` | `whatsapp/service.py` + `electron/whatsapp.cjs` | (1) | Store-level WhatsApp runs on store PC, per prior memory |
| Schema Sync | `SchemaSyncPage.jsx` | `/api/schema-sync/*` | (1) | |
| Settings | (system screen) | — | (1) | |

Additional components present in `src/` but not independently nav-listed above (used inside the screens listed): `bulkAssign.jsx`, `harvestReview.jsx`, `suggestionPanel.jsx`, `trendChart.jsx`, `storeTrends.jsx`, `siteCheckBar.jsx`, `webPanel.jsx`, `abnormalSales.jsx`.

## AI features — reality check (important for the master prompt's "do not claim unimplemented AI capability" rule)

A repo-wide search for `anthropic|openai|ollama|claude-|gpt-|llm` across `backend/**/*.py` surfaced exactly **one** genuine LLM-backed feature:

- **`backend/modules/procurement/shelf_sort_service.py`** — runs an optional Claude LLM pass over uncategorized product names to suggest shelf/category placement. Returns `{"suggestions": [...], "llm_available": pcat_ai.is_available()}` and degrades honestly to an empty list when no API key is configured. **This is the only real AI feature in the audited surface.**

Everything else in the current UI that sounds AI-adjacent is **rule-based, not model-backed**:
- `suggestion_service.py` (`GET /stores/{id}/products/{code}/suggestions`) — a deterministic best-margin-of-last-5-invoices ranking query, not a model call.
- `trendChart.jsx`, `storeTrends.jsx`, `NonMovingStock.jsx`, `RateAnalysis.jsx` — rule-based aggregation/analysis, no LLM involvement.

**Consequence for §4 of the master prompt ("G. AI Intelligence Centre"):** demand forecasting, anomaly detection beyond the existing rule-based abnormal-sales check, supplier recommendation intelligence beyond the existing ranking query, and natural-language business queries **do not exist today**. Proposing an "AI Intelligence Centre" module is proposing net-new development, not integration of existing capability — classify as **(6) Planned, not implemented** in `04_MODULE_INTEGRATION_MATRIX.md`, and the redesign plan must not present it as already-functional.

## Classification summary

- **(1) Existing & working:** all 17 nav screens, including Procurement/Purchase-Manager functionality and all original Supplier Stock Client functionality — confirming these were never two separate codebases to begin with.
- **(2) Existing but incomplete:** the uncommitted tenant export-defaults lock (backend + frontend both touched, not yet committed as a tested unit — see `01_PROJECT_STATUS_REPORT.md`).
- **(3) Duplicate functionality:** Order Workspace logic duplicated/entangled inside `App.jsx` rather than factored alongside Procurement — a code-organization issue, not a product-duplication issue.
- **(4) Missing integration:** none found — every nav screen has a working backend dependency.
- **(5) Broken functionality:** none found in this pass.
- **(6) Planned but not implemented:** the master prompt's full "AI Intelligence Centre" vision (forecasting, anomaly detection, NL queries, supplier recommendation intelligence) — only the shelf-sort classifier exists today.
