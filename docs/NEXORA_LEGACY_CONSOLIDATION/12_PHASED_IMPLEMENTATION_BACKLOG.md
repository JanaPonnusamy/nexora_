# 12 — Phased Implementation Backlog

Status: PROPOSED. Ordered by the brief's own Phase 7C.1–7C.7 staging (§14
of the original task), not re-authored here. This backlog is NOT authorized
for execution — it is the planning artifact Phase 7C.1 (Architecture
Approval) should review. Every item cites the investigation finding it
responds to.

---

## Phase 7C.1 — Compatibility and Architecture Approval (no code)

| Task | Depends on | Owner decision required | Acceptance criteria |
|---|---|---|---|
| Resolve decisions A1–A7 (doc 13 §A) | — | YES — all seven | Written, dated owner sign-off per decision, recorded back into doc 13 or a successor doc |
| Triage and fix D1 (cross-tenant auth gap, doc 09 §2) | — | Partial — fix approach, not whether to fix | `optimization_router.py`, `intelligence_router.py`, `pipeline_router.py`, `snapshot_router.py`, `compare_router.py`, and `procurement/router.py`'s `update_cycle`/`delete_cycle` each gain the same `require_procurement_*` + `assert_tenant_access` pairing `pm_router.py` already uses (doc 09 §2b); `test_procurement_reports_tenant_scoping.py`'s pattern (doc 10 §1c) extended to each |
| Confirm whether `legacy_order_parity.py` becomes the single owned implementation (B1) | A1 | YES | Decision recorded; if yes, `order_local.sql`/etc. explicitly relabeled "historical reference, not canonical" in their own file headers |

## Phase 7C.2 — Shared Procurement Data Preparation

| Task | Depends on | Tables affected | Risk | Tests required |
|---|---|---|---|---|
| Root-cause and fix `sync.Products` duplicate-row possibility (C5, doc 04 §15) | 7C.1 complete | `sync.Products` (store-sync merge pipeline) | High if unfixed — every downstream consumer currently defends against it independently instead of relying on a guarantee | Add a test asserting `sync.Products` sync/merge produces at most one live row per `(store_id, ProductCode)`; keep the existing defensive `ROW_NUMBER()`/`OUTER APPLY` guards in `decision_repository.py`/`workspace_repository.py`/`legacy_order/repository.py` as defense-in-depth, don't remove them |
| Reconcile Supplier Stock ownership (A5) | 7C.1 (A5 decided) | `procurement.supplier_stock*` and/or `OrderNMC.SupplierStock`/`SupplierOffer` (exact names: see doc 03 CSV) | Medium — picking the wrong owner means re-migrating consumers later | Regression test comparing both implementations' output for the same store/date before retiring either |
| Reconcile Non-Moving Stock ownership (A6) | 7C.1 (A6 decided) | per doc 03 CSV, `nonmoving_report`/`nonmoving_analysis` tables | Medium, same pattern as above | Same pattern as above |
| Build the data-freshness check Legacy Order would need before trusting a Refresh | 7C.1, Cycle/Refresh integration below | `procurement.procurement_refreshes.snapshot_status` | Low — read-only check | Test asserting generation refuses/warns when `snapshot_status != 'Ready'` |

## Phase 7C.3 — Cycle and Refresh Integration

| Task | Depends on | Risk | Tests required |
|---|---|---|---|
| Wire `repository.refreshing_in_progress()` into `orchestration_service.create_refresh` (close the overlap gap, doc 04 §11) | — | Medium — currently two concurrent refreshes on the same cycle are unprevented server-side | Test: second concurrent `create_refresh` call against the same cycle is rejected or queued, not silently racing |
| Apply and enable `PROCUREMENT_REFRESH_IDEMPOTENCY` (migration 0029) if retry-safety is required for the consolidated flow | A1–A7 resolved | Low — additive, already flag-gated | Existing idempotency-key tests (if any — not confirmed in doc 10, verify before relying on them) |
| Apply and enable `PROCUREMENT_VPL_HISTORY` (migration 0030) if Refresh history is to back the regression/comparison tooling in doc 17 §6 | — | Low — additive, already flag-gated, but migration explicitly marked "do not run without explicit authorization" in its own header | Verify `vpl_history_repository.write_history_batch`'s retry-safe unique index behaves as documented, under a real concurrent-retry test |
| Build the "Legacy Order consumes a completed Refresh" integration path, additively and flag-gated (doc 11 §3) | All of the above | High — this is new wiring; Legacy Order today runs its own independent SQL (doc 04 §6, Q5/Q6 both NO) | Golden-file comparison: Legacy Order's existing output vs. the new Refresh-driven path, for the same store/date, byte-identical before this path is enabled by default anywhere |

## Phase 7C.4 — Enhanced Legacy Order Engine

