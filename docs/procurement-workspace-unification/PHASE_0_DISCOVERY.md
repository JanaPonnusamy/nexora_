# Phase 0 discovery

Repository root: `E:\Nexora`. `Project_Master_Document.md` is not in the repo. Project memory is `PROJECT.md`. Audit folder `docs/procurement-workspace-unification/` already existed and was reused.

Named UI shells (`WorkspaceShell`, `PageHeader`, `FilterToolbar`, `AppDataGrid`, `InspectorPanel`, `SplitView`) were not searched. Phase 0 does not build UI.

Quantity sources used:

- Agreed formula: master prompt section "Quantity and rare movers".
- Legacy SQL: `backend/modules/legacy_order/sql/order_local.sql` and `order_process.py` Additional Row update.
- VB: `D:\VBDOTNET\OrderManagement\OrderManagement\Form1.vb` `FetchSourceData` recency hard-coded at 10 days.
- Nexora: `backend/modules/procurement/decision_rules.py` `evaluate`, called unchanged.

No production file under `backend/modules/procurement/` or `frontend/` was edited.
