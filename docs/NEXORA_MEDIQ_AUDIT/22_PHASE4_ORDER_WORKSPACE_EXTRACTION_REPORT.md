# 22 — Phase 4 Order Workspace Extraction Report
**NEXORA MEDIQ — Phase 4**
Date: 2026-11-12

## 1. Extraction summary

Three verified extraction steps landed this session, each committed separately after a passing build + full test baseline. `App.jsx` went from 15,796 lines (Phase 1 baseline) to **15,204 lines** — a reduction of 592 lines (3.7%) — with three new, independently-testable modules created. The remaining, larger pieces (the `OrderIntelligence`/`PROCUREMENT_UI` cluster and the `OrderWorkspace` component body itself) are precisely mapped but not yet extracted — see §8/§9.

## 2. Before / after architecture

**Before:** every grid-settings control, export card, supplier picker, formatter, and document-detail modal used by Order Workspace, Procurement and the Label Exporter screen was defined inline inside the single 15,796-line `App.jsx`, with `PROCUREMENT_UI` (a bridge object letting `ProcurementWorkspace.jsx` reuse OW building blocks without importing `App.jsx` back) also defined there, pulling together pieces scattered across the file.

**After:**
- `OwSharedControls.jsx` (491 lines) — `resolveOwColumns`, `OwGridSettings`, `OwSupplierPicker`, `OwExportCard`, `OW_GEAR_PATH`, `OW_EXPORT_COLUMN_DEFS`, `orderOwKeys`, `healColOrder`. Used by Order Workspace, the Label Exporter screen, and Procurement (via `PROCUREMENT_UI`).
- `OwFormatters.js` (58 lines) — `asArray`, `fmtOwQty`, `fmtOwMoney`, `fmtOwDate`, `fmtOwPct`, `fmtOwSigned`, `owLandingPct`. Pure, no React. Used app-wide: Order Workspace, Label Exporter rendering, and the Procurement rendering region.
- `OwDocumentCard.jsx` (133 lines) — the purchase-invoice/sales-bill detail modal and its fully-closed dependency set (`OW_DOC_COLUMNS`, `owFmtDocCell`, `owFmtDateTime`, `owSum`, `owBlank`).
- `App.jsx` (15,204 lines) — imports from all three; `PROCUREMENT_UI` still composes `OwExportCard`/`OwSupplierPicker`/`OwDocumentCard` (now imported) with `OrderIntelligence` and the `exportKit` helpers (still local, per §8).

## 3. Files created, modified, deleted

**Created:** `OwSharedControls.jsx`, `OwFormatters.js`, `OwDocumentCard.jsx`.
**Modified:** `App.jsx` only (three separate commits, one per extraction step).
**Deleted:** none.

## 4. Business behavior preserved

No business logic, calculation, or API contract was changed in any of the three steps — each was a pure move of existing code into a new file, confirmed by:
- Every symbol's real call sites were grep-verified before moving (not assumed from doc 17's original line-range estimate, which three separate findings this session proved incomplete — see doc 20 and doc 21 §9).
- No function body was edited; only `function foo() {...}` declarations moved location and gained an `export` keyword.
- `PROCUREMENT_UI`'s composition (the existing no-circular-import bridge to `ProcurementWorkspace.jsx`) was preserved exactly — it still assembles the same five keys (`IntelPanel`, `DocumentCard`, `ExportCard`, `SupplierPicker`, `exportKit`), just sourcing three of them from imports now instead of local definitions.
- Role-based access, tenant-aware behavior, and loading/error/empty states inside `OwDocumentCard` are byte-for-byte the same JSX as before the move.

## 5. Tests added

No new tests were added in this session's Phase 4 work specifically — the three moves were pure refactors with no new behavior to test, and the existing 61-test desktop suite (view-model/pure-function tests, per doc 16) continued to serve as the regression gate at every step. This is a known gap, not an oversight: none of `OwSharedControls`, `OwFormatters`, or `OwDocumentCard` have dedicated unit tests yet, consistent with the pre-existing pattern that `App.jsx`'s inline helpers were also untested before extraction. Recommended as follow-up: `OwFormatters.js`'s six pure functions are now trivially testable in isolation and should get a `OwFormatters.test.js` in the next session, following the project's established `*View.js` + `*.test.js` convention.

## 6. Test results (exact commands and output)

```
cd E:\Nexora\desktop\supplier-stock-client
node --test src/*.test.js src/state/*.test.js
```
Run after every one of the three steps. **Result each time: 61 pass, 0 fail, 0 skipped.**

