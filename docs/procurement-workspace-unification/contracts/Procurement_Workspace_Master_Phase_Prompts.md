# Procurement Workspace Unification --- Master Phase Prompts

**Project:** E:`\Nexora  `{=tex} **Related legacy application:**
D:`\VBDOTNET`{=tex}`\OrderManagement  `{=tex} **Purpose:** Implement the
unified Procurement/Order Workspace safely, in gated phases, while
preserving existing production behavior until explicit cutover approval.

## Master instructions for Codex / Claude

You are working on the Nexora procurement workspace unification. Follow
this document as the implementation contract. Work only on the phase
explicitly authorized by the user. Do not silently proceed into later
phases.

### Non-negotiable safety rules

1.  Read `docs/procurement-workspace-unification/` audit files and the
    relevant existing source files before changing anything. Do not
    rescan the entire repository; follow the audit dependency map.
2.  The live SQL Server was **not** opened during the audit. Never
    assume live schema, constraints, indexes, triggers, row counts, or
    production data semantics. Inspect available schema/migrations
    first; if live DB access is required, stop and request explicit
    approval.
3.  Existing legacy screens and current procurement screens must remain
    usable. Build the new workspace as a separate route/component set
    behind a feature flag. Do not delete, replace, or repoint the old
    screen until the user approves cutover.
4.  No production order generation, export, assignment, or data mutation
    during Phase 0. Use test fixtures only.
5.  Never change the live quantity formula merely to make two engines
    agree. Run identical test cases against the agreed target formula,
    the legacy SQL behavior, and Nexora `decision_rules.evaluate`;
    report all three results and explain differences.
6.  No speculative business rules, fake data, silent fallback, hidden
    auto-assignment, or automatic portal submission. Unknown behavior
    must be recorded as UNKNOWN and surfaced for approval.
7.  Use small, reviewable changes. Run focused tests after each phase.
    Report changed files, migration impact, tests, acceptance results,
    and rollback path. Stop at the phase gate.
8.  Do not create extra tables "for convenience." Use the exact data
    objects requested here plus existing approved Nexora objects. Before
    adding any column/table, document why existing fields cannot support
    the requirement.
9.  All database migrations must be additive, idempotent where
    practical, transaction-safe, reversible where feasible, and safe for
    existing rows. Never drop or truncate existing production data as
    part of a migration.
10. Do not store credentials, supplier portal secrets, or sensitive
    tokens in source control or logs.

## Confirmed business decisions

### Quantity and rare movers

-   Default sales window: 90 calendar days.
-   Minimum cover: 13 days. Maximum cover: 18 days.
-   Last-valid-sale recency gate: 15 days, separate from cover/quantity
    calculation.
-   Physical stock for the agreed target profile: `Products.TotalStock`.
    Do not silently substitute `ProductTrans.StockInHand` or batch
    totals.
-   Exclude `DontConsiderInOrder` products/sales from all applicable
    order-demand calculations.
-   Target gross demand:
    `MAX(avgDailySales * maxDays, maxBillQty, maxDayQty, avgBillQty)`.
-   Net demand:
    `grossDemand - Products.TotalStock - confirmedSupplierPendingQty`.
-   Pack suggestion: `CEILING(netDemand / SaleUnit)` when net demand is
    positive and `SaleUnit` is valid.
-   If `SaleUnit` is null, zero, or invalid, block automatic quantity
    and show a data-error/manual-review reason. Never fall back to
    loose-unit ordering.
-   Keep eligibility separate from sizing. A product failing recency
    must not enter the normal auto-order list; it may appear in a
    separate review category with the reason.
-   Rare-moving products: show a **suggested quantity of 1 pack/unit for
    review**, with a strong **RARE MOVING --- MANUAL REVIEW REQUIRED**
    warning. Do not automatically assign, export, or place an order. PM
    must explicitly review and confirm. Validate final quantity against
    the actual `SaleUnit`/pack rules before export; do not silently
    treat one loose unit as one pack.
-   Do not auto-order excluded/zero/negative suggestions. Preserve a
    reason/result for audit.
