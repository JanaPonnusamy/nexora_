# 11 — Target Architecture & Migration Plan

Status: PROPOSED. This document designs, but does not authorize or
implement, the consolidated architecture. It is built strictly on the
VERIFIED/PARTIAL findings of docs 02–10 and 15–17 — every design choice
below cites the evidence it rests on; where evidence is thin, that is
stated rather than papered over.

---

## 1. Proposed final architecture

```
                         sync.* (Products, ProductSaleInformation,
                         PurchaseTrans, ProductTrans) — READ ONLY
                         by both engines today (doc 04 §8, §9)
                                      │
                                      ▼
                    ┌─────────────────────────────────┐
                    │  CYCLE / REFRESH (reused as-is)  │   procurement.procurement_cycles
                    │  procurement.orchestration_service│   procurement.procurement_refreshes
                    └─────────────────┬─────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────┐
                    │  SHARED CALCULATION LAYER         │
                    │  legacy_order_parity.py            │ ← already the proven,
                    │  (promote to the canonical,        │   default, unit-tested
                    │   single-owner implementation)     │   bridge (doc 04 §5)
                    └─────────────────┬─────────────────┘
                                      │
                         ┌────────────┴────────────┐
                         ▼                          ▼
              ┌────────────────────┐   ┌─────────────────────────┐
              │ LEGACY ORDER TABLES │   │ PROCUREMENT VPL / WORKING │
              │ OrderManagement,    │   │ ITEMS                     │
              │ OrderHeaderDetails  │   │ procurement_virtual_      │
              │ (unchanged shape,   │   │ products, procurement_    │
              │  doc 08 §2)         │   │ order_items                │
              └──────────┬──────────┘   └─────────────┬─────────────┘
                         │                             │
                         ▼                             ▼
              Order Workspace UI              PM Workspace UI
              (Qty Check/Pending/Export,       (Supplier Assignment,
               unchanged per doc 17 §1)         Export, GRN Reconciliation)
```

**This is not a new pipe** — it is the pipe that already exists today
between Procurement's Refresh and `legacy_order_parity.py` (doc 04 §4-§5),
with one structural change: `legacy_order_parity.py` becomes the **single
owned** calculation module rather than a parity-checking transcription that
must be kept in sync by hand with a separate, independently-maintained
`order_process.py`/`repository.py` SQL implementation. Both the Legacy
Order engine and the Procurement VPL generation call the *same* module for
the *same* answer, instead of two people maintaining two copies of the same
formula (the exact risk doc 04 §7 and doc 06 narrative note 6 flag today).

## 2. Shared data layer

**What already qualifies as "shared" (VERIFIED, no new work)**:
- `sync.Products`, `sync.ProductSaleInformation`, `sync.PurchaseTrans`,
  `sync.ProductTrans` — both engines already read these tables directly,
  independently (doc 04 §8, §9; doc 06 §0). No migration needed to "share"
  them — they are already the common source.
- The real OrderNMC→NEXORA_PLATFORM sync engine
  (`legacy_order.sync_engine.py`) — Procurement's `distribution_service`
  already calls it rather than duplicating it (doc 04 §6; doc 05 §C.1). This
  is the correct existing precedent for "reuse, don't duplicate" and should
  be the template for anything else currently duplicated.

**What requires reconciliation before being called "shared" (NOT yet
resolved, flagged in doc 03/doc 05)**:
- `sync.Products` duplicate-row exposure — both `decision_repository.py`
  and `legacy_order/repository.py` were independently patched for the same
  root cause in the current working tree (doc 04 §15, doc 02 §6). The fix
  should move upstream (fix `sync.Products`'s sync/merge logic to guarantee
  one row per `(store_id, ProductCode)`) rather than being defended against
  in every consumer separately.
- Supplier Stock: `procurement/supplier_stock_*` vs.
  `legacy_order/supplier_stock_harvest.py` + `supplier_portal.py` — two
  independent implementations of conceptually the same capability (doc 05
  §B, §C.2). Pick one owner before treating either as "the shared layer."
- Non-Moving Stock: `nonmoving_report/*` vs. `nonmoving_analysis/*`, both
  mounted, never diffed against each other (doc 05 §B, §C.2).
- Warehouse demand signal: Product Intelligence's cross-store VPL union vs.
  NMW Sales Report's despatch-bill signal (doc 05 §C.3) — not yet
  cross-validated; this investigation does not resolve which is correct.

## 3. Cycle/Refresh integration

Per doc 04, the Cycle→Refresh pipeline is already well-formed for reuse as
the data-preparation layer **in front of** a consolidated engine — but two
real gaps must be closed first, not inherited silently:

1. **No server-side overlap lock on `create_refresh`** (doc 04 §11) — the
   `refreshing_in_progress()` helper exists but is never called. Before
   Legacy Order generation is wired to depend on a Refresh being complete,
   this must be fixed, or a double-triggered refresh could leave Legacy
   Order reading a half-built VPL.
2. **VPL History and Refresh Idempotency are both off by default** (doc 04
   §3, §13) — their migrations are marked "NOT APPLIED." If the consolidated
   architecture is to rely on Refresh history for comparison/rollback
   (doc 17 §6), these must be formally applied and enabled first, not
   assumed live because the code exists.

