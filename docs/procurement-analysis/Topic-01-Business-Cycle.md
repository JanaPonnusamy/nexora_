---
module: Procurement
version: 1.0
status: Ratified
owner: Solution Architecture
updated: 2026-06-27
---

# Procurement V1 — Business Analysis

## Topic 01: Business Cycle

> **STATUS: RATIFIED (2026-06-27).** The conflicts raised here have been resolved by business
> decision and applied to the FDD (`Procurement_Business_Architecture_Specification.md`, §5–6).
> See **§8 — Ratified Decisions & Resolutions** at the foot of this document. The decision log
> is maintained in `Working-State.md`; provenance in `Evidence.md`.

> **Method:** Business knowledge extraction from legacy evidence. Search-first, read only
> matching regions. Code is evidence only; the FDD is the output. No code generated, no
> business redesign.
>
> **Evidence sources read (Topic 01 only):**
> - Legacy Python: `procurements/services/cycle_service.py`, `refresh_service.py`,
>   `repository/cycle_repo.py`, `refresh_repo.py`, `schemas/cycle_schema.py`,
>   `refresh_schema.py`, `constants/cycle_status.py` (empty).
> - OrderNMC stored procedures (business reference): `nx_sp_CreateOrderCycle`,
>   `nx_sp_CloseOrderCycle`, `nx_sp_GetActiveOrderCycle`, `nx_sp_RefreshOrderCycle`,
>   `nx_sp_GetRefreshes`.
> - Legacy VB.NET (`OrderManagement`): searched for `cycle` / `refresh_id` / `order_cycle`
>   → **no matches**. The Business Cycle concept does **not** exist in the VB.NET system.

---

### 1. Business Summary

A **Business Cycle** ("Order Cycle" in the legacy data model) is a per-store procurement
planning period. It is opened for a store, worked through one or more **Refreshes**, and
then closed. Inside a cycle, each **Refresh** regenerates the procurement working set (the
"virtual product list") using a configurable **Min Days / Max Days** window, and is numbered
sequentially. The cycle carries a **rolling_days** window (default **90**) that scopes the
sales history used by the decision engine.

The concept is **new to the NEXORA Python procurement rewrite**. The legacy VB.NET
`OrderManagement` desktop application has no cycle/refresh notion — procurement there was
not organised into bounded, re-runnable planning periods. This confirms the Business Cycle
is a deliberate modernization, not a port of existing behaviour.

---

### 2. Current Implementation

**Data model (inferred from the procedures):**

| Table | Role |
|-------|------|
| `Stores` | Store master; `StoreName` → `StoreCode` (used as `store_id`). |
| `order_cycles` | The Business Cycle. Key columns: `id`, `store_id`, `StoreName`, `cycle_no`, `cycle_status`, `rolling_days`, `live_refresh_count`, `last_refresh_id`, `started_at`, `closed_at`, `cycle_closed_at`, `offline_mode`, `remarks`, audit columns. |
| `order_cycle_refreshes` | A Refresh within a cycle. Key columns: `id`, `cycle_id`, `refresh_no`, `refresh_status`, `min_days`, `max_days`, `generated_product_count`, `generation_started_at`, `generation_completed_at`, `remarks`, `StoreName`, audit columns. |
| `order_virtual_items` | The generated working set ("virtual products") per refresh (built by `nx_sp_BuildVirtualProductList` — Decision Engine, see Topic 03). |
| `order_items` | Procurement line items carrying `remaining_qty` (pending). |
| `order_item_assignments` | Supplier assignments with `assignment_status`. |

**Operations (SP contract):**

- **Create** — `nx_sp_CreateOrderCycle(StoreName, rolling_days, remarks, created_by)`:
  validates store + `rolling_days > 0`; **auto-closes** any existing `ACTIVE` cycle for the
  store; computes `cycle_no = MAX(cycle_no)+1` per store; inserts the new cycle as `ACTIVE`
  with `live_refresh_count = 0`, `last_refresh_id = NULL`, `offline_mode = 0`.
- **Get Active** — `nx_sp_GetActiveOrderCycle(StoreName)`: returns the single `TOP 1`
  `ACTIVE` cycle for the store (newest by `id`). Implies **one active cycle per store**.