| Task | Depends on | Risk | Tests required |
|---|---|---|---|
| Add a startup assertion/test guarding against `PROCUREMENT_GENERATION_PROFILE=nexora` being set without the stock-source fix (doc 06 Rule #7, Risk #1 in doc 01 §4) | — | High if skipped — ~26% of a catalogue could silently shift order quantities | Unit test asserting the assertion fires in the unsafe configuration |
| Fix `decision_rules.final_required`'s SaleUnit fallback to match the already-locked registry target (block, don't fall back to loose units) (doc 06 Rule #22) | — | Medium — only affects the non-default rollback engine today, but must be fixed before any promotion | Test asserting `sale_unit<=0` blocks the line under BOTH profiles |
| Wire supplier-pending (`PRR-STK-PENDING`) to a real source, OR formally confirm it stays 0 (B2) | B2 decided | Medium — changes historical order sizes if wired | Regression comparison before/after, store-by-store opt-in |
| Verify and, if missing, wire Procurement Refresh's respect for `dbo.OrderProductSkip` (A3) | A3 decided | Medium-High — a wrong answer here means skipped products silently resurface | Test: a product skipped `until_next_sales` under Legacy Order stays skipped across a Procurement Refresh, until a real sale occurs |
| Apply migration 0026 (Rules Registry durable persistence) if store/tenant overrides are to be trusted in production (B4) | B4 decided | High if skipped — overrides silently revert on restart today | Test: override survives a simulated backend restart (requires durable storage, not just the in-process `RulesRegistry`) |
| Apply migration 0030 (VPL History durable persistence) if manual-edit carry-forward is to be trusted in production (B4) | B4 decided | Same as above | Same pattern |
| Reconcile the warehouse-demand signal (A4) into whichever engine is canonical | A4 decided | Medium — affects real NMW purchase volume | Comparison report: Product Intelligence's union-find output vs. NMW Sales Report's despatch-bill output, for the same period, presented to the owner before either is treated as sole source |
| Reconcile supplier-selection formula (A2) into whichever engine is canonical | A2 decided | Medium — changes which supplier gets which product line | Comparison report over historical assignments, not a priori preference for the "simpler" or "more sophisticated" formula |

## Phase 7C.5 — Prediction and Procurement Intelligence

Per doc 07: there is no existing forecasting infrastructure to extend —
this phase starts from the dataset inventory in doc 07 §1, not from a
partial implementation.

| Task | Depends on | Risk | Tests required |
|---|---|---|---|
| Build a deterministic baseline (moving average + week-of-year seasonal index from `ProductSaleInformation`; purchase-rate trend from `PurchaseTrans`; multi-month stock trend from `ProductTrans`'s monthly-keyed `StockInHand`) — per doc 07's own recommendation | 7C.1–7C.4 stable | Low — read-only, additive, recommendation-mode only per doc 17 §2.4 | Backtest against old Refresh rows vs. actual later sales/receipts (contingent on confirming old Refresh rows are retained — C2) |
| Confirm C1/C2 (actual historical depth, retention) via a read-only live-DB check, if/when authorized | Owner authorizes a read-only DB check | None if truly read-only | N/A — a verification task, not a code task |
| Explicitly do NOT introduce ML before the deterministic baseline is backtested and measured | — | — | Per the brief: "Add machine learning only if data quality and measured performance justify it" |

## Phase 7C.6 — Functional and Business Validation

| Task | Depends on | Risk | Tests required |
|---|---|---|---|
| Extend `rulebook_order.compare_engines`/`compare_workbook` to cover Legacy-vs-Enhanced, not just Legacy-vs-RuleBook (doc 10 §2 recommendation) | 7C.4 complete | Low — extending an existing, proven tool | The extended tool itself IS the test harness |
| Add recorded-production-input cases to `tests/procurement_formula_compare.py` (today synthetic-only, doc 10 §1b) | — | Low | New test cases, no new infrastructure |
| Run the comparison across multiple stores/tenants (retail, warehouse, agent-synced) per the brief's own §12 requirement | 7C.1–7C.5 | — | Per-store-type comparison report |
| No real order submission during any of this validation (brief §12, restated in doc 17 §6.3) | — | — | Dry-run/logging mode only, per doc 17 §2.4 |

## Phase 7C.7 — Procurement Workspace Retirement

**NOT AUTHORIZED by this investigation or this backlog.** Listed only for
completeness per the brief's own roadmap structure. Before this phase can
even be planned in detail, doc 11 §5 flags that Procurement already
depends on several Legacy Order *infrastructure* files
(`sync_engine.py`, `branch_stock()`, the abnormal-sales DB connection) that
are not procurement business logic and would need to be explicitly
re-homed or kept alive, not simply deleted alongside any retired UI.

---

## Cross-cutting: files and modules likely affected (for scoping, not a work order)

| Area | Files (non-exhaustive, see doc 14 for full citations) |
|---|---|
| Shared calculation layer | `backend/modules/procurement/legacy_order_parity.py`, `quantity_profile_t.py` |
| Legacy Order core | `backend/modules/legacy_order/order_process.py`, `repository.py`, `rulebook_order.py`, `service.py` |
| Procurement Decision Engine | `backend/modules/procurement/decision_service.py`, `decision_repository.py`, `decision_rules.py`, `orchestration_service.py` |
| Security fix (D1) | `backend/modules/procurement/optimization_router.py`, `intelligence_router.py`, `pipeline_router.py`, `snapshot_router.py`, `compare_router.py`, `router.py` |
| Rules durability (B4) | `backend/modules/procurement/sql/0026_procurement_rules_registry.sql`, `0030_vpl_history_persistence.sql`, `rules_resolution.py`, `vpl_history_repository.py` |
| Supplier Stock reconciliation (A5) | `backend/modules/procurement/supplier_stock_service.py`, `supplier_stock_repository.py`, `backend/modules/legacy_order/supplier_stock_harvest.py`, `supplier_portal.py` |
| Non-Moving reconciliation (A6) | `backend/modules/nonmoving_report/*`, `backend/modules/nonmoving_analysis/*` |