Legacy Order's own order generation (`order_process.run_order_process`)
would, under this target architecture, become a **consumer of a completed
Refresh** rather than running its own independent SQL pass — this is new
wiring (Q5/Q6 in doc 04 are both currently NO: Legacy Order does not consume
Procurement's refreshed data today). This is the single largest piece of
new integration work implied by the target architecture, and should be
built additively per doc 17 §2 (a feature-flagged path that falls back to
Legacy Order's existing independent SQL if the Refresh is missing/stale).

## 4. Legacy Order enhancements (what moves, what doesn't)

| Capability | Source today | Action under target architecture |
|---|---|---|
| Quantity formula | Two copies: `order_local.sql`/etc. (SQL) and `legacy_order_parity.py` (Python, kept in parity by hand) | Python (`legacy_order_parity.py`) becomes the ONE owned implementation; the SQL files become historical reference / fallback only, per doc 17 §1 (never deleted without separate approval) |
| Cycle/Refresh lifecycle | Procurement-only today | Adopted as-is by Legacy Order order generation, additively (doc 17 §2) |
| Working Items / Pending | Procurement-only | Adopted conceptually; Legacy Order's existing Qty Check/Pending screens are the UI — the underlying "pending = remaining_qty > 0" derived-state model (doc 05 §A) can back them without a schema rewrite |
| Supplier Optimization (MOV gap-filling) | Procurement-only, net-new, already opt-in | Adopted as a new, additive step after supplier assignment, per doc 06 Rule #24 |
| GRN Reconciliation state model | Procurement-only | Adopted additively; legacy has no equivalent to regress (doc 06 Rule #11) |
| Skip system (`dbo.OrderProductSkip`, 3 modes) | Legacy Order-only | PRESERVED exactly (doc 17 §1); Procurement Refresh's respect for it is UNKNOWN today (doc 06 Rule #29b) and must be verified/wired before cutover |
| Compare-previous-order (4 rules) | Legacy Order-only | PRESERVED exactly (doc 17 §1) |
| Auto-Assign best-margin | Legacy Order-only | PRESERVED exactly; Procurement's own supplier ranking (frequency+recency) is a DIFFERENT, uncompared formula (doc 06 Rule #20) — NEEDS_OWNER_DECISION before either is called canonical |
| Non-moving/slow-moving classification | Procurement rollback engine has it (`movement_class`); live default profile hardcodes it to `None` (doc 06 Rule #18) | ADOPT as a display-only field once the live default profile is updated to populate it — no quantity impact |

## 5. Migration stages (maps to the brief's own §14 roadmap)

This document does not re-author the brief's phased roadmap (Phase
7C.1–7C.7, already specified in the original task and unchanged here). It
adds the specific prerequisites this investigation surfaced for each stage:

- **7C.1 (Architecture Approval)** — cannot complete until the
  owner-decision list in doc 13 is resolved, specifically: canonical
  sales-history window, canonical supplier-ranking formula, whether
  `legacy_order_parity.py` or the SQL files become the retained reference
  implementation, and resolution of the two duplicate-ownership feature
  pairs (§2 above).
- **7C.2 (Shared Data Preparation)** — blocked on fixing the `sync.Products`
  duplicate-row root cause (§2) before building anything new on top of it;
  otherwise every new consumer inherits the same defensive-patch burden two
  modules already carry independently today.
- **7C.3 (Cycle/Refresh Integration)** — blocked on closing the two gaps in
  §3 (overlap lock, VPL History/Idempotency durability) before Legacy Order
  is made to depend on Refresh completion.
- **7C.4 (Enhanced Legacy Order Engine)** — must follow doc 17's additive/
  flag-gated/fail-independently discipline exactly; the SaleUnit-blocking
  and stock-source conflicts (doc 06 Rules #7, #22) must be fixed in
  whichever engine is promoted, with the regression tests in doc 17 §6 in
  place first.
- **7C.5 (Prediction)** — blocked on nothing structural, but doc 07
  confirms no historical-trend infrastructure exists yet (only rolling-window
  reads); this phase starts from zero, not from an existing partial system.
- **7C.6 (Functional Validation)** — the existing `rulebook_order.compare_engines`/
  `compare_workbook` dry-run harness (doc 02 §3.11) and the
  `legacy_order_parity`/`tests/procurement_formula_compare.py` test harness
  (doc 10 §3) are the correct starting point; doc 17 §6 specifies what to add
  to them.
- **7C.7 (Retirement)** — not authorized by this investigation, per the
  brief. Flagging only: Procurement already depends on several Legacy Order
  files for infrastructure, not business logic, that it borrowed rather than
  duplicated (`sync_engine`, `branch_stock`, the abnormal-sales DB
  connection — doc 04 §6, doc 05 §1). Retirement planning must account for
  these dependencies explicitly; they are not Legacy-Order-business-logic
  that simply goes away when Legacy Order's UI is retired.

## 6. Rollback strategy

The architecture already contains its own rollback precedent, twice over:
- `PROCUREMENT_GENERATION_PROFILE=nexora` is the existing, proven
  env-var rollback away from the legacy-parity default (doc 04 §5, doc 06 §0).
- `dbo.LegacyOrderEngine.Engine` is the existing, proven per-store rollback
  between LEGACY SQL and RULEBOOK (doc 02 §3.11).

The target architecture's rollback strategy is the same shape, applied one
level up: a per-store (not global) flag that reverts order generation to
"run the existing, untouched SQL/Python path exactly as it works today,"
with no code deleted or disabled to make that possible — per doc 17 §7. This
is deliberately not a new rollback mechanism to design; it is the existing
one, extended.
