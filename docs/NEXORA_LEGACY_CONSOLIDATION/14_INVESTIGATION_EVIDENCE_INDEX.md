# 14 — Investigation Evidence Index

Consolidated quick-reference across all Phase 7C deliverables. Each
document's own evidence index (where present) is the authoritative detail —
this file is a navigation aid across documents, not a replacement for them.

---

## Document map

| Doc | Title | Primary evidence base |
|---|---|---|
| 01 | Executive Summary | Synthesizes 02–10, 15–17 |
| 02 | Legacy Order Dependency Map | `backend/modules/legacy_order/*` (full read), `frontend/src/pages/legacy-order/*`, `desktop/supplier-stock-client/src/ProcurementWorkspace.jsx` |
| 03 | Procurement Table Inventory (CSV) | `backend/modules/*/sql/*.sql`, inline SQL across ~26 procurement + legacy_order repository files |
| 04 | Cycle/Refresh Data Flow | `backend/modules/procurement/orchestration_service.py`, `decision_service.py`, `decision_repository.py`, `vpl_repository.py`, `legacy_order_parity.py` |
| 05 | NEXORA Feature Inventory | `backend/modules/procurement/*` (~60 files), `stock_availability`, `quick_stock`, `rate_analysis`, `nonmoving_analysis`, `nmw_sales_report` |
| 06 | Business Rule Comparison | `legacy_order/order_process.py`, `rulebook_order.py`; `procurement/decision_rules.py`, `legacy_order_parity.py`, `rules_catalog.py` |
| 07 | Historical Data & Prediction Readiness | `sync.ProductSaleInformation`/`PurchaseTrans`/`ProductTrans` consumers; `ordernmc_mirror/service.py`; `product_category_ai.py` |
| 08 | Legacy Output Compatibility | `legacy_order/repository.py` grid functions, `order_export.py` |
| 09 | Security and Tenant Review | `backend/dependencies/auth.py`, `store_scope.py`; `procurement/access.py`; all procurement sub-routers |
| 10 | Test and Regression Gap Report | `backend/tests/test_legacy_order_*.py`, `tests/test_procurement_*.py`, `desktop/supplier-stock-client/src/*.test.js` |
| 11 | Target Architecture & Migration Plan | Synthesizes 02–10 |
| 12 | Phased Implementation Backlog | Synthesizes 02–10, 13 |
| 13 | Unknowns & Owner Decisions | Synthesizes 02–10, 15–16 |
| 15 | Multi-Tenant Database Architecture | `backend/config/database.py`, `backend/repositories/tenant_repository.py`/`store_repository.py`, `backend/modules/bootstrap/repository.py`, `legacy_order/database.py` |
| 16 | Schema Migration & All-Tenant Deployment Plan | `backend/modules/schema_sync/*`, `backend/modules/sync/schema_evolution.py`, `backend/api/app.py:165-197` |
| 17 | Zero-Regression & Additive Enhancement Plan | Synthesizes 02, 06, 08, 16 into a forward design |

## Key file:line citations (cross-document, highest-reuse evidence)

