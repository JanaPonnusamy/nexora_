# 13 — Tenant Export-Defaults Feature Test Report
**NEXORA MEDIQ — Phase 1 Baseline Stabilization**

This document isolates the testing-specific findings for the tenant export-defaults feature (full functional validation is in `12_UNCOMMITTED_WORK_VALIDATION.md`).

## Tests executed for this feature

**None exist to execute.** A targeted grep across every `*.test.js` file in `desktop/supplier-stock-client/src` and every file in `backend/tests/` for `export_default`, `export-default`, and `TenantExportDefaults` returned zero matches on both sides of the stack.

## Why this matters now, not later

This feature has a genuine server-side authorization boundary (`has_full_access` gating the write path) and a genuine data-shape contract (`file_format` enum, `columns` list). Both of those are exactly the kind of logic that regression tests catch regressions in — and exactly the kind of logic a future refactor (Phase 2's `App.jsx` decomposition, which touches `ProcurementWorkspace.jsx` where part of this feature's frontend lives) could silently break without any test to catch it.

## Recommended tests (not implemented in this phase — Phase 1 is read-only)

**Backend (pytest, following the existing project convention):**
1. `GET /export-defaults` with no row present → returns `{"locked": false, "file_format": null, "columns": null}`, HTTP 200.
2. `GET /export-defaults` with a row present → returns the stored values.
3. `PUT /export-defaults` as a non-superadmin → HTTP 403.
4. `PUT /export-defaults` as a superadmin with a valid `file_format` → HTTP 200, row persisted (via repository mock or test DB).
5. `PUT /export-defaults` with an invalid `file_format` (not `xls`/`xlsx`/`csv`) → HTTP 422 (schema validation).
6. `PUT /export-defaults` across a tenant boundary (user's tenant ≠ requested tenant) → HTTP 403 via `assert_tenant_access`.
7. (After the `columns` whitelist defect from `12` is fixed) `PUT /export-defaults` with an unrecognized column key → HTTP 422.

**Frontend (following the existing `*View.js` + `*.test.js` pattern already used for `orderWorkspaceView.js`, `procurementWorkspaceView.js`, etc.):**
1. Rendering the export panel when `locked: true` disables user-level file-format/column controls.
2. Rendering the export panel when `locked: false` leaves controls editable.
3. Graceful handling when the `GET /export-defaults` call itself fails (network/5xx) — confirm the export panel still renders in a sane default state rather than breaking the whole Procurement/Order Workspace screen.

## Test infrastructure note (relevant to item 3 above)

Item 3 above was **not independently verified** in this phase — whether the current frontend code already handles a failed `GET /export-defaults` call gracefully, or whether it could break the surrounding export UI, was flagged in `12` as "not independently re-read line-by-line beyond confirming the overall additive shape of the diff." This should be the first thing checked, manually or via the test above, before this feature is considered safe to ship.

## Verdict

**Not yet testable as "passing" because no tests exist.** The feature is not proven broken — static review in `12` found it architecturally sound apart from the `columns` whitelist gap — but "no defects found by reading the code" and "verified by tests" are different claims, and this report is not making the second one.