-   Modified/cancelled bill semantics and `transactionvalidity` values
    are not fully verified. Do not invent the mapping; keep it
    configurable/blocked until verified.

### Workspace and workflow

-   Host the new screen inside the existing Supplier Stock Client
    Electron app as a new route/screen.
-   Keep old screens untouched and usable until user-approved cutover.
-   Modes/loaders remain distinct:
    1.  **Qty Check** --- review product suggestions; no supplier
        assignment just from loading.
    2.  **Auto Purchase Update** --- use existing supplier purchase
        history (`LoadDataForSupplier` behavior).
    3.  **Supplier Stock Availability** --- use supplier stock
        availability (`LoadDataForSupplierStock` behavior; stock \> 0).
-   Reuse the existing Suggestion Box between the grid and detail panel
    for supplier suggestions, cross-branch matches, and non-moving
    warnings.
-   Right detail panel order: Product Details, Purchase, Sales, Sales
    Trend Chart. History can open in a drawer.
-   Target compact workspace at 1366×768. Filter row must be compact,
    not twice the height of a normal grid row.
-   Admin store switch must immediately clear the old grid and all
    detail-panel values. Discard stale responses. When new data loads,
    focus/select the first row and display that row's details.
-   If the user closes/switches screen during loading, do not show stale
    data when returning.
-   Row-level auto-save remains; no separate Save button. On save
    failure, keep the edit and focus on the same row.
-   Default essential columns: product, order qty, stock, pack, status.
    Essential columns cannot be hidden. Optional columns/panels may be
    hidden/resized; persist layout by user (and store only if current
    architecture supports it), and provide Reset to Default.
-   Filters/counts where applicable: All, Reviewed, Not Reviewed,
    Assigned, Unassigned, Pending, Not Supplied. Counts must match the
    visible data and active store/order.
-   Mark reviewed only after a meaningful PM action (quantity edit,
    supplier assignment, Pending/Not Supplied decision), not merely
    selecting or viewing a row.
-   Delete key in Auto Purchase Update and Supplier Stock modes: only
    when filter is not All; hide the row from the current filtered view
    only, do not delete order/database data or mark it as skipped. Move
    focus to the next row.
-   Keyboard behavior must be implemented as a tested mode-specific
    matrix, based on the existing Stock Client semantics:
    -   Enter saves; in supplier-selection context, Enter may assign the
        highlighted supplier as the existing client does.
    -   Up/Down saves edited quantity before moving; never move away
        before save success.
    -   Esc sets quantity to 0 and saves, then advances; this is not a
        skip/delete.
    -   Right Arrow opens supplier suggestions only if that is the
        approved new-workspace contract; do not assume legacy clients
        already use it.
    -   Preserve edit and row focus on save failure.
-   Do not reload the whole grid after each edit or while a portal job
    runs.

### Supplier assignment, export, and receipt rules

-   Qty Check uses manual supplier assignment. Auto Purchase Update uses
    purchase history. Supplier Stock uses supplier stock availability.
-   Manual assignment wins. Auto Assign Remaining only fills unassigned
    products and never overwrites manual assignments.
-   Assignment must not silently recalculate final quantity.
-   One supplier per product line. Reject a second supplier assignment
    with a clear conflict response.
-   If no supplier meets margin/eligibility, use the approved fallback
    only with a visible warning; manual below-margin assignment requires
    explicit confirmation and audit.
-   Historical effective cost must be based on actual received purchase
    records within 90 days, using latest six records if more than six
    exist, otherwise all records. Account for discount/free units per
    record. Never apply today's offer to historical purchases. If no
    recent price exists, show **Stale Price --- Manual Review** and
    exclude from auto-ranking until verified. Tax basis requires source
    verification.
-   Cross-branch matching must use existing mapping/normalization.
    Low-confidence, fuzzy, or pack-mismatched results require manual
    inspection; never auto-assign or auto-transfer. For credible
    products with no branch sales for \>180 days, show a persistent
    warning in the existing Suggestion Box; PM chooses source
    branch/billing route.
