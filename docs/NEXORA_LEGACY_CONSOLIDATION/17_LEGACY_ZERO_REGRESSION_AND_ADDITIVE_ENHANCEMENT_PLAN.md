# 17 — Legacy Zero-Regression & Additive Enhancement Plan

Status: PROPOSED DESIGN, informed by VERIFIED findings in docs 02–10, 15–16.
This document does not authorize or perform any implementation. It exists to
satisfy the owner's mandatory addendum: existing Legacy Order and Procurement
Workspace behaviour must not regress, and all enhancement must be additive
and independently-failable.

---

## 1. Existing functionality that must not change

Enumerated from docs 02, 06, 08 with file:line anchors, so a future
implementer has a concrete checklist, not a principle to interpret:

| Behaviour | Anchor | Why it's load-bearing |
|---|---|---|
| LEGACY engine SQL (`order_local.sql`/`order_remote.sql`/`order_warehouse.sql`) | doc 02 §3.3, doc 08 §1 | Default engine for every store not opted into RULEBOOK |
| RULEBOOK engine formula (`quantity_profile_t.evaluate_profile_t`) | doc 02 §3.3, doc 08 §1 | Owner-approved 2026-10-25; live for opted-in stores |
| `OrderManagement`/`OrderManagementBackup`/`OrderHeaderDetails` schema shape | `order_process.COLUMN_MAP`, `order_process.py:119-146` | Every downstream grid/export/WhatsApp/compare reads this exact shape |
| Best-margin auto-assign (last-5-receipt margin + tie-break) | doc 08 §1 "Auto-Assign margin/pick" | Matches owner ruling "OW Bulk Assign best margin" |
| 3-mode skip system + `dbo.OrderProductSkip` carry-forward | doc 02 §3.10 | Durable exclusion state; losing it re-surfaces intentionally-skipped lines |
| Compare-previous-order 4-rule set | doc 02 §3.11 | Governs whether a regenerated order silently carries forward supplier/qty decisions |
| Single-warning rule (`service.py:488-515`) | doc 02 §2.2 | Explicit owner ruling: one warning only |
| Evening/scheduled second order run | doc 02 §3.12 | Per-store schedule, claimed via `LastRunDate` to prevent double-run |
| Export formats and fixed column layout (`.xlsx`/`.xls`/`.csv`/PNG, `_layout_fixed`) | doc 02 §3.13, doc 08 §2 | Downstream consumers (WhatsApp sharing, printed sheets) expect this exact shape |
| `Status`/`Qtycheck` workflow state machine | doc 08 §2 | No Procurement equivalent exists; it IS the Legacy Order workflow |
| Tenant/store scoping (`_scope_tenant`, `WHERE StoreName=?` on every query) | doc 02 §3.14 | The entire multi-tenant isolation guarantee for this module |
| Three-tier permission model (`require_admin`/`require_order_console_access`/`require_admin_or_store_pm`) | doc 02 §3.15 | Current access-control contract |
| `legacy_order_parity.py`'s current default-profile behaviour | doc 04 §5, doc 06 §0 | Already proven to reproduce LEGACY math; must not silently drift from it |

## 2. Additive feature architecture

Every new capability must satisfy ALL of:

1. **Lives in its own module/file(s)**, not inlined into `order_process.py`,
   `repository.py`, `decision_service.py`, or `decision_repository.py`'s
   existing functions. Precedent already exists for this discipline:
   `product_identity.py` and `quantity_profile_t.py` were added as new,
   separate files and *imported into* the existing engines rather than
   edited into them (doc 02 §4).
2. **Reads, never writes, existing core tables** (`OrderManagement`,
   `Products`, `ProductSaleInformation`, `PurchaseTrans`, `ProductTrans`,
   `procurement.procurement_virtual_products`) unless the write is to a
   column added under the expand-and-contract discipline in doc 16.
3. **Fails independently** — wrapped in the same `try/except` +
   graceful-degrade idiom already used 52+ times in this codebase for
   optional-schema handling (doc 16 §7). A new intelligence/prediction call
   that throws, times out, or returns no rows must leave the existing
   quantity/output untouched, not raise past its own boundary.
4. **Starts in recommendation/comparison mode only.** No new calculation may
   write to `OrderManagement.OrderQty` (or its Procurement equivalent) until
   it has been separately approved per Phase 7C.6 of the brief's own
   roadmap. The existing `rulebook_order.compare_engines`/`compare_workbook`
   dry-run harness (doc 02 §3.11) is the direct precedent and should be the
   template: compute, diff, export — never write.
5. **Is config/flag-gated off by default**, following the exact pattern
   already used for `PROCUREMENT_VPL_HISTORY`, `PROCUREMENT_REFRESH_IDEMPOTENCY`,
   and `PROCUREMENT_GENERATION_PROFILE` (doc 04 §3, §13; doc 06 §0). A new
   feature is enabled per-tenant/store only after explicit opt-in, matching
   how RULEBOOK itself was rolled out (`dbo.LegacyOrderEngine.Engine`, doc 02
   §3.11).

## 3. Existing API contracts to preserve

