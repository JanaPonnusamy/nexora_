# 13 — Unknowns & Owner Decisions

Consolidated from docs 02–10, 15–16. Each item states what is unresolved,
why it matters, and what evidence exists today. None of these should be
decided unilaterally by an implementer — per the brief, "a more
sophisticated formula is not automatically better," and several of these
are exactly that trap.

---

## A. Decisions the owner must make before Phase 7C.2

| # | Decision | Current state (evidence) | Why it matters |
|---|---|---|---|
| A1 | Which sales-history window is canonical: hardcoded 90 days (Legacy/live-default), `PRR-QTY-WINDOW` registry (rollback engine, store-overridable), or `rolling_days` (rollback engine, Refresh-header-supplied)? | Three independent knobs exist today that don't talk to each other (doc 06 Rule #2) | Changing one without the others silently diverges Qty Check vs. Procurement screens for the same store |
| A2 | Which supplier-selection/ranking formula is canonical: legacy desktop's 5-factor weighted score, Procurement's live 2-factor (frequency+recency), or Procurement's locked-but-unimplemented 90-day/latest-6-GRN cost formula? | Three different, unreconciled formulas compete; none validated against actual outcomes (doc 06 Rule #15, #20) | Different top-ranked supplier is plausible for the same product under each formula — a real purchasing-decision change, not cosmetic |
| A3 | Does Procurement Refresh respect Legacy Order's durable skip-carry-forward system (`dbo.OrderProductSkip`, 3 modes)? | `decision_repository.load_source` has no join against any skip table found in this audit (doc 06 Rule #29, narrative note 6) | If Procurement Refresh ignores active skips, a product a store operator deliberately suppressed ("until next sales") could resurface under a consolidated engine |
| A4 | Which warehouse-demand signal is correct for NMW ordering: Product Intelligence's cross-store VPL union, or NMW Sales Report's despatch-bill-based signal? | Two different, uncompared answers exist (doc 05 §C.3); memory hint claims despatch-bill is correct but this was not independently re-verified in code | Directly affects how much the warehouse buys — a real inventory/cash decision |
| A5 | Which Supplier Stock implementation is authoritative: `procurement/supplier_stock_*` or `legacy_order/supplier_stock_harvest.py` + `supplier_portal.py`? | Both exist, mounted, not reconciled (doc 05 §B, §C.2) | Blind reuse of both would duplicate maintenance effort and could diverge on live supplier stock numbers shown to buyers |
| A6 | Which Non-Moving Stock implementation is authoritative: `nonmoving_report/*` or `nonmoving_analysis/*`? | Both mounted, never diffed against each other in this pass (doc 05 §B, §C.2) | Same duplication risk as A5 |
| A7 | Is the "Unified Procurement Workspace" directive (merge OW + Procurement into one workspace — an older memory note) superseded by this investigation's "consolidate around Legacy Order" framing, or do both apply? | No code contradicts the newer direction, but the two historical directives are not literally the same thing (doc 02 §5.1) | Affects whether the target UI is "Legacy Order Workspace, enhanced" or "one new merged workspace" — a user-facing decision, not just backend |

## B. Decisions the owner must make before Phase 7C.4