-   Export only currently assigned products for the selected supplier.
    Mark exported only after confirmed successful export. Preserve
    partial success and retry failed/unconfirmed lines without
    duplicates.
-   Distinguish **Export Copy** (new format/file, no new supplier order)
    from **Place on Portal** (creates supplier order).
-   Export settings precedence: Store + Supplier → Store default →
    System default. If existing schema lacks a tier, inspect before
    proposing the smallest additive schema change. Validate required
    columns and persist the settings version/format used by each export.
-   After confirmed portal export, original supplier, export batch, and
    quantity history must remain immutable. Any release/reassignment
    must be an explicit audited action; local edits must not pretend to
    modify a confirmed portal order.
-   Portal work must run as a background job, separate from UI
    rendering. Keep Selenium fallback until a Playwright adapter is
    proven. Never import the old OrderBot main script into the Nexora
    server process. Do not report success merely because a button was
    clicked; require a confirmed order reference/status. Unknown
    availability blocks portal submission; Excel/WhatsApp export may
    allow an explicit override. Portal stock must not change
    suggested/final quantity.
-   Price increase above the configured threshold requires approval and
    records price, threshold, approver, and time.
-   Receipt/pending: confirmed ordered qty minus actual received qty,
    less valid cancellations/reversals. Drafts, failed exports, and
    unexported assignments do not count as confirmed pending. GRN
    reference alone does not prove full receipt. Partial receipt retains
    remaining balance. Cancelled supplier orders remove their
    outstanding balance but preserve history. Not Supplied releases
    outstanding qty from pending while preserving original order history
    and requires an explicit decision/audit.
-   Closing a review session may be allowed with supplier deliveries
    outstanding, after showing unfinished assigned work, unexported
    assignments, and outstanding supplier orders. Ignored unassigned VPL
    rows do not block closure and are not automatically carried forward
    as pending.

## Database requirements --- VPL and order history

### Required intent

-   Keep the existing `OrderHeaderDetails` table as the order/header
    identity source. Inspect its actual schema and keys before changing
    it.
-   Add a **dedicated VPL working table** modeled on the legacy
    `OrderManagement` line-level behavior, but do not overwrite or
    repurpose the existing legacy `OrderManagement` table. Use an
    unambiguous name in the target database, following the current
    database/schema naming conventions (for example, a VPL-specific
    working-lines table).
-   Add a **VPL backup/history table** to retain the previous order's
    line snapshot when a new VPL/order is generated. The backup must
    preserve the original order/header ID and store identity so each
    history row can be traced to its order.
-   The UI should display only the **latest 10 distinct order/header
    histories** for the selected store. This is a display/query limit,
    not a reason to delete older backup records. Retain history in the
    database unless a separately approved retention policy says
    otherwise.
-   Before adding columns to `OrderHeaderDetails`, check whether
    existing columns already provide the required data. Add only missing
    fields required for safe lifecycle tracking. Do not add duplicate
    fields with different names for the same meaning.
-   Keep VPL suggested quantity, PM final quantity, assigned quantity,
    received quantity, remaining/pending quantity, review state,
    assignment/export state, and reason fields distinct. Do not overload
    `Remarks` to represent multiple states.
-   Preserve the current Nexora cycle/refresh/order-item lifecycle
    unless the repository audit proves an existing object already
    fulfills a requirement. Do not create a parallel duplicate
    procurement lifecycle.
-   Do not assume SQL Server schema or primary keys. Confirm whether
    target DB is the Nexora platform DB or legacy branch DB from
    existing configuration before writing migration scripts. Do not run
    a migration against production without explicit approval.
-   Use a transaction for snapshot backup + new VPL generation. If
    backup or generation fails, roll back the whole transaction and
    preserve the previous good order. Never delete current lines first
    and hope reinsertion succeeds.
-   Enforce duplicate protection with a verified key equivalent to
    `(store, order/refresh header, product code)`. Validate product
    identity is store-scoped; do not assume ProductCode equality means
    cross-store identity.
