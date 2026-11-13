# 30 — Phase 7A frontend gap inventory
**NEXORA MEDIQ — web app vs Electron, read-only**
Date: 2026-11-13

## 1. What this is

Read-only survey required before any Phase 7 consolidation code. No screen was added, renamed, or deleted. No CSS, nav, or backend file was edited. The in-flight Quick Stock and legacy-order working tree was not touched.

Sources, both read at HEAD `9908c57` plus the uncommitted files listed in §8 (those files were not used as the inventory):

- Web nav: `frontend/src/components/sidebar/navConfig.ts` (48 leaf entries with the VPL History flag off; 49 when that flag is on).
- Web routes that exist but are not in that nav: `frontend/src/routes/AppRouter.tsx`.
- Electron screens: `desktop/supplier-stock-client/src/App.jsx` `screens` (20 ids) and `desktop/supplier-stock-client/src/erpNav.js`.

These are two applications. A screen in one is not a screen in the other.

## 2. Counts

| Bucket | Count | Meaning |
|---|---|---|
| Web nav leaves (VPL off) | 48 | One row in §3. NMW Bill Export is its own leaf but the same route as NMW Sales Report. |
| Same job, own Electron screen | 10 | Including that duplicate NMW leaf. |
| Related Electron UI, not the same screen | 7 | Do not treat as "already ported". |
| No Electron screen | 31 | The port backlog. VPL History is a 32nd, and it is hidden unless a flag is on. |
| Electron screens | 20 | Six of them have no web nav twin. |
| Dead Electron nav id | 1 | `audit_logs` is in `erpNav.js` and is not in `screens`. Nothing renders it. |

## 3. Web nav mapped to Electron

Status words used below: **Match** = an Electron screen does this job. **Partial** = something related exists and is not this page. **Missing** = no Electron screen.

### Platform

| Web | Route | Electron | Status |
|---|---|---|---|
| Overview | `/overview` | `nexora_dashboard` is a different screen (procurement/sales/sync widgets, two of them still Planned). It is not the platform KPI / store-health overview. | Missing |
| Platform Management | `/platform/manage` | Users and roles exist as `user_management` and `role_management`. Tenants and stores have no Electron screen. | Partial |

### Inventory

| Web | Route | Electron | Status |
|---|---|---|---|
| Stock Availability | `/stock-availability` | Three Electron screens share this job. See §4. The web page's product + Batch/MRP tabs are what `network_stock` was written to mirror. | Partial |
| Stock Check Report | `/stock-check-report` | None. | Missing |
| Label Exporter | `/label-exporter` | `label_exporter` | Match |
| Box Workspace | `/label-exporter/box-workspace` | Not inside the Electron label exporter. | Missing |
| NMW Sales Report | `/nmw-sales-report` | `nmw_sales` | Match |
| Non-Moving Report | `/non-moving-report` | `non_moving` | Match |
| Received, Not Ordered | `/received-not-ordered` | A `ReceivedNotOrdered` panel lives inside `order_entry` (`PmOrderEntry.jsx`). It is not its own screen. | Partial |
| Sale Analysis | `/sale-analysis` | None. | Missing |
| Stock Integrity Check | `/stock-integrity` | None. | Missing |

### Procurement

| Web | Route | Electron | Status |
|---|---|---|---|
| Cycle & Refresh | `/procurement/console` | None. `/procurement/cycles`, `/procurement/refreshes`, and `/procurement/refresh` are further routes with no sidebar row and no Electron screen. | Missing |
| Purchase Manager | `/procurement/workspace` | `procurement_workspace`. See §5. Not the same file as the web page, and not the same screen as Order Workspace. | Partial |
| Product Intelligence | `/procurement/intelligence` | Order Workspace has an intelligence panel. There is no Product Intelligence screen. | Partial |
| Refresh Compare | `/procurement/compare` | None. This diffs two procurement refreshes. It is not Legacy Order compare. | Missing |
| Shelf Sorting & Excel Split | `/procurement/shelf-sort` | None. | Missing |
| Shelf Category Training | `/procurement/shelf-categories` | None. | Missing |
| Pharmacy Reports | `/procurement/reports` | None. The Electron dashboard reads one procurement-reports summary endpoint. That is not this page. | Missing |
| Supplier Stock Distribution | `/procurement/distribution` | None. | Missing |
| Procurement Rules | `/procurement/rules` | None. | Missing |
| VPL History | `/procurement/vpl-history` | None. Omitted from the nav unless `VITE_VPL_HISTORY_SCREEN=1` or a localStorage flag. The page never calls live generation. | Missing (flagged off) |
| NMW Bill Export | `/nmw-sales-report` | Same route and same Electron screen as NMW Sales Report. | Match (duplicate leaf) |