| Topic | File:line | Cited in |
|---|---|---|
| RULEBOOK writes into Legacy Order's own tables | `order_process.py:629-723` (`insert_data_into_destination`) | 01, 02, 06, 11 |
| `legacy_order_parity.py` is the Procurement default profile | `decision_service.py:93-97` | 01, 04, 05, 06, 11 |
| Legacy Order has zero imports of `modules.procurement` | grep across `legacy_order/*.py`, confirmed no matches | 02, 04, 11 |
| Procurement → Legacy Order one-way dependency table | `distribution_service.py:465-482`, `abnormal_sales_repository.py:15`, `reports/repository.py:8-40` | 04, 05, 11 |
| Stock-source conflict (~26% of catalogue) | `_dbutil.py:17-19`, `rules_catalog.py:134-149` | 01, 06, 12 |
| SaleUnit-blocking conflict | `rules_catalog.py:195-209`, `decision_rules.py:201-204` | 01, 06, 12 |
| `refreshing_in_progress()` defined but never called | `repository.py:272-287`, confirmed by repo-wide grep | 04, 11, 12 |
| `sync.Products` duplicate-row defensive patches (uncommitted, both sides) | `decision_repository.py` (ROW_NUMBER partition), `workspace_repository.py` (_PRODUCT_KEY/_PRODUCT_RANK), `legacy_order/repository.py` (collapse_lines) | 02, 04, 11, 12, 13 |
| Five unauthorized Procurement sub-routers | `optimization_router.py`, `intelligence_router.py`, `pipeline_router.py`, `snapshot_router.py`, `compare_router.py` — confirmed by full-file reads, zero `assert_tenant_access`/`require_procurement_*` imports | 01, 09, 10, 12, 13 |
| `pm_router.py` as the gold-standard auth pattern | `pm_router.py:56-89, 768-779, 823-834, 1053-1063` | 09, 12, 17 |
| No automated cross-tenant schema migration exists | `backend/modules/schema_sync/service.py:178-538`, `backend/api/app.py:165-197`, absence of any `alembic`/`schema_version` table | 01, 15, 16, 17 |
| Backward-compatibility idiom (COL_LENGTH/OBJECT_ID) — 52 files | `legacy_order/database.py:222-229`, `sync/schema_evolution.py:66-86` | 16, 17 |
| No ML/forecasting anywhere | `procurement/product_category_ai.py:1-31,79-95` (LLM call, display-only, not decision-affecting) | 01, 07 |
| Supplier stock is snapshot-only, no history | `repository.py:918-936` (DELETE+INSERT), `supplier_stock_repository.py` (one `transaction_date` per row) | 06, 07, 13 |
| Best-margin auto-assign (matches owner ruling) | `repository.py:1666-1845` | 02, 08, 17 |
| 3-mode skip system | `repository.py:2035-2149`, `sql/0010_order_skip_rules.sql` | 02, 06, 13, 17 |
| Compare-previous-order 4 rules | `repository.py:2519-2574` | 02, 08, 17 |
| Single-warning rule (owner ruling) | `service.py:488-515` | 02, 17 |
| Legacy-vs-RuleBook dry-run harness (no DB write) | `rulebook_order.compare_engines`/`compare_workbook`, `GET /engine/{store}/compare.xlsx` | 02, 10, 11, 12, 17 |
| Field-level output risk map | doc 08 §2 full table | 08, 11, 17 |
| `dbo.tenants`/`dbo.stores` registry (within one HO only) | `tenant_repository.py:26-36`, `store_repository.py:11-69` | 15, 16 |
| HO route failover list (`dbo.ho_routes`) | `backend/modules/bootstrap/repository.py:1-60` | 15 |
| Device Controller = app binaries only, not schema | `device_controller/packages.py:1-29`, `service.py:1-96` | 15, 16 |
| `schema_evolution.py` — the one real automated schema tool, scoped to `sync.*` only | `backend/modules/sync/schema_evolution.py:21-147` | 16 |

## Known gaps in this evidence base (be honest about what was not traced)

- Live database contents (row counts, actual earliest dates, actual current
  schema version per physical database) were **never queried** — this
  investigation was 100% static code/SQL-file analysis, per the read-only
  mandate. See doc 13 §C for the specific facts this limits.
- Several named test files in doc 10 were identified by filename/location
  only, not read to EOF (explicitly marked INFERRED in doc 10 §1a/§1b) —
  reading them in full could reclassify some "UNCOVERED" rule areas to
  "Covered."
- The table inventory (doc 03) prioritized breadth over column-level
  completeness per its own instructions — many `ColumnName=UNKNOWN` rows
  exist by design where a table was referenced by name but its full column
  list was not visible in the code paths read.
- Mid-file sections of the largest repository files (`procurement/repository.py`,
  `supplier_stock_analysis/repository.py`, 1000-1500+ lines each) were
  covered via targeted grep+read rather than full line-by-line read in doc 03's
  investigation, per its own breadth-over-completeness instruction.
- `webPanel.cjs` and `supplier_stock_analysis/router.py` were only partially
  verified in doc 09's security review (outside its two named modules).

## Confidence summary across all docs

Every individual document tags its own claims VERIFIED / PARTIAL / INFERRED
/ UNKNOWN; no claim in this index or in doc 01/11/12/13/17 upgrades a
source document's confidence tag. Where this index states something as
fact, it is because the cited source document marked it VERIFIED.