-   Use foreign keys and indexes only after inspecting actual key types
    and existing conventions. Migration must be safe to rerun and
    include verification queries plus a rollback plan.
-   Add tests for: first VPL, next VPL with backup, interrupted
    generation rollback, no duplicate product lines, two stores with
    same ProductCode, latest 10 order histories displayed while older
    histories remain queryable, and old
    OrderHeaderDetails/OrderManagement data unchanged.
-   Do not create or migrate tables until the relevant phase gate is
    explicitly approved.

## Phase prompts

### Phase 0 --- Golden formula fixture (test-only; do this first)

**Prompt to agent:**

Inspect only the audit files and relevant code paths. Build a test-only
fixture runner that applies identical synthetic inputs to: 1. the agreed
target formula above, 2. legacy `FetchSourceData` / `order_local.sql`
behavior, represented faithfully and tested against the SQL expression,
3. Nexora `backend/modules/procurement/decision_rules.py` `evaluate`.

Include the audited examples where the engines produce different pack
counts, plus cases for SaleUnit 0/null, zero sales, recency failure,
stock, pending quantity, rare movers, same-day bills, bill aggregation,
and `DontConsiderInOrder`. Record input values and all three
outputs/reasons in a deterministic expected table. Do not change API,
migrations, live DB, UI, or production quantity behavior. If exact SQL
execution requires a DB unavailable in tests, clearly label a faithful
transcription and test its clauses against `order_local.sql`; do not
claim it executed the live SQL. **Acceptance gate:** focused tests pass;
differences are documented; unresolved validity/bill-time assumptions
remain explicit. Stop and report.

### Phase 1 --- Freeze generation profile and source contracts

**Prompt to agent:**

After Phase 0 is accepted, document the approved generation profile and
parameter snapshot. Keep the target formula in a dedicated, tested
function near `decision_rules.py`; do not silently replace the existing
engine. Keep current default behavior unchanged until an explicit
store-level cutover approval. Inspect source data contracts for all
three modes and identify required read models/endpoints without
implementing UI. Confirm stock source, pending source, transaction
validity, date semantics, and role mapping status. Unknowns must remain
blocked/profile-controlled, not guessed. **Acceptance gate:** rulebook,
test expectations, source field map, and profile selection behavior
reviewed. No live order changes.

### Phase 2 --- Database schema/migration plan for VPL and backup history

**Prompt to agent:**

Inspect current Nexora migrations/repositories and the target DB
configuration. Determine whether `OrderHeaderDetails` belongs to the
intended target DB and how it keys stores/orders. Preserve
`OrderHeaderDetails`. Design the smallest schema change that provides a
dedicated VPL working-lines table modeled on `OrderManagement` and a VPL
backup/history table. Reuse current cycle/refresh/order-item tables
where they already fulfill the same role; avoid duplicate lifecycle
tables. Add only necessary columns to `OrderHeaderDetails` after proving
they are missing. Define keys, foreign keys, indexes, order snapshot
version, creation timestamp, store identity, product identity,
suggested/final/assigned/received/remaining quantities,
review/assignment/export statuses, and reason/audit fields as
appropriate to the existing schema. Do not overload `Remarks`. Ensure
the latest-10 limit is applied in the history query/UI, not by deleting
older records. Write migration + rollback + verification queries and
tests, but do not execute on production. Stop for schema review
approval. **Acceptance gate:** schema diff reviewed; no destructive
operations; migration is rerunnable and transaction-safe; existing data
preservation tests pass.

### Phase 3 --- Read-only mode data contracts

**Prompt to agent:**

Implement read-only backend data contracts for the three existing modes,
reusing the established loaders and source semantics rather than copying
SQL into the renderer. Return store/order identity, products, stock,
pack/SaleUnit, suggested/final quantity, eligibility/reason, supplier
candidates, and detail-panel inputs needed by the new workspace. On
store/mode switch, clear old data immediately and discard stale
responses. Do not write order quantities or assignments in this phase.
**Acceptance gate:** API tests prove store isolation, correct
mode-specific product sets, no stale-store rows, and stable response
shape. Existing endpoints remain intact.

