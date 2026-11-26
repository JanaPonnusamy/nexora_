# Order Sync Redesign — Plan (draft for review, not yet built)

Status: **planning only**. Nothing in this doc has been implemented. Every
item is additive — existing direct-pull sync, existing OrderNMC/OrderSMS/
OrderSuccess tables, and existing Qty Check / Assign / Export flows stay
exactly as they are until a replacement path is proven and explicitly
cut over, store by store.

Scope of this doc (five items, all raised by the owner):

1. "Nexora live" as a manual 3rd Source option in Legacy Order.
2. 180-day retention on OrderNMC/OrderSMS/OrderSuccess trans tables.
3. Local SQLite cache on each store's app for order-relevant data, with
   write-back to central. **Single-order-scoped**: each order push
   deletes the old cache file and plants a fresh one — no accumulation,
   no growing local DB (owner ruling, this turn).
4. **Per-product order history in SQLite is the last 5 rows for that
   product, not the last 5 generated orders.** (Narrower than it first
   sounds — see §3.3.)
5. **Dead-batch problem in `Batches`**: each store caps at ~30k *active*
   batches, but the table keeps accumulating zero-stock ("dead") batch
   rows forever, with no purge. Needs its own fix, independent of the
   other four.
6. **Concurrent-edit visibility**: when a second user opens the same
   product's order card while another user already has it open, the
   second user should see who's editing and decide, rather than both
   silently overwriting each other. Normal case is one store = one
   user, so this is a safety net, not the common path.

---

## 1. Current state (verified in code, this session)

- `sync_engine.TABLE_PLAN` relays 9 tables per store:
  `Products, SaleInformation, ProductTrans, PurchaseTrans,
  ProductSaleInformation, SalesRep, OrderSuppliers, Batches,
  SupplierProductMatch`.
- Two source paths already exist for the same destination tables:
  `get_query_for_table` (direct branch pull) and `platform_query_for_table`
  (NEXORA_PLATFORM `sync.*` relay, used today only for agent-synced stores
  via `LEGACY_AGENT_SYNCED_STORES`, default `{"NMV"}`).
- `Batches` is synced as a **full-replace snapshot**
  (`sync_engine.py:479-490`): the branch only ever sends rows with
  `Stock > 0`; before each MERGE, Nexora first zeroes every row that still
  shows `Stock > 0` in the destination
  (`UPDATE Batches SET Stock = 0 WHERE StoreName = ? AND Stock > 0`), then
  merges in the branch's current nonzero rows. **This zeroes stock but
  never deletes the row.** A batch that sold out a year ago still has a
  permanent `Stock = 0` row in `Batches` today — this is the dead-batch
  accumulation, confirmed directly in code, not inferred.
- Per-product order history already exists and is already capped:
  `repository.qty_check_order_history` (port of VB's
  `RetrieveDataForOrderDetailsAsync`) returns `TOP 25` rows from
  `OrderManagementBackup` for one `(ProductCode, StoreName)`, newest
  first. This is the exact shape the SQLite cache needs — just `TOP 5`
  instead of `TOP 25`, same query, same table.
- No existing concurrent-edit lock or "who's editing this" indicator was
  found anywhere in `legacy_order/router.py` or `repository.py`. Qty
  Check / Assign endpoints write directly with no row-level lock token.
  This is genuinely new.
- Procurement reads `NEXORA_PLATFORM.sync.*` directly (not OrderNMC) —
  confirmed in `workspace_repository.py`. Order Process reads/writes
  OrderNMC/OrderSMS/OrderSuccess exclusively. These are separate
  pipelines today and this plan does not merge them.

---

## 2. Architecture diagram

