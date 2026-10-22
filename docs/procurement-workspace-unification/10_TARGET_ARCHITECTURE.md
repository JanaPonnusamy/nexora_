# 10 — Target architecture

## Ownership decision (2026-10-19)

The new procurement lifecycle is owned by `NEXORA_PLATFORM` schema `procurement` (`procurement_cycles`, `procurement_refreshes`, `procurement_virtual_products`, `procurement_order_items`, `procurement_order_item_assignments`). OrderNMC `order_*` names and `OrderHeaderDetails` stay legacy. They are not a second owner of the new lifecycle, and this decision does not rename live objects. Detail and the live `OrderHeaderDetails` column read are in `AUTONOMOUS_WORK_CONTROL.md` and `PHASE_2_VPL_HISTORY.md`.

Proposed names below this heading are still marked **proposed** where the original text says so. They do not exist.

## Where it lives

New route inside Supplier Stock Client (`desktop/supplier-stock-client`), not a replacement of `OrderWorkspace` or `PurchaseWorkspacePage`. Both stay mounted until cutover approval.

The React grid should be a thin client. Formulas stay in Python next to `decision_rules.py`, behind a profile flag defaulting to **off** so current Purchase Manager behavior does not change.

## Reuse

| Piece | Use |
|---|---|
| `decision_rules` structure (exclude, then size, then pack) | New function beside `evaluate`. Do not edit `evaluate` until Profile T is the approved default. |
| `assignment_service` one-supplier and qty cap | Assign path |
| `reconciliation_rules.assignment_state` | Receipt remaining |
| `supplier_export_settings` row | Store+supplier tier |
| `product_mapping.scoring.classify` | Suggestion box confidence. Fuzzy stays manual. |
| `LoadDataForSupplier` / `LoadDataForSupplierStock` SQL | Mode queries, reimplemented as API read models, not copied as strings into the renderer |
| Stock Client `makeCommitQty` focus-before-response pattern | Keyboard, with a stuck-row if the save fails |
| OrderBot step list (`login`, distributor, `add_product`, confirm) | Spec for the adapter. Not imported. |
| WhatsApp Playwright profile pattern (`backend/modules/whatsapp/service.py`) | How a persistent browser profile is already hosted |

## Patch later (not now)

| Piece | Patch |
|---|---|
| `carry_forward_skips` | Separate until-next-demand from sale-date release |
| `load_source` | Ability to read `Products.TotalStock` when the profile says so |
| `final_required` SaleUnit `<= 0` | Profile T returns a data error instead of loose units |
| Legacy `order_export.py` | File success before exported flag, when that path is still used |
| ProductGrid Esc | Only if Purchase Manager is later pointed at this contract |

## New components (proposed)

| Component | Responsibility |
|---|---|
| `quantity_profile_t` | Agreed formula only. Inputs listed in the rulebook. |
| Mode loaders | Qty Check query, purchase-history query, supplier-stock query. Shared grid, different row sources. |
| Pending service | Confirmed qty − received, per product across suppliers. Drafts excluded. |
| Cost rank | Last six received lines in 90 days, effective unit cost, stale label. |
| Portal worker | One job per profile. Playwright adapter per portal. PharmaRack first. |
| Layout prefs | User (+ store if the client already keys settings that way). Reset. |

## Grid

Essential columns, not hideable: product, order qty, stock, pack, status.

Optional: sales, MRP, last GRN, supplier, pending.

Detail drawer, collapsed at 1366×768, order: Product, Purchase, Sales, Trend.

Suggestion box (existing): supplier candidates, cross-branch match, 180-day warning, margin warning.

## Keyboard for the new screen

| Key | Behavior |
|---|---|
| Enter | Save final qty, advance. Qty 0 is reviewed at zero, not a skip. |
| Up / Down | Save, then move. Failed save stays. |
| Esc | Set 0, save, advance. Not a skip reason. |
| Right | Open suggestion list. Does not assign. |
| Enter on a highlighted supplier | Assign if the mode allows and the line is not export-locked. |
| Delete | Ignored when the supplier filter is All. Otherwise hides the row in the current filter. No API delete. |
| Place on portal | Button only. Disabled while that supplier’s job runs. |

## Authorization

Until Role 1 and Role 2 are confirmed as Admin and PM, the new screen should use the Stock Client’s existing purchase-manager vs super-admin flags (`App.jsx` ~371–391), and hide Start / Close / template settings from the purchase-manager flag. Do not invent a third role model in the first slice.

## Data

No new table is approved by this document. The current `OrderManagement` row cannot store portal line status, Not Supplied, and template version without either overloading `Remarks` or adding columns. Overloading `Remarks` is rejected. A schema change is an approval item in `12_APPROVAL_REQUIRED_DECISIONS.md`, not a design fact.
