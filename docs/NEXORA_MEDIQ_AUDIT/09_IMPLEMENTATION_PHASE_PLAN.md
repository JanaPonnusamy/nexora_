# 09 — Implementation Phase Plan (proposed, pending approval)
**NEXORA MEDIQ Unification — Phase 0 Audit**

Phase 0 authorization does not permit starting any of this. This is a proposed sequence for the owner to approve, reject, or amend.

## Phase 1 — Stabilize baseline
- Get the current uncommitted tenant export-defaults feature committed/merged (risk #4 in `08`).
- Confirm scope decision on `order-management-client` (recommendation: out of scope — needs explicit owner sign-off, not just this audit's recommendation).
- Re-verify the "could not verify" items from `01`/`05` that are relevant to whichever screens Phase 2 touches first.

## Phase 2 — Rebrand (low risk, bounded)
- Window title (`main.cjs:238`), `package.json` `productName`/`appId`, installer artifact-name template, logo asset, in-app header text.
- Coordinate with the `NexoraStockClientWatchdog` package-verification logic (risk #6) before changing `appId`/artifact naming, since the fleet update mechanism depends on consistent naming.
- No business-logic touch — can ship independently and early.

## Phase 3 — Structural refactor (before visual redesign of Order Workspace/Procurement)
- Extract Order Workspace logic out of `App.jsx` into its own module, following the existing `ProcurementWorkspace.jsx` / `*View.js` pattern already used elsewhere in the codebase.
- Add regression tests for extracted logic as it's pulled out, following the existing `*View.js` + `*.test.js` convention.
- This phase exists specifically to reduce risk #2 and #3 from `08` before Phase 4 begins.

## Phase 4 — UI/UX modernization
- Introduce shared component library (buttons, dropdowns, tables, forms) incrementally, screen by screen — not a big-bang rewrite, given ongoing concurrent backend development (risk #3).
- Sidebar navigation replacing the 5-group menubar, sourced from the existing `screens` array (no backend contract change).
- Dark/light theme depth audit and completion (`src/theme.js` — not fully audited yet).
- New Dashboard screen (module A) built from existing data endpoints; no AI-generated content until Phase 5 produces something real to show.

## Phase 5 — AI Intelligence Centre (net-new development, scoped and estimated separately)
- Build out real capability incrementally, each one labeled honestly in the UI as to whether it's a verified calculation or an AI-generated prediction, per master prompt §4G.
- Start from the one real precedent already in the codebase (`shelf_sort_service.py`'s honest `llm_available` degrade pattern) as the template for how new AI features should fail gracefully and disclose their nature.
- Do not backfill UI copy implying forecasting/anomaly-detection/NL-query capability ahead of the backend actually existing.

## Phase 6 — Regression validation
- Confirm all 17 existing screens still function against the real backend (not mocked), per master prompt §9.
- Confirm tenant/store isolation still holds after any refactor (re-run the server-side `assert_tenant_access` pattern checks from `07`).
- Confirm packaging/installer still produces a working signed update recognized by the watchdog service.

## Open questions requiring owner decision before Phase 1 starts
1. Confirm `order-management-client` is out of scope (recommended) or should be folded in as a larger, separately-budgeted rebuild.
2. Confirm whether "AI Intelligence Centre" should ship incrementally (recommended, Phase 5) or is expected alongside the Phase 4 UI redesign.
3. Confirm who owns coordinating the rebrand with the `NexoraStockClientWatchdog` update-verification logic.