### Phase 4 --- Separate compact workspace shell (read-only)

**Prompt to agent:**

Add a new route and new components inside the existing Electron Stock
Client host. Use a compact single-row filter bar, grid, existing
Suggestion Box concept, and right detail panel. Keep old screens/routes
unchanged and reachable. Default grid columns: S.No, Product, Unit,
Pack, Stock, Suggested Qty, Final Qty, Status, Offer (adapt only to
available verified data). At 1366×768, prevent filter row from becoming
twice normal row height. On store change clear grid and all detail
values immediately. On load select/focus first row and show its details.
Add loading/empty/error states. Feature flag defaults OFF. **Acceptance
gate:** screenshot/layout tests at 1366×768 and 1280×640; store-switch
and stale-response tests pass; old screen smoke test passes. No write
APIs called.

### Phase 5 --- Detail panel, filters, and layout preferences

**Prompt to agent:**

Wire Product Details, Purchase, Sales, and Sales Trend Chart in that
order. History opens in a drawer. Add applicable filters and accurate
counts for All, Reviewed, Not Reviewed, Assigned, Unassigned, Pending,
and Not Supplied. Keep selection/viewing from marking a product
reviewed. Allow optional columns/panels to be resized/hidden, but
protect essential columns and provide Reset to Default. Persist
preferences by user using existing preference storage if available; do
not create a new table without approval. **Acceptance gate:**
filters/counts are tested; layout remains compact; preference
persistence is scoped correctly.

### Phase 6 --- Quantity autosave and keyboard contract

**Prompt to agent:**

Implement quantity editing with positive integer validation and the
approved pack rules. Enter saves; Up/Down must save successfully before
moving; Esc sets 0 and saves then advances; supplier-selection Enter
assigns only in the appropriate mode/context. Right Arrow behavior must
follow the explicitly implemented workspace contract and must not
conflict with the existing client. Save failure must preserve the edit
and focus. Do not reload the grid on every save. Mark Reviewed only
after a meaningful PM action. No Delete key may delete database/order
data; filtered Delete only hides the row in the specified modes and only
outside the All filter. **Acceptance gate:** automated keyboard matrix
for every mode; save failure retains row/edit; reload confirms persisted
quantity; negative, noninteger, too-large, and invalid pack values
rejected.

### Phase 7 --- Supplier assignment and Suggestion Box

**Prompt to agent:**

Implement manual assignment, supplier recommendations, cross-branch
candidates, non-moving warnings, and Auto Assign Remaining under the
rules above. Never overwrite manual assignments or change final quantity
during assignment. Enforce one supplier per product. Low-confidence or
pack-mismatched cross-branch matches require explicit PM confirmation.
Show stale price and low-margin warnings. Preserve an audit trail for
overrides and assignment changes. **Acceptance gate:** tests for one
supplier per product, manual assignment precedence, Auto Assign
Remaining, stale prices, low margin, cross-branch confidence, and
warning persistence.

### Phase 8 --- Export settings and reliable export

**Prompt to agent:**

Implement export settings precedence Store+Supplier → Store → System
default, reusing existing settings where possible and proposing the
smallest missing schema additions only after review. Validate required
columns. Export only products assigned to the selected supplier.
Separate Export Copy from Place on Portal. Save export record/settings
version only after a confirmed successful file creation; preserve
partial results and retry safely. Do not mark failed exports successful.
**Acceptance gate:** compare generated output with approved legacy
examples; test all precedence tiers, required-column validation, partial
failure, retry idempotency, and duplicate portal-order prevention.

### Phase 9 --- Portal worker adapter (background, staged)

**Prompt to agent:**

Create a separate background portal worker/adapter; do not import legacy
OrderBot main.py into the Nexora API process. Keep Selenium fallback
while Playwright is being validated. Persist job IDs and per-line
outcomes; capture order reference/status before reporting success.
Handle uncertain outcomes by checking the existing order before
retrying. Run one job per supplier portal profile and prevent unsafe
browser-profile concurrency. Unknown availability blocks portal
submission. Portal stock must not alter suggested/final quantity. Price
increases above threshold require recorded approval. **Acceptance
gate:** adapter tests with isolated/test endpoints, failure
traces/screenshots without secrets, retry/duplicate prevention, UI
remains responsive, and no false-success state.

