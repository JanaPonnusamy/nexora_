# 01 — Executive Summary

Phase 7C: Enhanced Legacy Order Consolidation — Investigation & Migration Blueprint.
Status: **INVESTIGATION COMPLETE**. Read-only throughout. No source code, database
schema, or business data was modified to produce this document set — see
§8 "Changes made" for the verification evidence.

This summary synthesizes the findings of docs 02–17. Tags — **VERIFIED** (read
the exact code), **PARTIAL** (read code, inference fills a gap),
**INFERRED** (reasoned from adjacent evidence), **UNKNOWN** (flagged, not
resolved) — carry through from the source documents; this summary does not
introduce new claims beyond what they establish.

---

## 1. The single most important finding

**The consolidation the owner is asking for has already substantially
happened in the code, quietly, as a byproduct of other work.**

`backend/modules/procurement/legacy_order_parity.py` is a maintained,
unit-tested, line-faithful Python transcription of Legacy Order's own
`order_local.sql` / `order_remote.sql` / `order_warehouse.sql` quantity math.
It is not a side experiment — it is the **default** generation profile for
Procurement's Decision Engine (`decision_service.py:93-97`,
`PROCUREMENT_GENERATION_PROFILE` defaults to `legacy_local`). The *original*
Nexora formula (`decision_rules.evaluate`) is the one demoted to an explicit,
non-default rollback path. (VERIFIED — doc 04 §5, doc 06 §0.)

Symmetrically, inside Legacy Order itself, a second engine
(`rulebook_order.py`, owner-approved 2026-10-25) already computes quantities
using Procurement's own formula module
(`modules.procurement.quantity_profile_t.evaluate_profile_t`) and writes the
result into the **same** `OrderManagement` tables the classic SQL engine
writes into (VERIFIED — doc 02 §3.3).

So today there are not two competing, isolated procurement systems —
there are **three quantity-calculation code paths that already agree with
each other on the live default configuration**, sharing tables and
sharing a formula module. The consolidation task is less "merge two
systems" and more "retire the duplication that already exists, and choose
one place for the shared logic to live."

## 2. Current architecture (as verified, not as assumed)

```
                 Legacy Order (backend/modules/legacy_order/)
                 ───────────────────────────────────────────
  sql/order_local.sql, order_remote.sql, order_warehouse.sql  (LEGACY engine)
  rulebook_order.py → procurement.quantity_profile_t          (RULEBOOK engine)
                 │
                 ├─ writes → OrderManagement / OrderManagementBackup /
                 │           OrderHeaderDetails / dbo.OrderProductSkip
                 │
                 └─ depends on (one-way imports, never the reverse):
                        procurement.abnormal_sales_service
                        procurement.product_identity
                        procurement.quantity_profile_t
                        procurement.rules_resolution

                 Procurement Workspace (backend/modules/procurement/)
                 ─────────────────────────────────────────────────
  Cycle → Refresh → decision_service.generate_vpl
                        │
                        ├─ legacy_order_parity.py   (DEFAULT profile — reproduces Legacy Order math)
                        └─ decision_rules.evaluate  (ROLLBACK profile — the "real" Nexora formula)
                 │
                 ├─ writes → procurement.procurement_virtual_products (VPL),
                 │           procurement.procurement_order_items (Working Items)
                 │
                 └─ depends on legacy_order for:
                        the real OrderNMC→NEXORA_PLATFORM sync engine
                        (legacy_order.service.start_sync, blocking, before export)
                        branch-stock reads (legacy_order.repository.branch_stock)
                        abnormal-sales DB connection (legacy_order.database)

  Both sides read the SAME sync.* source tables (Products, ProductSaleInformation,
  PurchaseTrans, ProductTrans) independently — no shared read layer today.
```

VERIFIED (doc 02 §2, §4; doc 04 §1, §6, §8).

## 3. Target architecture fit

The brief's target diagram (NEXORA data → Cycle/Refresh → unified data layer
→ Enhanced Legacy Order → output → validation → workflow) is **achievable
with moderate, not extreme, risk**, specifically because:

- The "unified data layer" step is largely already real: `decision_repository.load_source`
  reads the identical `sync.*` tables Legacy Order's own SQL reads, and
  `legacy_order_parity.py` already proves the two rule sets can be made to
  agree exactly (doc 04 §5, §9).
- The "Enhanced Legacy Order Engine" step already has a working seam:
  `rulebook_order.py` demonstrates that a Python-computed quantity can be
  written into Legacy Order's own tables without disturbing the output
  contract (doc 02 §3.3, doc 08 §1).
- The "Legacy Order Output" contract is well-understood and has a complete
  field-level map with risk ratings (doc 08 §2) — the two highest-risk
  fields (`Status`/`Qtycheck`, the workflow state machine, and
  `ProductCode`/`OrderQty`, the join key and the actual decision) have no
  direct Procurement equivalent and must be preserved exactly.

