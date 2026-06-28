---
module: Procurement
version: 1.0
status: Active
owner: Solution Architecture
updated: 2026-06-27
---

# Procurement V1 — Evidence Ledger

> Provenance for the business-knowledge extraction. Lists exactly which legacy sources were read
> per topic (search-first, matching regions only) and the key contracts found. Code is evidence
> only — the FDD is the design.

## Source systems

| System | Location | Use |
|--------|----------|-----|
| Legacy VB.NET | `D:\VBDOTNET\OrderManagement\OrderManagement` | Store-level order/purchase desktop app. Reference only. |
| Legacy Python (ProcureX) | `D:\NEXORA\backend\modules\procurements`, `D:\NEXORA\frontend\src\apps\procurex-ui` | Thin API/repo over OrderNMC stored procedures. |
| OrderNMC SQL DB | `192.168.10.73 / OrderNMC` (SQL Server) | Business reference. **All procurement logic lives in stored procedures.** |

## Topic 01 — Business Cycle

**Python read (matching only):** `services/cycle_service.py`, `services/refresh_service.py`,
`repository/cycle_repo.py`, `repository/refresh_repo.py`, `repository/sp_executor.py`,
`schemas/cycle_schema.py`, `schemas/refresh_schema.py`, `constants/cycle_status.py` (empty),
`D_NEXORA_core/db_connection.py`.

**VB.NET searched:** keywords `cycle` / `refresh_id` / `order_cycle` → **0 matches** (concept absent).

**OrderNMC stored procedures read:**

| Procedure | Contract / key logic |
|-----------|----------------------|
| `nx_sp_CreateOrderCycle` | `(StoreName, rolling_days, remarks, created_by)`. Validates store + `rolling_days>0`; **(legacy) auto-closed prior `ACTIVE` cycle → `CLOSED`** [superseded by D1]; `cycle_no = MAX+1` per store; inserts `ACTIVE`, `live_refresh_count=0`, `offline_mode=0`. |
| `nx_sp_CloseOrderCycle` | `(CycleID, remarks, updated_by)`. Requires `active`; **(legacy) blocked close on pending `order_items.remaining_qty>0` and open `order_item_assignments` (`draft`/`exported`/`partial_received`)** [superseded by D2]; sets `completed`, `cycle_closed_at`. |
| `nx_sp_GetActiveOrderCycle` | `(StoreName)` → `TOP 1` `ACTIVE` cycle (one active per store). |
| `nx_sp_RefreshOrderCycle` | `(cycle_id, min_days, max_days, remarks, created_by)`. Validates `min_days>0`, `max_days>=min_days`, cycle `ACTIVE`; `refresh_no = MAX+1` per cycle; inserts `PROCESSING`; updates `live_refresh_count` (`PROCESSING/ACTIVE/PARTIAL`), `last_refresh_id`; calls `nx_sp_BuildVirtualProductList`; sets `ACTIVE` + `generated_product_count`. Transactional. **(legacy multi-live refreshes)** [superseded by D3]. |
| `nx_sp_GetRefreshes` | `(cycle_id)` → all refreshes, `refresh_no DESC`. |

**Inferred tables:** `Stores`, `order_cycles`, `order_cycle_refreshes`, `order_virtual_items`,
`order_items` (`remaining_qty` = pending), `order_item_assignments` (`assignment_status`).

**Bridge into Topics 02–03:** `nx_sp_BuildVirtualProductList(@CycleID,@StoreID,@StoreName,@RefreshID,
@MinDays,@MaxDays,@CreatedBy)` populates `order_virtual_items` — the Decision Engine / Workspace source.

## Topic 02 — Procurement Workspace

**Python read (matching only):** `repository/session_repo.py`, `services/session_service.py`,
`repository/product_repo.py`, `sql/px_launcher_sp.sql`, `sql/nx_sp_GetSupplierQueueByRefresh.sql`.
Keyword sweep `priority|section|skip|manual_review|demand|workspace` → matches only in session /
supplier-queue files (no section/priority concept in the workspace layer).

**Frontend read:** `procurex-ui/state/useProcureStore.js` → empty placeholder (no model).

**VB.NET read:** `OrderProcess.vb` → `LoadOrderData` (matched method only; the working-list builder).

**OrderNMC / launcher stored procedures:**