### Master Data, Document Extraction

| Web | Route | Electron | Status |
|---|---|---|---|
| Product Mapping | `/product-mapping` | None. | Missing |
| Document Extraction Workspace | `/document-extraction/review` | None. | Missing |
| Document Extraction History | `/document-extraction/history` | None. | Missing |

### Sync

| Web | Route | Electron | Status |
|---|---|---|---|
| Sync Live | `/sync/live` | `sync_live` | Match |
| Sync Schedules | `/sync/schedules` | None. | Missing |
| Sync Config | `/sync/config` | None. | Missing |
| Sync Mapping | `/sync/mapping` | None. | Missing |
| Sync Agents | `/sync/agents` | None. | Missing |
| Store Agent Devices | `/sync/devices` | Settings lists devices. That is not this page. | Missing |
| Store Client Monitor | `/sync/stock-clients` | None. | Missing |
| HO Routes | `/sync/ho-routes` | Edited inside `SettingsScreen`, not its own screen. | Partial |
| Backend Update | `/sync/backend-update` | None. | Missing |
| Device Control | `/sync/device-control` | None. Backend `modules/device_controller/` already exists. | Missing |
| Remote Terminal | `/sync/terminal` | None. | Missing |
| Mail Transfer | `/sync/mail-transfer` | None. | Missing |

### Administration, Expiry, System

| Web | Route | Electron | Status |
|---|---|---|---|
| Modules | `/administration/modules` | None. | Missing |
| Permissions | `/administration/permissions` | `role_management` edits the same matrix. It is not this page's layout, and it is under Masters. | Partial |
| Audit Logs | `/administration/audit-logs` | `audit_logs` is named in `erpNav.js` only. No `screens` entry and no component. The dashboard shows five recent audit rows for super admins. | Missing |
| Expiry Report | `/expiry-report` | None. Batch panels show an expiry column. That is not this report. | Missing |
| Expiry Stock | `/expiry-stock` | None. | Missing |
| Reports | `/reports` | None. | Missing |
| Time Report | `/time-report` | `time_report`, placed under Sales & Reports. | Match |
| Pass Gen | `/pass-gen` | None. | Missing |
| Legacy Order | `/legacy-order` | `legacy_order` | Match |
| Order Workspace | `/legacy-order/workspace` | `order_workspace` | Match |
| WhatsApp | `/whatsapp` | `whatsapp` | Match |
| Settings | `/settings` | `settings` | Match |

### Routes outside the sidebar

`/quick-stock` is a public kiosk route. Its files are the other session's uncommitted work, including `desktop/quick-stock-client/`. It is not on the port list for this phase.

Redirects only: `/platform/tenants`, `/platform/stores`, `/platform/users`, `/platform/roles`, `/sync-administration`, `/sync/dashboard`, `/sync/tables`, `/sync/store-health`, `/sync/history`, `/legacy-order/qty-check`, `/label-exporter/review`.

## 4. Stock: three Electron screens, one job, one unique piece

| Id | Label | What it actually is |
|---|---|---|
| `stock` | Stock Availability | Horizontal store panels. One search box accepts a product or a batch number. Offline product index. This is the fallback render for any unmatched `activeScreen`. |
| `stock_vertical` | Stock (Vertical) | Default screen (`useState` and post-login). One column per store, green/blue cross-store selection, offline index. Search is name or code with `*` wildcard. No Batch/MRP tab. |
| `network_stock` | Network Stock | Comment in `App.jsx` says this mirrors the web Stock Availability page, including a Product tab and a Batch/MRP tab (batch number, MRP, product name). |