```mermaid
graph TB
    subgraph Store["Store PC"]
        Branch[("Branch SQL Server<br/>(POS data)")]
        Agent["Store Agent<br/>(already running on all 6 stores)"]
        App["Stock Client / Procurement app"]
        SQLite[("Local SQLite cache<br/>(NEW — current order only,<br/>replaced each push)")]
    end

    subgraph HO["HO backend (.73 / .32 / .80)"]
        Platform[("NEXORA_PLATFORM<br/>sync.* (full history)")]
        Central[("OrderNMC / OrderSMS / OrderSuccess<br/>(trans tables, 180-day window — NEW cap)")]
        Relay["sync_engine relay<br/>(platform_query_for_table)"]
        DirectPull["Direct branch pull<br/>(get_query_for_table)<br/>UNCHANGED, stays live"]
        Purge["180-day purge job (NEW)"]
        Push["Order-relevant push service (NEW)"]
        LockAPI["Edit-lock API (NEW)"]
    end

    Branch -->|existing, unchanged| DirectPull
    DirectPull --> Central
    Agent -->|existing, every ~30min| Platform
    Platform -->|existing relay, NMV only today| Relay
    Relay --> Central
    Platform -.->|NEW: manual "Nexora live" source, any store| Relay

    Central -->|order processed| Push
    Push -->|"wait for pending write-back,<br/>then delete old file, write new"| SQLite
    App -->|read Qty Check / Assign / Export| SQLite
    App -->|write qty/assign/export| SQLite
    SQLite -->|write-back sync| Central

    App -.->|open product card| LockAPI
    LockAPI -.->|"editing: user X"| App

    Purge -->|delete rows older than 180d| Central
    Central -.->|full history preserved| Platform
```

---

## 3. The five items

### 3.1 "Nexora live" source option

Add a third choice to the existing Source dropdown (`frontend LegacyOrderPage.tsx`,
today: Local copy / Remote live). "Nexora live" reuses
`sync_engine.platform_query_for_table` on demand for *any* store, not just
agent-synced ones — same relay query, same MERGE, just triggered manually
per run instead of being gated by `LEGACY_AGENT_SYNCED_STORES`.

No change to `order_process.py`'s branching logic beyond accepting this as
a third `mode` value that forces `query_cs = database.central_connection_string()`
after running the relay once, synchronously, before the order query — same
shape as today's `is_agent_synced` branch, just not permanently flagged on
the store.

Direct-pull and today's Local/Remote options are untouched.

### 3.2 180-day retention

Purge rows older than 180 days from the six trans tables in
OrderNMC/OrderSMS/OrderSuccess (`SaleInformation`, `ProductTrans`,
`PurchaseTrans`, `ProductSaleInformation`, plus `OrderManagement` /
`OrderManagementBackup` if in scope — needs confirming against §3.3 below,
since order history reads from `OrderManagementBackup`). Full history
stays in `NEXORA_PLATFORM.sync.*` untouched.

**Before deleting anything**: grep every screen that reads these tables
with no date filter or a date filter wider than 180 days — Previous Order
Comparison, Purchase History, any audit/report view — and repoint those
specific reads at `NEXORA_PLATFORM.sync.*` first. Ship the purge job in
report-only mode (count rows that *would* be deleted, no delete) for at
least one cycle before it deletes anything.