What is **not** already solved, and is the real work of a future phase:

- **No automated, versioned, tenant-aware schema migration mechanism exists**
  anywhere in the codebase (doc 15 §identified gaps, doc 16 §6 — "the single
  biggest gap for the Phase 7C consolidation requirement"). Schema
  propagation across `.73`/`.32`/`.80`/remote-store databases today is
  entirely manual or best-effort self-healing per process, with no
  cross-database tracking.
- **A real, exploitable cross-tenant authorization gap exists today**,
  independent of consolidation: five Procurement sub-routers
  (`optimization_router`, `intelligence_router`, `pipeline_router`,
  `snapshot_router`, `compare_router`) and several endpoints in
  `procurement/router.py` itself (`update_cycle`, `delete_cycle`) have **zero**
  tenant/auth checks (doc 09 §2). This is a security finding that should be
  triaged on its own timeline, not folded silently into the consolidation
  backlog.
- **Several NEXORA capabilities that look production-ready are feature-flagged
  off by default** and have code comments stating their durable persistence
  migrations are "NOT APPLIED": VPL History (`PROCUREMENT_VPL_HISTORY`),
  Refresh Idempotency (`PROCUREMENT_REFRESH_IDEMPOTENCY`), and the
  Rules Registry's per-store override durability (migration `0026`). A store
  manager's custom min/max-cover override or a PM's manual quantity edit is
  **not** currently protected across a backend restart (doc 06 narrative
  note 3, doc 04 §13).
- **No forecasting/ML exists anywhere** — `product_category_ai.py` is an LLM
  call for shelf-label display text only, not a demand signal (doc 07 §0).
  Historical sales (`sync.ProductSaleInformation`) is the strongest
  prediction-ready dataset in the system but is read only as a 90-day rolling
  sum today, never as a longer time series (doc 07 §1.1).

## 4. Main risks (ranked)

1. **Stock-source conflict (doc 06 Rule #7)** — `Products.TotalStock`
   (Legacy, and Procurement's live default) vs. latest-month
   `sync.ProductTrans.StockInHand` (Procurement's rollback engine) disagree
   for an admitted ~26% of a store's catalogue. Already locked in the Rules
   Registry toward `TotalStock`, but only a procedural safeguard — not a code
   assertion — stops the rollback profile from ever becoming default without
   this fix. **Recommend a startup assertion/test as a tripwire.**
2. **No tenant-aware schema migration mechanism** (doc 15, doc 16) — any
   consolidation that requires a new table/column must currently be
   hand-applied, one database at a time, with no cross-database "has this
   landed everywhere" visibility.
3. **Cross-tenant authorization gaps in five live Procurement routers**
   (doc 09) — a real security exposure, not a consolidation-blocking issue,
   but should not be inherited silently into whatever engine survives
   consolidation.
4. **Duplicate `sync.Products` rows per (store, ProductCode) is a live,
   actively-being-patched bug class** (doc 04 §15, doc 02 §6) — both
   Legacy Order's `repository.py` and Procurement's `decision_repository.py`/
   `workspace_repository.py` were independently hardened against this in the
   current working tree. Any unified engine inherits this exposure unless the
   root cause (why can `sync.Products` hold duplicates at all) is fixed once,
   upstream.
5. **Two unresolved "duplicate ownership" feature pairs** need a decision
   before reuse, not an assumption of equivalence: Supplier Stock
   harvesting/analysis (`procurement/supplier_stock_*` vs
   `legacy_order/supplier_stock_harvest.py`), and Non-Moving Stock
   (`nonmoving_report/*` vs `nonmoving_analysis/*`, both mounted, never
   diffed against each other) (doc 05 §C.2).
6. **Two different, uncompared answers exist for "how much should the NMW
   warehouse buy"** — Product Intelligence's cross-store VPL union vs. NMW
   Sales Report's despatch-bill demand signal (doc 05 §C.3). Neither has been
   validated as correct against the other.
7. **Test coverage clusters exactly where authorization gaps cluster** (doc
   10 §1c) — the same five under-authorized Procurement sub-routers are also
   the least-tested, meaning a regression there would likely ship unnoticed
   on both axes simultaneously.

## 5. What can be reused with HIGH confidence (reuse-first priority order)

1. `legacy_order_parity.py` — already the default, already proven, already
   unit-tested in isolation (doc 05 §A, doc 10 §1b).
2. The Cycle → Refresh → VPL sequencing/lifecycle model
   (`procurement_cycles`/`procurement_refreshes`) as the data-preparation
   wrapper Legacy Order currently lacks entirely (doc 04 §1-§2, doc 05 §A row 1).
3. The Working Items / Pending derived-state model (`remaining_qty > 0`,
   no separate Pending table) — simple, portable (doc 05 §A rows "Working
   Order Items", "Pending management").
4. The backward-compatibility idiom already used consistently in 52+ files
   (`COL_LENGTH`/`OBJECT_ID`/`sys.columns` existence checks, graceful
   degrade) — this is the strongest existing asset for the owner's new
   "Legacy Order must survive a missing optional table/column" requirement
   (doc 16 §7). Extend it; do not invent a parallel mechanism.
5. The GRN Reconciliation state model (`EXPORTED → PARTIAL_RECEIVED →
   RECEIVED`) as an additive enhancement — legacy has no equivalent concept
   today and nothing would regress by adding it (doc 06 Rule #11).
6. The Supplier Order Optimization Engine's minimum-order-value gap-filling
   (`optimization_service.py`) — a genuinely new, already-opt-in capability
   with no legacy behaviour to regress (doc 06 Rule #24).

## 6. What requires an explicit owner decision before any code changes

See doc 13 for the full list; headline items:

- Which sales-history window is the one source of truth (90-day hardcoded
  vs. the Rules Registry's `PRR-QTY-WINDOW` vs. the rollback engine's
  `rolling_days`) — three knobs exist today that don't talk to each other
  (doc 06 Rule #2).
- Which supplier-selection/cost-ranking formula is canonical — three
  different, unreconciled formulas currently compete (legacy desktop
  5-factor score, Procurement's live 2-factor ranking, Procurement's
  locked-but-unimplemented 90-day/6-GRN cost formula) (doc 06 Rule #15, #20).
- Whether Procurement Refresh currently respects Legacy Order's durable
  skip-carry-forward system (`dbo.OrderProductSkip`) at all — not confirmed
  either way in this investigation (doc 06 Rule #29, narrative note 6).
- Which of the two warehouse-demand signals (cross-store VPL union vs.
  despatch-bill based) is correct for NMW ordering (doc 05 §C.3).
- Which of the two supplier-stock and two non-moving-stock implementations
  is authoritative (doc 05 §C.2).
- Whether the "Unified Procurement Workspace" directive (an older memory
  note: merge OW + Procurement into one workspace) is superseded by this
  investigation's "consolidate around Legacy Order" framing, or whether both
  are meant to coexist (doc 02 §5.1).

## 7. Overall readiness

**READY FOR ARCHITECTURE REVIEW** — not "ready to implement." The
investigation found enough already-working convergence
(`legacy_order_parity.py`, `rulebook_order.py`) that a consolidation plan is
realistic, but it also found enough open owner decisions (§6), unresolved
duplicate-ownership pairs, an unrelated security gap, and a fully-manual
schema-deployment mechanism that **no implementation should start** until
Phase 7C.1 (Compatibility and Architecture Approval, per the brief's own
roadmap) formally resolves them. See doc 11 for the proposed target
architecture and doc 12 for the phased backlog that should follow approval.

## 8. Changes made

**Documentation only.** Verified via `git status` at the end of this
investigation: the only new filesystem entries are the fourteen-plus files
under `docs/NEXORA_LEGACY_CONSOLIDATION/`. Every file listed as modified in
the repository's working tree at the *start* of this investigation
(`backend/modules/legacy_order/order_process.py`,
`backend/modules/legacy_order/repository.py`,
`backend/modules/procurement/decision_repository.py`,
`backend/modules/procurement/workspace_repository.py`, and others) was
**already modified before this investigation began** — these are
pre-existing, in-progress work by the owner/another session, read via `git
diff` for context (and cited where relevant, e.g. doc 02 §6, doc 04 §15) but
never staged, committed, reverted, or further edited by this investigation.
No database connection was opened for a write. No migration was executed. No
Cycle/Refresh was triggered. No supplier order was generated or submitted.
Procurement Workspace and Legacy Order were not removed, disabled, or
functionally altered.

## 9. Recommended next phase

**Phase 7C.1 — Compatibility and Architecture Approval**, per the brief's
own roadmap (§14). Prerequisites before it can start:
- Owner resolves the decisions in §6 above (full list: doc 13).
- Owner explicitly triages the cross-tenant authorization gap (doc 09) on
  its own track — it is a live security exposure, not a consolidation
  design question, and fixing it does not require waiting for a
  consolidation decision.
- Owner confirms which of the two warehouse-demand and two
  supplier-stock/non-moving implementations is authoritative, so the
  "requires extension" vs. "duplicate, retire one" classifications in doc 03
  can be finalized rather than left as `DUPLICATE_CANDIDATE`/`UNKNOWN`.

Only after that should Phase 7C.2 (Shared Procurement Data Preparation)
begin, and only with the zero-regression and multi-tenant migration
constraints in doc 17 and doc 16 treated as binding engineering constraints,
not aspirational guidance.