From doc 02 §2.1–2.3 and doc 05: every route currently under
`/api/legacy-order/*` (enumerated in `router.py`, 1305 lines) and every route
Procurement's desktop/web clients call today must keep its current request
shape, response shape, and status-code semantics. New capability is exposed
through **new routes**, not by changing the response shape of an existing
one — e.g. a future "predicted demand" value is a new field on a new
endpoint or an optional, additively-added response field with a documented
default when absent, never a silent repurposing of an existing field like
`OrderQty` or `WantedType`.

## 4. Existing calculations to preserve

The full rule-by-rule comparison in doc 06 is the source of truth. Every row
marked `KEEP_LEGACY` in that document is a hard constraint for this plan:
demand calculation (#1), rounding (#25), supplier-product matching (#21),
pack-size blocking behaviour (#22 — the live default path, not the
rollback engine's divergent behaviour), minimum order quantity floor (#23),
and the shared order-generation duplicate-prevention path (#30).

Rows marked `NEEDS_OWNER_DECISION` (sales-history window #2, supplier
selection #20, purchase-rate ranking #15, durable skip-carry-forward
interaction with Procurement Refresh #29b) must **not** be resolved
silently by an implementer picking "the more sophisticated" option — per
the brief's own instruction and this plan's constraint, they require
explicit owner sign-off before any code encodes a choice.

## 5. Optional feature isolation — concrete mechanism

Reusing the existing `COL_LENGTH`/`OBJECT_ID` idiom (doc 16 §7) and the
existing env-flag pattern (doc 04 §3):

```
new_table_or_column_present = <COL_LENGTH/OBJECT_ID check, cached per-process>
if not new_table_or_column_present or not FEATURE_FLAG_ENABLED:
    # existing behaviour, unchanged, no new code path entered
    return existing_result
# new code path, additive only, wrapped in try/except that falls back
# to existing_result on ANY exception
```

This mirrors `schema_evolution.py`'s `force_nullable=True` discipline (doc
16 §EXISTING (d)) and `legacy_order/database.py`'s `COL_LENGTH('dbo.Stores',
'tenant_id')` precedent (doc 16 §7) — both already-proven patterns in this
codebase, not a new abstraction to design from scratch.

## 6. Regression tests required

Per doc 10's gap analysis, the following must exist **before** any new
calculation is allowed to leave recommendation/comparison mode:

1. A golden-file snapshot of full generated orders per store, covering at
   least one retail store, one warehouse store, and one agent-synced
   (NMV-style) store — extending the existing `rulebook_order.compare_workbook`
   pattern (doc 02 §3.11) rather than inventing a new harness.
2. Recorded-production-input cases added to the existing
   `tests/procurement_formula_compare.py` / `test_legacy_order_parity.py`
   harness (doc 10 §3) — today it is synthetic-cases-only; real historical
   inputs replayed against both old and new calculations would catch drift
   the synthetic cases miss.
3. A parallel dry-run mode in production (extending the existing
   `PROCUREMENT_GENERATION_PROFILE` flag pattern, doc 06 §0) that computes
   and logs the new engine's hypothetical output for every real order run,
   without ever submitting it — giving a real-world accuracy baseline before
   cutover, with zero risk to the live order.
4. Explicit tests for the two confirmed cross-engine conflicts already on
   record (doc 06 Rule #7 stock-source, Rule #22 SaleUnit-blocking) that
   assert the **legacy** behaviour is what ships, as a tripwire against
   either conflict resurfacing silently if `PROCUREMENT_GENERATION_PROFILE`
   is ever changed.
5. Closing the authorization test gap identified in doc 10 §1c for any new
   router this plan introduces — the new code must not repeat the
   zero-tenant-check pattern already found in `optimization_router.py`,
   `intelligence_router.py`, `pipeline_router.py`, `snapshot_router.py`,
   `compare_router.py` (doc 09 §2).

## 7. Release and activation strategy

1. New capability ships **disabled by default**, per-tenant/store opt-in,
   same mechanism as RULEBOOK's rollout.
2. Enabled first in recommendation/comparison mode only (§2.4) for a
   defined pilot store list, with the dry-run-logging harness (§6.3)
   running in the background to accumulate an accuracy baseline.
3. Promotion from comparison mode to live order generation requires: (a)
   the regression tests in §6 passing, (b) a quantified comparison report
   (quantity differences, supplier allocation differences, purchase value
   differences — per the brief's own Phase 7C.6 criteria) reviewed by the
   owner, and (c) explicit owner authorization, store by store — not a
   global flip.
4. Rollback is symmetric: disabling the per-store flag reverts instantly to
   the existing engine, because the existing engine's code path is never
   modified or removed by this plan (§1, §2.2) — this is the same rollback
   guarantee `PROCUREMENT_GENERATION_PROFILE=nexora` already provides today
   as a rollback path away from `legacy_local`.

## 8. Cross-reference to the multi-tenant migration constraint

Any new table/column this plan requires must follow doc 16's proposed
expand-and-contract discipline: additive, nullable, verified per-tenant
database before the owning feature is enabled on that tenant. §5 of this
document is the application-code half of that discipline; doc 16 is the
schema-deployment half. Neither is sufficient alone — a feature flag that
checks `COL_LENGTH` correctly still needs the column to have actually been
deployed to that tenant's database first, which doc 16 establishes has no
automated mechanism today.
