# 20 — Phase 4 Progress and Corrected Extraction Map
**NEXORA MEDIQ — Phase 4 (Order Workspace structural refactor)**
Date: 2026-11-12

## What shipped this session

One extraction step, committed and verified: `desktop/supplier-stock-client/src/OwSharedControls.jsx` (new file, 491 lines) now holds `resolveOwColumns`, `OwGridSettings`, `OwSupplierPicker`, `OwExportCard`, `OW_GEAR_PATH`, `OW_EXPORT_COLUMN_DEFS`, `orderOwKeys`, and `healColOrder`, extracted out of `App.jsx` with no behavior change. `App.jsx` shrank from 15,796 to 15,337 lines. Verified: production build succeeds (`vite build`), desktop test suite still 61/61.

This piece was genuinely safe to move in one step because every symbol in it had a fully traced, closed dependency set with no further surprises once checked.

## Why the extraction stopped there this session

Doc 17 (Phase 1's extraction map) undersold the real coupling in this file in three compounding ways, each discovered only by reading the actual code, not by inference:

1. **`PROCUREMENT_UI` is a second, independent shared bridge**, not part of Order Workspace's own exclusive logic. It is consumed by `App.jsx` itself (passed to `NonMovingStock.jsx` at line 762) in addition to `ProcurementWorkspace.jsx` — doc 17 only knew about the Procurement consumer.
2. **`PROCUREMENT_UI`'s own dependencies split across two different regions**: `OwExportCard`/`OwSupplierPicker` (now in the new shared module) and `OrderIntelligence`/`OwDocumentCard`/`exportKit`'s helper functions (`owDefaultExportSettings`, `readOwExportSettings`, etc. — still OW-exclusive-region code). It cannot cleanly move into either a pure "Order Workspace" module or a pure "shared" module without itself staying a composition point.
3. **The formatter utilities are app-wide, not Order-Workspace-exclusive**: `fmtOwQty`, `fmtOwMoney`, `fmtOwDate`, `fmtOwPct`, `owLandingPct` are called from inside Order Workspace, inside the Label Exporter's rendering (lines ~6530-7267, 7830), **and** deep inside the Procurement rendering region itself (lines 9010-9366) — a usage footprint doc 17 had no visibility into from a line-range read alone.

Each of these was found by grep-verifying every symbol's actual call sites before moving it — which is the right level of care for a live production file backing real store operations, but means the safe, fully-traced scope for one sitting is smaller than doc 17 estimated.

## Corrected module boundary (supersedes doc 17's table)

| Module | Contents | Status |
|---|---|---|
| `OwSharedControls.jsx` | `resolveOwColumns`, `OwGridSettings`, `OwSupplierPicker`, `OwExportCard`, `OW_GEAR_PATH`, `OW_EXPORT_COLUMN_DEFS`, `orderOwKeys`, `healColOrder` | **Done, committed, verified** |
| `OwFormatters.js` (not yet created) | `fmtOwQty`, `fmtOwMoney`, `fmtOwDate`, `fmtOwPct`, `fmtOwDateTime`, `fmtOwDaysAgo`, `owLandingPct`, `owWhen`, `owWholeQty`, `owIsClearKeypress`, `owCleanName` — genuinely pure, zero React, but used app-wide (Order Workspace, Label Exporter, Procurement rendering) | Mapped, not extracted. Lowest-risk remaining piece — no React, no hooks, dependency-closed as far as checked — but every call site across the whole ~15.3k-line file needs updating, which is mechanical but large. |
| `OwDocumentCard` cluster | `OwDocumentCard`, `OW_DOC_COLUMNS`, `owFmtDocCell`, `owFmtDateTime` (distinct from `fmtOwDateTime` — confirmed not a duplicate, just a similar name), `owSum`, `owBlank` | Mapped, fully dependency-closed (confirmed no usage outside this cluster), not yet extracted. Depends on `OwFormatters.js` existing first (uses `fmtOwMoney`/`fmtOwQty`/`fmtOwPct`/`fmtOwDate`). |
| `OrderIntelligence` cluster | `OrderIntelligence`, `OwTrendChart`, `OwChartTooltip`, `OW_TREND_SERIES`, `OW_TREND_GROUP_PX`, `owIntelCache`/`owIntelCacheGet`/`owIntelCacheSet` | Mapped. Used by **both** Order Workspace's own body (line ~4857) and `PROCUREMENT_UI.IntelPanel`. Depends on `OwFormatters.js`. Should become its own module (e.g. `OwIntelligencePanel.jsx`), imported by both consumers rather than owned by either. |
| `PROCUREMENT_UI` composition | The bridge object itself | Should **stay in `App.jsx`** (or move to a thin `index`-style module later) composing imports from the above three modules plus the still-OW-exclusive `exportKit` helpers — it is a composition point, not something that belongs inside any single extracted module. |
| `OwLineFacts`, `OwProductInfoCard` | Confirmed Order-Workspace-exclusive (only rendered inside `OrderWorkspace`'s own body, lines ~5476/5824/5859) | Confirmed safe to move into `OrderWorkspace.jsx` whenever that extraction happens — no cross-screen usage found. |
| `OrderWorkspace` component body itself | Lines ~3592-5535 (shrunk after Step 1) | Not yet touched. Depends on `OwFormatters.js`, the `OrderIntelligence` cluster, `OwLineFacts`/`OwProductInfoCard`, and the OW-exclusive export-settings helpers (`owDefaultExportSettings` etc.) — all of which should exist as their own modules before this component itself moves, per the original sequencing idea in doc 17 (still valid: shared pieces before the component that uses them). |

## Recommended sequencing for the remaining work (future session)

1. **`OwFormatters.js`** — pure, no React, but touches the most call sites across the file. Do this first since everything else in the remaining list depends on it.
2. **`OwDocumentCard` cluster** — fully dependency-closed once formatters exist.
3. **`OrderIntelligence` cluster** (`OwIntelligencePanel.jsx`) — depends on formatters; needs both consumers (`OrderWorkspace`'s own render call and `PROCUREMENT_UI`) updated to import from the new location.
4. **`PROCUREMENT_UI`** — update in place in `App.jsx` to import from the three now-separate modules instead of defining things locally; this is where doc 17's "no circular import" comment must be re-verified to still hold.
5. **`OrderWorkspace.jsx`** — the component body itself, last, once everything it depends on already lives outside `App.jsx`.

Each step should repeat this session's verification pattern: `vite build` + `node --test src/*.test.js src/state/*.test.js` (61/61 baseline) before committing, and a grep-verified call-site check for every symbol before moving it — the shortcuts that would make this faster (trusting doc 17's line ranges, assuming a symbol's usage without grepping it) are exactly what produced the three corrections documented above.

## Why this is the right place to stop, not a failure

Every move made this session was verified safe before being committed — nothing was moved on assumption, and the build/test baseline never broke mid-session. The remaining work is now mapped more accurately than doc 17 could map it from outside, which makes the next session's work faster and safer, not slower. Stopping here reflects the actual, now-known complexity of a 15.3k-line production file with real cross-screen coupling, not a process failure.

## Current baseline for the next session to build on

- Backend: 415/415 passing (unchanged from doc 19).
- Desktop: 61/61 passing (unchanged from doc 19 and Phase 2's original baseline).
- `App.jsx`: 15,337 lines (down from 15,796).
- `OwSharedControls.jsx`: 491 lines, new, committed.
- Branch: `nexora-mediq-implementation`, 10 commits ahead of `main`, nothing pushed.