Role filters already point restricted logins at `stock_vertical` only: `isStockViewerOnly`, `isStockAndLabelViewer`, and `isSmsPurchaseManagerOnly`. They do not mention `stock` or `network_stock` by id. Those two still appear for anyone who gets the `stock_availability` module, because all three screens share that module name.

Unique piece that vertical does not have: Network Stock's Batch/MRP search. Deleting `network_stock` without folding that tab in would drop it. Horizontal layout itself is the older presentation of the same search.

No deletion was done. Recommended 7B shape, waiting on the owner: fold the Batch/MRP tab into `stock_vertical`, rename that screen **Stock Enquiry**, then remove `stock` and `network_stock` (nav, the fallback render, and the shared module id). 

## 5. Order screens are not three copies

The owner described three order workspaces. The code has four Electron screens and two web twins. They were not collapsed.

| Screen | Job | Web twin |
|---|---|---|
| `order_workspace` (`OrderWorkspace.jsx`) | VB-style quantity review and supplier assignment on the legacy-order API. Phase 4 extraction. Kept mounted while hidden so its state survives a switch. | `/legacy-order/workspace` |
| `procurement_workspace` (`ProcurementWorkspace.jsx`) | File header, dated 2026-10-25: one Purchase Manager workspace using the Order Workspace model, and "the old Order Workspace stays untouched." Also kept mounted while hidden. | `/procurement/workspace` (`PurchaseWorkspacePage.tsx`, a separate 3,000-line page) |
| `order_entry` (`PmOrderEntry.jsx`) | Purchase manager types last bill + last GRN and starts Order Process. Also hosts the Received-Not-Ordered list. | No route named Order Entry. Received-Not-Ordered is its own web page. |
| `legacy_order` (`LegacyOrderGeneration.jsx`) | Super-admin, all-tenant order generation, per-store compare mode, evening schedule. | `/legacy-order` |

Compare today is a per-store mode inside Legacy Order on both apps (owner ruling 2026-11-05: PREVIOUS_PENDING, TODAY, NONE, HO). Neither app has an Order Compare screen. Refresh Compare (`/procurement/compare`) is a different job and must not be reused as that screen.

Which of the four Electron screens is "the latest" is not answered by file dates. `ProcurementWorkspace.jsx` says the older Order Workspace was deliberately kept. Deleting either one is an owner decision.

## 6. Decisions this survey does not make

1. Electron is the client to extend. The web app is not decommissioned by this document.
2. The 31 missing rows are a backlog, not an instruction to port all of them.
3. Stock Enquiry rename and the two deletions wait on confirmation, including whether Batch/MRP search is folded in first.
4. None of the four order screens is removed until the owner names the survivor, or says they stay because the jobs differ.
5. Order Compare, Sync Live timing, Device Control, Time Management as its own section, responsive layout, multi-tab, and the visual nav pass are later sub-phases. They were not started.
6. Multi-tab is a shell change. Which screens may be open together is still an owner question, and it stays unanswered until the screen list is stable.

## 7. Suggested port order, not started

After the decisions in §6:

1. 7B — Stock Enquiry, only after the stock confirmation. Order screens stay until named.
2. 7C — a new Order Compare screen. Do not reuse the `legacy_order` id.
3. 7D — time `SyncLive.jsx`'s three calls (`syncControlCenter`, `syncLive`, `syncHistory`) before changing them.
4. Then the written order: responsive pass, Device Control (existing `device_controller` API, the missing Sync rows), Time Management as its own section, multi-tab proposal, nav visual pass.

## 8. Left untouched

Uncommitted files from other sessions were still dirty after this survey and were not staged: `backend/modules/legacy_order/order_process.py`, `backend/modules/quick_stock/`, `backend/tests/test_legacy_order_warehouse_stock_sync.py`, `frontend/src/pages/quick-stock/`, `desktop/quick-stock-client/`, `backend/storage/whatsapp/send_log.json`.

No tests were run. No application code changed, so there was nothing new to execute.

## FINAL VERDICT

**COMPLETE** for the inventory. **BLOCKED** for 7B onward until the owner confirms the port list, whether the web app is only a backlog, the Stock Enquiry deletion, and which order screen (if any) is removed.
