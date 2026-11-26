# 10 — Test and Regression Coverage Gap Report

Scope: all test files touching Legacy Order, Procurement Workspace,
Cycle/Refresh, Supplier Stock, Stock Enquiry, Sales/Order calculations,
Supplier allocation, Tenant security, Store isolation, Order output/export.
Read-only, 2026-11-13. Tags: VERIFIED / PARTIAL / INFERRED / UNKNOWN as in
doc 09.

## 1. Test inventory by file

Two test roots exist: `backend/tests/` (pytest, imports `modules.*` with
`backend/` on `sys.path` implicitly via conftest or explicit insert) and
`tests/` at repo root (pytest, each file inserts `backend/` onto `sys.path`
manually, VERIFIED pattern e.g. `tests/test_procurement_product_identity.py:13-15`).
Both are plain pytest — no custom runner found. Desktop JS tests use Node's
built-in `node:test` (VERIFIED import style in both `.test.js` files), run via
`npm test` (not confirmed by reading `package.json` this pass — INFERRED from
import style and file naming convention `*.test.js`).

### 1a. Legacy Order (`backend/tests/test_legacy_order_*.py`)

| Test file | Covers | Verified | Missing | Automated | Mocks/real data |
|---|---|---|---|---|---|
| `test_legacy_order_store_access.py` | `require_order_console_access` path-pattern gate: admin/NMV-PM/viewer on own vs other store | Store-level isolation logic, NOT the live route table (synthetic `_FakeRequest`) | Whether every actual router.py route is correctly classified into the right path-pattern tuple | pytest, no DB (`get_connection` monkeypatched to raise) | Mocks only |
| `test_legacy_order_qtycheck_status.py` | qtycheck/status contract for `orders_by_supplier`, `assigned_orders`, `all_assigned_orders`; `export_order` assigns+exports only grid product_codes | SQL-shape assertions (checked/pending/unknown qtycheck states) + export scoping | Real DB execution of the SQL itself | pytest | Mocks (asserts on SQL string/params, doesn't execute) |
| `test_legacy_order_auto_assign.py` | Best-margin supplier proposal: receipt margin math, tie-break (more supplies then most recent), inactive/unpriced supply exclusion, fallback to most-frequent-active, no-data case | Business rule: **Supplier allocation / best-margin ranking** | Real auto-assign against live SupplierStock/PurchaseTrans | pytest | Pure function unit tests, synthetic data |
| `test_legacy_order_skip_rules.py` | Skip mode validation, skip modes match platform's 3 modes, carried skips reapplied inside the Order Process transaction | Business rule: **Skip/reject persistence across regenerated orders** | Interaction with Qty Check / Pending Order screens end-to-end | pytest | Mocks |
| `test_legacy_order_rulebook_engine.py` | Not read this pass (file exists, name implies the Rulebook vs Legacy SQL engine selection) | — | — | pytest (INFERRED) | Unknown |
| `test_legacy_order_processing_lock.py` | Not read this pass; name implies the per-store Order Process concurrency/applock | — | — | pytest (INFERRED) | Unknown |
| `test_legacy_order_restore_and_review.py` | Not read this pass; name implies restore-backup-order + match-review flows | — | — | pytest (INFERRED) | Unknown |
| `test_legacy_order_platform_store_id.py` | Not read; store_name↔platform store_id resolution | — | — | pytest (INFERRED) | Unknown |
| `test_legacy_order_auto_sync.py` | Not read; auto-sync job scheduling | — | — | pytest (INFERRED) | Unknown |
| `test_legacy_order_nmv_seam.py` | Not read; remote-store (NMV) integration seam | — | — | pytest (INFERRED) | Unknown |
| `test_legacy_monthly_stats_window.py` | Not read; monthly stats date-window math | — | — | pytest (INFERRED) | Unknown |
| `test_legacy_order_warehouse_stock_sync.py` (untracked, NEW) | `_sync_agent_source_stock`: triggers live device sync for an AGENT-connected warehouse source when stale, skips when recently synced (throttle via `LEGACY_WAREHOUSE_STOCK_SYNC_MIN_INTERVAL_SECONDS`), is generic to ANY store name (not hardcoded), degrades quietly when `platform_store_id` is unresolvable or the sync call throws (`DeviceSyncTimeout`), and `refresh_warehouse_stock` calls the sync BEFORE reading central stock for an AGENT source but never for a LAN source | VERIFIED full file read: 7 tests, all monkeypatched, no DB/network | Real device-sync round trip (end-to-end against an actual store agent); also doesn't test what happens if `trigger_and_wait` partially succeeds (syncs 2 of 3 tables then fails) | pytest, DB-free | Mocks only |

Root-level `tests/test_legacy_order_parity.py` and `tests/procurement_formula_
compare.py` / `tests/test_procurement_formula_compare.py` are the
legacy-vs-platform comparison harness — covered in detail in §3.

### 1b. Procurement (`tests/test_procurement_*.py`, `tests/test_vpl_history*.py`)

| Test file | Covers | Verified | Missing | Automated | Mocks/real |
|---|---|---|---|---|---|
| `test_procurement_decision_engine.py` | Core decision engine: PARA500 trace, average daily sales, days-cover, movement-class/stock-status buckets, final-required determinants + strip-unit conversion, every exclusion reason (not-selling, adequate-cover, zero-required, stale-sale, recently-received, missing-GRN-watermark, inactive/flagged), min-qty floor parity with legacy formula, per-bill-floor qualification override, max-line-sale-qty spike parity, rare-mover top-up parity with legacy Additional Row, parameter validation, bulk/no-N+1 engine shape | VERIFIED 24 test names read; this is the single most-covered business-rule surface in the repo | Direct comparison against a REAL legacy SQL execution (it's all transcription-based, see §3) | pytest | Pure-function unit tests, synthetic cases |
| `test_procurement_rare_mover_guard.py` | PROCUREMENT_RARE_MOVER_ENFORCEMENT flag on/off, per-row (not global) confirmation requirement, `assign_single`/`bulk_assign`/`export` all independently blocking an unconfirmed rare-mover row, bulk isolates the bad row without blocking the rest | VERIFIED 15 test names | Real end-to-end UI flow (confirm → assign → export) against a live refresh | pytest | Mocks |
| `test_procurement_product_identity.py` (untracked, NEW) | Product-grid line identity/collapse rules: same store+code = one line across API re-fetch, snapshot reload, two different SupplierProductMatch rows for the same product, two different stores stay separate, two different products with similar names stay separate; also 3 source-code shape assertions (`OUTER APPLY` not `LEFT JOIN`, `ROW_NUMBER() PARTITION BY`) in `workspace_repository._FROM`/`_PRODUCT_RANK`, `legacy_order.repository.assigned_orders`, `decision_repository.load_source` | VERIFIED full file read: 13 tests | Real SQL execution against a DB with actual duplicate SupplierProductMatch rows (the source-inspection tests prove the SQL *text* has the right clause, not that the live query plan avoids the multiply) | pytest, DB-free | Pure function + `inspect.getsource` string assertions |
| `test_procurement_orchestration.py` | `create_business_cycle` validation guards (requires `created_by`, blocks duplicate ACTIVE cycle, rejects missing store), full Refresh pipeline integration with stubs | VERIFIED test names + the `test_open_cycle_requires_user` 403 assertion, which is validating presence of a string, NOT a real auth/tenant check (see doc 09 §2c) | A real tenant-ownership test — none of these tests supply a cross-tenant user and assert rejection, because the underlying code has no such check to test | pytest, no DB | Stubs/fakes |
| `test_procurement_pipeline.py` | `_refresh` stub shape (1 reference found, not fully read) | PARTIAL | Auth/tenant check (none exists in `pipeline_router.py`, see doc 09 §2f) — confirmed by absence: no `tenant`/`auth`/`403` tokens anywhere in a grep of the file | pytest (INFERRED) | Unknown |
| `test_procurement_pm_router_auth.py` | Server-side capability checks for 6 pm_router mutation routes (assign, bulk_assign, change_supplier, remove_assignment, export, submit_grn) — explicitly scoped to the router-level gate only, not business behavior | VERIFIED docstring + imports; uses real `TestClient` + real JWT (`create_access_token`) with `access.load_module_codes` monkeypatched | Tenant-ownership rejection (a token for tenant A hitting a tenant-B tenant_id) — not in scope per this file's own docstring, and no OTHER file fills that gap for pm_router either | pytest + FastAPI TestClient (real HTTP through the router, no live DB — services monkeypatched) | Real JWTs, mocked services |
| `test_procurement_pm_router_auth_round2.py` | Presumably more of the above (not read this pass) | — | — | pytest (INFERRED) | Unknown |
| `test_procurement_rules_auth.py` | PROCUREMENT_ADMIN capability gate for rules registry: requires token at all (401), workspace-only capability cannot write a default | VERIFIED 2 of N tests read | Tenant-ownership rejection for `/rules/effective`, `/rules/overrides/*` (the router DOES call `assert_tenant_access` per doc 09 §2i, but no test exercises the cross-tenant-403 path specifically — only capability is tested here) | pytest + TestClient | Real JWTs, mocked `access.load_module_codes` |
| `test_procurement_concurrency_d4_d5.py` | Not read; name implies concurrency safety (D4/D5 features) | — | — | pytest (INFERRED) | Unknown |
| `test_procurement_phase2_alignment.py` | Not read; likely schema/migration alignment checks | — | — | pytest (INFERRED) | Unknown |
| `test_procurement_pm_workflow.py` | Not read; likely end-to-end PM workflow (assign→export→GRN) | — | — | pytest (INFERRED) | Unknown |
| `test_procurement_sprint3.py` | Not read; likely Sprint 3 feature regression (snapshot engine?) | — | — | pytest (INFERRED) | Unknown |
| `test_procurement_rules_registry.py` | Not read; rules registry CRUD/versioning logic | — | — | pytest (INFERRED) | Unknown |
| `test_vpl_history.py`, `test_vpl_history_claude_edge.py`, `test_vpl_history_repository.py` | Not read; VPL-history workspace memory-store logic + Claude-suggestion edge cases | — | — | pytest (INFERRED) | Unknown |
| `test_quantity_profile_t.py` | Not read; likely `quantity_profile_t.py` (t-distribution or similar demand-smoothing?) business logic | — | — | pytest (INFERRED) | Unknown |

### 1c. Tenant/role/auth-specific

| Test file | Covers | Gap |
|---|---|---|
| `backend/tests/test_procurement_reports_tenant_scoping.py` | Full cross-tenant-403 + own-tenant-200 + superadmin-any-tenant-200 matrix for `reports_router.py`'s 6 endpoints (dashboard, store_analysis, compare + 2 Excel exports) | This exact pattern is **absent** for `optimization_router.py`, `intelligence_router.py`, `pipeline_router.py`, `snapshot_router.py`, `compare_router.py`, and the ungated endpoints of `orchestration_router.py`/`vpl_router.py`/`procurement/router.py` — see doc 09 for the full list |
| `backend/tests/test_role_user_access_control.py`, `test_role_module_access_matrix.py` | Not read; platform-wide role/module grant matrix (outside legacy_order/procurement scope, but underlies `access.load_module_codes`) | — |
| `backend/tests/test_legacy_order_store_access.py` | See §1a | Live-route-table coverage, as noted |

### 1d. Desktop (`desktop/supplier-stock-client/src/*.test.js`)

| Test file | Covers | Verified | Missing |
|---|---|---|---|
| `procurementWorkspaceView.test.js` | Pure view-logic helpers: quantity parsing/capping (`pwWholeQty`), column order/width persistence, warehouse-card detection (`pwIsWarehouseCard` for `ST_*`/`is_warehouse`/`warehouse` tag), qty-grid keyboard navigation (`pwQtyKeyAction`), plus (per file header, not fully enumerated) assign-refusal, export-guard, finalize-plan, GRN-for-selection, supplier-line/compare, offer text/remark logic | VERIFIED ~10 of the exported functions tested by name; file is large, not read to EOF | No test exercises the component against a live/mocked API response shape end-to-end — these are pure-function unit tests of exported helpers only, not render/integration tests |
| `theme.test.js` (untracked, NEW) | `normalizeThemePreference` defaulting, `resolveTheme` system-vs-explicit resolution | VERIFIED full file: 3 tests | Trivial module; no gap of consequence |

No desktop test exercises `session.js` (token storage/expiry), `client.js`
(the fetch wrapper — retry/timeout logic, auth header injection), or
`UserManagementScreen.jsx`. **This is a gap**: `client.js`'s retry-on-
transient-status logic and `detailToMessage` error-parsing (both fairly
intricate, `client.js:14-52`) have no test coverage found anywhere in
`desktop/supplier-stock-client/src/*.test.js`.

## 2. Business-rule coverage matrix (30 areas)

Cross-referencing the areas named in the task against what the test
inventory above actually exercises:

| # | Business rule area | Coverage | Evidence |
|---|---|---|---|
| 1 | Demand/window-sales calculation | **Covered** | `test_procurement_decision_engine.py` (avg daily sales, days-cover), `tests/procurement_formula_compare.py` legacy transcription |
| 2 | Min order quantity (min_qty floor) | **Covered** | `test_procurement_decision_engine.py::test_min_qty_floor_matches_legacy_formula`, `test_qualifies_via_per_bill_floor...` |
| 3 | Max order quantity / spike cap | **Covered** | `test_max_line_sale_qty_spike_parity` |
| 4 | Scheme/discount handling on supplier offers | **UNCOVERED** — no test file found asserting discount/scheme math (e.g. `pwEffectiveDiscount` in `procurementWorkspaceView.js` is exported and presumably tested by name in the desktop test file, but no BACKEND test for discount application in export/assignment was found) | Gap |
| 5 | Supplier allocation / best-margin ranking | **Covered** | `test_legacy_order_auto_assign.py` (7 tests) |
| 6 | Rounding (pack ceiling, CEILING semantics) | **Partially covered** | `_ceil`/CEILING logic embedded in `decision_rules`/`legacy_order_parity` and exercised incidentally by the parity tests, but no dedicated rounding-edge-case test (e.g. exact pack-size boundary, negative/zero sale_unit) found standalone |
| 7 | Duplicate order prevention (same product/store/supplier collapse) | **Covered** | `test_procurement_product_identity.py` (new, thorough — 13 tests) |
| 8 | Skip/reject persistence across regeneration | **Covered** | `test_legacy_order_skip_rules.py` |
| 9 | Abnormal/bulk-bill sales detection (5x/3x rule) | **Covered** | `tests/test_abnormal_sales.py` (10 tests: 5x abnormal, 3x warning, needs-2-other-bills, marked-bill excluded from average, zero/negative ignored, custom thresholds) |
| 10 | Rare-mover top-up + confirmation gate | **Covered** | `test_procurement_decision_engine.py::test_rare_mover_topup_*`, `test_procurement_rare_mover_guard.py` (15 tests) |
| 11 | Qty Check / status contract (checked vs pending vs unknown) | **Covered** | `test_legacy_order_qtycheck_status.py` |
| 12 | Pending-order carry-forward across refreshes | **Covered** | `refresh_comparison.py` logic covered by... **not directly tested** — `refresh_comparison.adjust_suggested` has no dedicated test file found (only used by `comparison_service.carry_forward`, which itself has no test file found). **Gap**: the carry-forward RULE (previously-completed excluded, carried pending added on top) has no unit test despite being pure, easily-testable logic |
| 13 | Export scoping (grid product_codes only, deleted rows excluded) | **Covered** | `test_legacy_order_qtycheck_status.py::test_export_order_assigns_and_exports_only_grid_products` |
| 14 | Supplier min-order-value / consider-minimum-order | **UNCOVERED** — `optimization_service.py` has `set_min_order`/`set_consider_minimum_order`/`list_min_order_config`; no test file found exercising this logic at all (not `optimization_router` tests, not `optimization_service` tests) | **Gap** — also the exact module with zero router auth (doc 09 §2d) |
| 15 | Below-minimum supplier move suggestions (optimization engine) | **UNCOVERED** — same `optimization_service.py`; `_best_combo`/`_optimize_one` have no test file found | **Gap** |
| 16 | Network/cross-store movement opportunities | **Partially covered** | `backend/tests/test_network_movement.py` exists (not read this pass, but file name matches `network_movement_service.py` directly) |
| 17 | Product Intelligence consolidation (cross-store VPL union) | **UNCOVERED** — `intelligence_service.py`'s `build_intelligence`/`_group_products`/union-find (`_UnionFind` class) has no test file found | **Gap** — also zero router auth (doc 09 §2e) |
| 18 | Supplier-offer resolution / auto-assign across stores (Product Intelligence mode 2) | **UNCOVERED** — `resolve_assignment`/`assign_supplier_product` in `intelligence_service.py`, no test found | **Gap** |
| 19 | VPL compare (refresh-to-refresh diff) | **Partially covered** — INFERRED only; no test file matching `compare_service`/`compare_repository` found by name (would expect `test_procurement_compare.py` or similar — absent) | **Gap** |
| 20 | VPL snapshot refresh (per-product / changed-only) | **UNCOVERED** — `snapshot_service.py`'s `refresh_vpl`/`refresh_product`/`get_status`/`get_progress`, no test file found matching | **Gap** — also zero router auth (doc 09 §2g) |
| 21 | Pipeline run (Sync→Cycle→Refresh→Decision→VPL end-to-end) | **Partially covered** | `test_procurement_pipeline.py` exists but only partially read this pass; likely covers the orchestration shape, not a full real-data run |
| 22 | Cycle open/close lifecycle + reconciliation | **Covered (logic), not (auth)** | `test_procurement_orchestration.py` tests validation guards; doc 09 notes the auth/tenant gap on the same functions |
| 23 | GRN submission / reconciliation | **Partially covered** — `reconciliation_service.submit_grn` is called from a well-guarded route (`pm_router.py:1053-1063`); no dedicated `test_reconciliation*.py` found by name in either test root | **Gap** |
| 24 | Supplier WhatsApp send / auto-send batching | **UNCOVERED** in the procurement/legacy_order scope reviewed — `supplier_whatsapp.py` has no obviously-matching test file in `backend/tests/` or `tests/` (memory notes a separate "WhatsApp headless send" module tested elsewhere, but that's the sending transport, not the batching/auto-send RULE in `legacy_order/supplier_whatsapp.py`) | **Gap** |
| 25 | Supplier stock harvest + fuzzy match / 3-tier review | **UNCOVERED** by this review's search — no `test_supplier_stock_harvest*.py`/`test_supplier_match_review*.py` found in either root (memory doc references this module's existence and design, not a test file) | **Gap** |
| 26 | Supplier portal credential storage (encryption) | **UNCOVERED** — no test file found for `supplier_portal.py`'s encrypt/decrypt of portal passwords | **Gap** |
| 27 | Warehouse stock sync (agent-source live refresh) | **Covered** | `test_legacy_order_warehouse_stock_sync.py` (new, thorough) |
| 28 | Tenant isolation (cross-tenant 403) | **Partially covered** | Only `reports_router` has the full matrix; 6+ sibling routers have none (doc 09) |
| 29 | Store isolation (store-level, not just tenant) | **Covered for Legacy Order**, **not modeled for Procurement** (procurement is tenant-only by design per `store_scope.py` docstring, so "store isolation" doesn't apply the same way — not a gap, a design choice, confirmed in doc 09 §1) |
| 30 | Order output/export file correctness (columns, headers, split-by-size, image/PDF format) | **Partially covered** | `export_order`/`export_pending_order` scoping tested (#13 above); no test found asserting actual file CONTENT correctness (column headers, PDF font per the "Label Exporter PDF font" memory ruling, split-file boundaries) for Legacy Order's Excel/PDF export, nor for `export_document_service.py`'s configurable export |

**Summary: 11 of 30 areas have solid coverage, 3 are partial, 16 have zero
test coverage found.** The zero-coverage areas cluster heavily in exactly
the five procurement sub-routers flagged in doc 09 as having no auth either
(#14, #15, #17, #18, #20) — these modules are under-tested AND under-
authorized, which is a worse combination than either alone: a regression in
`optimization_service`'s move-suggestion math would currently be caught by
neither a business-logic test nor an authorization test.

## 3. The existing "legacy vs NEXORA" comparison harness — what it actually is

Three files form a real, working golden-comparison harness, confirmed by
reading them in full:

- **`backend/modules/procurement/legacy_order_parity.py`** — a pure-Python
  (no SQL Server I/O) transcription of `order_local.sql`, `order_remote.sql`,
  `order_warehouse.sql`, and the Additional Row zeroing in
  `order_process.insert_data_into_destination`. Exposes `min_qty`/`max_qty`
  CASE logic (`:58-80`) and (per the test file's usage) a `buyer_result`
  entry point. Explicitly documents that the three modes (local/remote/
  warehouse) are NOT the same formula — remote divides by SaleUnit with no
  NULLIF and uses `>` instead of `>=` on the date spike. VERIFIED.
- **`tests/procurement_formula_compare.py`** — test-support module (not a
  test file itself — no `test_` functions) defining THREE parallel pure
  functions over the same synthetic cases: `target_formula` (the agreed
  2026-10-19 Procurement Workspace rules), `legacy_order_local` (SQL
  transcription + Additional Row zeroing), and `legacy_vb_form1` (the much
  older VB Form1.FetchSourceData arithmetic, same as legacy_order_local
  except recency is hardcoded to 10 days instead of 15). VERIFIED
  (`:1-90`, docstring + `legacy_bounds`/`legacy_order_local` read in full).
- **`tests/test_procurement_formula_compare.py`** — the actual pytest file.
  Calls `decision_rules.evaluate` (the REAL, live Nexora engine — not a
  reimplementation, per its own docstring `:11`) against the SAME synthetic
  case dict as `legacy_order_local`/`legacy_vb_form1`, and asserts the three
  outputs either agree or documents exactly why they diverge. VERIFIED
  (`:1-60` read; imports `decision_rules` directly, builds a
  `DecisionParameters` object per case at `_nexora()`, `:31-56`).
- **`tests/test_legacy_order_parity.py`** — a second, overlapping harness:
  calls `legacy_order_parity.buyer_result` directly (not the compare-module
  trio) across local/remote/warehouse modes, and includes clause tests that
  read the actual `.sql` files off disk (`_sql()`, `:34-35`) and assert
  specific substrings are present — i.e. it also guards against the SQL
  transcription silently going stale if someone edits `order_local.sql`
  without updating the Python port. VERIFIED (`:1-60` read; `_SQL = Path(...)
  "modules"/"legacy_order"/"sql"`, confirms this reads the live SQL files,
  not committed copies).

**So: a real golden-file-style comparison harness already exists today**,
and it is unusually rigorous — it doesn't just compare numbers, it also
locks the Python transcription to the literal SQL text so the two can't
silently drift apart. What it does NOT do, and what would be needed for the
"old Legacy Order vs future Enhanced Legacy Order" comparison the task asks
about:

1. **It compares against synthetic/hand-built cases, not recorded production
   inputs.** `cases()` (referenced but not the full body read this pass) in
   `procurement_formula_compare.py` is a fixed, hand-authored case list —
   there is no mechanism found that captures a real store's actual
   window-sales/stock/frequency numbers from a live order run and replays
   them through both engines.
2. **It compares formulas, not full order runs.** The harness operates at
   the level of "given this one product's numbers, does min_qty/max_qty/
   inclusion agree" — it does not run an entire store's Order Process end to
   end and diff the resulting order (every product, every supplier
   assignment, every qty) between the legacy engine and Nexora's.
3. A SEPARATE, simpler dry-run tool already exists for a related but
   different comparison: `legacy_order/router.py`'s `GET /engine/{store_name}
   /compare.xlsx` (`:406-428`, VERIFIED) calls `rulebook_order.compare_engines`
   to produce an Excel workbook comparing the **Legacy SQL engine vs the
   platform's own Rulebook engine** for a real store, live data, writing
   nothing — this is a genuine "dry run against real production data"
   capability, but it compares Legacy-SQL-engine vs Rulebook-engine, NOT
   Legacy vs a hypothetical future "Enhanced Legacy Order." It is evidence
   the codebase already has the pattern (read-only side-by-side Excel diff
   keyed by store) that a new Legacy-vs-Enhanced comparison could reuse.

## 4. Proposed regression approach for Legacy vs future Enhanced Legacy Order

Given what exists, the lowest-risk, most reuse-friendly approach:

1. **Reuse the `compare.xlsx` pattern (`legacy_order/router.py:406-428` +
   `rulebook_order.compare_engines`) as the shape for a new "Legacy vs
   Enhanced" dry-run endpoint.** It already solves: resolving a real store,
   running two engines over the same real data, and rendering an Excel diff
   with zero writes. Point it at (old engine function, new engine function)
   instead of (legacy SQL, rulebook).
2. **Capture recorded production inputs, not just synthetic cases, for the
   formula-level harness.** `procurement_formula_compare.cases()` should
   gain a mode that loads a snapshot of real `window_sales_qty`/
   `line_frequency`/`max_line_qty`/`total_stock`/`sale_unit`/`last_sale`/
   `last_received` tuples pulled once (read-only) from a real store's recent
   Order Process run, so the parity tests exercise the actual long-tail of
   production data shapes (zero sale_unit, null last_received, fractional
   stock, etc.) rather than only the hand-picked edge cases already present.
   This is additive — it would sit alongside, not replace, the existing
   hand-authored `cases()`.
3. **Golden-file snapshot per store, per day, for whole-order comparison.**
   Serialize each store's full generated order (every product_code,
   final engine qty, assigned supplier) from a live Order Process run to a
   JSON/CSV snapshot committed under something like
   `backend/tests/golden/legacy_order/<store>/<date>.json`. When "Enhanced
   Legacy Order" exists, a new test runs the SAME captured inputs (stock/
   sales/frequency snapshot, not a live DB) through both the old and new
   engine and diffs against the golden file — catching any unintended
   change to the OLD engine's behavior as a regression, and making the NEW
   engine's deltas an explicit, reviewable diff rather than a surprise.
   `test_legacy_order_parity.py`'s pattern of reading the live `.sql` files
   and asserting clause presence is the right model for keeping any such
   snapshot from going stale silently — the same "clause lock" idea should
   gate the golden files (e.g. a test that fails loudly if `order_local.sql`
   changes without a human re-generating the golden snapshots).
4. **A parallel dry-run comparison MODE in production**, not just in tests:
   expose the Enhanced engine behind a flag (mirroring
   `PROCUREMENT_GENERATION_PROFILE` in `legacy_order_parity.py:34-37`, which
   already toggles between `legacy_local` and `nexora` profiles) so a real
   Order Process run can compute both engines' outputs server-side, persist
   only the chosen (old) engine's result as the real order, but also log/
   store the Enhanced engine's hypothetical result for side-by-side review
   — i.e. extend the existing profile-flag pattern rather than inventing a
   new mechanism. This gives the team real-world volume of comparisons
   without ever submitting an order generated by the unproven engine.
5. **Close the tenant/store-isolation test gap concurrently.** Since
   doc 09 found 6+ procurement routers with no tenant-scoping test at all,
   any new Enhanced-Legacy-Order work that touches those routers should not
   ship without adding the `test_procurement_reports_tenant_scoping.py`-style
   403/200/superadmin matrix for whichever router it extends — otherwise the
   same unfixed gap just grows a new, also-untested surface.

## 5. Blockers / caveats

- Not all test files were read to EOF — several (`test_procurement_pm_
  workflow.py`, `test_procurement_sprint3.py`, `test_vpl_history*.py`,
  `test_legacy_order_rulebook_engine.py`, and others marked INFERRED above)
  were identified by name/location only; their actual coverage could shift
  some "UNCOVERED" calls to "Covered" if read in full. This report
  prioritized the modules doc 09 flagged as auth-gapped (optimization,
  intelligence, pipeline, snapshot, compare, orchestration) since that's
  where business-rule gap and security gap compound.
- No test was executed (per task instructions — read-only). "Automated:
  pytest" above means the file is structured as pytest and appears
  self-contained (no live DB/network required per its own fixtures/
  monkeypatching), not that it was run and confirmed green in this session.
- `desktop/supplier-stock-client`'s test runner config (`package.json`
  test script) was not opened — "Node's built-in `node:test`" is inferred
  from import syntax only.