| # | Decision | Current state (evidence) | Why it matters |
|---|---|---|---|
| B1 | Should `legacy_order_parity.py` (Python) become the single owned implementation, with the SQL files (`order_local.sql` etc.) demoted to historical reference only? | Proposed in doc 11 §4 as the lowest-risk path, but not yet owner-approved | Changes which file future bug reports/changes target; the SQL files currently ARE the ported-from-VB source of truth |
| B2 | Should the `PRR-STK-PENDING` placeholder (confirmed supplier pending, always 0 today in both LEGACY and RULEBOOK) be wired to a real data source, and if so, what source? | No source currently verified to exist; registry itself blocks the value (doc 02 §3.7, doc 06 Rule #9) | A real pending-purchase subtraction could meaningfully reduce over-ordering, but changes historical order sizes — needs explicit opt-in design |
| B3 | Should the RULEBOOK/LEGACY SaleUnit-missing asymmetry be reconciled (LEGACY silently orders 0; RULEBOOK raises `BLOCKED_SALE_UNIT`)? | Confirmed asymmetry, not yet fixed in either direction (doc 02 §3.9, doc 06 narrative note 2) | Low risk today (RULEBOOK is opt-in, not default) but must be resolved before any engine is promoted platform-wide |
| B4 | Should store/tenant rule overrides and manual-edit carry-forward (`RulesRegistry`, `VplWorkspace`) be made durable (apply migrations 0026/0030) before being advertised as production features? | Both are in-process-only today; a backend restart silently reverts them with no operator warning (doc 06 Rule #26, #28, narrative note 3) | A store manager or PM could lose configured overrides/edits without knowing it happened |

## C. Items this investigation could not resolve (code-only limits)

| # | Item | What's missing | How to resolve |
|---|---|---|---|
| C1 | Actual earliest/latest date in `sync.ProductSaleInformation`/`PurchaseTrans`/`ProductTrans` (central copy) | Code shows no retention floor on the HO side; real depth is a live-DB fact (doc 07 §1.1) | A read-only `SELECT MIN(TransactionDate)` against a non-production dev DB, if/when authorized |
| C2 | Whether old `procurement_virtual_products`/`procurement_order_items` rows from past Refreshes are retained long-term | No purge job found, but not positively confirmed either (doc 07 blockers) | Same as C1 |
| C3 | Whether `vpl_history.py` (the older in-memory prototype, distinct from `vpl_history_repository.py`) is still reachable from any live UI | Not traced to a frontend call site in this pass (doc 04 §13, open question) | Grep `frontend/` and `desktop/` for its router's mount path |
| C4 | Whether `snapshot_service.py`'s changed-only incremental refresh path (`refresh_vpl(changed_only=True)`) has any live caller | `orchestration_service.py` never calls into it; UI call site not traced (doc 04 §10) | Grep `frontend/`/`desktop/` for `/vpl/{id}/snapshot/refresh` |
| C5 | Whether `sync.Products` can legitimately hold more than one live row per `(store_id, ProductCode)` by design, or whether this is purely a sync-pipeline defect | Two independent defensive patches exist in the current working tree (doc 04 §15, doc 02 §6) treating it as a defect to guard against, not confirmed root-caused | Needs direct investigation of the store-sync merge logic that populates `sync.Products` |
| C6 | Full picture of which `.sql` files under `backend/modules/*/sql/` are auto-applied vs. human-run-only, beyond the sample verified in doc 16 | Doc 16 verified the pattern via representative examples (procurement, legacy_order, bootstrap); not every module's files were individually traced | Would require a full repo-wide audit (not attempted — breadth over completeness was the brief for doc 03) |

## D. A live, unrelated finding that needs its own decision track

| # | Item | Evidence | Recommended track |
|---|---|---|---|
| D1 | Five Procurement sub-routers (`optimization_router`, `intelligence_router`, `pipeline_router`, `snapshot_router`, `compare_router`) and two endpoints in `procurement/router.py` (`update_cycle`, `delete_cycle`) have zero tenant/auth checks — a real cross-tenant IDOR exposure, with direct precedent (`reports_router.py` had this exact bug class found and fixed before; `test_procurement_reports_tenant_scoping.py` proves it) | doc 09 §2, confirmed by reading every route in each named router | This is a security fix, not a consolidation design question. Recommend triaging and fixing independently of the Phase 7C timeline — it does not need to wait for any architecture decision above. |

## E. Conflicting or ambiguous rules flagged during the investigation

- Doc 06 Rule #7 (stock source) and Rule #22 (SaleUnit blocking) are each
  *already* correctly identified and locked in the Rules Registry toward the
  legacy-safe behaviour — these are not open questions, they are confirmed
  risks with a known-correct answer that simply hasn't been enforced by code
  yet (no startup assertion exists). Listed here for completeness, not as
  open decisions.
- Doc 06 Rule #26/#27 note that neither Legacy nor NEXORA has a genuine
  tenant-level (as opposed to store-level) rule-override tier — NEXORA's own
  registry documentation acknowledges this gap rather than inventing a
  fictitious tier. Not an open decision unless the owner wants to introduce
  a tenant tier that doesn't exist on either side today.
