# 17 — Order Workspace Extraction Map
**NEXORA MEDIQ — Phase 1 Baseline Stabilization**

No code was moved or modified in producing this map, per Phase 1 boundaries. This supersedes Phase 0's vaguer "15.8k lines of entangled logic" characterization with a concrete, line-cited boundary.

## Headline correction to Phase 0

`App.jsx` is 15,796 lines (consistent with the ~15.8k estimate), but **`OrderWorkspace` is already a single, named, top-level component function** — not logic scattered loosely throughout the file. This makes the extraction considerably more tractable than Phase 0 implied.

## Structure found

- `function OrderWorkspace({ session, settings, hidden })` — starts at **`App.jsx:4040`**, body runs to just before line 5995 (next top-level function, `owDefaultExportSettings`).
- Rendered once, at `App.jsx:771`: `<OrderWorkspace session={session} settings={runtimeSettings} hidden={activeScreen !== 'order_workspace'} />`, sitting directly beside `<ProcurementWorkspace ...>` at line 774 — **the two are already siblings at the render level**, not entangled into each other.
- `orderWorkspaceVisited` (state flag controlling lazy-mount, analogous to `procurementVisited` for its sibling) lives at line 361, **outside** the `OrderWorkspace` function — this is a navigation-shell concern, not Order Workspace business state, and should stay in `App.jsx`.

## Concrete extraction boundary table

| Line range | Content | Destination |
|---|---|---|
| 361 | `orderWorkspaceVisited` state | Stays in `App.jsx` (nav/lazy-mount shell concern) |
| 3578–4039 | `resolveOwColumns`, `OwGridSettings`, `OwSupplierPicker`, `OwExportCard` | **New shared module** (e.g. `OwSharedControls.jsx`) — confirmed reused by Procurement (`OwGridSettings` re-rendered at line 9512, inside the Procurement rendering region). Must not be duplicated or exclusively owned by either workspace. |
| 4040–5978 | `OrderWorkspace` component body + local state (`qtyRows`, `pendingRows`, `rows`, `workflow`, `exportSettings`, `owColCfg`, `owLayout`, `owRecord`) | New `OrderWorkspace.jsx` |
| 5995–7535 (~1,540 lines) | `ow*`/`Ow*`-prefixed pure helpers and sub-components exclusive to Order Workspace: `owDefaultExportSettings`, `owMigrateExportSettings`, `fmtOwQty`, `owWholeQty`, `OwLineFacts`, `OwProductInfoCard`, `OrderIntelligence`, `OwTrendChart`, `OwChartTooltip`, `OwDocumentCard` | Pure helpers grow the existing `orderWorkspaceView.js`; sub-components go into `OrderWorkspace.jsx` |
| 7536+ | `LabelExporter`-related cluster | Unrelated, out of scope for this extraction |

## Backend dependency — important finding

Order Workspace is backed entirely by `legacy*`-prefixed `client.js` methods (`legacyOrders`, `legacyAssignSupplier`, `legacyQtyCheckRows`, `legacyUpdateOrderQty`, `legacyExportOrder`, `legacyPurchaseDetails`, `legacySaleBill`, and others — roughly 35 distinct calls found). **These are the same `/api/legacy-order/*` endpoints the separate "Legacy Order" nav screen (`LegacyOrderGeneration.jsx`) also calls.** Order Workspace shares a backend surface with Legacy Order, not with Procurement's `pm_router.py`/`PROCUREMENT`-prefixed API family. This matters for sequencing: Order Workspace extraction work is more exposed to churn in `legacy_order/*` (the most actively-committed backend module per `08_INTEGRATION_RISK_REGISTER.md`) than to churn in `pm_router.py`.

## Already-extracted precedent to build on

`orderWorkspaceView.js` (210 lines) already exists and already holds pure display-fact helpers in the project's established view-model pattern (`OW_PANEL_DEFS`, `OW_PANELS_DEFAULT`, `OW_LAYOUT_DEFAULT`, `owNormalizeLayout`), with a paired `orderWorkspaceView.test.js`. **The extraction plan should grow this file** with the additional pure functions from the 5995–7535 cluster, and create a new `OrderWorkspace.jsx` for the component/JSX itself — exactly mirroring the existing `ProcurementWorkspace.jsx` split, not inventing a new pattern.

## Sequencing recommendation for Phase 2

1. Extract the shared cluster (3578–4039) into its own module first — lowest risk, used identically by both workspaces today, no behavior branching to preserve.
2. Extract the pure-helper cluster (5995–7535) into `orderWorkspaceView.js`, adding tests as each function moves (following the existing `*View.js` + `*.test.js` convention) — this is mechanical and testable in isolation.
3. Extract the `OrderWorkspace` component body (4040–5978) into `OrderWorkspace.jsx` last, once its dependencies (steps 1–2) already live outside `App.jsx`.
4. Re-run the full `node --test` suite (61 tests, see `16_EXISTING_TEST_BASELINE.md`) after each step, not just at the end.

## What was not done

No code was moved. This is a mapping exercise only, per Phase 1's Step 6 instruction ("Do not extract or move code yet").
