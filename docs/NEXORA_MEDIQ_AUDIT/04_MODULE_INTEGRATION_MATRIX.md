# 04 — Module Integration Matrix
**NEXORA MEDIQ Unification — Phase 0 Audit**

This matrix maps the master prompt's proposed module structure (§4) onto what actually exists today, per `03_COMPLETE_FEATURE_INVENTORY.md`.

| Proposed module (master prompt) | Maps to existing | Integration action needed |
|---|---|---|
| A. Dashboard | **Does not exist today.** No dashboard/overview screen in the 17-screen nav. | Net-new screen. Can be built from existing data sources (stock, procurement, supplier) without new backend logic for most KPIs; "AI-generated operational insights" should be scoped down to what's real (see AI note below) or explicitly marked aspirational. |
| B. Inventory Intelligence | Stock Availability, Stock (Vertical), Network Stock, Non-Moving Stock | Already exists as separate nav items; consolidate under one grouped section in the redesigned nav, no backend change needed. "Excess stock" / "low-stock alerts" as named concepts not confirmed to exist as dedicated backend logic — verify before promising them in UI copy. |
| C. Procurement Workspace | `ProcurementWorkspace.jsx` + Order Workspace (inside `App.jsx`) + `PmOrderEntry.jsx` + `LegacyOrderGeneration.jsx` | Already functionally complete; the actual work here is code-organization (extract Order Workspace out of `App.jsx` into its own module) plus visual redesign, not integration. |
| D. Supplier Intelligence | Supplier Stock Analysis (`supplierCompare.jsx`), Rate Analysis, supplier WhatsApp, Web Panel (supplier portals) | Already exists; consolidate under one nav group. |
| E. Purchase Management | GRN submit, pending-order adjust (inside `pm_router.py`/Procurement screens) | Already exists inside Procurement; master prompt treats it as a distinct top-level module — recommend keeping it as a tab/section within Procurement rather than forcing a new top-level split, since the data and backend are shared. |
| F. Sales Intelligence | NMW Sales Report, Time Report (attendance, not sales — naming overlap risk), abnormal-sales review | Partially exists; "sales-based purchase recommendations" as a distinct capability is not confirmed — the existing `suggestion_service.py` ranking is supplier-margin-based, not sales-demand-based. Verify before promising. |
| G. AI Intelligence Centre | Only the shelf-sort Claude classifier (`shelf_sort_service.py`) | **Mostly net-new.** Demand forecasting, anomaly detection (beyond existing rule-based abnormal-sales check), supplier recommendation intelligence, NL queries — none exist. Must be scoped and estimated as new development in `09_IMPLEMENTATION_PHASE_PLAN.md`, not assumed as an integration task. |
| H. Reports and Analytics | NMW Sales Report, Time Report, Label Exporter, existing export functionality (`client.js` export calls, Electron `.xls/.xlsx/.csv` write) | Already exists, scattered across multiple screens; consolidating under one "Reports" nav group is a UI reorganization, not new backend work. |
| I. Settings and Administration | Settings screen (exists, scope not deeply audited), tenant/role model (backend-enforced per `07_SECURITY_AND_TENANT_AUDIT.md`) | User/role management UI depth not verified in this pass — needs a follow-up read of the actual Settings screen component before committing to scope. |

## order-management-client

Not mapped to any proposed module. Recommendation (carried from `02_APPLICATION_ARCHITECTURE.md`): **explicitly out of scope.** It is a narrow, deliberately frozen remote-access replica of the legacy Order Management form, with its own separate build pipeline and no shared UI surface. Folding it into NEXORA MEDIQ would mean rebuilding it as an Electron screen from scratch — a decision with real cost that the master prompt does not ask for and the project's standing "legacy Order Workspace is frozen" rule argues against.

## Integration risk flagged here, detailed in 08

Order Workspace and Procurement are not cleanly separated in the current codebase (`App.jsx` holds Order-Workspace-specific constants like `OW_EXPORT_COLUMN_DEFS` alongside Procurement wiring). Any module-boundary redesign work here should be sequenced *before* heavy UI redesign of those two screens, not alongside it, to avoid merge conflicts with the actively-developed backend (`pm_router.py`, `legacy_order/*`).