```
cd E:\Nexora\backend
.venv/Scripts/python.exe -m pytest tests/ --tb=short
```
Run after the final step (backend was not touched by any Phase 4 change, included per the validation checklist). **Result: 415 passed, 0 failed, 21 warnings** (same pre-existing deprecation warnings as doc 19/21, unrelated).

## 7. Build results

```
cd E:\Nexora\desktop\supplier-stock-client
npx vite build --mode development
```
Run after every one of the three steps. **Result each time: build succeeded**, module count rising 108 → 109 → 109 → 110 as each new file was added, no errors. Same pre-existing chunk-size-warning (unrelated, present since before this session).

## 8. Known limitations

- **`PROCUREMENT_UI`'s `exportKit` helpers** (`owDefaultExportSettings`, `owMigrateExportSettings`, `readOwExportSettings`, `writeOwExportSettings`, `owExportDateFolder`, `owSaveExport`, `owSafeFileName`, `owSafePathSegment`) are still defined locally in `App.jsx`. They were deliberately left in place this session — moving them requires either moving `PROCUREMENT_UI` itself or accepting a partial, confusing split, and doc 20 already flagged this as needing its own careful pass.
- **The `OrderIntelligence` cluster** (`OrderIntelligence`, `OwTrendChart`, `OwChartTooltip`, `OW_TREND_SERIES`, `OW_TREND_GROUP_PX`, `owIntelCache`/`owIntelCacheGet`/`owIntelCacheSet`) is fully mapped (doc 20) but not extracted. It is used by **both** `OrderWorkspace`'s own render call and `PROCUREMENT_UI.IntelPanel` — a genuine shared module, like `OwSharedControls.jsx`/`OwFormatters.js`/`OwDocumentCard.jsx`, but not yet created.
- **The `OrderWorkspace` component body itself** (currently ~3592-5535, shifted slightly from each extraction above) has not moved. It depends on the still-unextracted `OrderIntelligence` cluster and the still-local `exportKit` helpers, plus its own exclusive helpers (`OwLineFacts`, `OwProductInfoCard`, `owWhen`, `fmtOwDateTime`, `fmtOwDaysAgo`, `owWholeQty`, `owIsClearKeypress`, `owCleanName`, `owQtyDiffTone`, `OwQtyDiffArrow`) — all confirmed OW-exclusive by grep, all correctly left in place.

## 9. Remaining technical debt

Per doc 20's corrected sequencing (reconfirmed still valid after the reconciliation in doc 21):
1. `OwIntelligencePanel.jsx` for the `OrderIntelligence` cluster — next, since it's the last shared piece blocking the `OrderWorkspace` component extraction.
2. Update `PROCUREMENT_UI` in `App.jsx` to import `OrderIntelligence` from the new module instead of defining it locally.
3. `OrderWorkspace.jsx` for the component body itself — last, once everything it depends on lives outside `App.jsx`.
4. Add `OwFormatters.test.js` (and ideally tests for the other two new modules) — a real, low-risk gap left by this session's refactor-only scope.

No destructive or risky debt was introduced — every remaining item is additive extraction work on code that already works correctly today.

## 10. Git status and commit history

Branch: `nexora-mediq-implementation`. Working tree: only the pre-existing, out-of-scope Quick Stock drift and `send_log.json` (both untouched by this session, per doc 21 §8). Commits this session (newest first):

```
a317de8 refactor(desktop): extract OwDocumentCard and asArray
f2f96ba refactor(desktop): extract app-wide OW display formatters
d176faf docs: reconcile concurrent commits 8180792 and 43b303f (Phase 4)
43b303f feat(stock-client): trim SMS login nav to exactly 6 screens         [external]
95bb736 docs: add Phase 4 progress report and corrected extraction map
7a0d2d6 refactor(desktop): extract OW/Procurement shared grid+export controls
8180792 fix(auth): rename SMS purchase-manager role...                     [external]
c74a095 docs: add Phase 3 backend test environment and baseline report
```

No destructive git operations were performed. Nothing was pushed. `order-management-client` was not touched.

## 11. Recommendation for Phase 5

**Do not start Phase 5 (rebranding/Watchdog coordination) yet.** Phase 4 is genuinely in progress, not complete — three of an estimated six extraction steps are done, verified, and committed, with the remaining three precisely scoped (§9). Finishing the `OrderIntelligence` extraction and the `OrderWorkspace.jsx` component move first keeps the structural refactor as one coherent, trackable effort rather than leaving it half-done while rebranding work starts on top of a still-mid-refactor file. Recommend continuing Phase 4 in the next session using the sequencing in §9, then moving to Phase 5 once `App.jsx` no longer contains Order-Workspace-specific component logic.
