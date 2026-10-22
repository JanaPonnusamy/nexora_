# 13 — Evidence index

Line ranges are the regions read. SQL inside `FetchSourceData` is one VB string per branch (local at line 5997, remote at 5994).

| ID | Claim | Path | Symbol | Lines | Confidence |
|---|---|---|---|---|---|
| E-01 | Role 1 vs Role 2 menus | `D:\VBDOTNET\OrderManagement\OrderManagement\Form1.vb` | store-selection handler | 288–300 | VERIFIED |
| E-02 | Login reads `Users.Role` | `...\LoginForm.vb` | `btnLogin_Click` | 18–28 | VERIFIED |
| E-03 | Process Order needs today’s passcode | `Form1.vb` | `cboProcess_KeyPress` | 532–562 | VERIFIED |
| E-04 | Generation SQL, 10-day gate, line max, TotalStock, SaleUnit | `Form1.vb` | `FetchSourceData` | 5987–6029, local string 5997 | VERIFIED |
| E-05 | Additional row zeroed | `Form1.vb` | `InsertDataIntoDestination` | 6084–6087 | VERIFIED |
| E-06 | Qty check load | `Form1.vb` | `LoadQtyCheckData` | 896–916 | VERIFIED |
| E-07 | Qty save sets qtycheck | `Form1.vb` | `UpdateValues` | 1489–1506 | VERIFIED |
| E-08 | Enter assign skipped on Qty Check | `Form1.vb` | `UpdateDatabase(productCode)` | 2393–2396, 2400–2401 | VERIFIED |
| E-09 | Keys | `Form1.vb` | `dgvMain_KeyDown` | 2098–2233 | VERIFIED |
| E-10 | Delete is grid-only | `Form1.vb` | `DeleteCurrentRow` | 2295–2298 | VERIFIED |
| E-11 | Right Arrow → `free` | `Form1.vb` | `dgvMain_KeyDown` | 2181–2207 | VERIFIED |
| E-12 | Auto purchase join | `Form1.vb` | `LoadDataForSupplier` | 3848–3862 | VERIFIED |
| E-13 | Supplier stock join, stock > 0 | `Form1.vb` | `LoadDataForSupplierStock` | 4228–4266 | VERIFIED |
| E-14 | Compare previous assigned / sold | `Form1.vb` | `CompareOrderManagement` | 3872–3918 | VERIFIED |
| E-15 | Nexora formula | `backend/modules/procurement/decision_rules.py` | `final_required`, `evaluate` | 156–205, 306–348 | VERIFIED |
| E-16 | StockInHand, dont_consider forced 0, pending not loaded | `decision_repository.py` | `load_source` | 65–75, 147–175 | VERIFIED |
| E-17 | until_next_demand uses sale date | `order_items_repository.py` | `carry_forward_skips` | 59–103 | VERIFIED |
| E-18 | One supplier cap | `assignment_service.py` | assign | 66–94 | VERIFIED |
| E-19 | Receipt remaining | `reconciliation_rules.py` | `assignment_state` | 18–32 | VERIFIED |
| E-20 | Export settings shape | `supplier_export_settings_repository.py` | `get` | 10–24 | VERIFIED |
| E-21 | Rank weights, margin not used to rank | `frontend/src/components/procurement/purchaseValue.ts` | `AA_WEIGHTS`, `marginPercent` | 92–126 | VERIFIED |
| E-22 | Fuzzy pending under 96 | `backend/modules/product_mapping/scoring.py` | `AUTO_MIN`, `CONFIDENCE` | 22–33 | VERIFIED |
| E-23 | Nexora keyboard | `frontend/src/components/procurement/ProductGrid.tsx` | `onGridKey` | 278–398 | VERIFIED |
| E-24 | Web qty keys | `frontend/src/pages/legacy-order/OrderWorkspacePage.tsx` | `onQtyKeyDown` | 309–321 | VERIFIED |
| E-25 | Electron arrow saves; Delete hides | `desktop/supplier-stock-client/src/App.jsx` | `makeCommitQty`, `removeRow` | 4056–4089, 4831 | VERIFIED |
| E-26 | OrderBot flow and missing order id | `D:\VBDOTNET\OrderBot\main.py` | `add_product`, `place_order`, `main` | 149–190, 207–241 | VERIFIED |
| E-27 | PharmaRack URLs | `D:\VBDOTNET\OrderBot\config.json` | `base_url`, `order_cart_url` | 2–9 | VERIFIED |
| E-28 | PY is invoice/WhatsApp | `D:\VBDOTNET\PY\p4.py` | `login_sequence` | 76–77 | VERIFIED |
| E-29 | Python legacy recency default 15 | `backend/modules/legacy_order/service.py` | `DEFAULT_RECENCY_DAYS` | 23–25 | VERIFIED |
| E-30 | Batch sum vs TotalStock sample | — | — | — | UNKNOWN |
| E-31 | Cancelled-bill validity code | — | — | — | UNKNOWN |
| E-32 | Western Salem selectors | OrderBot README only | — | — | UNKNOWN |

Passwords, portal usernames, and connection strings seen in config and login SQL were not copied into this folder.