### Phase 10 --- Receipts, pending, Not Supplied, and closure

**Prompt to agent:**

Use actual confirmed order and receipt evidence to calculate pending.
Draft/unexported/failed orders do not count as confirmed pending. GRN
reference alone is not proof of full receipt. Support partial receipt,
cancellation/reversal handling only where a verified source exists, and
Not Supplied release with an audit trail. Allow review session closure
with a clear summary of outstanding deliveries/unexported assignments;
ignored unassigned VPL rows do not become pending or carry forward
automatically. **Acceptance gate:** tests for full/partial receipt,
outstanding balance, cancellation, Not Supplied, closure summary, and
next refresh. Unknown reversal source remains explicitly blocked.

### Phase 11 --- VPL backup/history and last-10 display

**Prompt to agent:**

After the approved migration is applied in a non-production/test
database, implement the transactional snapshot lifecycle: 1. Before
replacing the current working VPL/order lines, save a complete immutable
copy to the VPL backup/history table linked to the original order header
and store. 2. Generate the next VPL/order lines in one transaction. If
backup or generation fails, rollback and keep the last good order
visible. 3. Preserve all previous snapshots in the database; never
delete older history just to enforce the UI limit. 4. In the history
view, show only the latest 10 distinct order headers for the currently
selected store, ordered by verified order timestamp/order sequence.
Fetch detail lines for a selected header. Do not mix stores or count 10
line items instead of 10 orders. 5. Ensure every snapshot preserves
suggested/final quantities, supplier/assignment/export/receipt states,
reasons, and relevant source/profile parameters required to explain the
historical decision. 6. Do not change or repurpose the existing
`OrderHeaderDetails` semantics. Keep legacy `OrderManagement` behavior
isolated unless a separately approved migration explicitly changes it.
**Acceptance gate:** first order creates no bogus previous snapshot;
second order backs up the first; interrupted generation preserves the
previous order; same ProductCode across two stores stays separate;
last-10 query returns ten distinct orders while older snapshots remain
stored and queryable; old screens still work.

### Phase 12 --- Role permissions and integration

**Prompt to agent:**

Inspect the source and do not assume legacy Role 1 means Admin or Role 2
means PM. Keep role mapping disabled until the owner confirms the
mapping. Enforce permissions in backend and UI. Preserve Admin store
switching, PM review/assignment/receipt responsibilities, and the
approved lifecycle. Do not expose actions merely by hiding buttons;
enforce authorization server-side. **Acceptance gate:** permission
matrix approved; unauthorized API tests pass; store isolation tests
pass.

### Phase 13 --- Parallel run, acceptance, and cutover

**Prompt to agent:**

Run the new workspace in parallel for one explicitly selected
test/approved store and one full order cycle. Compare generated
quantities, exclusions, rare-mover warnings, supplier assignments,
exports, and receipt/pending totals with the approved reference
behavior. No automatic production cutover. Provide a discrepancy report
and obtain explicit user sign-off. Keep the old screen and generation
path available for rollback. Only after approval, enable the feature
flag for the approved store(s); preserve an immediate rollback switch.
**Acceptance gate:** zero unexplained quantity differences for the
approved profile, approved export diff, no duplicate portal orders,
history verified, users approve, rollback tested. Stop before cutover if
any criterion fails.

## Agent response format after each phase

Return: 1. Phase and scope completed. 2. Files changed. 3. Database
changes proposed/applied (state clearly whether any migration was
executed). 4. Tests run and exact pass/fail counts. 5. Acceptance
criteria checklist. 6. Known differences/unknowns and owner decisions
needed. 7. Rollback instructions. 8. Explicit statement that later
phases were not started.

Do not proceed to the next phase until the user reviews the report and
explicitly authorizes it.