**Open question carried over**: does `OrderManagementBackup` (the table
§3.3's order history reads) need its own longer retention, since it's the
source for per-product history? If SQLite caches the last 5 rows per
product locally, OrderManagementBackup itself may not need to carry
unlimited history centrally either — but this needs a row-count check
before deciding a number.

### 3.3 Local SQLite cache + write-back

Scope is **order-relevant data only**, not a full backup, and the file
itself is **disposable and single-order-scoped** — it is not a growing
local database. Owner ruling this turn: keep SQLite small and current-order-
only; once an order is processed the old file is dropped and a fresh one
is planted for the new order.

**Lifecycle (replace, never accumulate):**
1. Order Process finishes for the store → push service builds the cache
   payload for that order only (see contents below).
2. The file is named/stamped by the current `OrderId` (or current date —
   one per store, e.g. `order_cache_{store}_{order_id}.sqlite`), written
   to a fixed local path.
3. On write, the push service **deletes/replaces whatever SQLite file is
   already at that path first** — there is never more than one cache file
   per store at a time. No accumulation of old order files, no separate
   cleanup job needed because there's nothing left to clean: each push is
   a full replace, not an append.
4. If a write-back (see below) is still pending when a new order is
   pushed, that pending write-back must flush to central **before** the
   old file is deleted — the push service checks/waits for a clean
   write-back state, not a fixed delay, so an edit in flight is never
   silently dropped by the replace.

**Contents of one cache file (current order only):**
- Current order's lines for the store (Qty Check grid) — not historical
  orders.
- Supplier assignment state per line (status 0/1, assigned supplier) for
  this order.
- **Per-product order history = last 5 `OrderManagementBackup` rows for
  that product** (same query as `qty_check_order_history`, `TOP 5`
  instead of `TOP 25`) — explicitly NOT the last 5 orders generated for
  the store. This is reference data copied in at push time, read-only
  from the app's side, replaced along with everything else on the next
  push.
- Export state (what's been exported, pending export) for this order.

Reads (Qty Check, Assign/Unassign, Export) point at local SQLite first,
with central DB as fallback if SQLite is missing/corrupt (e.g. right
after an app reinstall, before the next order push repopulates it).
Writes (qty edits, assign/unassign, export) land in SQLite immediately,
then sync back to OrderNMC/OrderSMS/OrderSuccess automatically — central
DB remains source of truth (owner-confirmed in prior session). Because
the file is single-order-scoped and gets replaced wholesale on the next
push, write-back is the only thing that needs to survive past that
order's lifetime — the cache file itself is intentionally throwaway.

Open items needing an answer before build:
- Exact column list per cached table (keep it to what Qty Check/Assign/
  Export actually touch, not every OrderManagement column).
- Confirm write-back-before-replace is airtight for the case where an
  operator is still editing when the *next* order's Process run fires —
  does Process wait, warn, or force-flush?
- Write-back frequency: immediate per-write, or batched every N seconds.
- Confirm current Electron build's SQLite driver story (no existing
  SQLite usage found in the backend — this is new infra for the project).

### 3.4 Dead-batch handling (NEW, raised this turn)

Problem, stated precisely from the code: `Batches` is already capped per
store at roughly 30k *active* rows by the branch's own `Stock > 0` filter
on the way out — that part is fine and already working. What's missing is
on the **destination** side: the zero-out step
(`sync_engine.py:486-490`) sets `Stock = 0` on rows no longer present, but
never deletes them, so a store accumulates one permanent dead row per
batch that has ever sold out, growing unbounded for as long as the store
has existed.

Proposed fix (additive, no change to the existing sync mechanism):
a periodic purge — delete `Batches` rows where `Stock = 0` AND the batch
hasn't been touched (no `SyncDateTime` update) in N days (needs a number;
suggest starting from whatever the dead-batch count turns out to be
today, checked per store, since "lakhs" wasn't quantified in this
conversation). Runs as its own job, independent of the 180-day trans
purge in §3.2, since `Batches` isn't a trans table — it's a stock
snapshot. Needs a live row-count check across stores before picking a
cutoff.

### 3.5 Concurrent-edit visibility (NEW, raised this turn)

Today: no lock, no "who's editing" indicator anywhere in
`legacy_order/router.py`/`repository.py`. Two users can open the same
product's card and whichever submits second silently overwrites the
first.

Proposed (additive — a new table + a few new endpoints, no change to
existing write endpoints' core logic):
- New `dbo.order_edit_locks` row per `(store_name, product_code)`,
  stamped with `user_id` + `acquired_at`, expiring after a short TTL
  (e.g. 2 minutes) so an abandoned tab doesn't lock a product forever.
- On opening a product card, the frontend checks/acquires the lock; if
  already held by someone else, show "Being edited by {user}" with a
  choice (wait / take over / view read-only) instead of silently letting
  both edit.
- This is a UX safety net for the rare second-editor case — normal
  single-user-per-store usage is unaffected, no lock ever shown.

---

## 4. Build order (nothing starts until this doc is reviewed)

1. **Dead-batch purge** (§3.4) — smallest, most isolated, no dependency
   on anything else. Quantify dead-row counts per store first.
2. **"Nexora live" source option** (§3.1) — reuses proven relay code,
   additive dropdown entry.
3. **180-day retention, report-only first** (§3.2) — audit all readers of
   the 6 trans tables before any delete runs for real.
4. **Concurrent-edit lock** (§3.5) — new table + endpoints, frontend
   prompt; independent of SQLite work.
5. **Local SQLite cache + write-back** (§3.3) — largest piece, built last,
   piloted on one store before any other store's app points at it.

## 5. What stays untouched throughout

- Direct branch-pull sync for all stores not yet migrated.
- `OrderNMC`/`OrderSMS`/`OrderSuccess` as source of truth.
- Existing Qty Check / Assign / Export endpoints and their current
  single-editor behavior (until §3.5 ships and is turned on).
- `NEXORA_PLATFORM.sync.*` schema and Procurement's existing reads from it.