- **Refresh** — `nx_sp_RefreshOrderCycle(cycle_id, min_days, max_days, remarks, created_by)`:
  validates `min_days > 0` and `max_days >= min_days`; requires the cycle to be `ACTIVE`;
  computes `refresh_no = MAX(refresh_no)+1` per cycle; inserts the refresh as `PROCESSING`;
  updates the cycle (`live_refresh_count`, `last_refresh_id`); calls
  `nx_sp_BuildVirtualProductList`; then marks the refresh `ACTIVE` and stamps
  `generated_product_count`. Runs inside a transaction.
- **List Refreshes** — `nx_sp_GetRefreshes(cycle_id)`: all refreshes, newest `refresh_no` first.
- **Close** — `nx_sp_CloseOrderCycle(CycleID, remarks, updated_by)`: requires the cycle to be
  `active`; **blocks** closure if any `order_items.remaining_qty > 0` (pending) **or** any
  `order_item_assignments.assignment_status IN ('draft','exported','partial_received')`;
  otherwise sets `cycle_status = 'completed'`, stamps `cycle_closed_at`.

**Service/repository layers** are thin pass-throughs; **all business logic lives in the
stored procedures.** `constants/cycle_status.py` is empty — status values are string
literals inside SQL, not centrally defined.

---

### 3. Business Rules (extracted)

| # | Rule | Evidence |
|---|------|----------|
| BC-01 | A Business Cycle belongs to exactly one store, resolved by `StoreName` (case-insensitive). | Create / GetActive |
| BC-02 | **At most one ACTIVE cycle per store** at any time. | GetActive `TOP 1 ACTIVE`; Create auto-closes prior active |
| BC-03 | Creating a cycle **automatically closes** the store's current active cycle. | Create: `UPDATE … SET cycle_status='CLOSED' WHERE store_id=… AND cycle_status='ACTIVE'` |
| BC-04 | Cycles are numbered sequentially **per store**: `cycle_no = MAX+1`. | Create |
| BC-05 | A cycle carries a **rolling history window** `rolling_days` (default **90**) set at creation; it scopes sales history for the engine. | Create input; schema default 90 |
| BC-06 | `rolling_days` must be `> 0`; `StoreName` is mandatory. | Create validation |
| BC-07 | A new cycle starts `ACTIVE` with `live_refresh_count = 0`, no refreshes yet. The **first Refresh is a separate, explicit action**. | Create vs Refresh |
| BC-08 | A Refresh can only be generated on an **ACTIVE** cycle. | Refresh: "Invalid or closed cycle" |
| BC-09 | Refreshes are numbered sequentially **per cycle**: `refresh_no = MAX+1`. | Refresh |
| BC-10 | Each Refresh chooses its own **Min Days / Max Days** window; `min_days > 0` and `max_days >= min_days`. | Refresh validation |
| BC-11 | A Refresh transitions `PROCESSING → ACTIVE`; on completion it records `generated_product_count` (count of `order_virtual_items`). | Refresh |
| BC-12 | The cycle tracks `live_refresh_count` (refreshes in `PROCESSING`/`ACTIVE`/`PARTIAL`) and `last_refresh_id`. | Refresh |
| BC-13 | Closing a cycle is **blocked while pending exists**: any `order_items.remaining_qty > 0`. | Close validation |
| BC-14 | Closing a cycle is **blocked while open assignments exist**: status in `draft`/`exported`/`partial_received`. | Close validation |
| BC-15 | A manually closed cycle becomes `completed` with `cycle_closed_at` stamped. | Close |
| BC-16 | Refresh generation is **transactional** (refresh + virtual-list build commit together or roll back). | Refresh `BEGIN TRAN` |

---

### 4. Missing Rules (in the Business Architecture Specification but absent in legacy)

- **M-01 — "Closing" transitional state.** The spec defines `Created → Active → Closing →
  Closed`. Legacy has no `Created` (cycle is `ACTIVE` immediately) and no `Closing` interim
  state for finalisation.
- **M-02 — Single "Current" Refresh with supersession.** Spec: one Current refresh; a new
  refresh **supersedes** the previous. Legacy keeps **multiple refreshes live**
  (`live_refresh_count` counts several `ACTIVE`/`PARTIAL`). No `Superseded` status exists.
