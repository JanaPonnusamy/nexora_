# 01 — Repository and source inventory

Repository root: `E:\Nexora`. Legacy apps are outside the git root.

## Authoritative files read for this audit

| Area | Path | Role |
|---|---|---|
| VB form | `D:\VBDOTNET\OrderManagement\OrderManagement\Form1.vb` (~7325 lines) | Screens, SQL, keyboard, export |
| VB order worker | `...\OrderProcess.vb` | `UpdatePurchaseTrans4Order`, `LoadOrderData` |
| VB login | `...\LoginForm.vb` | `Users` username/password, `UserSession.UserRole` |
| VB session | `...\UserSession.vb` | `UserID`, `UserName`, `UserRole As Integer` |
| Nexora engine | `E:\Nexora\backend\modules\procurement\decision_rules.py` | `evaluate`, `final_required` |
| Nexora inputs | `...\decision_repository.py` `load_source` | Sales and stock SQL |
| Nexora skips | `...\order_items_repository.py` `carry_forward_skips` | Cross-refresh skip |
| Nexora assign | `...\assignment_service.py` | One supplier, qty cap |
| Nexora export settings | `...\supplier_export_settings_repository.py` | Per store+supplier row |
| Nexora receipt math | `...\reconciliation_rules.py` | `assigned − received` |
| Nexora ranking UI | `frontend\src\components\procurement\purchaseValue.ts` | Weights, margin display |
| Product match | `backend\modules\product_mapping\scoring.py`, `matcher.py` | Cross-identity match |
| Legacy SQL port | `backend\modules\legacy_order\sql\order_local.sql` | Python port; recency is a parameter |
| Legacy service | `backend\modules\legacy_order\service.py` | Defaults min 13, max 18, recency 15 |
| Web workspace | `frontend\src\pages\legacy-order\OrderWorkspacePage.tsx` | Qty review keyboard |
| Stock Client | `desktop\supplier-stock-client\src\App.jsx` function `OrderWorkspace` | Electron keyboard |
| OrderBot | `D:\VBDOTNET\OrderBot\main.py`, `config.json`, `README.md` | Portal cart |
| PY | `D:\VBDOTNET\PY\p4.py`, `Purani_Single.py`, `CoreFinal.py` | Invoice + WhatsApp only |

## Not inspected

- Live SQL Server (no connection opened). Indexes, constraints, and sample stock discrepancies are UNKNOWN.
- `order_warehouse.sql` body (warehouse demand). Not used for the retail target formula.
- VB `CentralSync*.vb` sync pipeline. Out of the order-qty path except that generation reads whatever sync has loaded.
- OrderBot was not executed.

## Existing docs (not overwritten)

- `docs/AUDIT_Legacy_Order_vs_Nexora_Purchase_Workspace_2026-10-19.md` — prior pass, before this VB read.
- `docs/Nexora_Demand_Generation_Rules.md` — matches `decision_rules.py`, not the agreed target in this prompt.
- `docs/Procurement_Decision_Flow.md` — stale relative to `decision_rules.py`.

This folder is the unification analysis. It does not replace those files.