| Procedure | Contract / key logic |
|-----------|----------------------|
| `nx_sp_GetCyclesByStore` | `(StoreName)` → cycles (uses `Order_cycles`: `cycle_id, cycle_no, store_name, cycle_status, created_date`). |
| `nx_sp_GetRefreshesByCycleLatest` | `(CycleID)` → refreshes (uses `Order_refresh`: `refresh_id, refresh_no, refresh_status`). |
| `nx_sp_OpenProcureWorkspace` | `(RefreshID, UserID, RoleName)` → **refresh header only** (no grid rows). |
| `nx_sp_GetSupplierQueueByRefresh` | `(RefreshId, StoreName)` → top-3 suppliers per product from `purchasetrans` (rank by `purchase_count DESC, last_grn DESC`), aggregated per supplier: `total_products`, `total_required_qty = SUM(final_required_qty)`. |
| `nx_sp_GetProductsBySupplier` | `(RefreshId, SupplierCode, StoreName)` → working rows for a supplier. |

**VB working-list logic (`LoadOrderData`):** grid from `PurchaseTrans4Order ⋈ Products`; filters
`ProductType=1`, `GRNDate >= @SpecificDate`, `GrnNumber > last OrderHeaderDetails.LastGRN`
(incremental by new GRN), `OrderQty IS NULL/0` (drops once ordered). Editable `OrderQty`, `OrSupplier`.

**Schema inconsistency:** launcher SPs (`Order_cycles`/`Order_refresh`) vs core SPs
(`order_cycles`/`order_cycle_refreshes`) — two naming conventions for the same entities.

**Tables referenced:** `order_virtual_items` (`product_code`, `StoreName`, `refresh_id`,
`final_required_qty`), `purchasetrans` (`ProductCode`, `StoreName`, `suppliercode`, `suppliername`,
`grndate`), `PurchaseTrans4Order`, `Products`, `OrderHeaderDetails` (`LastGRN`).

**Bridge into Topic 03:** `order_virtual_items.final_required_qty` is the engine output;
`nx_sp_BuildVirtualProductList` + VB order-qty logic are the formula sources.

## Topic 03 — Decision Engine

**OrderNMC stored procedures read (full definitions):**

| Procedure | Key logic |
|-----------|-----------|
| `nx_sp_BuildVirtualProductList` | `(@CycleID,@StoreID,@StoreName,@RefreshID,@MinDays,@MaxDays,@CreatedBy)`. Deletes refresh rows; calls metrics SP with **`@RollingDays = 30` (hard-coded)**; candidate `AvgDailySales>0 AND DaysCover<MinDays`; `Target=Avg×MaxDays`; `Raw=Target−Stock`; **floors** `Raw=MAX(Raw,MaxDaySaleQty,MaxBillQty)` (`SPIKE_PROTECTION`/`MAX_BILL_TRIGGER`); `Final=CEILING(Raw)`; drop ≤0; insert `order_virtual_items`. `procurement_action` inserted NULL. |
| `nx_sp_GetProductProcurementMetrics` | `(@StoreName,@RefreshID,@RollingDays=30)`. Source `ProductSaleInformation` filtered `TransactionValidity=0`, `DontConsiderInOrder=0`, window `today−RollingDays`. `AvgDailySales=SUM(Qty)/RollingDays`; `MaxDaySaleQty`,`MaxBillQty`,`MonthlySalesQty`,`BillingFrequency`; join `Products (IsActive=1)`; `DaysCover=Stock/Avg`; `StockStatus` OUT/LOW(<3)/SAFE(≤15)/OVERSTOCK; `MovementClass` FAST(≥50)/MEDIUM(≥10)/SLOW(>0)/NONMOVING. Outputs `##MetricsOutput`. |

**VB.NET `Form1.vb` (matched regions):** `MinDays=15`, `MaxDays=20` (ln 49–50); display columns
`slsqty`="90 Sls" (**90-day** sales), `maxsaleqty`, `wantedtype`="Wanted" (classification),
`totalstock`, `lastsaledate`; `result.MinDays/MaxDays` (ln 554–555).

**Tables:** `ProductSaleInformation` (`ProductCode,StoreName,Quantity,BillNumber,TransactionDate,
TransactionValidity,DontConsiderInOrder`), `Products` (`TotalStock,IsActive,MRP,PurchasePrice,ItemCost`),
`order_virtual_items`.

**Catalogued:** PR-BR-001…016 (full structure) in `Procurement_Business_Rules.md`.

## Topic 04 — Customer Demand

**Python read (matching only):** keyword sweep `demand|customer|salesman|wanted|mobile` across
`modules/procurements` → **no matching files** (demand not implemented in the procurement module).