- **M-03 — Sync pre-condition gate.** Spec requires confirming the Store Agent has synced
  required data before a cycle/refresh runs. Legacy performs **no sync-readiness check**.
- **M-04 — Pending carry-forward across cycles.** Spec: unreceived pending **carries forward**
  into the next cycle. Legacy instead **forbids closing** while pending exists (BC-13/14).
- **M-05 — Compare with previous Refresh.** Spec mandates a per-product delta view. No
  comparison logic appears in the cycle/refresh procedures (may live elsewhere — to confirm
  in Topic 02/03).
- **M-06 — Explicit read-only enforcement after closure.** Spec: closed cycles are immutable.
  Legacy relies on status filtering (only `ACTIVE` is loaded) rather than enforced immutability.

### 4b. Extra Rules (in legacy but not in the Specification)

- **X-01 — Automatic closure of the prior active cycle on creation** (BC-03). The spec says
  closure is *explicit, never automatic*.
- **X-02 — `rolling_days` is a first-class cycle attribute** chosen at creation (default 90),
  binding the history window to the cycle. The spec treats the 90-day window as a decision-
  engine rule, not a cycle parameter.
- **X-03 — Min Days / Max Days are chosen per-Refresh**, not as static engine config. Each
  refresh re-parameterizes the engine.
- **X-04 — `offline_mode` flag** on the cycle (default 0) — an offline capability not in the spec.
- **X-05 — `PARTIAL` refresh status** — a refresh state the spec does not describe.

---

### 5. Conflicts

| # | Conflict | Detail | Risk |
|---|----------|--------|------|
| C-01 | **Two terminal cycle statuses with different meaning.** | Auto-close on creation sets `'CLOSED'`; manual close sets `'completed'`. There is no single "closed" state. | Reporting/history ambiguity; "what does CLOSED vs completed mean?" |
| C-02 | **Status vocabulary inconsistency / case.** | Create & GetActive use `'ACTIVE'` (upper); Close checks `'active'` (lower) and writes `'completed'` (lower). Works only because SQL Server collation is case-insensitive. | Fragile; breaks under case-sensitive collation; obscures intent. |
| C-03 | **Automatic vs explicit closure.** | Legacy auto-closes the previous active cycle (X-01); spec requires explicit closure only. | A second "Create" silently terminates an in-flight cycle with open work, bypassing the close-time pending/assignment guards (BC-13/14). **Potential loss of governance.** |
| C-04 | **Pending at closure: block vs carry-forward.** | Legacy hard-blocks closure while pending/open assignments exist; spec carries pending forward to the next cycle. | Opposite policies — must be reconciled before build. |
| C-05 | **Refresh supersession vs multiple-live.** | Legacy permits multiple live refreshes; spec expects one Current + Superseded history. | Workspace/"current view" semantics differ fundamentally (impacts Topic 02). |
| C-06 | **Auto-close bypasses close guards.** | The create-time auto-close (BC-03) does **not** run the pending/assignment validations that manual close enforces (BC-13/14). | An active cycle with open pending can be terminated as `'CLOSED'` with no check. |

---

### 6. Recommended Design (documentation-level, no code)

1. **Adopt one canonical status vocabulary** for cycles — recommend `ACTIVE` and a single
   terminal `CLOSED`, with a separate reason/qualifier (e.g. `close_reason ∈ {COMPLETED,
   SUPERSEDED}`) instead of two different status strings (resolves C-01, C-02).
2. **Make closure explicit and guarded in all paths.** If auto-close on creation is retained
   for convenience, route it through the **same** pending/assignment validation as manual
   close, or require the prior cycle be closed first (resolves C-03, C-06).
3. **Decide the pending-at-closure policy once** (C-04). The spec's **carry-forward** is the
   stated business intent; recommend introducing a carry-forward step at closing rather than
   a hard block, with the close guards downgraded to a confirmation. Align with Topic 05
   (Pending).
4. **Refresh model:** confirm whether the business truly wants **multiple live refreshes** or
   a **single Current refresh** (C-05, M-02). Recommend formalising a `Current` refresh
   (`last_refresh_id`) and marking prior ones `SUPERSEDED` for history, preserving them
   read-only — this matches the spec and the existing `last_refresh_id` pointer.
