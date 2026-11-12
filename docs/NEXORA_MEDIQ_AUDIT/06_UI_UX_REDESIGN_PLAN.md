# 06 — UI/UX Redesign Plan
**NEXORA MEDIQ Unification — Phase 0 Audit**

This is a proposed plan only — Phase 0 authorization does not permit starting implementation. It assumes the architecture finding in `01`/`02`: there is one app to redesign, not two to merge.

## Current state

- No design system / component library — styling lives in one `src/styles.css` plus `src/theme.js`, applied ad hoc across `.jsx` files.
- No routing library; navigation is a flat `screens` array (`App.jsx:69-86`) rendered through 5 menubar dropdown groups (`navMenu.jsx`), not a sidebar.
- Branding throughout is "Axythic Supplier Stock" (window title in `main.cjs:238`, `productName`/`appId` in `package.json`, installer artifact name template, logo asset `src/assets/axythic-logo-mark.png` imported at `App.jsx:4`).
- `App.jsx` is ~15.8k lines, mixing navigation shell, Order Workspace business logic, and Procurement wiring together — the single biggest obstacle to a clean visual redesign, since screens are not independently composable components today.

## Proposed direction (subject to approval)

1. **Rebrand surface** — straightforward, bounded: window title string, `package.json` `productName`/`appId`/installer-name template, logo asset swap, in-app header text. Low risk, no business-logic touch.
2. **Navigation redesign** — replace the 5-group menubar dropdown with a sidebar nav grouped per the master prompt's proposed modules (B–I), using the existing `screens` array as the data source so no backend/routing contract changes are needed.
3. **Component library** — introduce a small shared set (buttons, dropdowns, form controls, table shell with sticky headers) used consistently across screens, per the master prompt's "unified reusable component library" ask. This should be introduced incrementally, screen by screen, not as a big-bang rewrite, given the active concurrent backend development noted in `01_PROJECT_STATUS_REPORT.md`.
4. **Dark/light theme** — `src/theme.js` already exists as a seam for this; needs inspection of its current depth before estimating effort (not fully audited this pass).
5. **`App.jsx` decomposition** — extract Order Workspace logic into its own module (paralleling `ProcurementWorkspace.jsx`) *before* or *alongside* the visual redesign of those two screens, not after — redesigning on top of entangled logic will be more expensive and riskier against the active backend churn in `pm_router.py`/`legacy_order/*`.
6. **Dashboard (module A)** — genuinely new screen; build from existing data endpoints first, defer "AI-generated operational insights" copy until real AI capability exists (see `03_COMPLETE_FEATURE_INVENTORY.md` AI section) to avoid overclaiming.

## Explicit non-goals (per master prompt §5 "avoid" list and §7 business-logic preservation)

- No change to purchase quantity calculations, supplier matching rules, stock/sales calculations, scheme/discount logic, or order processing as part of this UI work.
- No SQL procedure or schema changes as part of the UI merge (the one schema change currently in flight — `tenant_export_defaults` — is unrelated, pre-existing work, not part of this redesign).
- No rebrand of `order-management-client` — it stays out of scope entirely (see `04_MODULE_INTEGRATION_MATRIX.md`).

## Open items needing a decision before implementation planning can be finalized

- Depth of existing `src/theme.js` dark/light support (not yet audited).
- Whether Order Workspace/Procurement code separation happens as a dedicated refactor phase or incrementally during the visual redesign — recommend dedicated phase first (see `09_IMPLEMENTATION_PHASE_PLAN.md`).