**VB.NET `Form1.vb` (matched regions):** `RetrieveDataForOrderDetailsAsync` (ln 1441 — `OrderManagementBackup`:
`Orqty,OrgOrderQty,remarks,Wanteddate,WantedType,Orsupplier`), `RetrieveDataForOrderSummary` (ln 1468 —
`ordermanagement`). Customer/salesman appear only in **sales** queries (ln 1383–1412). "Wanted/WantedType"
= order classification, **not** customer demand.

**OrderNMC schema:**

| Object | Finding |
|--------|---------|
| `customer_demands` | Capture table: `id, store_id, product_id, product_label, required_qty, customer_name, mobile, remarks, status (varchar), created_by, manager_id, created_at`. Informal status; no priority/type/history/reason/trace. |
| `CustomerProductMatch` | 31,620 rows: `CustomerCode → CustomerProductCode/Name → ProductCode` (customer-specific product map). |
| `procurement_rows` | demand-related cols: `new_customer_demand (int)`, `status`, `order_status`, `wanted_type` — demand surfaces via a flag, not a traceable link. |
| Procedures | **None** match `%demand%`/`%wanted%`/`%customer%`. |

**Conclusion:** Customer Demand as a business entity is **greenfield**; only a thin capture table exists.
Approved architecture in FDD §10.5–10.13; catalogue PR-BR-026…035. `CustomerProductMatch` preserved
(PR-BR-035). VB "Wanted" kept **distinct** from demand (C-02).

**Key conflicts:** C-01 30-day window vs cycle 90 (rolling_days unused); C-02 Max-Bill/Max-Day are
**floors** not caps (FDD §8.5/8.6 to correct); C-03 **no pending deduction** in sizing.

**RESOLUTION (E1–E5, ratified 2026-06-27):** C-01 → engine uses cycle **Rolling Days** (configurable,
default 90); legacy hard-coded 30 **superseded**. C-02 → Max-Bill/Max-Day confirmed as **minimum
protection floors**; FDD §8.5/8.6 corrected. C-03 → sizing now `Target − Effective Available`
(`Stock + PendingReceivable + ConfirmedInTransit − Reserved`); PR-BR-014 added. C-04 → thresholds now
configurable (PR-BR-016). Explainability mandated (PR-BR-015, FDD §8.17). New doc
`Procurement_Decision_Flow.md` defines the execution sequence. The legacy SP formulas remain evidence;
the **target design supersedes** the legacy 30-day / cap / stock-only / hard-coded behaviour.

### Topic 02 (cont.) — Roles, Access & Sync Orchestration

**Provenance:** PR-BR-017…025 are **approved business decisions** (2026-06-27), **not** extracted from
legacy code. Recorded in FDD §3.4–3.6, §5.4/5.4a, §6.6, §7.0 and the Working-State role model. The legacy
procurement **auth layer** is examined below to validate/compare the implementation surface.

**Python read (matching only):** `auth/roles.py`, `auth/permissions.py`, `auth/auth_dependency.py`.

**Legacy access model found:**

| Role | Permissions |
|------|-------------|
| `SUPER_ADMIN` | `*` |
| `ADMIN` | `cycle:create`, `cycle:refresh`, `cycle:close`, `report:view` |
| `PURCHASE` | `assignment:create`, `assignment:update`, `export:create`, `validation:update`, `report:view` |
| `VIEWER` | `report:view` |

Enforcement: `require_roles(*roles)` and `require_permission(name)` FastAPI dependencies; role from JWT
(`get_current_user`). **No synchronization permissions exist in the procurement module** — confirms the
"Procurement independent of Sync" principle (PR-BR-025).

**Alignment:** cycle/refresh/close = admin-only (PR-BR-019/020 ✓); `PURCHASE` limited to
assignment/export/validation, no cycle/refresh (PR-BR-018 ✓). **Gaps:** no per-user "Procurement
Administration" grant (AC-01); no discrete `skip` / `final_qty` / `pending:finalize` / `export:approve`
permissions (AC-02); extra `VIEWER` role not in approved model (AC-03). See Topic-02 §8.

**RESOLUTION (AC-01…AC-04, 2026-06-27):** The legacy `roles.py` / `permissions.py` model
(`SUPER_ADMIN`/`ADMIN`/`PURCHASE`/`VIEWER` with broad permissions) is **superseded** — it is **not**
preserved where it conflicts with the Nexora Platform RBAC. Target design: discrete `procurement.*`
**permissions** on existing platform roles; no procurement-specific roles; Export Generation and Export
Approval split. Authoritative model recorded in FDD §3.5 and Working-State "Canonical access model".