5. **Introduce the `Closing` state** (M-01) only if a finalisation step (carry-forward,
   reconciliation) is adopted; otherwise document its omission deliberately.
6. **Record the sync-readiness gate** (M-03) as a pre-condition at cycle creation / first
   refresh, even if initially a manual acknowledgement.
7. **Centralise status constants** (the empty `cycle_status.py`) so vocabulary is defined once.
8. Treat `rolling_days` (cycle) and `min_days`/`max_days` (refresh) as the **canonical
   parameter split** in the FDD — this is a genuine, valuable legacy insight worth preserving.

---

### 7. Questions (for business owner sign-off)

1. **Auto-close on create:** Is silently auto-closing the prior active cycle intended
   business behaviour, or should creating a second cycle be **blocked** while one is active
   (forcing an explicit, guarded close first)?
2. **Pending at closure:** When a cycle is closed with unreceived pending, should it
   **carry forward** to the next cycle (spec) or remain **blocked from closing** (legacy)?
3. **Multiple live refreshes vs single Current:** Should several refreshes stay `ACTIVE`
   simultaneously, or should a new refresh **supersede** the previous one? This drives the
   entire Workspace "current view" (Topic 02).
4. **Terminal status meaning:** Do `CLOSED` (auto) and `completed` (manual) represent two
   distinct business outcomes, or should they be unified?
5. **`rolling_days` vs Min/Max Days:** Confirm the intended split — `rolling_days` (history
   window, per cycle, default 90) vs `min_days`/`max_days` (cover targets, per refresh).
6. **`offline_mode` and `PARTIAL` refresh status:** What business scenarios do these
   represent? (Not described in the specification.)
7. **Sync readiness:** Should cycle creation / first refresh be **gated** on confirmed Store
   Agent sync, and if so, automatically or by manual acknowledgement?

---

---

### 8. Ratified Decisions & Resolutions (2026-06-27)

The Purchase Manager / business owner ratified the target design. Resolutions:

| Decision | Resolves | Target design (now in FDD) |
|----------|----------|----------------------------|
| **D1 — Explicit close only; never auto-close.** | C-03, C-06, X-01, Q1 | Creating a cycle **does not** auto-close the prior cycle. If an `ACTIVE` cycle exists, creation is **blocked** until it is explicitly closed by the Purchase Manager. |
| **D2 — Pending does not block closure; carries forward.** | C-04, M-04, BC-13, BC-14, Q2 | Closure is never blocked by pending. Unreceived pending and open assignments **carry forward** into the next cycle until finalized. |
| **D3 — One `CURRENT` Refresh; older `SUPERSEDED` (immutable).** | C-05, M-02, X-05, Q3 | Exactly one `CURRENT` refresh per cycle; generating a new one marks the prior `CURRENT` as `SUPERSEDED` and immutable. Multiple-live refreshes are dropped. |
| **D4 — Preserve Rolling Days (cycle) vs Min/Max Days (refresh).** | X-02, X-03, Q5 | Documented as the canonical parameter split (FDD §5.7). Rolling Days per cycle (default 90); Min/Max Days per refresh. |
| **D5 — Standardize status values; drop legacy casing/names.** | C-01, C-02 | Cycle: `ACTIVE` → `CLOSED`. Refresh: `GENERATING` → `CURRENT` → `SUPERSEDED`. Legacy `active`/`completed`/`PROCESSING`/`PARTIAL` not preserved. Status constants to be centralized. |

**Open (deferred, not blocking Topic 02):** Q4 (terminal-status meaning) is absorbed by D5
(single `CLOSED`). Q6 (`offline_mode`, legacy `PARTIAL`) and Q7 (sync-readiness gate) remain
open clarifications carried in `Working-State.md` — they do not block subsequent topics.

---

*Next topic in order: **Topic 02 — Procurement Workspace** (keywords: virtual, workspace,
review, assign, grid, order_items). The engine entry point `nx_sp_BuildVirtualProductList`
and `order_virtual_items` identified here are the bridge into Topics 02 and 03.*
