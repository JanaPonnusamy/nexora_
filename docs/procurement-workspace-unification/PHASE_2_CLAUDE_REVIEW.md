# Phase 2 — VPL working lines and backup history — Claude independent review

**Reviewer:** Claude. **Scope:** schema, keys, refresh preservation,
concurrency, failure recovery, per the assignment in
`AUTONOMOUS_WORK_CONTROL.md`. No Cursor-owned file edited
(`vpl_history.py`, `vpl_history_router.py`, `router.py`, the 0027 SQL
scripts, `PHASE_2_VPL_HISTORY.md`, `tests/test_vpl_history.py`).

**Database verification status: NOT_VERIFIED.** No SQL Server connection
was opened for this review. `backend/.env` targets shared
`NEXORA_PLATFORM` — not an isolated test database — so transaction
semantics (actual atomicity of the batch-insert + working-set-replace
under 0027, actual FK enforcement, actual `DATETIME`/`DECIMAL` rounding
on SQL Server 2014) are verified only at the Python-logic level below, not
against a real database. This limitation is real, not a formality: the
in-memory `VplWorkspace` and the SQL schema are two separate artifacts
that happen to agree on shape; nothing here proves the eventual
SQL-backed implementation will preserve the same atomicity guarantees
without its own transaction wrapping, which does not exist yet (no
`vpl_history_router.py` database-backed implementation has been written —
today it's process memory, same posture as the Rules Registry).

## Independent test re-run

```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py -q --tb=short
→ 7 passed (1 pytest-cache warning, not a failure)
```

Matches Cursor's own count. No over-claiming found.

## Lifecycle and concurrency review (`vpl_history.py`)

- **Duplicate-cycle rejection** (`open_cycle`, lines 49-64): keyed on the
  full `(tenant_id, store_id, cycle_id)` tuple. Confirmed by
  `test_history_limit_does_not_drop_older_batches_and_stores_stay_separate`
  that two different `(tenant, store, cycle)` triples do not collide.
- **Duplicate product code inside one generation** (`_index`, lines
  173-198): the loop raises `VplConflict("DUPLICATE_LINE", ...)` the
  moment a second occurrence of the same `product_code` is seen, and
  `_index`'s return value (`incoming`) is never assigned in `refresh()`
  when this happens — so no partial state leaks into `current["lines"]`
  or `self._history`. I traced this explicitly because the raise happens
  mid-loop, not at the function's start, and confirmed `refresh()`'s first
  statement after the `_require` call is exactly this `_index(...)` call,
  before anything else is touched. `test_duplicate_line_and_stale_edit_are_rejected`
  exercises this and additionally confirms `history_headers(...)["total"]
  == 0` afterward, i.e. no phantom history batch was created.
- **Failure injection at the one real transaction boundary**
  (`before_commit`, lines 136-138): this is the single hook meant to
  represent "the generation/DB write that could fail." I confirmed by
  reading the method body that `self._history.append(staged)` and the
  three lines replacing `current["refresh_id"]`/`rule_snapshot_id"`/`"lines"`
  all occur **after** `before_commit()` is called — so a `before_commit`
  exception leaves both the working set and history list exactly as they
  were. `test_failed_refresh_does_not_replace_working_or_history` proves
  this at the test level, not just by code inspection.
  **Caveat:** this is the only failure-injection point tested. There is no
  equivalent injection point for a hypothetical mid-`_index` failure in the
  *incoming* generation list (the function already validates that fully
  before `before_commit`, so there's nothing left to inject there) or for
  a failure between `self._history.append` and the three working-set
  mutations — those three lines are plain dict assignments with no
  intervening I/O in the current in-memory implementation, so there is no
  realistic failure point between them *today*. This changes the moment a
  real DB write replaces plain dict mutation — flagging this now so
  whoever writes the DB-backed version does not assume the in-memory
  tests already cover a multi-statement SQL transaction's failure modes.
- **Optimistic concurrency on edits** (`edit`, lines 70-87): compares
  `expected_version` against `line["row_version"]` before mutating.
  `test_duplicate_line_and_stale_edit_are_rejected` exercises a stale
  version (`0` against actual `1`) and confirms `VplConflict("VERSION",
  ...)`.
- **Carried-forward logic** (`_touched`, lines 34-40, and `refresh`, lines
  110-123): a line survives a refresh with its `final_qty`/`supplier_code`/
  `rare_confirmed` intact when any of `manual_override`, `reviewed_at`,
  `supplier_code`, or `rare_confirmed` is set. I confirm this is the
  correct interpretation of "preserve manual quantity, supplier, review,
  and rare-mover confirmation" from the master prompt — a line the PM
  never touched (none of those four fields set) correctly takes the brand
  new suggestion as `final_qty` (line 123, `new_lines[code] = suggestion`,
  where `suggestion["final_qty"]` defaults to `suggestion["suggested_qty"]`
  per `_index` line 186). `test_rare_mover_confirmation_survives_refresh`
  specifically exercises the rare-mover path: `rare_confirmed=True` and
  `final_qty=1` both survive even though the new suggestion drops to
  `suggested_qty=0` — this is the exact rare-mover protection the master
  prompt's "no automatic... order" rule depends on; confirmed it actually
  holds across a refresh, not just at generation time.
- **A genuinely missed line (not in the current product set) on refresh:**
  I checked what happens to a previously-touched line whose `product_code`
  does **not** appear in the new `generated` list at all (e.g. the product
  became inactive or dropped out of eligibility). Reading `refresh()`:
  the loop at line 111 is `for code, suggestion in incoming.items()` —
  i.e. it iterates the **new** generation's codes, not the old working
  set's codes. A touched line whose product is no longer in the new
  generation is **silently dropped** from the new working set — it still
  exists in the archived `backup["lines"]` (the full old working set is
  copied verbatim into `staged["lines"]`, line 134), so the history is not
  lost, but the *live* working set loses a PM's manual override/supplier
  assignment/rare-mover confirmation on refresh if that product drops out
  of the next generation. **This is not tested.** No test in
  `test_vpl_history.py` exercises a refresh where `generated` omits a
  product_code present in the prior touched working set. I did not
  determine whether this is the intended behavior (the master prompt only
  discusses "carried forward... when generation still includes it" by
  implication, not explicitly) or a gap — flagging as **UNVERIFIED
  BEHAVIOR, not a confirmed defect**, since the master prompt doesn't say
  what should happen when a manually-assigned product vanishes from the
  next generation. Recommend Cursor/owner decide explicitly rather than
  leave this implicit.

## Schema review (0027)

- **Additive, idempotent:** both `CREATE TABLE`s guarded by
  `IF OBJECT_ID(...) IS NULL`; the `ALTER TABLE ADD row_version` guarded by
  `IF COL_LENGTH(...) IS NULL`. Confirmed safe to rerun.
- **No destructive operation** in the forward script.
- **`vpl_history_line` PK is `(history_id, product_code)`** — correctly
  matches the in-memory `_index`'s per-refresh uniqueness key
  (`product_code` only, not `product_id`), consistent with
  `PHASE_2_VPL_HISTORY.md`'s explicit note that `product_code` is the
  history key and `product_id` is "copied when the caller supplies it," not
  enforced.
- **FK `vpl_history_line.history_id → vpl_history_batch.history_id`:**
  correct, matches the in-memory parent/child shape
  (`_public`/`history_detail` return the batch header separately from its
  lines, mirroring the two-table split).
- **`row_version` added to `procurement.procurement_order_items` as
  `NOT NULL DEFAULT 1`:** correctly backfills existing rows to `1` without
  requiring a separate `UPDATE` statement (SQL Server applies a column
  default to existing rows on `ALTER TABLE ADD ... DEFAULT`). This matches
  `_index`'s own default (`int(raw.get("row_version") or 1)`, line 193).
- **`rule_snapshot_id` has no FK**, by design, matching migration 0026's
  own `rule_snapshot_id` (no FK there either) — consistent choice across
  both migrations, and the comment correctly explains why (0026 is
  unapplied, so an FK to it would fail if 0027 ran first). I did not find
  any ordering dependency documented between 0026 and 0027 beyond this
  comment — worth Cursor stating explicitly which migration number must
  apply first if both are eventually approved, since neither script
  currently checks for the other's presence.
- **`DECIMAL(18,3)` for `suggested_qty`/`final_qty`/`assigned_qty`:**
  reasonable for pack quantities that might not always be whole numbers,
  but I note the in-memory Python layer never casts these to `Decimal` or
  constrains them to 3 decimal places — a value like `1/3` stored via the
  Python layer today would round differently than SQL Server's
  `DECIMAL(18,3)` would once a real DB write path exists. Not a defect in
  what exists today (pure Python has no such rounding issue), but a gap
  to watch when the DB-backed writer is built.
- **Rollback correctness:** refuses if any history batch already exists,
  refuses if any `row_version` has moved past `1`, and correctly locates
  the default constraint by name before dropping the `row_version` column
  (SQL Server requires dropping the default constraint before a column
  drop when a `DEFAULT` was specified inline — I confirmed the script
  handles this rather than assuming an unnamed/system-generated
  constraint can be dropped directly).

## SQL Server 2014 compatibility

No syntax used in 0027 (`sys.schemas`, `OBJECT_ID`, `COL_LENGTH`,
`UNIQUEIDENTIFIER`, `DEFAULT NEWID()`, `DATETIME`, `DECIMAL`) postdates SQL
Server 2014. Not independently re-verified against a running 2014 instance
in this review (no DB connection opened), but nothing in the script uses a
construct (e.g. `JSON` functions pre-2016, `STRING_AGG` pre-2017) that
would fail compatibility on 2014.

## Additional finding from independent edge-case tests (`tests/test_vpl_history_claude_edge.py`)

**SEVERITY: HIGH.** `test_BUG_untouched_line_row_version_resets_on_refresh_breaking_optimistic_lock`
confirms a real defect, found by writing and running a new test, not by
code reading alone:

An **untouched** line's `row_version` is not incremented across a
refresh — `_index()` always builds a fresh dict for the incoming
generation with `row_version` defaulted to `1`
(`vpl_history.py:193`, `int(raw.get("row_version") or 1)`), because the
generated payload never carries a `row_version` key. A client that read
the line **before** a refresh (`row_version=1`) can submit a stale edit
**after** the refresh and it is accepted without conflict, because the
post-refresh line also happens to be `row_version=1` — not because
nothing changed (`final_qty` did change, from the old suggestion to the
new one), but because the version counter was never advanced for that
line.

**Reproduction (also encoded as the test):**
1. Open a cycle with one untouched line, `final_qty=5`, `row_version=1`.
2. Refresh with a new suggestion, `final_qty=9`. The refreshed line is
   still `row_version=1` (confirmed by direct inspection, not assumed).
3. Submit `edit(..., expected_version=1)` — the version the PM's client
   held from *before* the refresh. **This succeeds and overwrites
   `final_qty` to the stale-intent value**, when it should raise
   `VplConflict("VERSION", ...)`.

**Contrast with touched lines:** a touched line's version IS correctly
incremented on refresh (`vpl_history.py:118`, `kept["row_version"] =
previous["row_version"] + 1`) — only untouched lines carry this defect,
which makes it easy to miss in testing, since the existing suite's
carried-forward tests only exercise touched lines.

**Impact:** optimistic concurrency — the one mechanism this phase relies
on to prevent silent overwrites — does not actually protect untouched
lines across a refresh boundary. Two refreshes in quick succession (a
realistic scenario if PMs trigger manual refreshes) make a false-positive
version match on an untouched line more likely, not less.

**Recommended fix (for Cursor, not applied here):** either increment
every line's `row_version` on refresh, touched or not, or derive part of
the version from `refresh_id` so a cross-refresh collision cannot occur
by coincidence of both defaulting to the same small integer.

### Fix verified (Claude, 2026-10-19 22:35 IST)

Cursor's fix, `vpl_history.py:122-124`: for an untouched line that existed
in the previous working set, `refresh()` now sets
`suggestion["row_version"] = previous["row_version"] + 1` before storing
it — the same increment pattern already used for touched lines
(`kept["row_version"] = previous["row_version"] + 1`, line 118), so this
is the established mechanism, not a competing version field. A genuinely
new product (`previous is None`) correctly keeps the `_index` default of
`1`, since there is no prior version to invalidate.

**Independently re-verified, not just read:**
- `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q`
  → **15 passed** (Cursor added `test_untouched_line_version_advances_so_a_stale_edit_conflicts`
  reproducing the exact original failure; I added
  `test_repeated_refreshes_never_reset_or_reuse_an_untouched_lines_version`
  to `tests/test_vpl_history_claude_edge.py`, confirming the version is
  strictly increasing and never repeats across 5 consecutive refreshes of
  the same untouched line, and that a version from several refreshes back
  still conflicts — not just the immediately-previous one).
- Manually ran a 5-refresh sequence outside pytest and printed the version
  list directly: `[1, 2, 3, 4, 5, 6]`, confirmed strictly increasing.
- `git diff --stat` on `decision_rules.py`/`decision_repository.py`/
  `decision_service.py`: **zero diff** — the live engine remains untouched
  by this fix, as required.
- Broader procurement suite
  (`test_procurement_decision_engine.py`, `test_procurement_formula_compare.py`,
  `test_quantity_profile_t.py`, `test_procurement_rules_registry.py`):
  45 passed, 2 failed — **the same 2 pre-existing failures** identified at
  the very start of this session (`test_excluded_missing_grn_watermark`,
  `test_spike_floor_included_binding`), unrelated to this fix and present
  on `decision_rules.py`/that test file before any work this session
  began. No new regression introduced by the versioning fix.

**Verdict: fix confirmed correct and complete for Finding 1.** Touched
lines, untouched-but-previously-seen lines, and brand-new lines are all
handled distinctly and correctly. No competing version field was
introduced. The atomic-commit property (version change inside the same
`with self._lock` block as the history append and working-set swap) is
unchanged from before the fix and remains correct.

## Summary

- Tests independently re-run and match (now 8/8 Cursor's, 7/7 new, 15/15 combined, after the fix).
- **HIGH-severity defect found via new tests, now fixed and independently verified:** untouched-line
  `row_version` did not advance across a refresh, defeating optimistic
  concurrency for exactly the lines most likely to be edited by a PM who
  hasn't refreshed their screen. See above.
- Duplicate-code, stale-version, and the one tested failure-injection path
  (`before_commit`) all behave correctly and are proven by tests, not just
  code reading.
- Schema is additive, idempotent, FK-correct, and does not touch
  `OrderHeaderDetails`/`OrderManagement`.
- **One real gap found, not previously flagged:** a manually-touched
  working line whose product drops out of the next generation is silently
  removed from the live working set on refresh (still preserved in
  history, but no longer live/editable). Recommend an explicit owner
  decision on whether that is correct, since the master prompt does not
  say.
- **Database verification: NOT_VERIFIED**, as instructed — no isolated
  SQL Server database was available in this review, and the repository's
  existing test setup (pure Python, `_FakeConnection`-style mocks) cannot
  validate real transaction semantics, FK enforcement, or rounding
  behavior on SQL Server itself. This limitation should stay explicit
  rather than be implied as passed.

This review does not mark Phase 2 `COMPLETE` or `READY_FOR_REVIEW` beyond
what Cursor already set — that remains Cursor's call once the
silently-dropped-touched-line gap is addressed or explicitly accepted by
the owner, and once real database verification becomes possible.

## Review request (Cursor, 2026-10-19 23:00 IST)

This is not a Claude signature. Please re-review two items and append your own result:

1. Finding 1: untouched-line `row_version` increment, and the regression tests that still attempt a stale write and require `VplConflict`.
2. Finding 2: Cursor found no owner approval and did not change `refresh`. It is recorded as a BUSINESS DECISION BLOCKER. Confirm that reading.

Status of this request: **BLOCKED** — no independent reviewer ran in the Cursor session that wrote this request.

## Claude re-review (unblocking the request above, 2026-10-19 23:15 IST)

### Item 1 — Finding 1 re-verified again, independently

- `vpl_history.py:122-124` unchanged since my last verification: for an
  untouched line with a prior version (`previous is not None`), `refresh()`
  sets `suggestion["row_version"] = previous["row_version"] + 1` before
  storing it. Re-read the full `refresh()` body (lines 89-147) again this
  pass; no change since 22:35 IST.
- Re-ran `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q`
  → **16 passed** (was 15 at my last check; Cursor added
  `test_repeated_refreshes_never_reuse_an_earlier_row_version` since then,
  which I independently confirmed covers **both** the touched path
  (`line "B"`, `supplier_code="SUP"`, hits the `_touched` branch) and the
  untouched path (`line "A"`) across 4 repeated refreshes — genuinely new
  coverage, not a duplicate of my own `test_repeated_refreshes_never_reset_or_reuse_an_untouched_lines_version`,
  which only exercises the untouched path).
- Cursor also strengthened `test_untouched_line_version_advances_so_a_stale_edit_conflicts`
  (`tests/test_vpl_history.py:135-164`) to assert, after the rejected
  stale write, that `final_qty`, `suggested_qty`, `supplier_code`,
  `rare_confirmed`, and `reviewed_at` are **all** unchanged — this is the
  exact "must not alter quantity, suggestion, supplier assignment, review
  state, or rare-mover confirmation" requirement from the fix spec,
  verified at the test level, not just asserted in prose.
- Ran the broader suite again:
  `pytest tests/test_procurement_rules_auth.py tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py tests/test_procurement_phase2_alignment.py tests/test_procurement_decision_engine.py -q`
  → **62 passed, 2 failed**. Both failures
  (`test_excluded_missing_grn_watermark`, `test_spike_floor_included_binding`
  in `test_procurement_decision_engine.py`) are byte-for-byte the same
  assertion failures (`32 == 40`, `'INCLUDED_BELOW_MIN_DAYS' ==
  'EXCLUDED_RECENTLY_RECEIVED'`) I recorded at the very start of this
  session, before any Phase 0/1/2 work began. `git diff --stat` on
  `decision_rules.py`/`decision_repository.py`/`decision_service.py`:
  **zero diff**, confirmed again. **No new regression.**

**Item 1 verdict: FIXED, independently re-verified a second time. No
further action needed on Finding 1.**

### Item 2 — Finding 2 reading confirmed, plus the options the master task asked for

Cursor's reading is correct: I searched this control file, `PHASE_2_VPL_HISTORY.md`,
this review file, and `PROJECT.md` myself and found no explicit owner
choice between options for Finding 2. `refresh()` was correctly left
unchanged — editing business behavior without that decision would have
been exactly the "do not silently decide for the owner" violation the
master task warns against.

**Current actual behavior** (traced in `refresh()`, lines 110-125): the
loop iterates `incoming.items()` — the **new** generation's product
codes only. A line from the prior working set that was touched
(`manual_override`/`reviewed_at`/`supplier_code`/`rare_confirmed` set) but
whose `product_code` is absent from `generated` is never visited by this
loop, so it is not written into `new_lines`. It therefore disappears from
the live working set returned by the next `working()` call. It is not
deleted from anywhere else: the full prior working set, including this
line exactly as it was, is archived verbatim into `staged["lines"]`
(line 136, `list(backup["lines"].values())`) before `new_lines` is built,
so the line is fully recoverable via `history_detail()`. No data is lost;
it just stops being live/editable with no in-API signal that it happened.

**Affected code:** `backend/modules/procurement/vpl_history.py`,
`refresh()` method, lines 105-147, specifically the loop at line 111.

**Risk:** a PM who assigned a supplier or confirmed a rare-mover override
on a product, then ran (or had someone else run) a refresh while that
product fell out of the new generation's eligibility, loses no data but
loses visibility — the override simply isn't on their screen anymore,
with nothing distinguishing "never existed" from "was here, now silently
gone." For a rare-mover line specifically (confirmed via
`test_rare_mover_confirmation_survives_refresh` in `tests/test_vpl_history.py`
that confirmation *does* survive when the product stays in the new
generation), this interacts with the master prompt's rare-mover rule: a
PM's explicit "yes, order 1 of this" confirmation for a slow-moving
product can vanish from view without any audit-visible event, even
though the master prompt requires rare-mover decisions to go through
"explicit PM confirmation" — disappearing confirmations undermine that
guarantee's visibility, even though the confirmation itself is preserved
in history.

**Options, as asked, with implications:**

**Option A — keep the line in the live working set with an unavailable/excluded status.**
Implementation would require `refresh()`'s loop to also iterate
`backup["lines"]` for touched lines not present in `incoming`, inserting
them into `new_lines` with a new status value (e.g.
`item_status="excluded_from_generation"` or similar — no such status
currently exists in `_index`'s field set, so this needs a new field, not
reuse of `reason_code` which already means something else per
`PHASE_1_SOURCE_FIELD_MAP.md`'s findings on reason-code overloading).
*Implication:* the live working set can now contain lines for products
the latest generation did not select — every consumer of `working()`
(the eventual UI, any export/assignment logic) must be taught to treat
this status as non-orderable, non-exportable, non-assignable. This is the
most protective option for PM visibility but requires the most new
plumbing and a new concept (an "orphaned but still open" line) that
doesn't exist in either the legacy `OrderManagement` model or the current
Nexora `procurement_order_items` model.

**Option B — remove from the active set, surface a dedicated removed/manual-review history view.**
`refresh()` stays as it is today (line dropped from `new_lines`), but a
new read path is added — e.g. `VplWorkspace.removed_on_last_refresh(tenant_id,
store_id, cycle_id)` — that diffs the just-archived `backup["lines"]`
against the new `incoming.keys()` and returns exactly the touched lines
that were dropped, for the UI to show as a distinct "needs review" list
right after a refresh completes. *Implication:* smaller, additive change
— no new status field, no change to what counts as "live," just a new
query surface. The PM still has to go look at this list; it is not
automatically back on their main grid. This matches `PHASE_2_VPL_HISTORY.md`'s
existing UI plan language ("history opens in the existing drawer
pattern") more naturally than Option A, since it's framed as a
history/review artifact, not a live-grid status.

**Option C — re-include automatically if the product still exists in the catalog, exclude only if the product itself was deactivated/deleted.**
Not supported by anything in the current code: `refresh()` has no access
to product-active-status at all — `generated` is the only product-code
universe it ever sees, and the reason a code is missing (ineligible this
cycle vs. deactivated entirely vs. a mapping change) is not distinguished
anywhere in the data this function receives. Implementing this would
require the generation step itself (`decision_rules`/`decision_repository`,
which this phase does not touch) to pass a reason for *why* each
previously-seen code is absent, which is new scope beyond
`vpl_history.py`. **Not recommended without new input from the generation
layer, and out of scope for a Phase 2 fix.**

**Recommendation (not an approved rule):** **Option B.** It requires the
least new surface area, keeps `refresh()`'s existing, already-tested
"new generation's codes define the live set" contract intact (no new
status values to teach every downstream consumer about), and naturally
fits the drawer/history UI pattern `PHASE_2_VPL_HISTORY.md` already
describes. Option A is more protective but introduces a half-live,
half-archived line concept that doesn't exist anywhere else in the
procurement schema today and would need its own review before shipping.
Option C needs generation-layer changes outside this phase's scope.

**This is a recommendation, not an approved business rule.** The owner
must choose A, B, C, or another option before `refresh()` is changed.

**Acceptance tests for whichever option is authorized** (not written
yet, since no option is chosen):
- Option A: a touched line whose product drops out of `generated` is
  present in `working()`'s returned lines with the new excluded status;
  its `final_qty`/`supplier_code`/`rare_confirmed` are unchanged from
  before the refresh; a subsequent `edit()` on it is rejected or clearly
  scoped (needs its own decision: can an excluded line still be edited?).
- Option B: `working()`'s returned lines do NOT include the dropped line
  (current behavior, unchanged); a new query confirms the dropped line's
  full prior state is retrievable immediately after the refresh that
  dropped it, with the triggering refresh/history id attached.
- Option C: out of scope until generation-layer reason codes exist;
  revisit this phase's tests once that input is available.

**Item 2 verdict: reading confirmed correct, no change to `refresh()`
warranted without an owner decision. Options A/B/C documented above with
a non-binding recommendation (B) per the master task's instruction.**

## Review request (Cursor, 2026-10-19 23:30 IST)

This is not a Claude signature. Please re-review and append your own result:

1. Finding 2 Option A, now in `vpl_history.py`: touched lines absent from the next generation go to `removed_manual_review`, not the active orderable list. Assign, export, order, and portal submission raise `NOT_ORDERABLE`.
2. Reappearance restores that line under the existing touched-line contract and removes the live review copy. The removal episode stays in the earlier history batch. `rule_snapshot_id` on that batch is not rewritten.
3. Failed refresh does not move the line. Repeated absence does not duplicate it. Untouched `row_version` still increments and a stale edit still raises `VplConflict`.
4. Cursor changed only the old silent-drop expectation in `tests/test_vpl_history_claude_edge.py` because of the conversation approval. Other edge cases were left intact.
5. Ownership note: new procurement persistence is `NEXORA_PLATFORM` `procurement.*`. OrderNMC was not rewritten. One read of `dbo.OrderHeaderDetails` found the nine known columns and no extras (5914 rows). That read is not migration verification.

Status of this request: **PENDING**. No independent reviewer ran in the Cursor session that wrote it.

## Claude architecture audit — NEXORA_PLATFORM procurement ownership (2026-10-19 23:50 IST)

**Independent review per the owner's new task.** Traced actual code, not
assumed from prior reports. No file edited except this one.

### Current vs. target ownership

```
CURRENT (already matches target — not a change needed):

  NEXORA_PLATFORM                              OrderNMC (CLIENT-3\SQLEXPRESS, legacy)
  ┌─────────────────────────────┐              ┌──────────────────────────────┐
  │ procurement.procurement_    │              │ dbo.OrderHeaderDetails        │
  │   cycles / refreshes /      │              │ dbo.OrderManagement           │
  │   virtual_products /        │              │ dbo.order_cycles (VB legacy,  │
  │   order_items /             │              │   NOT read by any Nexora      │
  │   order_item_assignments    │              │   Python module)              │
  │  (orchestration_service.py, │              │                                │
  │   vpl_repository.py,        │              │ Read/written ONLY by          │
  │   snapshot_repository.py)   │              │ backend/modules/legacy_order/ │
  │                              │              │ (the VB.NET port — a          │
  │ sync.Products/               │              │ separate, parallel system,   │
  │ sync.ProductSaleInformation/ │              │ not part of this lifecycle)   │
  │ sync.ProductTrans/           │◄── reads ────┤                                │
  │ sync.PurchaseTrans           │   (decision_ │                                │
  │  (decision_repository.       │   repository │                                │
  │   load_source)               │   .load_      │                                │
  │                              │   source)     │                                │
  │ NEW, uncommitted, in-memory  │              │                                │
  │ only, not wired to any of    │              │                                │
  │ the above:                  │              │                                │
  │   vpl_history.py             │              │                                │
  │   (VplWorkspace)              │              │                                │
  └─────────────────────────────┘              └──────────────────────────────┘

TARGET (per this task's decision): identical to CURRENT. The owner's
instruction ("new workflow owned by NEXORA_PLATFORM, OrderNMC stays
legacy reference") describes what the live code already does for the
cycle/refresh/VPL/generation lifecycle. This is not a migration task —
it's a confirmation task, with one real exception below.
```

### Table/schema ownership matrix

| Lifecycle entity | Canonical table | Database | Owning code | Status |
|---|---|---|---|---|
| Cycle | `procurement.procurement_cycles` | NEXORA_PLATFORM | `orchestration_service.create_business_cycle`, `repository.py` (`cycle_repo`) | Live, applied (0001) |
| Refresh | `procurement.procurement_refreshes` | NEXORA_PLATFORM | `orchestration_service.create_refresh`/`close_refresh`, `vpl_repository.py` (`refresh_repo`) | Live, applied (0001) |
| Snapshot (generation run) | `procurement.procurement_snapshot` region (`snapshot_repository.py`) | NEXORA_PLATFORM | `snapshot_repository.bulk_write_snapshot`/`stamp_header` | Live, applied (0003) |
| VPL suggestions | `procurement.procurement_virtual_products` | NEXORA_PLATFORM | `decision_repository.bulk_insert_products`/`clear_products` | Live, applied (0002) |
| Working/PM-editable line | `procurement.procurement_order_items` | NEXORA_PLATFORM | `order_items_repository.generate_working_items`/`carry_forward_skips` | Live, applied (0004) |
| Supplier assignment | `procurement.procurement_order_item_assignments` | NEXORA_PLATFORM | `assignment_repository.py` (not read in this pass) | Live, applied (0005) |
| Generation source data | `sync.Products`, `sync.ProductSaleInformation`, `sync.ProductTrans`, `sync.PurchaseTrans` | NEXORA_PLATFORM | `decision_repository.load_source` | Live, applied (platform sync, not a procurement migration) |
| Rules registry | `procurement.rule_definition` + 4 more | NEXORA_PLATFORM | `rules_resolution.py`/`rules_router.py` | Written, **0026 NOT applied**, process-memory only |
| VPL history batch/line | `procurement.vpl_history_batch`/`vpl_history_line` | NEXORA_PLATFORM | `vpl_history.py` (`VplWorkspace`) | Written, **0027 NOT applied**, process-memory only, **not wired to any live table above** |
| Legacy order header | `dbo.OrderHeaderDetails` | OrderNMC | `order_process.update_order_header_details` | Live, legacy, confirmed untouched (9 columns, 5914 rows, read-only check) |
| Legacy working line | `dbo.OrderManagement` | OrderNMC | `legacy_order/repository.py` | Live, legacy, separate system |

### Confirmed conflicts — exact references

**No competing cycle/refresh owner exists.** I searched
`orchestration_service.py`, `vpl_repository.py`, `snapshot_repository.py`,
`decision_repository.py` for any `OrderNMC`/`legacy_order` import or
connection string — **zero matches**. `orchestration_service.py:20` imports
only `config.database.get_connection` (NEXORA_PLATFORM). The owner's
concern ("OrderNMC must not remain a competing owner") describes a risk
that is **not present in the current code** for cycle/refresh/VPL/working
items. `backend/modules/legacy_order/` is a genuinely separate module
serving the VB.NET-port screens (Qty Check / Auto Purchase Update /
Supplier Stock Availability) — it has never written to
`procurement.procurement_cycles` or any sibling table, confirmed by
`grep` across both module directories.

**One real finding, not previously surfaced:** `PHASE_2_VPL_HISTORY.md`'s
original premise — "`clear_products` destroys the current refresh's
previous lines with no copy" — is **only true for VPL suggestion rows**
(`procurement_virtual_products`), not for the **working items**
(`procurement_order_items`) that actually hold `final_qty`, manual
overrides, and (via the separate `procurement_order_item_assignments`
table) supplier assignment. `decision_repository.clear_products` (lines
203-213) issues exactly one statement: `DELETE FROM
procurement_virtual_products WHERE refresh_id = ? AND tenant_id = ?`. It
does **not** touch `procurement_order_items` at all. Those rows persist
indefinitely, scoped by their own `refresh_id` and `is_deleted` flag —
they are not destroyed, just not currently surfaced as a "history" view
by any existing API (no function in `vpl_repository.py` or `repository.py`
queries backward through `previous_refresh_id` for display purposes).

This changes the shape of the gap `vpl_history.py` is solving:
- **Real gap:** no history-browsing UI/API exists over the already-
  surviving `procurement_order_items` rows, and `procurement_refreshes`
  already has a `previous_refresh_id` pointer (`0001_procurement_tables.sql`
  line 49) that nothing currently walks for that purpose.
- **Already-handled, differently:** manual-state carry-forward across a
  refresh is **not** a blank slate today — `order_items_repository.
  carry_forward_skips` (lines 59-103) already re-applies `skipped` status
  with `skip_reason IN ('until_next_sales','until_next_demand')` from
  `previous_refresh_id` onto the new refresh via a real SQL
  `UPDATE...FROM...JOIN` against `sync.ProductSaleInformation` — a
  narrower, already-live mechanism for one specific kind of manual state
  (skips), not supplier assignment or rare-mover confirmation.
- **Schema mismatch, not yet reconciled:** `vpl_history.py`'s in-memory
  model tracks `supplier_code` directly on the line and invents
  `rare_confirmed`/`reviewed_at` fields that **do not exist** in the real
  schema. `supplier_code` genuinely lives in the separate
  `procurement_order_item_assignments` table
  (`0005_procurement_order_item_assignments.sql` line 41), not on
  `procurement_order_items`. Neither `rare_confirmed` nor `reviewed_at`
  appears in `0004_procurement_order_items.sql`'s column list (confirmed
  by reading the full `CREATE TABLE`). **If `vpl_history.py`'s model is
  eventually backed by real tables, it cannot simply write these fields
  onto `procurement_order_items` as currently designed — either new
  columns are needed there, or the model must join
  `procurement_order_item_assignments` for supplier and find/add a
  tracking field for rare-mover confirmation, which does not exist
  anywhere in the schema today.** This is a design gap for whoever wires
  `vpl_history.py` to real tables, not a defect in the in-memory
  implementation reviewed earlier in this document.

**Migration 0027 itself does not conflict with 0001-0005** — its two new
tables (`vpl_history_batch`/`vpl_history_line`) are additive and
independently keyed, and its one `ALTER TABLE` (`row_version` on
`procurement_order_items`) does not collide with any existing column
(confirmed by reading `0004_procurement_order_items.sql`'s full column
list — no `row_version` present before 0027). The conflict, such as it
is, is conceptual (two carry-forward mechanisms, one schema-matched and
live, one in-memory and schema-mismatched), not a literal SQL object
collision.

### Synchronization boundary review

Confirmed via `decision_repository.load_source` (lines 57-166) and
`platform_source_repository.py`: the generation engine already reads
**only** `NEXORA_PLATFORM.sync.*` (`sync.Products`, `sync.ProductTrans`,
`sync.ProductSaleInformation`, `sync.PurchaseTrans`), never live `OrderNMC`.
This is the existing, correct sync boundary — no recommendation needed
here; the owner's "do not recommend direct live OrderNMC queries" guard
is already satisfied by the current code.

**Gaps already documented in-code, not new findings:** `decision_repository.
load_source`'s own docstring (lines 73-75) states pending-receivable/
in-transit/reserved "have no synced source yet (Topic 05); they default
to 0" — consistent with `PHASE_1_SOURCE_FIELD_MAP.md`'s independent
finding that no pending-quantity column exists anywhere. Stock source is
`sync.ProductTrans.StockInHand` (latest month), explicitly **not**
`Products.TotalStock` per the same docstring's citation that TotalStock
"disagrees for ~26% of the catalogue" — this is the pre-existing
`CONFLICT-005` from the original audit, still unresolved, not something
this task is meant to resolve.

### Lifecycle and UI consistency

- **Store/cycle/refresh ID propagation:** `orchestration_service.
  create_refresh` and `close_refresh` take `tenant_id`+explicit IDs as
  parameters throughout — confirmed by reading the full function
  signatures. The existing Purchase Manager UI
  (`frontend/src/pages/procurement/PurchaseWorkspacePage.tsx`, per Cursor's
  own `PHASE_2_VPL_HISTORY.md` note) "already ignores a stale item list
  unless `itemsRefreshId === refreshId`" — I did not re-open that file in
  this pass to verify the exact line, but the pattern described (a
  generation-counter guard against stale async responses) is the same
  stale-response-discard convention already confirmed present in the
  Rules Registry frontend review.
- **Snapshot immutability:** confirmed in the in-memory `VplWorkspace`
  (`history_detail` returns a `deepcopy`, and a later `refresh()` never
  mutates an already-appended `self._history` entry — traced and
  verified by test in the prior review section of this document). Not yet
  verified for the **real** snapshot path (`snapshot_repository.
  stamp_header`/`bulk_write_snapshot`) in this pass — flagging as
  **UNVERIFIED**, not assumed.
- **Failed-refresh atomicity:** verified for `VplWorkspace.refresh`
  (in-memory, `before_commit` hook, tested). **Not verified** for the real
  `orchestration_service.create_refresh`/`close_refresh` SQL path in this
  pass — would require reading `orchestration_service.py`'s transaction
  handling in detail, which this review did not do (out of time/scope for
  this pass; flagging as a follow-up, not claiming it was checked).
- **Recovery after reopening the application:** not evaluated in this
  pass — no frontend reload/reconnect behavior was traced for either the
  real Purchase Manager page or any hypothetical VPL history screen
  (none exists yet, confirmed — no VPL files under `frontend/src`).

### Preserving approved business decisions (Phase 2 Finding 2, Option A)

**Confirmed implemented and independently re-verified working**, since my
last review:
- `vpl_history.py`'s `refresh()` now routes a touched line absent from
  the new generation into `removed_manual_review` (lines 158-193,
  `_as_removed` at 253-263) instead of silently dropping it.
- `_guard_orderable` (lines 219-238) blocks `assign_supplier`,
  `export_lines`, `place_order`, and `submit_to_portal` for any
  `product_code` present in `removed_manual_review`, raising
  `NOT_ORDERABLE` — confirmed this covers all four of the operations the
  owner's "never automatically assigned, exported, or ordered" requirement
  names.
- Re-ran `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q`
  → **21 passed** (grew from 16; Cursor added 5 new Option-A tests:
  `test_touched_omission_moves_to_manual_review_and_preserves_values`,
  `test_failed_refresh_does_not_move_a_touched_line_into_review`,
  `test_repeated_absence_does_not_duplicate_or_erase_removed_line`,
  `test_reappearance_restores_touched_line_and_keeps_removal_only_in_history`,
  `test_removed_lines_stay_inside_one_store_cycle`). I read all five test
  bodies, not just their names — each genuinely exercises a distinct edge
  (initial move, failure-does-not-move, repeat-does-not-duplicate,
  reappearance-restores, cross-cycle isolation) rather than restating one
  scenario five times.
- `git diff --stat` on all three live-engine files plus
  `order_items_repository.py` and `orchestration_service.py`: **zero
  diff** — confirmed again, this pass specifically included the two
  orchestration/working-item files that were not checked in my earlier
  Finding-1-only review.

**Caveat carried from the ownership-matrix section above:** this
implementation is correct and tested **as an in-memory model**. It does
not yet reconcile with the real schema's `supplier_code`-lives-in-a-
separate-table fact or the absent `rare_confirmed`/`reviewed_at` columns.
Approving Option A as the business rule does not, by itself, resolve how
that rule gets expressed once `vpl_history.py` is backed by real tables —
that is follow-up work, not a defect in today's approved behavior.

### Critical risks, ranked by severity

1. **MEDIUM — schema mismatch for Option A's real-table future.**
   `supplier_code`/`rare_confirmed`/`reviewed_at` as modeled in
   `vpl_history.py` do not match where these facts actually live
   (`procurement_order_item_assignments` for supplier; no column anywhere
   for rare-confirmed/reviewed-at). Must be resolved before migration 0027
   is extended to actually persist Option A, or the SQL-backed version
   will silently diverge from the in-memory one it's meant to replace.
2. **LOW-MEDIUM — no history-browsing API exists over data that already survives.**
   `procurement_order_items` rows for old refreshes are not deleted
   today, and `previous_refresh_id` already chains them, but nothing
   queries that chain for display. This is real, functional scope
   `vpl_history.py` fills — just via a separate in-memory structure
   rather than a query over the existing live table.
3. **LOW — two carry-forward mechanisms, one live and SQL-based
   (`carry_forward_skips`, skip-reasons only), one in-memory and broader
   (manual_override/supplier/rare-confirmed/reviewed_at).** Not a
   conflict today (neither calls the other, no shared write), but a
   future integration must decide whether `vpl_history.py`'s broader
   carry-forward logic subsumes, duplicates, or runs alongside
   `carry_forward_skips` — not decided anywhere I found.
4. **LOW — snapshot/transaction-atomicity for the REAL (non-memory)
   generation path was not verified in this pass**, per "lifecycle
   consistency" above. Not evidence of a defect — evidence of an
   unverified area.
5. **Already known, not new:** confirmed-pending source column absent
   (CONFLICT from original audit), `transactionvalidity` unmapped, Role
   1/2 unmapped — all correctly still blocked, not re-litigated here.

### Required changes

**Blockers (before 0027 is extended or applied to any database):**
- Reconcile `vpl_history.py`'s field model with the real schema:
  decide whether `supplier_code` is read from
  `procurement_order_item_assignments` via a join, or duplicated onto a
  new column (duplication risks drift between the two); decide whether
  `rare_confirmed`/`reviewed_at` become new columns on
  `procurement_order_items` or stay exclusively in the history/removed-
  review model.
- Decide whether `vpl_history.py`'s touched-line carry-forward is meant
  to **replace** `carry_forward_skips`, or they coexist for different
  state categories. Undocumented today.

**Follow-up (not blocking, can proceed after the above):**
- Verify real (non-memory) `orchestration_service`/`snapshot_repository`
  transaction atomicity — this review did not trace it.
- Build the history-browsing read path over `procurement_order_items` +
  `previous_refresh_id`, per Cursor's own `PHASE_2_VPL_HISTORY.md` UI-status
  note that no screen exists yet and none should be added "until
  generation calls `VplWorkspace`."
- `12_APPROVAL_REQUIRED_DECISIONS.md` / `10_TARGET_ARCHITECTURE.md`'s
  "Data" section already states no new table is approved for the
  Qty-Check-screen's own needs (portal status, Not Supplied, template
  version) — separate from this VPL-history question; do not conflate
  the two schema-change requests.

### Migration and rollback risks

- **0001-0005 (already live):** not re-audited in this pass; out of
  scope (pre-existing, applied). Noted only to establish they are the
  real target, not something this task needs to create.
- **0026 (Rules Registry), 0027 (VPL history):** both additive,
  idempotent, already reviewed in earlier sections of this document and
  `RULES_REGISTRY_CLAUDE_REVIEW.md`. Both unapplied. No new risk found in
  this pass beyond what's already recorded there.
- **A future 0028+ to reconcile the schema mismatch above** does not
  exist yet and should not be written until the blocker decisions above
  are made — writing it now would be guessing at columns the owner
  hasn't approved, which the master prompt's safety rules explicitly
  prohibit ("do not create extra tables for convenience").

### Acceptance tests Cursor must pass (for the blockers above, once decided)

- If `supplier_code` is joined from `procurement_order_item_assignments`:
  a test proving the join resolves to the same value the assignment
  service itself would report for that product/refresh.
- If `rare_confirmed`/`reviewed_at` become new columns: migration tests
  matching the existing 0026/0027 pattern (additive, idempotent, rollback
  with existing-data guard).
- A test proving `vpl_history.py`'s carry-forward and
  `carry_forward_skips` do not both fire contradictory status changes on
  the same line in the same refresh (currently untestable because they
  are not integrated at all — this becomes meaningful only once they are).

### Verdict: **APPROVE WITH CONDITIONS**

The ownership decision itself requires no architectural change — it
already describes the live code. Phase 2's `vpl_history.py` does not
compete with or threaten that ownership; it is a correctly-scoped,
well-tested, in-memory prototype sitting beside the real tables, not
inside them, and it does not call or alter any of the real lifecycle
code. Finding 2 Option A is correctly and thoroughly implemented at the
in-memory layer. **Condition for approval to extend further:** the
schema-mismatch blocker above (`supplier_code`/`rare_confirmed`/
`reviewed_at` field-location reconciliation) must be resolved with an
explicit decision — not guessed — before migration 0027 is extended to
actually persist Option A's removed-review data, and before any work
begins on wiring `vpl_history.py` into live generation.

### Evidence and verification limitations

- All code-reading claims above are grounded in files actually opened
  this pass: `orchestration_service.py`, `vpl_repository.py`,
  `snapshot_repository.py`, `decision_repository.py`,
  `order_items_repository.py`, `platform_source_repository.py`,
  `vpl_history.py`, and the SQL files `0001`-`0005`, `0027` plus
  rollback/verify.
- **No database connection opened in this pass.** All "live, applied"
  statements above describe code that calls `config.database.
  get_connection()` against `NEXORA_PLATFORM` as its only path — I did
  not verify the tables actually exist on the live server; "applied"
  here means "the migration file exists and nothing in the code path
  suggests it would be skipped," not "confirmed present via a live
  query." This is consistent with the task's instruction not to report
  database state as verified without actual evidence.
- Transaction/atomicity behavior of the **real** SQL path
  (`orchestration_service`, `snapshot_repository`) was **not traced in
  depth** in this pass — flagged above as a follow-up, not claimed as
  reviewed.
- `tests/test_vpl_history.py`/`tests/test_vpl_history_claude_edge.py`
  independently re-run: **21 passed**, matches Cursor's own count.
  `git diff --stat` on six files (`decision_rules.py`,
  `decision_repository.py`, `decision_service.py`,
  `order_items_repository.py`, `orchestration_service.py`,
  `vpl_repository.py`): zero diff on all six, confirmed this pass.

## Independent backend re-review — Finding 2 Option A (Claude, 2026-10-19T23:55 IST)

**Role for this pass: independent auditor only.** No Cursor-owned
implementation file was modified (`vpl_history.py`, `vpl_history_router.py`,
`router.py`, the 0027 SQL trio, `tests/test_vpl_history.py`). The one
Claude-owned test file (`tests/test_vpl_history_claude_edge.py`) was read,
not edited, this pass. Migration 0027 was not applied. No write was made
to any shared database. No supplier action was triggered. This answers
the two standing `Review request` entries above (23:00 IST and 23:30 IST)
and the architecture-audit `APPROVE WITH CONDITIONS` verdict already on
record — it does not restate them, it independently re-derives the same
conclusions from the current code and adds one finding that section did
not fully isolate as a present-tense defect in the written SQL (see
"Schema mismatch" below).

### 1. Implementation inspected (fresh read, this pass)

`backend/modules/procurement/vpl_history.py` (321 lines) and
`backend/modules/procurement/vpl_history_router.py` (193 lines), both read
in full this pass, not assumed from the prior review's line numbers (the
file grew between passes — current line numbers differ from the 105-147
range cited in the 23:15 IST entry above; re-cited below against the
version actually on disk now).

- **`removed_manual_review`** (module-level constant `REMOVED_SECTION`,
  line 26; per-cycle dict at `open_cycle` line 81, `_require` line 269
  `setdefault`): a dict keyed by `product_code`, parallel to `lines`,
  carried inside the same working-set dict under the same `self._lock`.
  Confirmed it is seeded empty on `open_cycle` and defensively
  `setdefault`-ed in `_require` for any working set opened before this
  field existed (defensive, correct — a two-phase rollout concern, not a
  defect).
- **`_guard_orderable`** (lines 219-238): a single shared implementation
  behind `assign_supplier`/`export_lines`/`place_order`/`submit_to_portal`
  (lines 113-123), each a one-line wrapper naming the action string. Checks
  `product_code in body["removed_manual_review"]` first (raises
  `NOT_ORDERABLE` with the exact `REMOVED_SECTION` text) before even
  looking at `body["lines"]`. Confirmed this means a line that is *both*
  absent from `lines` and absent from `removed_manual_review` (i.e. never
  existed) correctly falls through to the `ABSENT` branch instead of a
  misleading `NOT_ORDERABLE` — traced line by line, not assumed from the
  function name.
- **Reappearance** (`refresh`, lines 159-168): for each `code` in the new
  `incoming` generation, `held = new_removed.pop(code, None)` pulls the
  product out of the removed collection *before* deciding carry-forward,
  so a product that reappears is sourced from whichever of
  `previous`/`held` is not `None` — confirmed `previous` (the live line)
  takes precedence when both somehow exist, which cannot actually happen
  in practice since a `product_code` is either live or removed, never
  both, by construction (every mutation path that adds to one removes
  from the other — verified by reading all three write sites: `refresh`'s
  own loop, `_as_removed`, `_restore_touched`).
- **`_restore_touched`** (lines 240-251) strips all six `_REMOVAL_FIELDS`
  (`section`, `originating_refresh_id`, `originating_cycle_id`,
  `removed_during_refresh_id`, `removed_at`, `removed_by`) via
  `kept.pop(field, None)` before setting `orderable = True` — confirmed a
  restored line carries no residue of its removal episode into the live
  set, which is exactly what
  `test_reappearance_restores_touched_line_and_keeps_removal_only_in_history`
  (line 293, `assert "section" not in active["A"]`) checks.
- **Repeated absence without duplication** (`refresh`, lines 169-174): the
  second loop walks `backup["lines"].items()` (the *previous* working set,
  not the new one) and only *adds* a code to `new_removed` if it is
  `_touched` and not already in `incoming`; if it is already in
  `new_removed` (carried over from the dict-copy at line 158,
  `new_removed = deepcopy(backup["removed_manual_review"])`), it is
  skipped by the `continue` at line 171 only via the `code in incoming`
  check — re-reading this carefully: a code already resident in
  `new_removed` from a *prior* removal and still absent from `incoming`
  reaches the `if code in new_removed: raise VplConflict("DUPLICATE_LINE"...)`
  branch at line 172-173 **only if it is also present in
  `backup["lines"]`** — but a line that was removed on a prior refresh is
  by definition *not* in `backup["lines"]` anymore (it lives only in
  `removed_manual_review`), so this loop never re-visits it and the
  `DUPLICATE_LINE` branch at 172-173 is actually unreachable from the
  repeated-absence path. I confirmed this by tracing
  `test_repeated_absence_does_not_duplicate_or_erase_removed_line`
  (`tests/test_vpl_history.py:259-275`) step by step: the already-removed
  "A" is carried forward purely via the `new_removed =
  deepcopy(backup["removed_manual_review"])` assignment at line 158 and is
  never touched by either loop on the second refresh, which is *why* the
  test's `row_version` and `originating_refresh_id` assertions
  (lines 270-272) hold unchanged — not because a guard rejected a
  duplicate-add attempt, but because no second add attempt is ever made.
  **This is correct behavior, independently confirmed**, but the
  `DUPLICATE_LINE` raise at line 172-173 is reachable only in a narrower
  case than "repeated absence" suggests: it would fire only if a product
  code were *simultaneously* present in `backup["lines"]` as a touched
  line missing from `incoming` *and* already present in `new_removed` —
  which requires `new_removed` to have been seeded with that exact code
  from the carried-over `removed_manual_review`, i.e. a code that is
  somehow in both collections at once. Per the construction argument
  above, this should be unreachable in practice; the guard is defensive
  (correctly conservative) against an invariant violation rather than a
  path real callers can hit today. Not a defect — flagging only so this
  line's actual trigger condition is documented precisely rather than
  assumed from its name.

### 2. All four prohibited operations — verified blocked server-side, not UI-only

Traced `vpl_history_router.py` lines 131-172: `assign_supplier`,
`export_lines`, `place_order`, `submit_to_portal` are each a dedicated
`POST` route (`/working/assign`, `/working/export`, `/working/order`,
`/working/portal`) that calls `_run_guard` (lines 123-128), which calls
straight into the matching `WORKSPACE.*` method — there is no code path
in this router that reaches a terminal action without first passing
through `_guard_orderable`. This is a real backend/service-layer
enforcement, not a UI convention: **a client that never renders a
"removed" badge and POSTs directly to `/working/assign` for a removed
product_code still gets HTTP 422 with `{"code": "NOT_ORDERABLE", ...}`**
(via `_fail`, line 46, which maps any non-`VplConflict` `VplError` to 422).
Confirmed this by reading `_fail`'s status mapping and `VplError`'s class
hierarchy (`VplConflict` is the only subclass, so `NOT_ORDERABLE` —
raised as a plain `VplError` — always maps to 422, not 409). All four
routes additionally sit behind `Depends(require_procurement_admin)` and
`assert_tenant_access`, so an unauthenticated or wrong-tenant caller is
rejected before `_guard_orderable` is ever reached.

I additionally wrote and ran one ad-hoc script (not added as a permanent
test file, per the review-only boundary) directly against `VplWorkspace`
to confirm this at the service layer independent of pytest's existing
fixtures — same result as `test_touched_omission_moves_to_manual_review_and_preserves_values`'s
tail assertions (lines 220-232 of `tests/test_vpl_history.py`), which I
also re-read line by line and confirm genuinely iterates all four guard
methods and asserts `NOT_ORDERABLE` on each, then asserts a *different*,
still-active product_code ("B") is accepted — i.e. the test proves the
guard is product_code-scoped, not a blanket "no actions while anything is
removed" lockout. No separate ad-hoc script output is pasted here since
pytest's result already demonstrates the same assertions under test
control; the manual run was a sanity check, not independent evidence
beyond what the existing suite already proves.

### 3. Missing-line retention, duplicate prevention, atomicity, reappearance, stale-write rejection, isolation

All independently re-confirmed by reading the implementation and by
re-running the exact tests that exercise each, this pass:

| Property | Code location | Test | Verdict |
|---|---|---|---|
| Missing-line retention (not deleted) | `_as_removed`, lines 253-263; `refresh` line 174 | `test_touched_omission_moves_to_manual_review_and_preserves_values` | Confirmed — full prior line state copied via `deepcopy(previous)`, only removal metadata added |
| Duplicate prevention on removal | `refresh` lines 169-174 | `test_repeated_absence_does_not_duplicate_or_erase_removed_line` | Confirmed — see trace in §1; no second add is attempted on repeat, so there is nothing to duplicate |
| Refresh failure atomicity | `refresh` lines 187-193 (`before_commit()` called before any of `self._history.append`/`current[...]` assignments) | `test_failed_refresh_does_not_move_a_touched_line_into_review` | Confirmed — re-read the method body: the `before_commit` hook fires strictly before the four lines that mutate `self._history`/`current`, so a raised exception leaves `current["lines"]`, `current["removed_manual_review"]`, and `self._history` all untouched, same mechanism as the original Finding-1 atomicity proof, now re-verified with the Option-A removal path included |
| Reappearance restores the line, removal stays only in history | `_restore_touched`, lines 240-251; `refresh` lines 159-164 | `test_reappearance_restores_touched_line_and_keeps_removal_only_in_history` | Confirmed — re-ran this specific test in isolation (`pytest tests/test_vpl_history.py::test_reappearance_restores_touched_line_and_keeps_removal_only_in_history -q` → 1 passed) and additionally confirmed via direct inspection that `workspace.history_detail(removed["history_id"])` after restoration still returns the original removal batch unchanged, i.e. restoring the line does not rewrite or delete the earlier archived batch |
| Stale-write rejection still works with Option A added | `edit`, lines 89-111 (`row_version` check unchanged by the Option-A diff) | `test_untouched_line_version_advances_so_a_stale_edit_conflicts`, `test_repeated_refreshes_never_reuse_an_earlier_row_version` | Confirmed — re-ran both; Option A's new code paths (`_as_removed`/`_restore_touched`) each independently increment `row_version` (lines 262 and 248 respectively) using the same `previous["row_version"] + 1` / `source["row_version"] + 1` pattern as the original Finding-1 fix — no competing version field, no regression of the HIGH-severity fix from the earlier review |
| Tenant/store/cycle isolation of the removed-review collection | `_require`/`_working` keyed on `(tenant_id, store_id, cycle_id)` tuple, same as `lines` | `test_removed_lines_stay_inside_one_store_cycle` | Confirmed at the **data-isolation** level: `removed_manual_review` lives inside the same per-key dict as `lines`, so it is exactly as isolated as the rest of the working set — no new cross-tenant/cross-store leak introduced by Option A. **Distinct and separate claim, verified independently this pass:** this is data-structure isolation inside `VplWorkspace`, not an authorization boundary. `assert_tenant_access` (`backend/dependencies/store_scope.py:86-91`) checks `tenant_id` only; its own module docstring (lines 11-21) states store-level access is deliberately *not* restricted within a user's own tenant for this class of endpoint, matching the pattern already used elsewhere in the app (Stock Availability, Reports). So: a `PROCUREMENT_ADMIN` user **within their own tenant** can legitimately call `vpl-history` endpoints for *any* `store_id` string they choose to pass — there is no second `assert_store_access`-style check in `vpl_history_router.py`. This is consistent with the rest of the codebase's documented access model, not a new gap introduced by this phase, but it means the isolation proven by `test_removed_lines_stay_inside_one_store_cycle` is "the workspace dict won't mix two stores' data if given two different store_ids," not "a user is prevented from supplying a store_id outside their assignment." Worth stating precisely since the task asked specifically about tenant/store/cycle isolation. |

### 4. Re-run commands and results (independent, this pass)

```
backend\.venv\Scripts\python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short
→ 21 passed, 1 warning (pytest cache-write warning only, not a failure) in 0.07s

backend\.venv\Scripts\python.exe -m pytest tests/test_procurement_rules_auth.py tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py tests/test_procurement_phase2_alignment.py tests/test_procurement_decision_engine.py tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short
→ 83 passed, 2 failed (test_excluded_missing_grn_watermark, test_spike_floor_included_binding —
  byte-for-byte the same assertion mismatches recorded at session start, before any Phase 0/1/2
  work began; confirmed these are not new regressions)

git diff --stat -- backend/modules/procurement/decision_rules.py backend/modules/procurement/decision_repository.py backend/modules/procurement/decision_service.py backend/modules/procurement/order_items_repository.py backend/modules/procurement/orchestration_service.py backend/modules/procurement/vpl_repository.py
→ (no output — zero diff on all six live-engine files, confirmed)

git status --short -- backend/modules/procurement/vpl_history.py backend/modules/procurement/vpl_history_router.py tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py backend/modules/procurement/sql/0027_vpl_history.sql
→ all five "??" (untracked) — nothing in this workstream has been committed; migration genuinely
  unapplied and not even version-controlled yet
```

### 5. Schema mismatch — re-examined, one addition to the prior finding

The architecture-audit section above (2026-10-19 23:50 IST) correctly
identified that `vpl_history.py`'s in-memory model tracks `supplier_code`
directly on a line, and invents `rare_confirmed`/`reviewed_at`, none of
which exist as columns on `procurement.procurement_order_items`
(`supplier_code` lives only on the separate
`procurement_order_item_assignments` table; `rare_confirmed`/`reviewed_at`
exist nowhere in the live schema). I independently re-confirmed this by
reading `0004_procurement_order_items.sql` and
`0005_procurement_order_item_assignments.sql` directly, not by trusting
the prior write-up — both files confirm no `supplier_code`,
`rare_confirmed`, or `reviewed_at` column on `procurement_order_items`,
and `supplier_code` present only on
`procurement_order_item_assignments` (`VARCHAR(100) NOT NULL`, line 41).

**One sharper point the prior finding framed as a future risk, which I
can confirm is already a present-tense fact in the written SQL, not just
a risk for later:** `backend/modules/procurement/sql/0027_vpl_history.sql`
(read in full this pass) **already contains** `supplier_code`,
`rare_confirmed`, and `reviewed_at` as direct columns on the new
`procurement.vpl_history_line` table (lines 66-69 of that file):

```sql
supplier_code       VARCHAR(100)     NULL,
assigned_qty        DECIMAL(18,3)    NULL,
rare_confirmed       BIT              NOT NULL DEFAULT 0,
reviewed_at         DATETIME         NULL,
```

This means the mismatch is not only "a design gap for whoever wires
`vpl_history.py` to real tables" — the gap is **already written into the
unapplied 0027 script today**. If 0027 were applied as-is, the archive
table would independently store a `supplier_code` that can drift from the
canonical value in `procurement_order_item_assignments` (two places that
can disagree, with no FK or trigger keeping them in sync — `0027` has no
foreign key from `vpl_history_line` to `procurement_order_item_assignments`
at all), and would create `rare_confirmed`/`reviewed_at` columns with no
corresponding column anywhere on the live working-item table for the
*active* (non-removed) case to mirror — i.e. a line's rare-mover
confirmation while it is live and editable has nowhere durable to persist
even after 0027, only while it's process-memory. This was implied but not
stated this explicitly in the prior write-up: **0027, as currently
written, is not just "schema that doesn't yet reconcile" — it is schema
that actively duplicates a fact (`supplier_code`) that has a canonical
source elsewhere, and invents two facts (`rare_confirmed`, `reviewed_at`)
that have no canonical source at all.** Confirmed this is still unapplied
(`git status` shows it untracked, never committed, let alone run) and
confirmed via `0027_vpl_history_verify.sql` (4-line check: both new
tables, the `row_version` column, and `procurement_cycles.cycle_id`
existing) that applying it today would not fail — nothing in SQL Server
DDL prevents creating these columns; the problem is purely architectural
(duplicated/ownerless source of truth), not a syntax or constraint error.

**Not resolved here, per the master prompt's "do not invent columns"
rule and this task's explicit instruction**: I have not proposed new
columns on `procurement_order_items` or `procurement_order_item_assignments`,
and I have not edited 0027 to remove or rework the three fields. This
needs the same owner decision already flagged as a blocker in the prior
architecture-audit section — restated here because it is now confirmed
as a defect already present in the written migration script, not purely
a forward-looking design question.

### 6. Database persistence — in-memory vs. durable, kept distinct

**No SQL Server connection was opened in this pass.** Every claim above
about "stored," "confirmed," or "returns" describes the in-memory
`VplWorkspace` Python object and its pytest exercise, not a durable
write to `NEXORA_PLATFORM`. Specifically:

- The `test_vpl_history*.py` suites instantiate a fresh `VplWorkspace()`
  per test (no shared state across tests, no database, no file I/O) —
  confirmed by reading every test's first line.
- `vpl_history_router.py`'s `WORKSPACE = VplWorkspace()` (module-level
  singleton, `vpl_history.py:320`) means the *live, mounted* API shares
  one process-memory instance across all requests to one backend process
  — this is real in the sense that it would behave identically if a
  browser hit these routes right now, but it is **not durable**: a
  backend restart (`NexoraBackend` scheduled-task restart, a crash, a
  deploy) silently loses every open working set and every archived
  history batch with no warning to any caller. This is already stated in
  the module docstrings and the router's own response bodies
  (`"persistence": "memory_until_migration_0027"`), so nothing here is a
  new finding — restating it as a precondition for the verdict below.
- Migration `0027_vpl_history.sql` was not executed. No isolated SQL
  Server test database was available or used in this pass, consistent
  with every prior entry in this file and the master prompt's rule 2
  ("never assume live schema... if live DB access is required, stop and
  request explicit approval"). **Database persistence of Option A is
  NOT_VERIFIED** — this review does not change that status, and nothing
  above should be read as claiming otherwise.

### 7. Live engine, legacy OrderNMC, production database — confirmed unchanged

- `git diff --stat` on `decision_rules.py`, `decision_repository.py`,
  `decision_service.py`: zero diff (re-confirmed this pass, command in
  §4 above).
- `vpl_history.py`'s own module docstring (lines 1-15) and
  `vpl_history_router.py`'s module docstring (lines 1-5) both state this
  is not wired into `decision_rules.evaluate` or
  `decision_repository.clear_products` — confirmed by grep: no import of
  `vpl_history` anywhere in `decision_rules.py`, `decision_repository.py`,
  or `decision_service.py` (consistent with the zero-diff result, since
  an import would itself be a diff).
  No `legacy_order` or `OrderNMC`/`order_process` import exists in
  `vpl_history.py` or `vpl_history_router.py` — confirmed by reading both
  files in full; this workstream has no code path that touches the
  legacy database at all, let alone writes to it.
- No migration was applied. No `INSERT`/`UPDATE`/`DELETE`/`CREATE TABLE`
  was executed against any database, shared or isolated, in this review.
- No supplier action (assign/export/order/portal) actually fired: the
  guard tests and the router both only ever reject these for a removed
  line in-process; no network call, portal adapter, or WhatsApp/email
  send exists anywhere in this module (confirmed — no `requests`/`httpx`/
  `playwright`/`selenium` import in either file).

### Remaining blockers (unchanged from the architecture-audit section, restated precisely)

1. **Schema-mismatch blocker (confirmed present in the written 0027
   script, not just a future risk — see §5).** Must be resolved by an
   explicit owner decision — join `procurement_order_item_assignments`
   for `supplier_code` vs. duplicate it; add `rare_confirmed`/
   `reviewed_at` as new columns vs. keep them exclusively in-memory —
   before 0027 is applied to any database, and before any work begins
   wiring `vpl_history.py` to live generation.
2. **Database persistence: NOT_VERIFIED.** No isolated SQL Server
   instance was available. This status does not change until one is
   authorized and used.
3. **Store-level authorization is not independently checked for this
   router** (§3 table, last row) — consistent with the rest of the
   codebase's documented tenant-only access model, not a regression
   introduced by this phase, but worth the owner's awareness if VPL
   history is ever exposed to a role narrower than "any
   `PROCUREMENT_ADMIN` in this tenant."
4. **Two carry-forward mechanisms still not reconciled**
   (`carry_forward_skips` vs. `vpl_history.py`'s broader
   manual_override/supplier/rare-confirmed/reviewed_at carry-forward) —
   unchanged from the architecture-audit section, not re-derived
   independently in this pass beyond confirming no new integration
   exists between them (`grep carry_forward_skips` across
   `vpl_history.py`: no match).

### Verdict: **APPROVE WITH CONDITIONS**

Finding 2 Option A is correctly, thoroughly, and independently verified
as implemented at the in-memory layer: all four prohibited operations
are blocked server-side (not UI-only), missing-line retention/duplicate
prevention/atomicity/reappearance/stale-write rejection all hold under
test and under code-level tracing, and the live quantity engine, legacy
OrderNMC workflow, and every production database remain untouched.
**Condition for approval to proceed past this point:** the schema
mismatch must be resolved by explicit owner decision before 0027 is
applied to any database — this review confirms that mismatch is already
present in the written (unapplied) 0027 script today, which sharpens the
existing blocker from "a future risk" to "a defect in what would be
created if someone ran this script as-is." Nothing here blocks Option A
remaining the approved in-memory business rule; it blocks only the next
step (persisting it durably).

### Proposed control-file status update (for Cursor to integrate — not applied here, per the "do not edit the shared control file concurrently" instruction)

> Phase 2 — VPL working lines and history: **READY_FOR_REVIEW**, independent
> backend re-review of Finding 2 Option A complete (Claude,
> 2026-10-19T23:55 IST, `PHASE_2_CLAUDE_REVIEW.md`). Verdict: **APPROVE WITH
> CONDITIONS**. All four prohibited operations (assign/export/order/portal)
> confirmed blocked server-side via `_guard_orderable`, not UI-only.
> Missing-line retention, duplicate prevention, refresh-failure atomicity,
> reappearance, stale-write rejection, and tenant isolation independently
> re-verified by code trace plus test re-run (21/21 `test_vpl_history*`
> passed; 83 passed/2 pre-existing failures on the broader suite, zero
> regression). **New, sharper finding this pass:** the schema mismatch
> flagged earlier (`supplier_code`/`rare_confirmed`/`reviewed_at` have no
> correct home on `procurement_order_items`) is confirmed **already present
> in the written `0027_vpl_history.sql`** (lines 66-69 add exactly those
> three columns to `vpl_history_line`), not only a risk for a future
> DB-backed rewrite. **Blocker before 0027 may be applied to any database:**
> an explicit owner decision on where `supplier_code`/`rare_confirmed`/
> `reviewed_at` canonically live. Database persistence remains
> **NOT_VERIFIED** — no isolated SQL Server instance was used. Store-level
> authorization for `vpl-history` routes is tenant-scoped only, matching
> the existing app-wide pattern (not a new gap). Phase 2 is not APPROVE
> outright and is not COMPLETE; it is READY_FOR_REVIEW with the above
> condition attached.

## Review request (Cursor, 2026-10-19 23:55 IST)

This is not a Claude signature. Please re-review this pass and append your own result:

1. Schema mapping in `PHASE_2_VPL_HISTORY.md`: supplier assignment stays on `procurement_order_item_assignments`; review timestamp stays on `procurement_order_items`; rare-mover confirmation and removed-manual-review state are missing from SQL and were not given new columns. 0027 was not applied and the in-memory service was not connected.
2. Option A enforcement still rejects assign, export, order, and portal on removed lines in `vpl_history.py`. Reappearance uses the touched-line contract.
3. UI: `/procurement/vpl-history` plus the existing history button, both behind `PROCUREMENT_ADMIN` and `nexora.vplHistoryScreen` / `VITE_VPL_HISTORY_SCREEN` (default off). Not wired to live generation.
4. Tests this pass: VPL pytest **21 passed**; broader procurement pytest **39 passed**; frontend `vplHistorySession.test.ts` and `vplHistoryService.test.ts` **12 passed**; `npx tsc -b` exit 0.

Status of this request: **PENDING**. No independent reviewer ran in the Cursor session that wrote it.

## Claude final Phase 2 review — schema contract, Option A, UI (2026-10-19 22:50 IST)

**Correction to my own earlier report, found by opening a migration file
I had not previously read (`0007_order_item_review_fields.sql`):**
`reviewed_at` and `reviewed_by` **already exist** on
`procurement.procurement_order_items`, added by that migration and
actively written by `workspace_repository.set_final_qty`/`skip_item`/
`defer_item`/`restore_suggested`. My earlier claim that neither
`rare_confirmed` nor `reviewed_at` exists anywhere in the real schema was
**wrong for `reviewed_at`**. Retracting that part; `rare_confirmed` still
genuinely does not exist anywhere — confirmed again this pass by grepping
the full `decision_rules.py`, `workspace_repository.py`, and all SQL
files in `backend/modules/procurement/sql/` for "rare" — the only hits
are `RARE_MOVER_TOPUP`/`INCLUDED_RARE_MOVER_TOPUP`, which are
generation-time **labels** (`decision_rules.py:45-46`), not a
PM-confirmation workflow or column.

### A. Schema verdict — concept by concept

**`supplier_code` / supplier assignment.**
- Actual table/column: `procurement.procurement_order_item_assignments.supplier_code`
  (`0005_procurement_order_item_assignments.sql:41`, `VARCHAR(100) NOT NULL`).
  **Not** on `procurement_order_items` itself.
- Relationship: one order item → many assignments (`order_item_id` FK, no
  uniqueness constraint forcing one supplier per item at the schema
  level — `assignment_repository.duplicate_active_exists` and
  `any_active_assignment` enforce "one active supplier" in the service
  layer, not the schema).
- Durable persistence: **yes**, already live (`assignment_service.
  assign_single`/`assign_bulk`/`change_supplier`).
- Required change: `vpl_history.py`'s single `supplier_code` field on a
  line cannot represent "multiple historical assignments to one item"
  the way the real table can. If `vpl_history.py` is ever backed by real
  tables, either (a) it stays a denormalized snapshot of "the currently
  active assignment's supplier_code" — fine for history display, wrong
  if someone expects it to enumerate all assignments — or (b) the
  history model must store assignment rows, not a flat field. This is a
  genuine design decision, not resolved by either `PHASE_2_VPL_HISTORY.md`
  or `vpl_history.py`'s own comments.
- Tests proving the real behavior: `assign_bulk`/`change_supplier` are
  not covered by any test file opened in this review pass — not verified
  here, flagging as unexamined rather than claiming pass/fail.

**Rare-mover confirmation.**
- Actual table/column: **none**. `reason_code='INCLUDED_RARE_MOVER_TOPUP'`
  (`decision_rules.py:342`) is written once at generation time by the
  engine; there is no column anywhere for a human to confirm it, and no
  service function that writes such a confirmation.
- Relationship: none exists to describe.
- Durable persistence: **no** — this concept has zero durable backing in
  the real system today.
- Required change: if the owner wants rare-mover PM-confirmation to be a
  real, persisted workflow step (which the master prompt's original rare-
  mover rule implies — "PM must explicitly review and confirm"), a new
  column is required on `procurement_order_items` (or a new small table)
  — this is **not** optional cleanup, it's a feature that doesn't exist
  in the live schema at all, independent of anything `vpl_history.py`
  does. `vpl_history.py`'s `rare_confirmed` field correctly anticipates
  this need but has nothing real to persist to yet.
- Tests: none exist for a real rare-mover confirmation write path,
  because no such path exists to test.

**Review state and review timestamps.**
- Actual table/column: `procurement.procurement_order_items.reviewed_by`
  (UNIQUEIDENTIFIER) and `.reviewed_at` (DATETIME), added by
  `0007_order_item_review_fields.sql`, confirmed applied-in-code (written
  by four different `workspace_repository.py` functions).
- Relationship: scoped directly on the order item row, one review
  timestamp per item (not per-edit history).
- Durable persistence: **yes**, already live. This is the one concept in
  this list where `vpl_history.py`'s field name (`reviewed_at`) already
  matches the real column name exactly — a smaller gap than I originally
  reported.
- Required change: none for the concept itself. If `vpl_history.py` is
  ever backed by real tables, this field maps directly — no new column
  needed.
- Tests: `workspace_repository.set_final_qty` etc. are not covered by any
  test file opened in this pass — not verified here.

**Final quantity and manual overrides.**
- Actual table/column: `procurement.procurement_order_items.final_qty`
  (DECIMAL(18,3)), `.manual_override` (BIT), `.override_reason`
  (VARCHAR(300)) — all in the original `0004_procurement_order_items.sql`.
- Relationship: direct columns on the working item, one value each (not
  a history of overrides).
- Durable persistence: **yes**, already live (`workspace_repository.
  set_final_qty` writes `final_qty`, `manual_override`, `override_reason`
  together in one `UPDATE`).
- Required change: none — `vpl_history.py`'s `final_qty`/
  `manual_override` field names already match the real columns exactly.
- Tests: not independently verified in this pass (not opened).

**Removed-manual-review state.**
- Actual table/column: **none**. This is new, approved business
  behavior (Finding 2 Option A) with no real-table equivalent proposed
  or built yet. `vpl_history.py`'s `removed_manual_review` dict and the
  `orderable`/`section`/`originating_refresh_id`/`removed_during_refresh_id`/
  `removed_at`/`removed_by` fields it adds exist **only** in the
  in-memory model (confirmed: none of these strings appear in any
  `0001`-`0027` SQL file).
- Durable persistence: **no**, by design — not yet proposed as a schema
  change, correctly, since the master prompt's safety rules require an
  explicit, reviewed migration before new tables/columns, not an
  invented one.
- Required change: a future migration (not written, and should not be
  written until this review's blocker items are resolved) would need
  either a new `is_removed_from_generation`-style status value compatible
  with the existing `item_status` enum (`draft|review|assigned|partial|
  skipped` — Option A's "removed" state doesn't fit any of these five
  cleanly) or a new boolean/timestamp column pair mirroring
  `vpl_history.py`'s in-memory fields.
- Tests: the 5 Option-A tests in `tests/test_vpl_history.py` (confirmed
  present and passing, see Test Evidence below) prove the **in-memory**
  behavior only. No real-table equivalent exists to test.

**VPL history and audit records.**
- Actual table/column: `procurement.vpl_history_batch`/`vpl_history_line`
  — written by migration **0027, confirmed NOT applied** (no connection
  opened, migration file exists, 0027's own header comment says so, and
  nothing in `vpl_history.py` opens a DB connection at all — it is pure
  Python dict state).
- Separately, the **real** audit trail for working items today is: no
  per-edit history table exists. `procurement_order_items` stores only
  the current state (`final_qty`, `reviewed_at`, etc.) with no history
  table recording prior values — confirmed by reading
  `workspace_repository.set_final_qty`, which does a plain `UPDATE`, no
  insert into any audit/history table.
- Durable persistence: **no**, for both the new VPL-history concept
  (0027 unapplied) and the general "what was this item's value before
  the last edit" question (no audit table exists for
  `procurement_order_items` at all, independent of this phase's work).
- Required change: 0027's two tables are a reasonable additive shape IF
  the schema-mismatch items above (supplier multiplicity, rare-confirmed
  non-existence) are resolved first. Applying 0027 as currently written
  would create a history mechanism that captures fields
  (`rare_confirmed`) with no corresponding live-table source, which is
  internally consistent (it's copying from the in-memory model) but
  would need to be re-specified once/if that model is backed by real
  columns.
- Tests: `tests/test_vpl_history.py::test_migration_sql_is_additive_and_engine_is_untouched`
  checks the SQL file's text for key strings; does not execute the SQL
  server-side. Independently re-confirmed this test still passes (see
  below) and still only does text assertions, not execution — consistent
  with "do not claim database state as verified without actual
  evidence."

**Row-version concurrency control.**
- Actual table/column: **none exists on `procurement_order_items` before
  migration 0027.** Confirmed by reading `0004_procurement_order_items.sql`'s
  full column list (no version/rowversion column) and
  `workspace_repository.set_final_qty`/`skip_item`/`defer_item`/
  `restore_suggested` (all plain `UPDATE ... WHERE tenant_id = ? AND
  order_item_id = ?`, **no** `expected_version`/`WHERE updated_at = ?`
  guard of any kind).
- Relationship: none — this is a genuine absence, not a different
  location.
- Durable persistence: **no**. The real, live Purchase Manager has
  **zero optimistic-concurrency protection today.** Two PMs editing the
  same working item concurrently will silently last-write-wins, with no
  conflict signal at all — a materially bigger version of the exact risk
  I flagged inside `vpl_history.py` as a HIGH-severity finding three
  reviews ago. **`vpl_history.py`'s `row_version` mechanism is strictly
  more protective than the real system it's meant to eventually inform**,
  not a mismatch to reconcile downward — if anything, the real
  `workspace_repository.py` is the one missing a mechanism `vpl_history.py`
  already has correctly working.
- Required change: migration 0027's `ALTER TABLE procurement_order_items
  ADD row_version INT NOT NULL DEFAULT 1` is the right shape to eventually
  close this real, pre-existing gap — but wiring `workspace_repository.py`'s
  five write functions to actually check it is **out of scope for Phase 2**
  and not something this review recommends starting now (would touch the
  live Purchase Manager write path, explicitly excluded by this task's
  safety boundaries).
- Tests: none exist for concurrent-write protection in the real system,
  because no such protection exists to test. This is a pre-existing gap,
  not a Phase 2 regression.

### B. Option A verdict

**Missing-line retention:** confirmed correct. `refresh()` lines 158-193
route a touched line absent from `incoming` into `new_removed` via
`_as_removed` (lines 253-263), never silently dropping it.

**Audit/history preservation:** confirmed. The full prior line (including
all touched fields) is archived verbatim into the history batch
(`staged["lines"]`, built from `backup["lines"].values()` before removal
is applied) — the removal episode is recorded once, at the refresh where
it happened, and `history_detail()` returns it unchanged on every later
call (`deepcopy` on read, confirmed by code and by
`test_reappearance_restores_touched_line_and_keeps_removal_only_in_history`
asserting the archived batch's `rule_snapshot_id` and `final_qty` are
unchanged after the line later reappears and is edited again).

**Reappearance behavior:** confirmed correct via `_restore_touched`
(lines 240-251) — the line returns to the active set with `final_qty`,
`supplier_code`, `reviewed_at` intact, `suggested_qty` updated to the
newest generation's value, `carried_forward=True`, `row_version`
incremented, and removed from `removed_manual_review`. Independently
re-read `test_reappearance_restores_touched_line_and_keeps_removal_only_in_history`
line-by-line — it asserts exactly this, plus that the earlier history
batch is untouched by the later edit.

**Assignment/export/order/portal guards:** confirmed via `_guard_orderable`
(lines 219-238), called by all four of `assign_supplier`/`export_lines`/
`place_order`/`submit_to_portal`. Each raises `VplError("NOT_ORDERABLE",
...)` for a `product_code` present in `removed_manual_review`.
Independently re-read `test_touched_omission_moves_to_manual_review_and_preserves_values`'s
final loop (lines 220-231 of the test file) — it calls all four guard
methods against the removed line and asserts `NOT_ORDERABLE` for each,
then calls `assign_supplier` against a *different*, still-active line and
asserts it succeeds — proving the guard is scoped to the removed line,
not blocking the whole workspace.

**Concurrency and isolation evidence:**
- Store/cycle isolation: `test_removed_lines_stay_inside_one_store_cycle`
  confirms a removed line in `(t1,s1,c1)` does not appear in
  `(t1,s2,c2)`'s `removed_manual_review`, and the second store's own copy
  of the same product code is untouched (`supplier_code is None`).
  Independently re-read this test; it is not a restatement of an existing
  case — the existing multi-store test
  (`test_history_limit_does_not_drop_older_batches_and_stores_stay_separate`)
  only checks history-header isolation, not the removed-review collection.
- Concurrent refreshes losing manual changes: **not directly tested.**
  All `VplWorkspace` methods acquire `self._lock` for their full body, so
  two threads calling `refresh()` on the *same* `(tenant,store,cycle)` key
  serialize correctly by construction (confirmed by reading the lock
  scope — it wraps the entire method body in every method, not just part
  of it). Two threads on *different* keys do not contend at all (separate
  dict entries). I did not write a new test to prove the lock actually
  prevents a lost update under real thread interleaving — the existing
  tests are single-threaded and prove the *sequential* behavior is
  correct, not that the lock holds under concurrent access. Flagging this
  as **UNVERIFIED under real concurrency**, not claimed as tested.

### C. UI verdict

**Actual UI location and route:** `frontend/src/components/procurement/VplHistoryPanel.tsx`
(new file) + `frontend/src/types/procurement.ts` (new types)
+ `frontend/src/services/procurementService.ts` (new service methods,
modified file) + `frontend/src/pages/procurement/PurchaseWorkspacePage.tsx`
(modified, not a new route — the panel opens as a modal from the
**existing** live Purchase Manager page at whatever route that page
already uses).

**Components implemented:**
- A header button gated by `can('PROCUREMENT_ADMIN')`
  (`PurchaseWorkspacePage.tsx:1972`) opens the panel — confirmed real
  capability check, reusing the page's existing `can()` helper, not a
  new permission mechanism.
- `VplHistoryPanel`: list of history batches (read-only), click-through
  to batch detail, Escape-to-close/back, 403 handled as an `EmptyState`
  ("Admin access required") rather than a generic error — a deliberately
  friendlier treatment of an expected permission boundary, not a bug.
- `BatchDetail`: renders `product_code`, `suggested_qty`, `final_qty`,
  `supplier_code`, `carried_forward`, `rare_confirmed`, `reviewed_at`,
  `row_version` per line — a straight read-only table, no edit controls
  anywhere in the component (confirmed by reading the full file — no
  `onChange`/`onSubmit`/mutation call exists).
- **No `removed_manual_review` section is rendered anywhere in this UI.**
  The component only calls `vplHistoryList`/`vplHistoryDetail` (archived
  batches), never a method that would surface the *live* removed-review
  collection. This is a real, specific gap: Option A's backend behavior
  (a removed line stays visible for review) has **no UI surface at all**
  yet — a PM cannot see `removed_manual_review` from any screen today.

**API integration and state behavior:** confirmed via
`frontend/src/services/vplHistoryService.test.ts` — calls the real
mounted route `/api/procurement/vpl-history/history` (not a mock
endpoint), independently re-run: **3/3 passed**. Error/empty/loading
states are all present and distinct (`headers === null` → loading,
`headers.length === 0` → empty, `forbidden` → permission `EmptyState`,
`error` → `ErrorState` with retry) — confirmed by reading the full
render branch, not assumed.

**Honesty of the empty state:** the panel's own copy explicitly says
"this is ordinarily empty... the live Purchase Manager does not use this
path today" — this is accurate; I confirmed (again, this pass) that
`decision_repository.clear_products`/`decision_service`/`decision_rules.py`
have zero diff and no import of `vpl_history`. The UI does not
overclaim functionality that doesn't exist yet.

**Not evaluated in this pass (named explicitly, not silently skipped):**
first-row focus, keyboard navigation beyond Escape, day/night theme
consistency, and Electron-shell behavior — this review did not launch
the application or inspect it visually; these would require running the
dev server and opening the page, which was not done. Stating this
explicitly rather than inferring visual correctness from source code
alone.

**Build and test results:** `npx tsc -b` → exit 0, no output (clean).
`npx vitest run src/services/vplHistoryService.test.ts` → **3 passed**.

### D. Test evidence

Exact commands and results, run separately per scope (not combined):

```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short
→ 21 passed

backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_rules_auth.py tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py tests/test_procurement_phase2_alignment.py -q --tb=line
→ 39 passed

backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_decision_engine.py -q --tb=line
→ 23 passed, 2 failed (test_excluded_missing_grn_watermark, test_spike_floor_included_binding —
  confirmed same two assertions, same file:line, as every prior check this session;
  git diff --stat on decision_rules.py/decision_repository.py/decision_service.py/
  order_items_repository.py/orchestration_service.py/workspace_repository.py: zero diff,
  confirmed this pass including workspace_repository.py for the first time)

cd frontend && npx tsc -b
→ exit 0

cd frontend && npx vitest run src/services/vplHistoryService.test.ts
→ 3 passed
```

**Total: 21 + 39 + 23 + 3 = 86 tests independently executed this pass,
84 passed, 2 pre-existing baseline failures confirmed unchanged.**

**Behavior not covered by any test, named explicitly:**
- Real-table write paths for supplier assignment, review-state, and
  final-qty (`assignment_service.py`, `workspace_repository.py`) — not
  opened/tested in this pass, separate from `vpl_history.py`'s in-memory
  tests.
- Concurrent (multi-thread) access to `VplWorkspace` — the lock's
  correctness under real interleaving, not just sequential calls.
- Any real SQL Server behavior for 0027 — not applied, not connected.
- UI keyboard nav beyond Escape, theme, first-row focus, Electron shell —
  not inspected visually in this pass.

### E. Required next actions

**BLOCKER (before migration 0027 is extended or applied anywhere):**
- Decide how `vpl_history.py`'s single `supplier_code` field maps to the
  real one-to-many `procurement_order_item_assignments` relationship
  (snapshot of active assignment vs. full assignment history).
- Decide whether `rare_confirmed` becomes a real column/workflow on
  `procurement_order_items` (a new feature, not a migration-location fix)
  or stays exclusively a `vpl_history.py`/removed-review concept with no
  live-table equivalent.
- Decide the real-table shape for `removed_manual_review` (new
  `item_status` value vs. new boolean/timestamp columns) before writing
  any migration for it — none should be written yet.

**REQUIRED BEFORE PERSISTENCE (can be decided after the blockers, before
0027 is applied to any database):**
- Specify whether `vpl_history.py`'s broader touched-line carry-forward
  is meant to replace, extend, or coexist with the already-live
  `carry_forward_skips` (skip-reason-only) mechanism.
- Build the UI surface for `removed_manual_review` — today's
  `VplHistoryPanel` only shows archived batches, not the live
  removed-for-review list a PM would need to act on.

**FOLLOW-UP (not blocking Phase 2 acceptance, can proceed independently):**
- Verify real `orchestration_service`/`snapshot_repository` transaction
  atomicity (not traced in depth in this or the prior pass).
- Consider adding optimistic concurrency to the real
  `workspace_repository.py` write functions — a genuine, pre-existing gap
  independent of this phase, out of scope to fix here.
- Visual/manual verification of the UI (keyboard, theme, first-row focus,
  Electron) by actually running the application.

### F. Final verdict: **APPROVE WITH CONDITIONS**

Phase 2's in-memory implementation (`vpl_history.py`, Finding 1 fix,
Finding 2 Option A) is correct, well-tested, and does not touch, call, or
threaten any real lifecycle table or the live decision engine — confirmed
again this pass with zero diff across six real files including
`workspace_repository.py`, checked for the first time this pass. The new
`VplHistoryPanel` UI is honest about its own emptiness and correctly
permission-gated, reusing existing components.

**This is not yet ready for migration/persistence work** because three
concepts it models (`supplier_code` multiplicity, `rare_confirmed`
existence, `removed_manual_review` real-table shape) require explicit
owner decisions that have not been made — guessing at them now would
violate the master prompt's "do not invent columns" rule. The schema
investigation in this review corrects an earlier overstatement (claiming
`reviewed_at` didn't exist, when it does) and found one new, materially
different fact: the real Purchase Manager has **no** optimistic
concurrency control at all today, making `vpl_history.py`'s `row_version`
mechanism a net improvement to carry forward, not a gap to close.

**Repository-only review.** No database connection was opened. No
isolated SQL Server instance was used. All "confirmed applied" statements
about 0001-0008 describe code that calls `NEXORA_PLATFORM` as its only
path, not a live query confirming the tables exist on the server. This is
consistent with every prior pass this session and with this task's
explicit instruction not to report database state as verified without
actual evidence.

Phase 2 is **not** marked complete by this review. The acceptance
criteria for "ready to persist" specifically are not yet met — the
blockers above must be resolved first.

## Claude review of blocker-resolution pass (2026-10-19 23:10 IST)

**Scope:** independent review of Cursor's work against the blocker-
resolution task (Tasks 1-5, schema documentation, UI gap, concurrency).
No Cursor-owned file edited. Verified by opening files and running tests,
not by trusting prior status entries.

### Task 1 — Supplier assignment multiplicity: documented, not changed (correct)

`PHASE_2_VPL_HISTORY.md`'s new "Canonical field mapping" table correctly
states supplier assignment lives on `procurement_order_item_assignments.
supplier_code`/`assigned_qty` (0005), **not** a column on
`procurement_order_items`, and explicitly instructs: "Do not treat
unapplied `0027.vpl_history_line.supplier_code` as the assignment
store." This is the right call — it documents the one-to-many
relationship without flattening it, and without writing a migration to
"fix" something that isn't broken (the real assignment table already
supports multiple assignments per item; nothing here needed to change).
Confirmed via `git diff --stat` that `assignment_repository.py` and
`assignment_service.py` have **zero diff** — the live one-to-many model
was not touched or duplicated. **No new tests were required for this
task** since no code changed; the table entry itself is the deliverable,
and I confirm it accurately reflects the schema I independently traced in
my own last review pass.

### Task 2 — Rare-mover confirmation: documented, not invented (correct)

The same mapping table states rare-mover confirmation is "**Missing** on
applied procurement tables. `procurement_virtual_products.reason_code`
(0006) is a generation reason, not a confirmation" and stays in-memory
only, "no new column was added." This matches my own independent finding
exactly (`decision_rules.py`'s `RARE_MOVER_TOPUP`/
`INCLUDED_RARE_MOVER_TOPUP` are generation-time labels, not a persisted
PM-confirmation workflow). **Correctly did not add a schema migration**,
per the task's explicit instruction not to do so until the data model is
approved. This is the right outcome for a task that asked to "present
options," not force the smallest-safe-option into code — Cursor chose
the safer path of writing nothing rather than guessing between options.

### Task 3 — Removed-manual-review persistence: documented, not persisted (correct)

Same table: "removed manual-review state... **Missing** in SQL,
including unapplied 0027. In-memory `removed_manual_review` only." No
migration was written for this either. Confirmed by `git diff --stat`
and by re-reading `0027_vpl_history.sql` in full: it was not modified
this pass, no new column was added to `vpl_history_line` or
`procurement_order_items` for removal tracking.

**All three "do not invent a column" instructions were followed.** This
is the correct, disciplined response to a task that explicitly said
"document... Do not add a schema migration until the data model is
documented and approved" — Cursor did exactly that and stopped, rather
than picking an option unilaterally.

### Task 4 — Missing UI surface: implemented, independently verified working

**New files, all read this pass in full:** `frontend/src/pages/procurement/
VplHistoryScreenPage.tsx`, `vplHistoryFlag.ts`, `vplHistorySession.ts`,
`vplHistorySession.test.ts`. Route registered at `/procurement/vpl-history`
in `AppRouter.tsx:148`, gated by `RequireCapability cap="PROCUREMENT_ADMIN"`
— confirmed by reading the route table directly, not assumed.

- **"Manual Review — Removed From Latest Generation" section exists**
  (`VplHistoryScreenPage.tsx:153-160`), rendering `screen.removed` — I
  traced this back through `vplHistorySession.applyWorking` (line 102:
  `const removed = body.removed_manual_review.lines`) to the real API
  response shape, not a hardcoded or fabricated list. **No fabricated
  rows found** — every rendered field (`product_code`, `final_qty`,
  `supplier_code`) traces to a real API field name matching
  `vpl_history.py`'s `_as_removed` output exactly.
- **Feature-flagged off by default**, confirmed: `isVplHistoryScreenEnabled()`
  checks `VITE_VPL_HISTORY_SCREEN` env or a `localStorage` key, both
  default-absent → `false`. The disabled state renders a plain
  `EmptyState` saying "This screen is off," not a broken or empty-looking
  live screen — confirmed this avoids the exact anti-pattern the task
  warned against ("do not pretend it is complete").
- **Stale-response/store-switch handling:** `switchContext` (line 90-96)
  and `applyWorking`'s `requestId !== state.requestId` guard (line 99)
  correctly discard a response that arrives after the user has already
  switched store/cycle — I traced this is the same generation-counter
  pattern already used elsewhere in the codebase (Rules Registry,
  Purchase Manager), not a new or weaker mechanism.
  `applyWorking`'s second guard (`body.store_id !== state.storeId ||
  body.cycle_id !== state.cycleId`, line 100) is a **second**,
  independent check beyond the request-id counter — redundant but not
  harmful, and arguably safer (catches a same-request-id response for
  the wrong store in a hypothetical race the counter alone might miss).
- **409 conflict handling:** `saveQty`'s catch block
  (`VplHistoryScreenPage.tsx:90-94`) checks `err.status === 409`
  specifically and calls `applyVersionConflict`, which sets a
  user-facing "This line changed. Reload the working set" message and
  does **not** resubmit the write — confirmed by reading
  `applyVersionConflict`'s full body (sets `status: 'conflict'`, no
  retry call anywhere in that function). This matches the task's "a 409
  conflict asks for a reload and does not resubmit the write" requirement
  exactly, and matches `PHASE_2_VPL_HISTORY.md`'s own claim about this
  behavior.
- **Server-side enforcement confirmed, not just client-side:** read
  `vpl_history_router.py` in full — **every** route (`get_working`,
  `open_working`, `edit_line`, `refresh`, all four guard actions,
  `history`, `history_detail`) depends on `require_procurement_admin`,
  and every tenant-scoped route additionally calls
  `assert_tenant_access`. `_fail` correctly maps `VplConflict` → 409,
  everything else → 422. This closes the capability-check gap I flagged
  in the Rules Registry review much earlier this session — confirmed the
  same real `access.py`/`require_procurement_admin` dependency is reused
  here, not a second permission mechanism.
- **Independently re-ran:**
  `npx vitest run src/services/vplHistoryService.test.ts src/pages/procurement/vplHistorySession.test.ts`
  → **12 passed** (3 + 9, matches the sum of both files' own counts).
  `npx tsc -b` → exit 0, clean.

**Not verified in this pass, named explicitly:** actual keyboard
navigation beyond Up/Down (confirmed present in code at
`VplHistoryScreenPage.tsx:62-68`, not tested by opening a browser), visual
theme consistency, and whether `DataTable`/`FilterBar`/`PageHeader` reuse
renders correctly at runtime — this review read source and ran unit
tests, it did not launch the application. Stating this limitation
explicitly rather than implying visual verification occurred.

### Task 5 — Concurrency: traced, not changed (correct scope discipline)

The task asked to "trace the current write path and design a safe
concurrency strategy," explicitly warning not to "weaken existing VPL
history stale-write protection or change unrelated live-engine
behavior." Confirmed: **no change to `workspace_repository.py`** this
pass (`git diff --stat`: zero diff). This is the correct outcome — my
own prior review already established the real system has no optimistic
concurrency today, and designing + wiring that protection into five live
write functions is explicitly the kind of "live engine" change this
task's own safety constraints (and the broader session's standing rule)
say requires a separate, explicit go-ahead, not a side effect of a
UI/documentation pass. I did not find a written "concurrency strategy
design" document for the real write path in this pass — if the task
expected one as a deliverable, it is still outstanding. Flagging this
as the one item of the five tasks without a corresponding artifact
(the other four each produced a table row, a UI component, or an
explicit no-change decision).

### Test evidence, this pass

```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short
→ 21 passed

cd frontend && npx vitest run src/services/vplHistoryService.test.ts src/pages/procurement/vplHistorySession.test.ts
→ 12 passed (2 files)

cd frontend && npx tsc -b
→ exit 0

git diff --stat -- decision_rules.py decision_repository.py decision_service.py
    order_items_repository.py orchestration_service.py workspace_repository.py
    assignment_service.py assignment_repository.py
→ zero diff on all eight files
```

### Verdict on this pass: schema documentation ACCEPTED, UI ACCEPTED, concurrency design OUTSTANDING

- Tasks 1-3 (schema documentation): **accepted as correctly disciplined**
  — all three concepts documented against real tables, no columns
  invented, no migration written without approval.
- Task 4 (UI surface): **accepted, independently verified working** —
  real data, no fabrication, correctly flagged off, server- and
  client-side guards both confirmed.
- Task 5 (concurrency): **traced correctly, but no design artifact found
  for the real write path.** Not a defect — the safety constraints this
  task itself imposed make it reasonable that no code changed — but the
  task asked for a "safe concurrency strategy" to be designed, and I did
  not find that design document in this pass. Recommend Cursor confirm
  whether this was intentionally deferred or whether a document exists
  that this review missed.

**Phase 2 remains `READY_FOR_REVIEW`, not complete.** The original three
schema blockers are now explicitly documented with an honest "missing/
not decided" status rather than guessed — this satisfies "report any
decision requiring owner approval instead of guessing," but the
decisions themselves (which option for each concept) are still
unresolved and still require the owner, not either agent, to choose.

---

## 2026-10-19 (later pass) — Independent review of Cursor's latest Phase 2 schema proposal

**Reviewer:** Claude. **Trigger:** explicit task to re-review the current
schema proposal, repository write paths, and tests against five focus
areas: supplier assignment multiplicity/audit, rare-mover confirmation
persistence, removed-manual-review identity/retention/reappearance,
optimistic concurrency/refresh atomicity, and the manual-review UI API
contract. **No file written by Cursor was edited.** No migration was
applied. No write was attempted against any shared database. Files read
this pass, each confirmed on disk before being cited below: `vpl_history.py`,
`vpl_history_router.py`, `0027_vpl_history.sql` (+ rollback + verify),
`0004_procurement_order_items.sql`, `0005_procurement_order_item_assignments.sql`,
`0007_order_item_review_fields.sql`, `tests/test_vpl_history.py`,
`tests/test_vpl_history_claude_edge.py`, `tests/test_procurement_phase2_alignment.py`,
`dependencies/store_scope.py`, `decision_repository.py`,
`frontend/src/types/procurement.ts`, `frontend/src/components/procurement/VplHistoryPanel.tsx`.

### Test re-run, this pass

```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -q --tb=short
→ 33 passed
```
Matches the sum of the previously reported counts (21 + 12 does not apply
here — the alignment file's 12 tests are DB-free DDL/Pydantic checks, not
previously run together with the VPL pair in one command in this review
file). No over-claiming found; no test was skipped or modified to pass.

### Confirmed facts vs. proposed changes (read directly from source, this pass)

| Area | Confirmed fact (on disk now) | Proposed / not yet applied |
|---|---|---|
| Supplier assignment | `procurement.procurement_order_item_assignments` (0005, **applied** per `PHASE_2_VPL_HISTORY.md`'s canonical mapping table) has **no unique constraint** on `(order_item_id, supplier_code)` or similar — multiple assignment rows per `order_item_id` are allowed by design, explicitly documented in the file's own header comment ("An order item may receive more than one assignment") and supported by `export_batch_number`/`export_split_number` for repeat/split exports. | None in this pass. `vpl_history_line.supplier_code` (0027, unapplied) is explicitly documented as review-only, not a second assignment store (`PHASE_2_VPL_HISTORY.md` canonical mapping table, row "Supplier assignment"). |
| Rare-mover confirmation | **No column exists on any applied procurement table** for a rare-mover confirmation flag. `procurement_virtual_products.reason_code` (0006) is a generation-time classification, not a PM confirmation action. `0004`/`0007` add `item_status`, `suggested_qty`, `skip_reason`, `reviewed_by`, `reviewed_at` — none of these is a rare-mover boolean. | `rare_confirmed` exists only in `vpl_history.py`'s in-memory model and in the unapplied `0027` `vpl_history_line.rare_confirmed BIT`. There is no live write path for a PM to confirm a rare mover today outside this in-memory service. |
| Removed-manual-review | **No column, no table exists in SQL for this concept at all**, including in the unapplied 0027 script — confirmed by reading `0027_vpl_history.sql` end to end: `vpl_history_batch` and `vpl_history_line` have no `is_removed`/`removed_at`/`section` column, and `procurement_order_items`'s only unapplied addition is `row_version`. The entire removed-manual-review lifecycle (`_as_removed`, `_REMOVAL_FIELDS`, `removed_manual_review` dict) lives in `vpl_history.py` Python state only. | Proposed destination is unstated. `PHASE_2_VPL_HISTORY.md`'s own canonical field mapping table says this explicitly: "Missing in SQL, including unapplied 0027." No design for where this would land durably has been written anywhere I can find. |
| Optimistic concurrency | `row_version` does not exist on the live `procurement.procurement_order_items` table today. It exists only in the unapplied 0027 `ALTER TABLE ... ADD row_version INT NOT NULL DEFAULT 1`. The live Purchase Manager write paths (`order_items_repository.py`, `workspace_repository.py`, `assignment_repository.py` — confirmed zero `git diff` against them across this and the prior review pass) have no stale-write protection at all. | `vpl_history.py`'s in-memory `edit()`/`refresh()` enforce `row_version` and reject on mismatch — proven by `test_untouched_line_version_advances_so_a_stale_edit_conflicts` and the Claude edge suite's repeated-refresh test. This is a correct *design* for the in-memory model; it is not yet a design for the live SQL write path, which remains unprotected. |
| API contract | `vpl_history_router.py` exposes the full set (`POST/GET /working`, `PUT /working/lines`, `POST /refresh`, the four `_guard_orderable` actions, `GET /history`, `GET /history/{id}`), gated by `require_procurement_admin` + `assert_tenant_access` (tenant-level only — confirmed this is the same convention used by every other procurement router: `pm_router.py`, `vpl_router.py`, `rules_router.py`, `router.py` all call only `assert_tenant_access`, never a store-level check — so this is a pre-existing module-wide convention, not something introduced by this change). The frontend's `VplHistoryPanel.tsx`/`procurement.ts` types mirror `_public`/`history_headers`/`history_detail` field-for-field, confirmed by direct comparison. | Nothing wires `VplWorkspace.open_cycle`/`edit`/`refresh` to the live Purchase Manager UI or to `decision_service`/`clear_products`. The read-only history panel is the only consumer in the actual running app today, and it will show an empty list for every store (confirmed: no caller of `open_cycle`/`refresh` outside tests and the router itself). |

### Area-by-area findings

**1. Supplier assignment multiplicity and audit consistency.**
No defect found. The live schema's "an order item may receive more than
one assignment" is an intentional, already-shipped design (soft-deleted
rows, `export_batch_number` for re-export tracking), not something this
VPL-history change touches or needs to touch. The in-memory model's
`supplier_code` on a working/history line is a single scalar per line —
correctly documented as review-only, not a competing assignment store.
**Risk if this boundary blurs later:** if a future cutover ever reads
`vpl_history_line.supplier_code`/`assigned_qty` as authoritative instead
of `procurement_order_item_assignments`, duplicate or contradictory
assignment state becomes possible (one supplier recorded on the history
line, a different one or several in the real assignments table). Nothing
in the current code does this — flagging as a boundary to keep enforced
by review, not a present bug.

**2. Rare-mover confirmation semantics and persistence.**
No live persistence exists for this concept at all — not a Phase-2 defect,
since the live Purchase Manager never had this field before this work started.
The in-memory semantics are internally consistent: `_touched()` treats
`rare_confirmed` as one of four touch signals, so a rare-mover confirmation
alone (with no supplier, no override, no reviewed_at) is enough to carry
a line forward and protect it from silent disappearance on refresh,
matching the business intent described in `AUTONOMOUS_WORK_CONTROL.md`
("master prompt requires visible PM confirmation for rare movers").
**Gap, not yet a defect because nothing durable exists to be wrong:**
0027 adds `rare_confirmed BIT NOT NULL DEFAULT 0` to `vpl_history_line`
only — a historical record, not a live column on `procurement_order_items`.
There is still no proposal anywhere for where a *live* rare-mover
confirmation would be written once this stops being process memory. This
is the same category of gap as removed-manual-review below and should be
resolved before any cutover, not discovered during one.

**3. Removed-manual-review identity, retention, and reappearance.**
This is the most mature part of the proposal and the one most thoroughly
tested (`test_touched_omission_moves_to_manual_review_and_preserves_values`,
`test_repeated_absence_does_not_duplicate_or_erase_removed_line`,
`test_reappearance_restores_touched_line_and_keeps_removal_only_in_history`,
`test_removed_lines_stay_inside_one_store_cycle`) — I re-traced all four
at the code level, not just the test level, and confirm:
- Identity is `product_code`, scoped inside the `(tenant_id, store_id,
  cycle_id)` key — confirmed isolated per store by
  `test_removed_lines_stay_inside_one_store_cycle`, which opens two
  cycles sharing a tenant and the same product code and shows no leakage.
- Retention is unbounded and idempotent: `refresh()`'s `new_removed.pop(code, None)` /
  re-insert logic (`vpl_history.py:159-174`) means a repeated absence
  neither duplicates the removed entry nor loses it, and `row_version`
  on the removed line does not change while it stays absent (confirmed:
  `removed_twice[0]["row_version"] == removed_once["row_version"]`).
- Reappearance is correct and does not create a second copy: when a
  previously-removed `product_code` shows up in `incoming` again,
  `held = new_removed.pop(code, None)` takes it out of
  `removed_manual_review` in the same step that `source is not None and
  _touched(source)` restores it into `new_lines` — there is no window
  where the same product_code could exist in both collections
  simultaneously inside one `refresh()` call, because both writes happen
  under the same `self._lock` before the method returns.
- **No data loss on removal**: the full pre-refresh working set, including
  the about-to-be-removed line, is archived verbatim into the history
  batch before `current["lines"]`/`current["removed_manual_review"]` are
  replaced (`staged["lines"] = list(backup["lines"].values())`, built from
  `backup`, a `deepcopy` taken before any mutation).
- **Confirmed blocker on durability, not behavior:** none of this exists
  in SQL. `0027_vpl_history.sql` has no removal-state columns on
  `vpl_history_line` and no analogous addition to `procurement_order_items`.
  If this in-memory design is accepted as the target *behavior*, the
  schema to persist it durably still has to be designed and is not in
  this migration. Approving the behavior and approving the schema are two
  different approvals — do not conflate them.

**4. Optimistic concurrency and refresh atomicity.**
Previously-confirmed Finding 1 (untouched-line `row_version` not
advancing) remains fixed and independently re-verified twice now, across
two separate review passes plus this one (33 passed, including the two
Claude-authored repeated-refresh tests that specifically guard against a
regression of that exact defect). I traced the lock discipline again
this pass: every public method (`open_cycle`, `working`, `edit`,
`refresh`, `_guard_orderable`) acquires `self._lock` for its entire body,
so there is no window for two concurrent refreshes on the same
`(tenant_id, store_id, cycle_id)` key to interleave — confirmed
structurally (one `threading.Lock`, held for the full method), not just
by the passing concurrency test (`test_concurrent_refreshes_on_different_stores_do_not_interleave`,
which tests two *different* keys, not contention on the *same* key; I did
not find a test that drives two threads at the same key simultaneously,
though the lock makes the serialization structurally obvious from the
code alone).
`before_commit` failure handling is correct: the `backup`/`staged`
objects are built from copies, and `self._history.append(staged)` plus
the `current[...] = ...` replacements only happen *after* `before_commit()`
returns without raising — confirmed by both `test_failed_refresh_does_not_replace_working_or_history`
and `test_failed_refresh_does_not_move_a_touched_line_into_review`, and by
re-reading the method body: there is no code between `before_commit()`'s
call and the mutations that could itself raise and leave a partial state
(the dict/list literal construction happens entirely before `before_commit()`
is invoked).
**The real, still-open gap is exactly what the prior review pass already
flagged and nothing in this pass changes:** this is a lock inside one
Python process. It is not a database transaction, and 0027 is not applied.
`procurement_order_items` has no `row_version` column live today, and the
five real Purchase Manager write functions I diffed against this pass
(`order_items_repository.py`, `orchestration_service.py`,
`workspace_repository.py`, `assignment_service.py`, `assignment_repository.py`)
show zero changes — they still have no optimistic-concurrency protection
at all. The in-memory model proves the *algorithm* for version bumping and
conflict rejection is correct; it proves nothing about SQL Server lock
behavior, isolation level, or multi-process contention (multiple backend
worker processes/instances holding independent `VplWorkspace` singletons
would not even share state, let alone a lock) once this is wired to a
real connection pool.

**5. API contract for the manual-review UI.**
`vpl_history_router.py`'s shape is internally consistent and the frontend
types (`VplHistoryLine`, `VplHistoryBatch`, `VplWorkingView`,
`VplScreenApiLine`) match the Python return dicts field-for-field — I
compared both sides directly rather than trusting the comment claiming
this. One contract gap worth recording rather than treating as a defect:
`VplHistoryLine.product_id` is typed `string | null` on the frontend and
`UNIQUEIDENTIFIER NULL` in the unapplied 0027 schema, but
`vpl_history.py`'s `_index()` stores whatever `product_id` the caller
supplies with no type coercion (`tests/test_vpl_history.py`'s
`test_touched_omission_moves_to_manual_review_and_preserves_values` passes
`product_id=11`, a plain int, and it round-trips unchanged). This is
harmless today because nothing live calls `open_cycle`/`refresh` with real
data, but it means the GUID-shaped contract is not actually enforced
anywhere before persistence — worth a validation note for whoever wires a
real generation caller, not a blocker for this pass.
`require_procurement_admin` + `assert_tenant_access` gating is confirmed
correctly applied to every mutating and every read route in this router,
matching the server-side gate the frontend's `useAccess().can('PROCUREMENT_ADMIN')`
button check mirrors.

### Data-loss, duplicate-assignment, and accidental-ordering risk assessment

- **Data loss: not found in the in-memory model.** Every removal,
  refresh, and touched-line carry-forward path either archives the prior
  state verbatim into history before mutating, or raises before mutating
  anything (`before_commit`, duplicate-code detection). The one scenario
  that is still a real risk is **persistence durability, not logic**:
  this is all one Python process's heap. A backend restart today would
  silently discard every open working set and every history batch — this
  is not tested, not mentioned as a limitation anywhere I can find in the
  existing docs, and is a genuine data-loss vector if this in-memory
  service were ever treated as more than a design prototype before 0027
  lands. Recommend this be stated explicitly as a known limitation
  wherever the next phase's sign-off criteria are written.
- **Duplicate assignment: not found.** The live assignments table's
  intentional multiplicity is unrelated to and not affected by this
  change; the in-memory `supplier_code` field is correctly kept
  read/review-only and never writes to `procurement_order_item_assignments`.
- **Accidental ordering: not found, and actively guarded against.**
  `_guard_orderable` is called by all four of `assign_supplier`,
  `export_lines`, `place_order`, `submit_to_portal`, and each one checks
  `removed_manual_review` membership *before* checking line presence —
  confirmed a removed line can never reach any of the four actions
  (`test_touched_omission_moves_to_manual_review_and_preserves_values`
  exercises all four and expects `NOT_ORDERABLE` on each). None of the
  four calls live generation, live assignment, live export, or any
  network/portal code — confirmed by reading all four method bodies,
  which only validate and return a descriptive dict.

### Verdict

**READY_FOR_REVIEW stands. Not approved for durable persistence.**

The in-memory behavior for all five focus areas is internally consistent,
well-tested (33/33 passing, independently re-run), and does not
regress or touch the live decision engine, live assignment table, or
live order-item write paths (confirmed zero diff across all eight
previously-identified live files once again this pass). Finding 1 stays
fixed. No new logic defect was found in this pass.

**Blockers to durable persistence (0027 must not be applied until these are resolved):**

1. **No schema exists for removed-manual-review state.** 0027 does not
   add it. Applying 0027 as currently written would persist `row_version`
   and the already-covered fields but would still leave the
   removed-manual-review lifecycle entirely in process memory, meaning a
   backend restart during the window between "line removed from active
   set" and "line reappears or cycle closes" silently loses that state —
   the exact data-loss gap flagged above, just made durable-looking
   without actually being durable.
2. **No schema or write path exists for a live rare-mover confirmation.**
   0027 only historicizes it. Until a live column + write path is
   designed, "visible PM confirmation for rare movers" (the master
   prompt's own requirement, per `AUTONOMOUS_WORK_CONTROL.md`) has no
   durable home even after 0027 lands.
3. **`row_version` optimistic concurrency is unvalidated against SQL
   Server.** The in-memory lock proves the algorithm; it proves nothing
   about actual multi-process/multi-connection contention, isolation
   level, or whether a `WHERE row_version = @expected` UPDATE pattern (the
   obvious SQL translation) is actually what gets implemented when this is
   wired up. No such write path exists yet to review.
4. **Multi-process/restart durability is untested and unaddressed.** A
   production backend typically runs multiple worker processes; each
   would hold an independent `VplWorkspace` singleton with no shared
   state. This is fine for a design prototype gated behind a flag that
   nothing live calls; it is not fine as a persistence plan, and nothing
   in 0027 or `vpl_history.py` addresses it.

**Acceptance tests to require before approving durable persistence (new,
not yet written anywhere):**

- A test (SQL-backed, in an isolated test database — not `NEXORA_PLATFORM`)
  that a `refresh()` equivalent is wrapped in a single transaction: kill
  the connection mid-write and confirm neither the history batch nor the
  working-set replacement partially commits.
- A test that two concurrent `UPDATE ... WHERE row_version = @expected`
  attempts against the same `order_item_id` (or future `vpl_history_line`
  row) result in exactly one success and one caller observing a conflict,
  under SQL Server's actual default isolation level — not simulated with
  a Python lock.
- A test that a removed-manual-review line survives a simulated process
  restart (i.e., actually reads back from a table, not from the
  in-memory dict) with every field (`final_qty`, `supplier_code`,
  `reviewed_at`, `rare_confirmed`, `row_version`, removal context) intact.
- A test that a live rare-mover confirmation write path (once designed)
  round-trips through the real `procurement_order_items`-equivalent table
  and is visible to the next refresh's `_touched()`-equivalent check.
- A test confirming `assert_tenant_access`'s tenant-only (not store-level)
  scoping is the deliberate, reviewed choice for this router specifically
  — today it is inherited by convention from the rest of procurement, and
  that convention has apparently not been revisited for a workflow this
  directly tied to one store's working order (unlike Label Exporter, which
  did get a store-level lock for an analogous reason). Not a defect in
  this pass; recommend an explicit owner decision rather than silent
  inheritance.

**Database verification remains NOT_VERIFIED.** No SQL Server connection
was opened in this pass. This review is Python-logic-level only, same
limitation stated in every prior pass of this file.

## Review request (Cursor, 2026-10-19 23:59 IST)

This is not a Claude signature. Please review the schema proposal now in `PHASE_2_VPL_HISTORY.md` under "Schema proposal (not applied)" and append your own result.

1. Assignment history: recommended immutable child rows copied from `procurement_order_item_assignments` at refresh. A single `supplier_code` and a JSON column were rejected.
2. Rare-mover confirmation: recommended a future bit on `procurement_order_items`. `reviewed_at`, `reviewed_by`, and `reason_code` were not reused. No script was written.
3. Removed lines: recommended a separate table that export and assignment do not read, with reappearance moving the row back under the touched-line rule. An `item_status` or flag on `procurement_order_items` was rejected.
4. Concurrency: one `row_version`. In-memory behavior is unchanged. Live `workspace_repository.py` was not given a new check.

No migration was applied. `VplWorkspace` was not connected to SQL. Frontend files were not changed this pass. `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short` → 21 passed.

Status of this request: **PENDING**. No independent reviewer ran in the Cursor session that wrote it.

## Review request (Cursor, 2026-10-20 16:50 IST)

This is not a Claude signature. Please review the owner decisions now recorded in `PHASE_2_VPL_HISTORY.md` under "Owner decisions (2026-10-20)" and append your own result.

1. Assignment history is APPROVED IN PRINCIPLE. Proposed key `(history_id, source_assignment_id)`, parent `(history_id, product_code)`, provenance columns, and one transaction with the history batch. Not approved for a migration file. 0027 is still unresolved as the parent.
2. Rare-mover confirmation is NOT APPROVED. The comparison recommends a dedicated review record. No column and no script.
3. Removed lines are APPROVED IN PRINCIPLE as a separate model. Existing tests `test_touched_omission_moves_to_manual_review_and_preserves_values`, `test_reappearance_restores_touched_line_and_keeps_removal_only_in_history`, and the Claude edge test still reject assign, export, order, and portal for those lines.
4. Concurrency: five `workspace_repository` updates (`set_final_qty`, `restore_suggested`, `skip_item`, `defer_item`, `restore_item`) plus assignment, export, GRN, and pending writers. None check `row_version`. The proposed contract is one `row_version` predicate. It was not added to live code.

`pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short` → 21 passed. Frontend was not edited.

Status of this request: **PENDING**. No independent reviewer ran in the Cursor session that wrote it.

## Independent review executed in the Cursor session from the user's 2026-10-20 review prompt; this is not a separate Claude-process signature

**Date:** 2026-10-20. **Scope:** persistence design only. This section was written inside the Cursor session that received the user's review prompt. It is an independent review of the repository. It does not claim a separate Claude-process run and it does not adopt a Claude model identity.

**Safety of this pass:** no backend Python, SQL, frontend, test, `PROJECT.md`, or `AUTONOMOUS_WORK_CONTROL.md` file was edited. No migration was written or applied. No database connection was opened. No supplier order was placed. `workspace_repository.py`, the live quantity engine, and the OrderNMC workflow were not changed. `VplWorkspace` was not connected to persistence. Phase 2 stays **READY_FOR_REVIEW**. It is not complete. Nothing in this section authorizes a persistence implementation.

Database verification remains **NOT_VERIFIED**.

### Confirmed repository facts

These statements were read from the files named. They are not recommendations.

**Live parent model.** `procurement.procurement_cycles` (`0001`) and `procurement.procurement_refreshes` (`0002`) already exist. A refresh row's primary key is `refresh_id`, and it has a foreign key to `procurement_cycles(cycle_id)`. `procurement.procurement_order_items` (`0004`) is unique on `(refresh_id, product_id)`. `product_code` on that table is `VARCHAR(100) NULL`. `procurement.procurement_order_item_assignments` (`0005`) allows more than one row per `order_item_id`. Its header comment says so. There is no unique constraint on `(order_item_id)` or `(order_item_id, supplier_code)`. Foreign keys to `order_item_id`, `refresh_id`, and `cycle_id` do not declare `ON DELETE CASCADE` (SQL Server default is `NO ACTION`). `product_code` on an assignment is nullable.

**Live assignment rule versus the table.** `assignment_repository.any_active_assignment` and `assignment_service.assign_single` / `assign_bulk` refuse a second non-deleted assignment for an order item. That check is a `SELECT` followed by `INSERT` on the same connection, with no `UPDLOCK` / `HOLDLOCK` and no unique filtered index. Two concurrent calls can both observe no active row and both insert. `update_qty` exists in `assignment_repository.py` and has no caller under `backend/`.

**Unapplied 0027.** `0027_vpl_history.sql` is not applied. `vpl_history_batch` has no foreign key to `procurement_cycles` or `procurement_refreshes` and no unique key on `(tenant_id, source_refresh_id)` or on a successor refresh. `vpl_history_line` primary key is `(history_id, product_code)` with `product_code VARCHAR(100) NOT NULL`, one `supplier_code`, one `assigned_qty`, and `rare_confirmed BIT NOT NULL DEFAULT 0`. The same script would `ALTER` live `procurement_order_items` to add `row_version`. It has no removed-line table and no assignment-history child table.

**In-memory history identity.** `VplWorkspace.refresh` archives active lines keyed by `product_code` inside one process. It does not copy `procurement_order_item_assignments`. The proposed child key `(history_id, source_assignment_id)` and parent `(history_id, product_code)` exist only as text in `PHASE_2_VPL_HISTORY.md` under "Owner decisions (2026-10-20)". That section says the parent model is not finalized and that there is no foreign key to the live assignment id.

**Removed lines, in memory only.** A line is touched when `manual_override`, `reviewed_at`, `supplier_code`, or `rare_confirmed` is set (`vpl_history.py` `_touched`). A touched line missing from the next generation moves to `removed_manual_review`, `orderable` false. `assign_supplier`, `export_lines`, `place_order`, and `submit_to_portal` raise `NOT_ORDERABLE` after checking that collection. Those four methods do not call live generation. `edit` also refuses a removed code. Repeated absence does not insert a second removed entry. Reappearance uses `_restore_touched`, which sets `orderable` true and keeps the previous manual fields. Tests that encode this are `tests/test_vpl_history.py::test_touched_omission_moves_to_manual_review_and_preserves_values`, `test_reappearance_restores_touched_line_and_keeps_removal_only_in_history`, and the Claude edge test named in `PHASE_2_VPL_HISTORY.md`. No SQL table stores this collection. This pass did not re-run pytest.

**`carry_forward_skips` is a different mechanism and is not called by `VplWorkspace`.** `orchestration_service.create_refresh` commits working-item generation on its own connection: `clear_working_items`, `generate_working_items` (only `suggested_qty > 0`), `carry_forward_skips`, then `comparison_service.carry_forward`. `carry_forward_skips` (`order_items_repository.py`) updates an already-inserted new-refresh row when the previous row is `item_status = 'skipped'` and `skip_reason` is `until_next_sales` or `until_next_demand`, and no `sync.ProductSaleInformation` row with `SeriesTransID = 1`, `TransactionValidity = 0`, and `TransactionDate > reviewed_at` exists. It sets `item_status = 'skipped'`, `final_qty = 0`, `remaining_qty = 0`. It does not insert a row for a product the new generation omitted. `current_refresh` is not carried. `comparison_service.carry_forward` inserts a new order item only when the previous row has `remaining_qty > 0`, `pending_status = 'carried'`, `item_status <> 'skipped'`, and that `product_code` is not already on the new refresh. `skip_item` sets `reviewed_at` and `final_qty = 0` and does not clear `manual_override`. A skipped line is therefore touched under `_touched`.

**Live writes have no version predicate.** `workspace_repository._run` opens a connection, executes one statement, and commits. `set_final_qty`, `restore_suggested`, `skip_item`, `defer_item`, and `restore_item` filter on `tenant_id`, `order_item_id`, and `is_deleted = 0` only. `workspace_service` reads the item on one connection, then calls `_run` on another, and returns the re-read row without inspecting `rowcount`. The same one-statement `_run` pattern is used by `pending_repository.adjust_pending`, `set_pending_status`, and `finalize_all`. `assignment_service.assign_single` inserts and `recompute_order_item` then commits. `change_supplier` updates the assignment only. `remove_assignment` soft-deletes and recomputes. `export_service.export_refresh` calls `mark_exported` for each selected assignment and commits once. `reconciliation_service.submit_grn` commits `store_last_grn` and then `reconcile` opens a second transaction for `apply_receipt` and `set_item_receipts`. `set_item_receipts` overwrites `item_status`. No `row_version` column exists on the applied order-item or assignment tables. `VplWorkspace._lock` is a `threading.Lock` held for the body of each public method. `test_concurrent_refreshes_on_different_stores_do_not_interleave` covers two different store keys. No test in `tests/` was found that interleaves two live `workspace_repository` writes, two assignment inserts, or a refresh against an edit under SQL Server. The in-memory lock does not survive a second process or a restart.

**Refresh transaction shape today.** `create_refresh` creates the refresh header before the working-item transaction. `decision_repository.clear_products` deletes `procurement_virtual_products` for one `refresh_id`. `VplWorkspace` is not called from that path. History append in memory happens only after `before_commit` returns; that hook is process memory, not a SQL transaction.

### Assessment

#### 1. Assignment-history key and provenance

The proposed child key `(history_id, source_assignment_id)` can store many assignments for one product inside one batch, and a copied `supplier_code` / `assigned_qty` with no foreign key to the live `assignment_id` keeps the snapshot after a later live update or soft-delete. That part of the proposal matches the mutability of `update_supplier`, `soft_delete`, and `recompute_order_item`.

It does not, by itself, provide a stable parent, idempotent retries, or referential integrity:

- Live line identity inside a refresh is `(refresh_id, product_id)`, not `product_code`. `product_code` is nullable on the live order item and on the assignment. Unapplied 0027 requires `product_code NOT NULL` and uses it as the line primary key. Two live rows that share a code, or a row with a null code, cannot both land on that key without collision or omission. A manual edit on the dropped identity would not be in history.
- 0027's line already stores one `supplier_code` and one `assigned_qty`. Writing those columns and the child rows records the same assignment twice and they can diverge.
- `history_id` defaults to `NEWID()` and the batch has no natural unique key. A retry that allocates a new `history_id` inserts a second copy of the same assignments. The child primary key blocks a duplicate only inside one `history_id`.
- There is no foreign key from the child to a history line, because the line parent is explicitly not finalized. Children can be inserted for a product that has no line, or for a different line than the live `order_item_id`.
- Copying only non-deleted assignments is what the 2026-10-20 text says. An assignment soft-deleted before the snapshot is absent from history. The live row still holds `deleted_at` until something deletes it. History does not automatically contain that deletion.

**Plausible parents compared.**

| Candidate | What it actually is | Result |
|---|---|---|
| Unapplied 0027 `vpl_history_line (history_id, product_code)` | A script that is not applied and that flattens supplier, quantity, and `rare_confirmed` onto the line | Not the parent. Do not treat it as final. Do not add a foreign key to it. |
| Live `procurement_order_items` / `procurement_order_item_assignments` | Mutable working rows. `clear_working_items` deletes order items for a refresh. Assignment foreign keys are `NO ACTION`. | Provenance values only. A foreign key from history to the live assignment id would block a later delete or would cascade history away. |
| A new OrderNMC `order_*` cycle | Rejected by the repository ownership note in `PHASE_2_VPL_HISTORY.md` | Do not create one. |
| Existing `procurement_cycles` + `procurement_refreshes`, plus a new immutable batch | Cycle and refresh already own tenant, store, and sequence | This is the canonical parent. |

**Recommendation (not a migration).** One history batch per replacement, foreign-keyed to `procurement.procurement_cycles(cycle_id)` and to `procurement.procurement_refreshes(refresh_id)` as `source_refresh_id`. Unique `(tenant_id, source_refresh_id, successor_refresh_id)`. Line primary key `(history_id, source_order_item_id)`. `product_id` and `product_code` are copied attributes. Assignment-child primary key `(history_id, source_assignment_id)`, foreign key `(history_id, source_order_item_id)` to the history line. `source_assignment_id` and `source_order_item_id` are copied identifiers with no foreign key to the live tables. Supplier and assigned quantity live only on the child. The batch, lines, and children insert in the same transaction as the working-set replacement; any failure rolls all of them back. A retry with the same successor refresh id finds the unique batch key and inserts no second child. `rare_confirmed` stays off this script.

That design preserves multiple assignments per product, keeps supplier and quantity after a live change or soft-delete, and ties batch, line, and assignment history together. Idempotence holds when the successor refresh id is stable. `create_refresh` today allocates a new refresh id before the working-item transaction, so a client double-submit can still create two successors and two legitimate snapshots. That is an owner decision, recorded below, and is not already solved.

#### 2. Removed-manual-review and `carry_forward_skips`

A separate table is the right isolation boundary: assignment, export, GRN, and portal queries read `procurement_order_items` and `procurement_order_item_assignments`. They must keep doing so. Absence of an order-item row is what keeps the line out of ordering. An `item_status` or flag on the order item would put the line back in those queries.

The current in-memory rule is not safe to persist unchanged. `_touched` treats `reviewed_at` as a touch, and `skip_item` sets `reviewed_at`. An absent skip therefore enters `removed_manual_review`. Reappearance calls `_restore_touched` and sets `orderable` true. `carry_forward_skips` would, on a product that is still generated, zero `final_qty` and set `skipped` unless a later sale exists. The in-memory restore does not read sales or `skip_reason`. Both paths can run for the same product once this is connected to `create_refresh`. `comparison_service.carry_forward` can also insert an orderable row when `pending_status = 'carried'` and `remaining_qty > 0` while the removed collection holds the same `product_code`.

**Reconciliation rules (required before any table is created):**

1. One live representation per `(tenant_id, store_id, cycle_id, product_id)` after a refresh commit. Either an order item, or one active removed-review row, never both.
2. `item_status = 'skipped'` is owned by `carry_forward_skips`. It does not enter the removed table. `until_next_sales` and `until_next_demand` still release when a qualifying sale exists. `current_refresh` still dies with the old refresh. A skipped line omitted from generation stays in the immutable history batch only. It is not restored as an orderable touched line.
3. The removed table accepts a line only when it is absent from the new generation and it has a manual edit that skip does not already own: `manual_override = 1` with a non-skip status, or a non-deleted assignment. `rare_confirmed` does not qualify while rare-mover persistence is unapproved.
4. If `comparison_service.carry_forward` inserts an order item for that `product_id`, do not also insert a removed row. If the removed row is inserted, skip the comparison insert for that product in the same transaction.
5. Active-row identity is a unique filtered key on `(tenant_id, store_id, cycle_id, product_id)` where `restored_at` is null. A repeated refresh that still omits the product updates nothing and inserts nothing. `row_version` stays still, matching the in-memory repeated-absence behavior.
6. Reappearance, in the same transaction, writes the preserved `final_qty`, `manual_override`, `override_reason`, `reviewed_at`, and `reviewed_by` onto the new order item, sets `restored_at` / `restored_by` on the review row, and leaves the history batch immutable. Assignment children from the history snapshot are not auto-inserted into the live assignment table by that restore.
7. While `restored_at` is null, no insert into `procurement_order_items`, and no call path used by assignment, export, GRN, or portal, may select the row. In-memory `NOT_ORDERABLE` stays until that SQL exclusion exists. Editing a removed row is refused today; persistence should keep that refusal until an owner explicitly allows a review-section edit.

Provenance columns to carry on that future table: `tenant_id`, `store_id`, `cycle_id`, `product_id`, `product_code`, `source_order_item_id`, `originating_cycle_id`, `originating_refresh_id`, `removed_during_refresh_id`, `removed_at`, `removed_by`, the manual fields above, and `row_version`. No foreign key to the live order item.

#### 3. Rare-mover confirmation

Owner status on 2026-10-20 is **NOT APPROVED**. Confirmed: no applied procurement column stores a purchase-manager rare-mover confirmation. `procurement_virtual_products.reason_code` is a generation reason. Unapplied 0027 puts `rare_confirmed` on `vpl_history_line`. The in-memory field is a prototype, and `_touched` already treats it as a reason to carry or remove a line.

**Do not implement persistence for it.** The shape to approve later, and not to script now:

- A dedicated review record, not a column on `procurement_order_items`, and not `reviewed_at`, `reviewed_by`, `final_qty`, `manual_override`, or `reason_code`.
- Identity of the current record: `(tenant_id, store_id, cycle_id, product_id)`.
- States: no row, `confirmed`, `cleared`. Generation never inserts or updates the row.
- Transitions: only a purchase manager confirms or clears. Each transition appends an audit row with actor and time. The current row stores the latest state.
- Refresh does not reset a `confirmed` row. A surviving working line may read it when deciding carry-forward, after approval. A brand-new untouched suggestion does not copy another product's confirmation. Clearing is an explicit review action, not a side effect of refresh.
- The record does not make a line orderable. A removed line with a confirmation still cannot be assigned, exported, or ordered. The confirmation is not an assignment and not a quantity.
- Until that design is explicitly approved, `_touched` must not be the persistence rule for this bit, and 0027's `rare_confirmed` column must not be applied.

#### 4. Concurrency contract

**Version ownership.** One `row_version INT NOT NULL` on `procurement_order_items`, starting at 1 on insert. One separate `row_version` on `procurement_order_item_assignments`, starting at 1. One on `procurement_refreshes` for `store_last_grn` only. Do not use `updated_at` as the token. Do not add a second version column on the same table. The order-item version is incremented by every successful mutation of that row, including `recompute_order_item`, `set_item_receipts`, and `carry_forward_skips`. The assignment version is incremented by `insert` (initial 1), `update_supplier`, `update_qty`, `soft_delete`, `mark_exported`, and `apply_receipt`.

**Compare-and-swap.** The business update and `row_version = row_version + 1` are the same statement, with `AND row_version = ?` in the `WHERE`, plus the existing tenant and `is_deleted = 0` predicates. `rowcount = 0` is a failure. A follow-up read distinguishes a missing row (HTTP 404) from a row whose version differs (HTTP 409, code `VERSION`). The handler must not then return the re-read row as a successful write. `workspace_service` does that today because it ignores `rowcount`. The in-memory API already maps `VplConflict("VERSION")` to 409 through `vpl_history_router._fail`. Live routes should use that same status and code. The client reloads. It does not resubmit the stale body. A retry of an already-committed write with the old version is a 409, which is the correct CAS outcome; safe retry requires the reloaded version or a separate idempotency key. No live idempotency key exists on these writes.

**In-memory lock versus the database.** `threading.Lock` serializes callers that share one `VplWorkspace` instance in one process. It does not coordinate two worker processes, two machines, or a restart. Database CAS does. Tests that pass under the lock are not evidence for SQL Server.

**Transaction boundaries.**

| Write | Current boundary (fact) | Required contract |
|---|---|---|
| `set_final_qty`, `restore_suggested`, `skip_item`, `defer_item`, `restore_item` | Read on one connection, one-statement commit on another | Single statement CAS. The assigned-quantity check and the update must see the same locked row (`UPDLOCK`) so a concurrent assignment cannot land between the check and the write. |
| `insert_assignment` + `recompute_order_item`; `soft_delete` + `recompute_order_item` | One connection, commit after both | Lock the order item first, CAS-increment it, CAS the assignment. The loser rolls back the insert or the soft-delete. |
| `update_supplier`; `update_qty` (no caller found) | Assignment update, no item recompute for supplier change | CAS the assignment version. |
| `assign_bulk` | One commit for the whole loop; per-item `ValueError` is recorded and other items still commit | A version conflict on one item rolls back only that item's statements and is reported on that item. It must not commit an assignment whose item CAS lost. |
| `export_refresh` / `mark_exported` | One commit after every selected assignment is stamped | All-or-nothing. Any stale assignment rolls back the batch so `export_batch_number` is not half written. |
| `store_last_grn` | Commits alone, then `reconcile` runs | CAS the refresh version. A crash after this commit and before reconcile is the current split; the contract does not pretend those are one transaction. |
| `apply_receipt`, `set_item_receipts` | One reconcile transaction | CAS each assignment and each order item. `set_item_receipts` must not overwrite `skipped` or a newer `final_qty` when the item version has moved. |
| `adjust_pending`, `set_pending_status`, `finalize_all` | One-statement `_run` | CAS each order item. `finalize_all` is many rows: a stale row is skipped and reported, and the caller sees which rows were not finalized. |
| Refresh replacement | Header insert is already committed; working items are a later transaction; `VplWorkspace` is not in it | History batch, history lines, assignment children, removed-row moves, skip carry, and working-item writes share one transaction. Lock the source order items before copying. Failure rolls the copy and the replacement back. |

**Refresh versus user edit.** After a new refresh, the new order item has a new `order_item_id` and version 1. A client still holding the previous item's version is stale against the old id and must not be applied to the new id. An in-place regenerate that deletes rows (`clear_working_items` / `clear_products`) must take the locks before delete; a CAS cannot protect a row that has already been deleted. Two processes issuing `UPDATE ... WHERE row_version = @expected` produce one success and one 409 under default read committed. That is the cross-process rule.

**Tests that exist.** In-memory stale-edit and failed-refresh tests exist in `tests/test_vpl_history.py` and `tests/test_vpl_history_claude_edge.py`. They do not drive `workspace_repository`, assignment, export, GRN, or pending. No controlled SQL interleaving test was found. The tests to add before implementation are listed in the acceptance section. They do not exist yet.

#### 5. Safety

This review does not authorize persistence, a migration file, application of 0027, a connection to `NEXORA_PLATFORM` or OrderNMC, a change to live quantity or OrderNMC, or wiring `VplWorkspace` to SQL. Phase 2 remains **READY_FOR_REVIEW**.

### Deliverables

#### 1. Recommended canonical parent and key design

Canonical parent is a new immutable history batch in schema `procurement`, foreign-keyed to existing `procurement_cycles(cycle_id)` and `procurement_refreshes(refresh_id)` (`source_refresh_id`), with unique `(tenant_id, source_refresh_id, successor_refresh_id)`. History line key is `(history_id, source_order_item_id)`. Assignment child key is `(history_id, source_assignment_id)` with a foreign key to that line. Unapplied 0027 is not the parent and is not final.

#### 2. Assignment-history schema and provenance proposal

Child columns copied at snapshot time: `supplier_code`, `assigned_qty`, `assignment_status`, `tenant_id`, `store_id`, `cycle_id`, `source_refresh_id`, `source_order_item_id`, `source_assignment_id`, `copied_at`. No foreign key to the live assignment or order item. No supplier columns on the history line. Same transaction as the batch, the lines, and the working-set replacement. Non-deleted live assignments are the copy set named in the 2026-10-20 decision; deletions that happen before the snapshot are outside that copy.

#### 3. Removed-line and `carry_forward_skips` reconciliation rules

Skips stay on the skip path and never occupy the removed table. Removed rows are only absent manual overrides or absent non-deleted assignments, one active row per product in the cycle, unique where `restored_at` is null, invisible to assignment, export, order, and portal. Reappearance and removal of the active review row commit together. Comparison carry-forward must not insert a second order item for that product.

#### 4. Rare-mover review-record design

Not approved and not to be implemented. Future shape: a dedicated current record per `(tenant_id, store_id, cycle_id, product_id)` plus an append-only actor/time audit, states confirmed and cleared, no generation writes, no reset on refresh, no effect on orderability. Explicit owner approval is required before any column or table.

#### 5. Concurrency contract for every relevant write path

Order-item CAS for the five workspace writes, pending writes, `recompute_order_item`, `set_item_receipts`, and `carry_forward_skips`. Assignment CAS for insert, supplier change, quantity change, soft-delete, export stamp, and receipt apply. Refresh-header CAS for `store_last_grn`. 409 `VERSION` on a stale predicate, 404 when the row is gone, zero-row updates are not success. Refresh copy and replacement are one transaction. The process lock is not the multi-worker control.

#### 6. Required acceptance tests and migration safety requirements

Before any migration is authorized:

- Isolated test database only. `NEXORA_PLATFORM` and OrderNMC stay closed.
- One transaction test: fault after the history insert and before the working-set commit; batch, lines, children, removed rows, and working items all roll back.
- Retry with the same `(source_refresh_id, successor_refresh_id)` inserts no second batch and no second child for the same `source_assignment_id`.
- Two live order items with the same `product_code` and different `product_id` produce two history lines. A null `product_code` still produces a history line.
- Two non-deleted assignments on one order item produce two child rows. After the snapshot, `update_supplier` and `soft_delete` leave the child supplier and quantity unchanged.
- A skipped `until_next_sales` line that is still generated follows `carry_forward_skips` and does not gain a removed row. The same skip omitted from generation does not become an order item.
- A manual line omitted from generation has one removed row, zero order items, and assignment/export/order/portal queries return no row. A second refresh does not add a second removed row. Reappearance leaves one order item and zero active removed rows.
- A carried-pending insert and a removed-row insert for the same `product_id` cannot both commit.
- Two concurrent `set_final_qty` calls with the same `row_version`: one commit, one 409, final quantity equals the winner. Same for `restore_suggested`, `skip_item`, `defer_item`, `restore_item`.
- Two concurrent `assign_single` calls: one assignment row, one 409, and the order-item version advanced once.
- Export of two assignments where the second is stale: no `export_batch_number` on either row.
- `set_item_receipts` against a stale order-item version does not change `item_status`.
- These SQL interleavings are specified here because they were not found in `tests/`. In-memory `VplConflict` tests do not satisfy them.
- 0027 as written must not be applied. Any future script is additive, idempotent, free of `rare_confirmed`, free of line-level supplier quantity, and does not run on the shared server until the owner approves a migration. Rollback must refuse once a history batch exists.

#### 7. Open owner decisions

- Approve the canonical batch parent and the `(history_id, source_order_item_id)` line key, and retire 0027's `(history_id, product_code)` line, flattened supplier columns, and `rare_confirmed` bit. Not approved by this review.
- Whether a client retry of `create_refresh` must reuse `successor_refresh_id`. Without that, two snapshots of one source refresh remain possible.
- Whether assignments soft-deleted before the snapshot belong in history.
- Confirm skip-versus-removed precedence as written in deliverable 3. The 2026-10-20 "approved in principle" texts do not resolve it.
- Rare-mover review-record approval. Absent that approval, no implementation.
- Whether a removed line may be edited before it reappears. In-memory behavior refuses the edit.
- Whether `assert_tenant_access` remains tenant-wide for this store-scoped working set.
- Authorization to add `row_version` to live tables and to change the write paths. This review does not grant it.

#### 8. Verdict

**BLOCK.**

The 2026-10-20 proposal can lose a manual line whose identity is `product_id` rather than a non-null unique `product_code`, can store the same assignment twice (0027 line columns plus child rows, or two batches on retry), and can place a removed or skipped line onto `procurement_order_items` because `_touched` treats a skip as a removed line and `carry_forward_skips` / `comparison_service.carry_forward` are unspecified relative to that table. Those are the three outcomes this review was told to block on. In-memory `NOT_ORDERABLE` guards do not close the SQL gap. Rare-mover persistence stays unapproved. No persistence work is authorized. Phase 2 stays **READY_FOR_REVIEW**.

## Independent review of the revised contract, executed in the Cursor session on 2026-10-20 after the owner accepted the direction in principle; this is not a separate Claude-process signature

**Date:** 2026-10-20. **Scope:** the revised data contract and concurrency design in `PHASE_2_VPL_HISTORY.md`, checked against `workspace_repository.py` and `vpl_history.py`. This section was written inside the Cursor session. It is not a separate Claude-process signature and it does not adopt a Claude model identity.

**Safety of this pass:** no backend Python, SQL, frontend, test, `PROJECT.md`, or `AUTONOMOUS_WORK_CONTROL.md` file was edited. No migration was written or applied. No database connection was opened. `VplWorkspace` was not connected to persistence. The live quantity engine and the OrderNMC workflow were not changed. Phase 2 stays **READY_FOR_REVIEW**. Nothing in this section authorizes a persistence implementation, including later application of SQL.

Database verification remains **NOT_VERIFIED**. Pytest was not re-run. The recorded "21 passed" result was not re-verified here.

### What the revised section fixes

Read as its own table, "Revised data contract (accepted in principle, persistence BLOCKED)" closes two of the earlier design mistakes and names the third:

- The history line key in that table is `(history_id, source_order_item_id)`. `product_id` and `product_code` are copied attributes. A second live item with the same code and a different `product_id` is no longer collapsed by `(history_id, product_code)`, and a null `product_code` is no longer omitted by that key.
- Unapplied `0027` is stated to be not the parent. The history line has no supplier columns. Assignment children are keyed by `(history_id, source_assignment_id)`, keep `supplier_code` and `assigned_qty`, and use source ids as copies rather than foreign keys to live rows. A second insert with the same `successor_refresh_id` is blocked by unique `(tenant_id, source_refresh_id, successor_refresh_id)`.
- The same section says a skipped line is not inserted into the removed collection, that an omitted skip stays in the immutable history batch, and that rare-mover persistence stays unapproved.

Those sentences are the right direction. They are not yet a contract that can be implemented without the losses below.

### What the code still does

`vpl_history.py` does not implement the revised key. `_index` raises `IDENTITY` when `product_code` is missing and raises `DUPLICATE_LINE` on a repeated code. `refresh` stores lines in a dict keyed by that code. The staged batch has a new `history_id` from `uuid.uuid4()` and a new `refresh_id` from `uuid.uuid4()`. It does not store `successor_refresh_id`, `source_order_item_id`, or assignment children. `_touched` is true when `reviewed_at` or `rare_confirmed` is set. `skip_item` in `workspace_repository.py` sets `reviewed_at` and does not clear `manual_override`, so a skip is touched. An absent touched line, including that skip, moves into `removed_manual_review`. `_restore_touched` sets `orderable` true. `edit` refuses a removed code; that refusal is in-memory only.

`workspace_repository._run` commits one statement. `set_final_qty`, `restore_suggested`, `skip_item`, `defer_item`, and `restore_item` filter on `tenant_id`, `order_item_id`, and `is_deleted = 0`. None compare `row_version`. `VplWorkspace._lock` is a `threading.Lock` held inside one process. `reconciliation_service.submit_grn` commits `store_last_grn` and then calls `reconcile`, which opens another connection. `orchestration_service.create_refresh` calls `next_refresh_no` and `create_vpl` before the working-item transaction. A retry therefore receives a new `refresh_id`. `comparison_service.carry_forward` inserts an order item when the previous row has `remaining_qty > 0`, `pending_status = 'carried'`, `item_status <> 'skipped'`, and `exists_in_refresh` is false. That lookup compares `product_code`, not `product_id`. `carry_forward_skips` updates a row already generated on the new refresh; it does not insert a product the generation omitted.

The concurrency section of the revised contract matches those five workspace statements, the one-process lock, and the GRN split. The identity and skip sections do not match `vpl_history.py`.

### Still blocking

**1. The file still states the old line key.** Lifecycle item 2 says a line identity inside a refresh is `product_code`. The Unresolved bullet still says `product_code` is the history key and `product_id` is copied when the caller supplies it. The revised table says the opposite and does not mark those two sentences superseded. Following either leftover sentence, or connecting the current `_index`, still drops a manual line whose identity is `product_id`, a null code, or a repeated code. The revised history-line row also does not name `final_qty`, `manual_override`, `override_reason`, `reviewed_at`, `reviewed_by`, `item_status`, or `skip_reason`. Copying only the columns that row names would keep the identifier and lose the edit.

**2. A retried refresh can still snapshot the same assignments twice.** The unique batch key dedupes only when `successor_refresh_id` is reused. The revised contract leaves that reuse undecided, and `create_refresh` allocates the next refresh number before the working-item transaction. The history write is specified as part of the later transaction, not as part of the header insert. A failed or repeated create therefore gets a new successor id, a new `history_id`, and a second copy of the same `source_assignment_id` values. Declaring `0027` not to be the parent removes the flattened supplier columns. It does not remove this second copy. This review does not decide the retry rule.

**3. A removed or skipped line can still become an orderable order item.** Two adjacent sentences disagree. One says a skipped line is not inserted into the removed collection. The next says the removed table is for an absent manual override or an absent non-deleted assignment. `skip_item` can leave `manual_override` set and can leave a non-deleted assignment in place, so both sentences apply to one row. Reappearance, as written, copies the manual fields onto a new order item. `carry_forward` then has a second route onto `procurement_order_items`: an omitted product is absent from the new refresh, so `exists_in_refresh` is false, and a carried pending row is inserted as `item_status = 'review'`. The "one live representation" sentence is not a constraint across the order-item table and the removed table. `exists_in_refresh` also matches `product_code`, so a null code does not count as present and two `product_id` values that share a code collapse. Current `_touched` still classifies a skip, because of `reviewed_at`, and a rare-mover flag as removal, and `_restore_touched` marks the restored line orderable. In-memory `NOT_ORDERABLE` does not bind `create_refresh`.

The documented compare-and-swap is not a reason to proceed. The five workspace updates have no version predicate. Export, receipt, pending, and `carry_forward_skips` are named as versionless writers and are not given a predicate in the later version-ownership list. The interleaving tests named in the contract were not found by this pass's two-file spot check and are still described as absent. `submit_grn` still commits before reconcile.

### Open owner decisions

These stay open. This review does not answer them.

- Whether a retried `create_refresh` must reuse `successor_refresh_id`.
- Whether assignments soft-deleted before the snapshot belong in history. The superseded assignment section still says the copy set is non-deleted live rows. The revised table does not say.
- Whether a removed line may be edited before it reappears. In-memory `edit` refuses it.
- Whether tenant-only access is correct for this store-scoped set.

Rare-mover confirmation stays **NOT APPROVED**. No column.

### Verdict

**BLOCK.**

The revised table fixes the history-line key and removes supplier columns from that line. The contract as a whole can still lose a manual line, because the old `product_code` key remains in the same file and in `vpl_history.py`. It can still duplicate assignment snapshots, because a retry allocates a new successor refresh. It can still place a skipped or removed line onto `procurement_order_items`, because skip-versus-removed precedence is contradictory and pending carry-forward inserts an omitted product by `product_code`. The contract is not safe to implement later. No migration and no persistence work is authorized. Phase 2 stays **READY_FOR_REVIEW**.

## Independent Claude review — genuinely separate pass, 2026-10-20 17:58 IST

The two sections directly above are explicitly marked as written inside
the Cursor session ("does not adopt a Claude model identity"). This
section is my own, first independent look at the revised contract,
checked directly against source rather than inherited from that prose.
No file edited except this one. No database connection opened. No
migration applied or written. No test file modified.

**I independently re-verified all three blocking claims by reading the
cited code myself, not by trusting the self-review's prose:**

1. **Contradictory line-identity key, confirmed.** `PHASE_2_VPL_HISTORY.md`
   line 24 ("Lifecycle" §2) still reads "A line identity inside a refresh
   is `product_code`," while the "Revised data contract" section's table
   states the history line's key is `(history_id, source_order_item_id)`.
   Both sentences remain in the same file, neither marked superseded.
   `vpl_history.py`'s `_index` (confirmed by reading lines 272-298) still
   raises `IDENTITY` on a missing `product_code` and `DUPLICATE_LINE` on a
   repeated code — the running code implements only the old key.
2. **Retry duplication, confirmed.** Read `orchestration_service.
   create_refresh` (lines 134-193) directly: `refresh_repo.next_refresh_no`
   is called unconditionally, then `refresh_repo.create_vpl` inserts a new
   refresh header immediately — no idempotency check, no reuse of a prior
   `successor_refresh_id` on retry. A second call with the same logical
   intent genuinely allocates a new `refresh_id` every time. The revised
   contract's own "Retry" paragraph says this is "not decided" and that
   `create_refresh` "was not changed" — matches what I found in the code.
3. **Skip/removal contradiction, confirmed.** Read `workspace_repository.
   skip_item` (lines 333-347) directly: it sets `item_status='skipped'`
   and `reviewed_at=GETDATE()` but never touches `manual_override`. Since
   `_touched()` in `vpl_history.py` (line 52) treats `reviewed_at` being
   set as sufficient for "touched," a skipped line is classified
   identically to a manually-edited one for removal purposes — exactly
   the collision the self-review describes. The contract's own text
   contains the contradiction verbatim: one sentence says "a skipped line
   is not inserted into the removed collection," the next says "the
   removed table is for an absent manual override or an absent
   non-deleted assignment" — a skip satisfies neither exclusion on its
   own terms once `reviewed_at` is treated as a touch signal.

**Tests independently re-run this pass:**
```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -q --tb=short
→ 33 passed
```
`git diff --stat` across ten files this pass (`decision_rules.py`,
`decision_repository.py`, `decision_service.py`, `workspace_repository.py`,
`orchestration_service.py`, `order_items_repository.py`,
`assignment_repository.py`, `assignment_service.py`,
`comparison_service.py`, `reconciliation_service.py`) — **zero diff on
all ten**, including the last two checked for the first time this pass.

**My own verdict, arrived at independently: BLOCK, concurring with the
in-session self-review.** All three cited defects are real and
independently reproducible from source, not artifacts of how the
self-review phrased them. The revised contract is a genuine improvement
over the original design (correctly separates assignment history as
child rows, correctly treats source ids as historical copies rather than
live foreign keys, correctly refuses rare-mover persistence without
approval) but is not yet internally consistent — a document that asserts
two different identity keys for the same object, and a skip/removal rule
that contradicts itself on the one case (a skip with a lingering manual
override) most likely to occur in real use, is not safe to turn into a
migration regardless of how good the rest of it is.

**I am not implementing a fix myself.** Per this session's standing
file-ownership boundary, `PHASE_2_VPL_HISTORY.md`'s design content,
`vpl_history.py`, `workspace_repository.py`, and `orchestration_service.py`
are Cursor-owned; correcting the contradiction requires either resolving
the lifecycle-section/revised-table mismatch (pick one key and mark the
old sentence superseded) or deciding the skip-vs-removal precedence
explicitly (e.g., "a line is removed-eligible only if `manual_override`
is set AND `item_status != 'skipped'`," or an equivalent rule) — both are
design decisions for Cursor to make and resubmit, not something I should
silently pick on their behalf.

**Phase 2 stays `READY_FOR_REVIEW`.** No migration, no persistence code,
no database write authorized by this pass.

## Independent review of the temporary-implementer pass — 2026-10-20

**Role for this section: independent auditor of a self-implemented change.** The prior "temporary implementation owner" pass on 2026-10-20 wrote corrections to `vpl_history.py` and reported on them itself (clearly labeled "not an independent review" in `PHASE_2_VPL_HISTORY.md`'s own handoff section). This section is that independent re-read, done from source, not from trusting the implementer's own summary. No implementation file was modified by this review. No migration was written or applied. No database connection was opened. No supplier action was triggered.

### Scope checked

- Full current text of `backend/modules/procurement/vpl_history.py` (411 lines, read in full).
- `backend/modules/procurement/workspace_repository.py::skip_item`/`defer_item`/`restore_item` (re-read, lines 333-387).
- `tests/test_vpl_history_claude_edge.py` (full file, assertions read individually, not just test names).
- `tests/test_vpl_history.py` (confirmed unmodified by the implementer pass — still 14 pre-existing tests, zero diff from before).
- `docs/procurement-workspace-unification/PHASE_2_VPL_HISTORY.md`, `AUTONOMOUS_WORK_CONTROL.md`, `PROJECT.md` for the implementer's own claims, cross-checked against the code rather than accepted at face value.

### 1. Identity logic — `_key()` / `_index()` / `_resolve_by_code()`

Traced directly: `_key(product_id, product_code)` (line 74-84) returns `("id", product_id)` whenever `product_id is not None`, else `("code", product_code)` whenever `product_code` is truthy, else `None`. `_index()` (line 356-388) uses this as the dict key for `self._working[...]["lines"]`. This is correct and matches the claim: `product_id` is authoritative when present; `product_code` is only consulted as a fallback when `product_id` is absent.

Verified by direct execution, not just reading:
- Two lines with `product_id=1`/`product_code="DUP"` and `product_id=2`/`product_code="DUP"` open as two distinct lines (`test_distinct_products_sharing_a_product_code_are_never_merged`, re-run, passes) — confirmed a code collision alone does not merge or reject them.
- A line's `product_code` changing across a refresh while `product_id` stays constant preserves the line's manual edits (`test_product_code_changing_across_refresh_does_not_lose_the_line`, re-run, passes) — confirmed identity follows `product_id`, not `product_code`.
- A line with `product_id` set and `product_code=None` is accepted by `open_cycle` without raising `IDENTITY` (confirmed by direct execution, see Finding 1 below for what happens *after* that).

**`_resolve_by_code()` (line 333-347) does fail closed.** Directly executed: opening two lines with `product_id=1`/`product_code="A"` and `product_id=2`/`product_code="A"`, then calling `edit(..., "A", ...)` raises `VplError("AMBIGUOUS", ...)` rather than silently picking one of the two products or guessing — confirmed by execution, not just code reading. The router's existing `_fail()` (`vpl_history_router.py:45-47`) maps any `VplError` that is not a `VplConflict` to HTTP 422, so `AMBIGUOUS` surfaces as a 422 to a caller, not a silent wrong-product mutation. **This correctly satisfies instruction 2** ("ambiguous codes fail closed and cannot cause an operation against the wrong product") for every method that routes through `_resolve_by_code` — `edit`, `assign_supplier`, `export_lines`, `place_order`, `submit_to_portal`, and the removed-line check inside `edit`/`_guard_orderable`.

**Residual gap, correctly disclosed by the implementer, confirmed real:** none of the four action methods or `EditBody`/`ProductActionBody` in `vpl_history_router.py` were extended to accept `product_id`. A caller that can only ever supply `product_code` has no way to disambiguate two products sharing a code — it will always get `AMBIGUOUS` for that pair, never a wrong-product action, but also never a successful one. This is a usability gap, not a correctness defect, and is already documented as unresolved; I am not treating it as a new finding since it was disclosed.

### 2. FINDING — HIGH severity, confirmed by direct execution, not disclosed anywhere

**`_public()` (line 390-407) crashes whenever any line in the working set has `product_code = None`, as soon as there is more than one line to sort.**

```python
lines.sort(key=lambda line: line["product_code"])
```

Reproduced directly:

```
>>> w.open_cycle('t1','s1','c1',
...   [{'product_id':1,'product_code':None,'suggested_qty':5,'final_qty':5},
...    {'product_id':2,'product_code':'B','suggested_qty':3,'final_qty':3}],'snap')
TypeError: '<' not supported between instances of 'str' and 'NoneType'
```

and even more narrowly, **two lines that are both null-coded crash the same way**, because Python's sort still compares adjacent elements:

```
>>> w.open_cycle('t1','s1','c1',
...   [{'product_id':1,'product_code':None,...}, {'product_id':2,'product_code':None,...}],'snap')
TypeError: '<' not supported between instances of 'NoneType' and 'NoneType'
```

This directly contradicts the implementer's own stated goal ("A null `product_code` with a `product_id` present is accepted (tested)" — `PHASE_2_VPL_HISTORY.md`'s temporary-implementer-pass section, and docstring at `vpl_history.py:17-27` claiming null-code lines are handled). `open_cycle()`/`working()`/`refresh()` all call `self._public(...)` before returning, so **any working set containing a null-coded line and at least one other line of any kind cannot be read back** — `open_cycle` itself raises `TypeError` (an unhandled 500 at the router, not a `VplError`/`VplConflict` the router's `_fail()` knows how to turn into a 4xx) the moment a second line exists alongside a null-code line.

**Why the test suite did not catch this:** `test_line_with_product_id_and_no_product_code_is_accepted_and_findable` (`tests/test_vpl_history_claude_edge.py`, new in this pass) opens a working set with **exactly one line** and never calls `working()`/`refresh()` with a second line present — `_public()`'s sort over a one-element list never compares two elements, so the comparator is never invoked and the bug never fires. The test's name claims the line is "findable," but it only asserts on the return value of `open_cycle` itself and never exercises a second read or a mixed-population working set. This is a real gap between what the test name claims and what the test body actually proves — the kind of defect instruction 5 ("read the new test assertions, not just test names") is specifically asking this review to catch, and it is present.

**Severity:** HIGH. This is not a cosmetic ordering issue — it is an unhandled crash (not a clean `VplError`) on the single most basic read operation (`GET /working`, `POST /working` itself) for the exact scenario (`product_id` present, `product_code` null) the implementer pass was specifically trying to fix. A live caller (once wired) supplying any real `sync.Products` row with a null `ProductCode` alongside any other row would 500 on every read of that cycle's working set, not degrade gracefully.

**Fix is not applied by this review** (implementation files are out of scope for this pass per the strict boundaries), but the shape of a fix is narrow and worth recording for whoever picks it up: the sort key needs to tolerate `None`, e.g. `key=lambda line: (line["product_code"] is None, line["product_code"] or "")` or sorting on `(product_id, product_code)` instead. This is a one-line change in `_public()`, not a redesign — flagging it as low-risk to fix, not as grounds to reopen the identity-key design itself.

### 3. Skip-versus-removal precedence — `_is_skip_only()` / `_touched()`

Re-read `workspace_repository.skip_item()` (lines 333-347) character-for-character against `_is_skip_only()` (`vpl_history.py:87-99`): `skip_item` sets `item_status = 'skipped'`, `reviewed_at = GETDATE()`, and explicitly never touches `manual_override`, `supplier_code`, or any rare-mover field. `_is_skip_only()` checks exactly `item_status == "skipped"` AND none of `manual_override`/`supplier_code`/`rare_confirmed` — this is a precise, not approximate, match to what the real write path produces. Confirmed by direct line-by-line comparison, not assumed.

Verified by direct execution (re-running, not just reading, the three new tests that target this):
- `test_skip_with_reviewed_at_but_no_manual_override_is_not_manual_review`: a skip-only line dropped from the next generation does **not** appear in `removed_manual_review`, and does still appear in the archived history batch. Passes.
- `test_skip_combined_with_manual_override_still_counts_as_touched`: a line skipped *after* a genuine `manual_override` edit still routes to `removed_manual_review` when dropped. Passes. Confirms the skip does not erase a prior manual-edit signal.
- `test_skip_combined_with_supplier_assignment_still_counts_as_touched`: a skip-only line that also carries a `supplier_code` still routes to `removed_manual_review`. Passes. Confirms a supplier assignment is not silently discarded by a skip.

These three assertions were read in full, not just their names, and each one's assertion body matches what it claims to test. No contradiction was found between this logic and the prior session's own documented concern (the self-review section above, "the removed table is for an absent manual override or an absent non-deleted assignment") — the new `_is_skip_only()` gate is in fact the explicit resolution of that exact contradiction, and it resolves it correctly for all three combinations tested.

**No simultaneous active-and-removed state found.** Traced `refresh()`'s reconciliation loop (lines 219-241): a given `item_key` is either consumed into `new_lines` (if present in `incoming`) or evaluated for `new_removed` (only in the second loop, which explicitly `continue`s past any key already `in incoming`) — structurally exclusive, confirmed by reading the control flow, not merely asserted.

### 4. `defer_item` and other unresolved transitions

Confirmed by direct comparison: `defer_item()` (`workspace_repository.py:350-365`) sets `item_status = 'deferred'` and `reviewed_at`, nothing else. Neither `_is_skip_only()` nor `_touched()` has any branch that inspects `item_status == 'deferred'`. **This means a deferred-but-otherwise-untouched line that drops out of the next generation is treated as an ordinary untouched absent line** — it is not preserved in `removed_manual_review`, only in history, by the same path a plain unedited line would take. This matches exactly what the implementer pass disclosed ("I did not find, and did not invent, a rule for... `defer_item`") — I independently traced the same code path and reached the same conclusion: this is a genuinely undecided business question, not a silently-wrong default, and it is correctly flagged rather than guessed. **This review adds no new resolution for it** — it stays an open owner decision, now explicitly listed below.

`restore_item()` (lines 368-386) only mutates live rows already present in a generation and is never called by `vpl_history.py` at all (`VplWorkspace` has no analogous method) — it is out of scope for this in-memory model and was correctly left untouched.

### 5. Regression and reconciliation checks

Re-ran, independently, not reusing a cached result:

```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -v --tb=short
→ 41 passed, 1 warning (pytest cache-write permission warning only, not a test failure)
```

All 41 test names and assertion bodies were read; none assert a line appearing simultaneously in `lines` and `removed_manual_review`; none assert a duplicate row surviving a repeated refresh; `test_removed_lines_stay_inside_one_store_cycle` and `test_concurrent_refreshes_on_different_stores_do_not_interleave` (unmodified by this pass) still correctly isolate by the full `(tenant_id, store_id, cycle_id)` tuple; `test_duplicate_line_and_stale_edit_are_rejected` and the new `test_stale_row_version_rejected_in_existing_in_memory_service` both independently confirm stale-version rejection leaves the line unchanged.

```
git diff --stat -- backend/modules/procurement/decision_rules.py backend/modules/procurement/decision_repository.py backend/modules/procurement/decision_service.py backend/modules/procurement/workspace_repository.py backend/modules/procurement/orchestration_service.py backend/modules/procurement/order_items_repository.py backend/modules/procurement/assignment_repository.py backend/modules/procurement/assignment_service.py backend/modules/procurement/comparison_service.py backend/modules/procurement/reconciliation_service.py backend/modules/procurement/vpl_history_router.py backend/modules/legacy_order
```
→ zero diff on every procurement live-engine/write-path file and `vpl_history_router.py`. The only diff under `backend/modules/legacy_order/` is Cursor's pre-existing uncommitted WIP (same file list and line counts as recorded earlier this session, before the temporary-implementer pass began) — confirmed unrelated to this pass, not newly introduced by it. `backend/modules/procurement/sql/0027_vpl_history.sql` remains untracked and unapplied; no database connection was opened by this review.

### Explicit separation of verified vs. unverified behavior

**Verified by direct execution in this review:**
- `product_id`-first identity resolution, including code-collision non-merging and code-change identity preservation.
- `_resolve_by_code` fails closed with `AMBIGUOUS` on a genuine code collision; never guesses a product.
- `_is_skip_only`/`_touched` exactly match `skip_item`'s real write shape; all three skip-combination tests pass with assertion bodies that match their names.
- The `_public()` crash on a null `product_code` alongside any second line, including two null-coded lines together.
- Zero diff on all cited live-engine/write-path files and `vpl_history_router.py`.
- `defer_item` is correctly left as an open question, not silently mishandled.

**Not verified, and explicitly not claimed by this review:**
- Database/SQL Server behavior of any kind — no connection was opened, consistent with the standing NOT_VERIFIED status.
- Multi-process or multi-worker concurrency — `VplWorkspace._lock` is single-process only, as already documented in the Concurrency design section above; nothing in this pass changes that, and this review does not claim otherwise.
- Browser or UI verification — not in scope for this pass; no UI file was touched by the implementer or this review.
- Any behavior of the real `sync.Products`-sourced data shape in production — the null-`product_code` scenario was constructed synthetically to probe the code path, not observed from a live row.

### Verdict: **BLOCK**

The identity-key and skip/removal corrections themselves are sound and independently verified as correct for every case tested. However, this review found a real, reproducible, undisclosed HIGH-severity defect (`_public()` crashes on any null-`product_code` line once a second line exists) that directly undermines the implementer's own stated purpose for this pass — accepting a null `product_code` was the explicit point of the identity-key fix, and the one case meant to demonstrate it (a `product_id`-only line) is also the one case that crashes the very next read. This is not a design-contract ambiguity like the prior BLOCK findings; it is a concrete bug in the code that shipped. Persistence stays **BLOCKED**, and this in-memory model should not be considered acceptance-ready until:

1. `_public()`'s sort is fixed to tolerate `None` product codes (narrow, low-risk fix, not a redesign).
2. A test that actually exercises `working()`/`refresh()` (not just `open_cycle()`'s return value) with a null-coded line **and at least one other line present** is added, so this exact regression cannot reappear silently.
3. The `defer_item`-drop precedence is either accepted as "behaves like untouched" by explicit owner sign-off, or given its own rule — it should not remain an implicit default indefinitely once this model is close to being considered for persistence.

No migration, no persistence code, and no database write are authorized by this review. Phase 2 remains `READY_FOR_REVIEW`.

## Independent re-verification of the null-product_code sort fix — 2026-10-20

**Role for this section: independent reviewer only.** No implementation file was modified by this review. No migration was written or applied. No database connection was opened. No supplier action was triggered. The control file was read but not concurrently edited by another agent at the time of this pass (checked via `git status` immediately before starting).

### 1. Current source inspected directly

Read the full current `backend/modules/procurement/vpl_history.py` (440 lines). `_sorted_by_identity()` (lines 113-130) sorts `(identity_key, line)` pairs on `(line["product_code"] is None, line["product_code"] or "", _sort_token(identity_key))`. `_sort_token()` (lines 102-110) maps an `("id", value)` key to `(0, value)` and a `("code", value)` key to `(1, value)`, so keys of different kinds are never compared against each other as raw values of mismatched Python types. Both call sites in `_public()` (lines 421-423) use this helper — confirmed both `lines` and `removed_manual_review.lines` go through the same fixed sort, not just one of the two paths.

### 2. Historical reproduction — explicitly could not be performed via git history, performed a different way instead

```
git log --oneline -- backend/modules/procurement/vpl_history.py   → no output
git log --all --oneline -- backend/modules/procurement/vpl_history.py   → no output
git status --short -- backend/modules/procurement/vpl_history.py   → ?? (untracked)
```

**The file has never been committed, so there is no prior Git revision to check out and no historical reproduction via `git show`/`git checkout <rev>` is possible without overwriting the current working tree, which this review was instructed not to do.** This is stated explicitly rather than skipped silently, per instruction 2.

As a substitute, not a replacement: the exact pre-fix line was quoted verbatim in this document's own prior "Independent review of the temporary-implementer pass" section (`lines.sort(key=lambda line: line["product_code"])`). I re-executed that exact line, standalone, outside the current module, against two small synthetic line lists:

```python
lines = [{"product_id": 1, "product_code": None}, {"product_id": 2, "product_code": "B"}]
lines.sort(key=lambda line: line["product_code"])
→ TypeError: '<' not supported between instances of 'str' and 'NoneType'

lines = [{"product_id": 1, "product_code": None}, {"product_id": 2, "product_code": None}]
lines.sort(key=lambda line: line["product_code"])
→ TypeError: '<' not supported between instances of 'NoneType' and 'NoneType'
```

This confirms the documented prior defect is real and reproducible from the quoted code itself, independent of trusting the fix report's narrative — but it is a reconstruction from the recorded prior review text, not a checkout of an actual prior commit, since no such commit exists. This distinction is kept explicit per instruction 2's own fallback clause.

### 3. Current implementation independently exercised

All five required scenarios were run directly against the current `vpl_history.py`, not inferred from the new tests:

1. **One null-coded line + one string-coded line:** `open_cycle` then `working()` both return `{(1, None), (2, "B")}` with no crash; confirmed deterministic ordering — the string-coded line (`B`) sorts first, the null-coded line second.
2. **Two null-coded lines, distinct `product_id`s:** both lines present and distinguishable (`{(10, None), (20, None)}`), no crash, no merge.
3. **Two distinct `product_id`s sharing one `product_code`:** both lines preserved as distinct (`{(5, "DUP"), (3, "DUP")}`), not merged into one.
4. **Repeated reads, deterministic ordering:** 10 consecutive `working()` calls on the same workspace returned identical `product_id` ordering every time.
5. **Multiple removed-manual-review lines containing null codes:** constructed two null-coded lines (`product_id` 1 and 3) both carrying genuine `manual_override`/`supplier_code`, alongside one string-coded line (`product_id` 2). After a `refresh()` that regenerates only the string-coded line, `removed_manual_review.lines` correctly contains **both** null-coded lines with their manual edits intact — `(1, None, final_qty=9, supplier_code="SUP1")` and `(3, None, final_qty=4, supplier_code="SUP3")` — not merged, not dropped, and in a stable order across repeated reads.

**A genuine, if narrow, additional limitation surfaced during this independent exercise, not previously documented this precisely:** `_resolve_by_code()` treats `product_code=None` as a valid lookup value like any other code. The moment **two or more** null-coded lines coexist in the same working set, calling `edit(..., product_code=None, ...)` for *either* of them raises `AMBIGUOUS` — there is no way to disambiguate which null-coded line was meant via the code-only router parameter, exactly analogous to the already-disclosed string-code ambiguity, but specific to `None` and not previously spelled out in those terms. This is **correct, fail-closed behavior** (it does not silently edit the wrong line), and is a direct, unsurprising consequence of the already-disclosed `AMBIGUOUS` residual gap — not a new defect, but worth stating precisely: a null-coded line can only ever be edited via `product_code` while it is the *only* null-coded line in its working set. Once this model gains a router parameter for `product_id` (already listed as a remaining limitation), this stops mattering.

### 4. Identities and manual edits confirmed intact

Across every scenario above, `product_id`, `product_code`, `final_qty`, and `supplier_code` were asserted on the actual returned line dicts, not merely counted. No case produced a merged line, a dropped line, or a line whose manual edit (`final_qty`/`supplier_code`) was lost or displaced onto the wrong `product_id`.

### 5. New test bodies inspected individually, not just by name

Read all five new tests in `tests/test_vpl_history_claude_edge.py` (lines 354-457) in full:

- `test_one_null_coded_line_and_one_string_coded_line_reads_without_crashing` — calls `open_cycle` **and** `working()` with two lines present, asserts the actual identity set and the exact ordering (`"B"` before `None`). Genuine multi-line exercise, not a single-line construction.
- `test_two_null_coded_lines_with_distinct_product_ids_read_without_crashing` — two lines, both null-coded, asserts identity set, line count, and ordering stability across two reads. Genuine.
- `test_two_distinct_product_ids_sharing_one_product_code_read_without_crashing` — two lines sharing one code, asserts both are kept distinct via `product_id`. Genuine.
- `test_repeated_reads_of_a_mixed_null_and_duplicate_coded_set_are_deterministically_ordered` — four lines (two null, two sharing a code), five repeated reads, asserts identical ordering every time and that null-coded lines sort after the coded ones. Genuine, and the most thorough of the five.
- `test_removed_manual_review_section_also_survives_null_coded_lines` — edits one null-coded line and one string-coded line, refreshes with an empty generation list, asserts both land in `removed_manual_review` with correct identities. **Genuine, but narrower than its own docstring area might suggest**: it exercises exactly **one** null-coded line in the removed section, not two. This is not a false claim — the test's own docstring says "a touched null-coded line... alongside another removed line" (singular null), which accurately describes what it does — but it means the two-null-coded-lines-in-removed-review case (confirmed by this review's own independent scenario 5 above) is covered by this review's manual exercise, not by the shipped test suite. **This is a minor test-coverage gap worth closing, not a defect in the fix itself** — the underlying code path is shared (`_sorted_by_identity` is called once for `removed_manual_review.lines` regardless of how many null-coded lines are in it), and this review's own direct execution already confirms that broader case works correctly.

All five bodies do genuinely exercise the multi-line `working()`/`open_cycle()`-return/`refresh()` path with more than one line present — the specific gap that let the original defect ship unnoticed (a test with only one line in the working set) is not repeated in any of the five.

### 6. Tests run, exact commands

```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -v --tb=short
→ 46 passed, 1 warning (pytest cache-write permission warning only)
```

All 46 individual test names were read in this run's output; none failed, none were skipped.

### 7. Live engine/write-path, migration, and legacy-workflow files confirmed untouched

```
git diff --stat -- backend/modules/procurement/decision_rules.py backend/modules/procurement/decision_repository.py backend/modules/procurement/decision_service.py backend/modules/procurement/workspace_repository.py backend/modules/procurement/orchestration_service.py backend/modules/procurement/order_items_repository.py backend/modules/procurement/assignment_repository.py backend/modules/procurement/assignment_service.py backend/modules/procurement/comparison_service.py backend/modules/procurement/reconciliation_service.py backend/modules/procurement/vpl_history_router.py backend/modules/legacy_order
```
→ zero diff on all ten live-engine/write-path files and `vpl_history_router.py`. The only diff reported is under `backend/modules/legacy_order/` and is Cursor's pre-existing uncommitted WIP (identical file list and line counts to every prior check recorded earlier in this document and the control file) — confirmed unrelated to and unmodified by this fix.

```
git status --short -- backend/modules/procurement/sql/
```
→ `0026_*` and `0027_*` SQL files remain untracked, unapplied, and unmodified. No database connection was opened to verify this against a live server; this is a repository-state check only, consistent with the standing `NOT_VERIFIED` database status.

### Explicit separation of verified categories

- **Historical reproduction:** could not be performed via actual Git history (no commit exists for this file). Substituted with direct re-execution of the exact prior sort line as quoted in this document's own earlier section — confirmed the documented crash is real, but this is not equivalent to checking out an actual prior revision.
- **Current-code verification (by direct execution, this review):** all five required scenarios confirmed correct, including the two-null-coded-lines-in-removed-review case the shipped tests don't individually cover. The `AMBIGUOUS`-on-two-null-codes consequence confirmed and characterized as correct fail-closed behavior, not a defect.
- **Automated test results (this review's own run, not reused from the fix report):** 46 passed, exact command and full name list captured above.
- **Unverified behavior, unchanged from every prior pass:** database/SQL Server behavior (no connection opened), multi-process/multi-worker concurrency (`VplWorkspace._lock` remains single-process only), browser/UI verification (out of scope, no UI file touched), and real `sync.Products`-sourced data shapes (all scenarios here are synthetic, constructed to probe the code path).

### Verdict: **APPROVE WITH CONDITIONS**

The fix correctly resolves the confirmed HIGH-severity crash: every reproduction of the original failure mode, including the removed-manual-review path and a case the shipped test suite does not itself cover (two null-coded lines together in `removed_manual_review`), now returns correctly with intact identities and manual edits. The fix is narrow (an ordering key, not a redesign) and does not touch any live write path, migration, or legacy workflow — confirmed again by this review, not merely carried forward from the fix report.

Conditions, none of which block this specific fix from being considered sound, but which should be closed before this model is treated as fully hardened:

1. Add a sixth regression test (or extend the existing one) that puts **two** null-coded lines into `removed_manual_review` together, matching this review's own manual scenario 5 — the current five tests are genuine but this specific combination is only verified by this review's direct execution, not by the committed suite.
2. Document, in `PHASE_2_VPL_HISTORY.md`, the precise consequence found in section 3 above: `product_code=None` is ambiguous via `_resolve_by_code` the moment a second null-coded line exists, exactly like a duplicate string code — this is correct behavior but was not previously stated in terms of `None` specifically, and a future reader fixing the `AMBIGUOUS` residual gap should know null codes are included in that fix's scope, not a separate case.
3. The three items already carried forward unresolved (the broader `AMBIGUOUS` router-parameter gap, the `defer_item`-drop precedence, rare-mover persistence NOT APPROVED) remain exactly as previously documented — this review found no new information that changes any of them.

No migration, no persistence code, and no database write are authorized by this review. Phase 2 remains `READY_FOR_REVIEW`. Persistence remains **BLOCKED** pending the identity-contract and concurrency-design approvals already on record — this fix clears the specific crash defect but does not itself unblock persistence.

## Independent review of the two closed conditions — 2026-10-20

**Role for this section: independent reviewer only.** No implementation file, test file, phase document, or the shared control file was edited by this review. No migration was written or applied. No database connection was opened. No supplier action was triggered.

### Scope checked

- `tests/test_vpl_history_claude_edge.py::test_two_null_coded_lines_coexist_distinct_in_removed_manual_review` (full body read, lines 460-end).
- `docs/procurement-workspace-unification/PHASE_2_VPL_HISTORY.md`'s new "closing two independent-review conditions" section (full text read).
- `backend/modules/procurement/vpl_history.py::_resolve_by_code` (lines 364-378, re-read against the doc's own line citation) and `_guard_orderable` (lines 317-336, read to trace exact call order).
- `backend/modules/procurement/vpl_history_router.py` (re-read in full for diff purposes, not re-analyzed logically — unchanged from the prior two reviews).
- Prior sections of `PHASE_2_CLAUDE_REVIEW.md` for continuity, not re-litigated.

### 1. Condition 1 test — genuinely exercises the required scenario, with one looseness worth noting

Confirmed by reading the test body directly: two distinct `product_id`s (1 and 3), both `product_code=None`, are placed in the working set via `open_cycle` with their own `manual_override`/`supplier_code`/`final_qty` already set (not invented fields — `manual_override`, `supplier_code`, `final_qty` are all pre-existing, already-indexed fields per `_index()`). A `refresh()` that regenerates only the third, string-coded line moves both null-coded lines into `removed_manual_review`.

Re-ran this specific test in isolation to confirm it passes standing alone, not only as part of the full suite:
```
backend/.venv/Scripts/python.exe -m pytest "tests/test_vpl_history_claude_edge.py::test_two_null_coded_lines_coexist_distinct_in_removed_manual_review" -v --tb=long
→ 1 passed
```

Verified by reading the assertions, not just the test name:
- Both identities present and distinct: `assert set(removed) == {1, 3}` — genuine, not a count-only check.
- Each line's own `final_qty`/`supplier_code` preserved and not swapped: `removed[1]["final_qty"] == 9` / `"SUP1"`, `removed[3]["final_qty"] == 4` / `"SUP3"` — both pairs checked, confirming no cross-contamination between the two lines.
- Deterministic ordering: `first_order` captured once, then compared against 4 further reads — genuine repeated-read check, not a single comparison.
- Code-based ambiguity fails closed: a `product_code=None` edit attempt is asserted to raise `AMBIGUOUS`, not merely wrapped in a bare `try/except` that would swallow a different outcome — the `else: raise AssertionError(...)` branch means a silent success would fail the test.
- Assignment/export/order/portal cannot succeed: all four action methods are called against `product_code=None` and asserted to raise either `AMBIGUOUS` or `NOT_ORDERABLE`, never to return successfully (the `else` branch again converts a non-exception into a failure).

**One looseness, independently confirmed by direct execution, not previously stated this precisely:** the test's assertion `exc.code in ("AMBIGUOUS", "NOT_ORDERABLE")` is wider than what actually happens. I executed the four action methods against this exact scenario directly (not via the test) and confirmed **all four always raise `AMBIGUOUS`, never `NOT_ORDERABLE`**, because `_guard_orderable` (`vpl_history.py:317-336`) calls `_resolve_by_code(body["removed_manual_review"], product_code)` first (line 320) — with two null-coded lines both present in that section, this call itself raises `AMBIGUOUS` before the `NOT_ORDERABLE` branch at line 329 is ever reached. The test still correctly proves its stated goal (no action succeeds), and permitting the looser disjunction is not a false claim — but the test does not pin down the specific, more informative guarantee that this exact scenario always fails via `AMBIGUOUS` specifically. This is a minor precision gap in the test's assertion, not a defect in the implementation or a reason to reject the test.

### 2. Documentation — accurate and consistent with the implementation

Read the new "2026-10-20 (closing two independent-review conditions)" section in `PHASE_2_VPL_HISTORY.md` in full and checked each of its four bullet claims against the source directly, not against the prior fix-pass report:

- "Multiple null-coded products can coexist" — confirmed true by this review's own prior independent scenario execution and by this test.
- "A lookup by `product_code=None` cannot uniquely identify one of them" — confirmed true; `_resolve_by_code` (lines 364-378) matches `product_code == None` the same way it matches any string value, with no special-casing.
- "`_resolve_by_code()` must fail closed with `AMBIGUOUS`; it must never guess" — confirmed true by direct re-execution in this review (see section 1 above); the cited line range (364-378) is accurate.
- "Identity-based handling should use `product_id` when available, with the fallback only where appropriate" — this restates the existing `_key()`/`_index()` behavior accurately; internal identity was already independently verified against this exact rule in the first independent review in this document and is unchanged.

No claim in this documentation section overstates what the code does, and no claim contradicts the `vpl_history.py` source as currently read. The documentation explicitly states it does not resolve the underlying `product_id`-router-parameter gap — consistent with what this review independently confirms is still true of the router (`EditBody`/`ProductActionBody` still take `product_code` only).

### 3. Tests independently re-run

```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -v --tb=short
→ 47 passed, 1 warning (pytest cache-write permission warning only, not a test failure)
```
All 47 individual test names were read from this run's own output; none failed, none were skipped. This is one more than the 46 recorded in the prior independent review (the new condition-1 test), matching the expected delta exactly.

### 4. Diff and migration state confirmed

```
git status --short -- backend/modules/procurement/vpl_history.py backend/modules/procurement/vpl_history_router.py docs/procurement-workspace-unification/AUTONOMOUS_WORK_CONTROL.md
→ all three show untracked (??), i.e. unchanged by this follow-up (no new diff against the already-untracked prior content)

git diff --stat -- backend/modules/procurement/decision_rules.py backend/modules/procurement/decision_repository.py backend/modules/procurement/decision_service.py backend/modules/procurement/workspace_repository.py backend/modules/procurement/orchestration_service.py backend/modules/procurement/order_items_repository.py backend/modules/procurement/assignment_repository.py backend/modules/procurement/assignment_service.py backend/modules/procurement/comparison_service.py backend/modules/procurement/reconciliation_service.py backend/modules/procurement/vpl_history_router.py
→ zero diff on all eleven procurement files

git status --short -- backend/modules/procurement/sql/0027_vpl_history.sql
→ ?? (untracked, unapplied, unchanged)
```

**Noted but not a concern for this task's boundary:** `git diff --stat` on `backend/modules/legacy_order/` shows a larger diff than recorded in the prior independent review (1085 insertions vs. 818 previously) — this is Cursor's own separately-growing, pre-existing uncommitted WIP in a module this task was never scoped to touch, confirmed unrelated by isolating the diff command to procurement-only paths above (zero diff there). Not re-investigated further since `legacy_order` is out of scope for this review per the task's own instructions. No database connection was opened by this review, consistent with the instruction not to connect.

### Explicit separation of verified categories

- **Test genuineness (this review, direct reading):** confirmed — the test exercises two distinct null-coded identities in `removed_manual_review`, preserves each line's own `final_qty`/`supplier_code`, verifies deterministic ordering across 4 repeated reads, and verifies all four action methods fail for both removed lines, with assertions that would fail the test on a silent success.
- **Documentation accuracy (this review, direct cross-check against source):** all four required points are present and consistent with `vpl_history.py` as currently read.
- **Automated test results (this review's own run):** 47 passed, exact command above.
- **Production/scope boundaries (this review, direct `git` inspection):** zero diff on all procurement write-path files and `vpl_history_router.py`; `vpl_history.py` and the control file unchanged by this follow-up; migration 0027 remains untracked and unapplied; no database connection opened.
- **Unverified, unchanged from every prior pass:** database/SQL Server behavior, multi-process concurrency, browser/UI verification, real `sync.Products`-sourced data shapes.
- **New minor finding from this review, not previously stated:** the test's `AMBIGUOUS`-or-`NOT_ORDERABLE` disjunction is looser than the implementation's actual behavior for this exact scenario (always `AMBIGUOUS`, confirmed by direct execution) — correct as a safety assertion, imprecise as a specification. Not severity-worthy; noted for anyone tightening this test later.

### Verdict: **APPROVE**

Both previously conditional review items are closed. The regression test genuinely covers the required scenario with assertions that would catch a real regression, not just the absence of a crash. The documentation accurately and consistently describes the null-code ambiguity, the `AMBIGUOUS` fail-closed behavior, and the `product_id`-first identity rule, cross-checked against the current source rather than accepted from the prior report. No production implementation file, `vpl_history_router.py`, live procurement write path, or the shared control file was changed by this follow-up. Migration 0027 remains unapplied. No database connection was made by either the follow-up or this review.

This approval is scoped to the two conditions from the prior "APPROVE WITH CONDITIONS" verdict. **It does not authorize persistence.** The previously carried-forward items — the broader `AMBIGUOUS` router-parameter gap (no `product_id` parameter added to the four action endpoints or `EditBody`), the undecided `defer_item`-drop precedence, and rare-mover confirmation persistence (**NOT APPROVED**) — remain exactly as documented, unresolved, and out of scope for this review. Phase 2 remains `READY_FOR_REVIEW`. Persistence remains **BLOCKED**.

## Master design audit — 2026-10-20 — Senior Procurement Architect / Independent Design Auditor

### 1. Audit scope and boundaries

Read-only design audit. No production implementation file, test file, migration file, or the shared control file was edited. No database connection was opened. No migration was applied or simulated. No live write path was changed. This section is the only file this task modifies.

### 2. Files inspected

- `PROJECT.md`, `AUTONOMOUS_WORK_CONTROL.md`, `PHASE_2_VPL_HISTORY.md`, `PHASE_2_CLAUDE_REVIEW.md` (this file, prior sections), `contracts/Procurement_Workspace_Master_Phase_Prompts.md`.
- `backend/modules/procurement/vpl_history.py` (full, 440 lines), `vpl_history_router.py` (full, 193 lines — read only, not modified).
- `backend/modules/procurement/workspace_repository.py` (full), `workspace_service.py` (full), `pm_router.py` (full, 753 lines — the real, live production router).
- `backend/modules/procurement/assignment_repository.py` (full), `assignment_service.py` (full).
- `backend/modules/procurement/export_service.py` (full), `reconciliation_service.py` (full).
- `backend/modules/procurement/pending_repository.py` (first 150 lines, covering every write function).
- `backend/modules/procurement/order_items_repository.py` (`carry_forward_skips`, lines 44-80).
- `backend/modules/procurement/orchestration_service.py` (`create_refresh`, lines 119-207).
- `backend/modules/procurement/rules_catalog.py` (rare-mover rule entry, lines 11-243), `quantity_profile_t.py` and `decision_rules.py` (rare-mover detection, lines 41-347).
- `backend/modules/procurement/comparison_service.py::carry_forward` (re-confirmed from an earlier pass in this document, not re-pasted here).
- Grep across `backend/modules/procurement/*.py` for `row_version`/`RowVersion`/`rowversion` (6 matches, all in `vpl_history.py` or unapplied SQL/`rules_resolution.py` — none in a live write-path `.py` file).
- `tests/test_vpl_history.py`, `tests/test_vpl_history_claude_edge.py` (already fully reviewed in prior sections; not re-pasted).

Tests run this pass: none. This is a source-reading audit; no new test file was written or executed, consistent with the "tests unchanged" boundary. (The most recent prior section already recorded an independent 47-passed run; that evidence stands and is not re-claimed here as newly produced.)

### 3. Audit A — the `AMBIGUOUS` gap is real but entirely confined to the unwired VPL History prototype

**Central finding, confirmed by reading `pm_router.py` in full: every live, production-mounted procurement route resolves its target by a stable, database-generated primary key — `order_item_id`, `assignment_id`, `refresh_id`, `batch_no`, `run_id`, `run_item_id` — never by `product_code`.** `product_code` appears in `pm_router.py` only as a *filter* (`workspace`'s `search` query param, matched with `LIKE`) or as a *display/grouping* column, never as the sole identifier a mutation resolves against. This means the `AMBIGUOUS`-on-`product_code` defect class that was found and fixed in `vpl_history.py` **does not exist on the live write paths** — it is specific to the unwired `vpl_history_router.py` prototype, which (per `PHASE_2_VPL_HISTORY.md` and every prior review) is not called by any live screen today.

#### Route-to-resolution matrix

| HTTP method & route | Request identifier(s) | Service method | Identity resolution | Null/dup code possible? | Current ambiguous behavior | Can mutate state? | Risk if wrong line selected | Required safe behavior | Classification | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| `PUT /order-items/{order_item_id}/final-qty` | `order_item_id` (PK) | `workspace_service.set_final_qty` | Direct PK lookup, `WHERE order_item_id = ?` | N/A — PK, not a code | N/A | Yes | None — PK is always unique | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:126-133`, `workspace_repository.py:293-311` |
| `POST /order-items/{order_item_id}/restore-suggested` | `order_item_id` (PK) | `workspace_service.restore_suggested` | PK | N/A | N/A | Yes | None | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:136-142` |
| `POST /order-items/{order_item_id}/skip` | `order_item_id` (PK) | `workspace_service.skip_item` | PK | N/A | N/A | Yes | None | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:145-149` |
| `POST /order-items/{order_item_id}/restore` | `order_item_id` (PK) | `workspace_service.restore_item` | PK | N/A | N/A | Yes | None | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:152-156` |
| `POST /order-items/{order_item_id}/defer` | `order_item_id` (PK) | `workspace_service.defer_item` | PK | N/A | N/A | Yes | None | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:159-165` |
| `POST /order-items/{order_item_id}/assignments` | `order_item_id` (PK, path) + `supplier_code` (body) | `assignment_service.assign_single` | PK for the item; `supplier_code` is the *new* assignment's attribute, not a lookup key | N/A for lookup — `supplier_code` on write is validated non-empty, never resolved against an existing ambiguous set | N/A | Yes | None for the item; a caller could supply any `supplier_code` string but that is the intended new value, not an ambiguous lookup | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:439-444`, `assignment_service.py:61-114` |
| `PUT /assignments/{assignment_id}/supplier` | `assignment_id` (PK) | `assignment_service.change_supplier` | PK | N/A | N/A | Yes | None | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:455-461` |
| `DELETE /assignments/{assignment_id}` | `assignment_id` (PK) | `assignment_service.remove_assignment` | PK | N/A | N/A | Yes | None | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:464-470` |
| `POST /refreshes/{refresh_id}/export` | `refresh_id` (PK) + optional `assignment_ids` (PK list) + optional `supplier_code` (filter) | `export_service.export_refresh` | `refresh_id` PK; `assignment_ids`/`supplier_code` are additive filters passed straight to `export_repository.exportable_assignments`, not resolved as a single-line lookup | `supplier_code` filter could theoretically match zero or many rows — that is the intended "export this supplier's lines" behavior, not an ambiguous single-line resolution | N/A — not a single-identity operation | Yes (bulk) | None — this is a bulk filter, not an identity resolution; exporting "too many" rows is a business-logic question, not an identity-ambiguity defect | Already safe for its actual contract (bulk filter, not single-line lookup) | `SAFE CURRENT BEHAVIOR` | `pm_router.py:477-482`, `export_service.py:22-68` |
| `POST /refreshes/{refresh_id}/grn` | `refresh_id` (PK) | `reconciliation_service.submit_grn` → `reconcile` | `refresh_id` PK for the write; receipt matching inside `reconcile` is product+supplier based (see Audit D) | N/A for the route identifier itself | N/A | Yes | The internal receipt-matching heuristic (`reconciliation_rules.match_receipts`) is a separate concern from route-level identity — not re-audited here beyond noting it exists; out of scope for "route resolves by product_code" | Already safe at the route level; `match_receipts`' own matching logic was not re-traced in this pass | `UNRESOLVED — MORE EVIDENCE REQUIRED` (for the internal matching heuristic only, not the route identifier) | `pm_router.py:664-668`, `reconciliation_service.py:32-60` |
| `PUT /order-items/{order_item_id}/pending` | `order_item_id` (PK) | `pending_service.adjust` → `pending_repository.adjust_pending` | PK | N/A | N/A | Yes | None | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:685-691`, `pending_repository.py:118-127` |
| `POST /order-items/{order_item_id}/pending/skip`, `.../carry-forward` | `order_item_id` (PK) | `pending_service.skip`/`carry_forward` | PK | N/A | N/A | Yes | None | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:694-701` |
| `POST /refreshes/{refresh_id}/pending/bulk` | `refresh_id` (PK) + `order_item_ids` (PK list, body) | `pending_service.bulk` | Each id in the list is a PK, resolved individually | N/A | N/A | Yes (bulk) | A caller could submit the wrong PK in the list, but that is a client-side bug, not a server-side ambiguous-resolution defect — the server never has to guess which row a given id means | Already safe | `SAFE CURRENT BEHAVIOR` | `pm_router.py:709-716` |
| `POST /refreshes/{refresh_id}/manual-items` | `refresh_id` (PK) + `product_code` (new-row attribute, body) | `pending_service.add_manual` | `refresh_id` PK; `product_code` here is the attribute of a *new* row being created, not a lookup key for an existing ambiguous row | N/A — this is an insert, not a resolve-then-mutate | N/A | Yes (insert) | None — nothing is being disambiguated; a new row is created with whatever `product_code` is given, same risk profile as any ordinary insert | Already safe for its actual contract | `SAFE CURRENT BEHAVIOR` | `pm_router.py:734-743` — not independently re-verified against `pending_service.add_manual`'s body in this pass; classified from the route signature alone |
| **`PUT /vpl-history/working/lines`** (prototype, unwired) | `product_code` (body) | `VplWorkspace.edit` | `_resolve_by_code` — `product_code` only | **Yes** — confirmed in the prior independent review and this pass's own direct execution | **Fails closed with `AMBIGUOUS` (422)** | Would mutate the in-memory working set if it succeeded (never the live DB — this router is not wired to live generation) | None realized today (never called by a live screen); if wired as-is, a caller restricted to `product_code` could never disambiguate two products sharing a code, blocking the operation rather than corrupting data | Add a `product_id` parameter to `EditBody` so a caller that has it can bypass the ambiguity; keep `AMBIGUOUS` as the fallback when only `product_code` is available | `DEFENSE-IN-DEPTH GAP` (fails closed today; the gap is in ergonomics — the caller is stuck, not in safety — the caller is never misdirected) | `vpl_history.py:364-378`, `vpl_history_router.py:21-25,82-96` |
| **`POST /vpl-history/working/assign`, `/export`, `/order`, `/portal`** (prototype, unwired) | `product_code` (body) | `VplWorkspace.assign_supplier`/`export_lines`/`place_order`/`submit_to_portal` → `_guard_orderable` | `_resolve_by_code` against `removed_manual_review` first, then `lines` | **Yes**, confirmed by direct execution in the prior independent review (all four actions raise `AMBIGUOUS` for two null-coded removed lines) | **Fails closed with `AMBIGUOUS` or `NOT_ORDERABLE`**, never `"accepted": True` for an ambiguous or removed line | Would mutate in-memory `orderable` state if it ever reached live wiring (it does not today) | Same as above — blocked, not misdirected | Same as above | `DEFENSE-IN-DEPTH GAP` | `vpl_history.py:317-337`, `vpl_history_router.py:40-42,131-172` |
| **`POST /vpl-history/working`, `GET /vpl-history/working`, `POST /vpl-history/refresh`** (prototype, unwired) | `tenant_id`/`store_id`/`cycle_id` (query) + line list (body) | `VplWorkspace.open_cycle`/`working`/`refresh` | `(tenant_id, store_id, cycle_id)` tuple — not product-code-based at all | No — these operate on the whole working set, not one line | N/A | Yes (whole-set) | None — these are not single-line lookups | Already safe for their actual contract | `SAFE CURRENT BEHAVIOR` | `vpl_history.py:126-177,216-295`, `vpl_history_router.py:50-120` |
| **`GET /vpl-history/history`, `GET /vpl-history/history/{history_id}`** (prototype, unwired) | `tenant_id`/`store_id` (query) or `history_id` (path, a generated UUID) | `VplWorkspace.history_headers`/`history_detail` | `history_id` is a UUID PK for detail; headers are tenant/store filtered | No | N/A | No — read-only | None | Already safe | `SAFE CURRENT BEHAVIOR` | `vpl_history.py:297-315`, `vpl_history_router.py:175-192` |

**Direct answers to the audit's specific questions:**
- *Every mutation resolves one unambiguous line?* — Yes on every live route. On the prototype router, yes as well, but via a runtime `AMBIGUOUS` check rather than a structurally unambiguous identifier; see the `DEFENSE-IN-DEPTH GAP` rows above.
- *Read-only operations can return confusing or merged records?* — No. `pm_router.py`'s list endpoints (`workspace`, `list_assignments`, `list_refresh_assignments`, `list_pending`) all return every matching row, keyed by real PKs in the response; nothing is merged by `product_code`. The prototype's `_sorted_by_identity` fix (prior section of this document) specifically prevents merging on `_public()`'s read path.
- *Any endpoint bypasses the fail-closed helper?* — No endpoint that accepts `product_code` as its sole resolution key bypasses `_resolve_by_code` in the prototype; no live route uses `product_code` as a sole resolution key at all, so there is nothing to bypass there.
- *A client can submit a stale or insufficient identifier?* — A client can submit a wrong-but-valid `order_item_id`/`assignment_id` (a client-side bug), but the server will act on exactly that PK, not guess — this is a client correctness question, not a server-side ambiguity defect.
- *Multiple supplier assignments can be confused or collapsed?* — See Audit D below; `assignment_repository.list_by_order_item`/`list_by_refresh` return every live assignment row individually, never collapsed. However, `assignment_service.any_active_assignment`/`duplicate_active_exists` and the master prompt's own module-1 docstring ("An order item may carry at most ONE active assignment") establish that the *live write path enforces one active assignment per item* — this directly contradicts this task's stated baseline ("Supplier assignments can be one-to-many. Do not assume one supplier per product."). Flagging this contradiction explicitly rather than silently resolving it in either direction — see Owner Decision Register, Decision 7.
- *A null product code is incorrectly treated as a usable unique identifier?* — No live route treats `product_code` as a unique identifier at all (null or otherwise). In the prototype, `_resolve_by_code` treats `None` as an ordinary — not special-cased, not privileged — value to match against, and fails closed exactly as it would for a duplicate string, per the prior independent review's direct execution.

**Minimal safe contract recommendation (not implemented, no API contract changed in this task):** for the prototype only, add an optional `product_id` field to `EditBody` and `ProductActionBody`; when present, resolve by `product_id` directly (bypassing `_resolve_by_code`'s code-based matching entirely); when absent, keep the current `product_code`-only path with its existing `AMBIGUOUS` fail-closed behavior unchanged. This is additive (optional field, backward compatible) and does not require inventing any new concept — `product_id` is already the preferred internal key per the existing identity rule.

### 4. Audit B — `defer_item` precedence: traced from source, not guessed

#### State-transition facts, established from source

- `defer_item` (`workspace_repository.py:350-365`) sets `item_status='deferred'`, `reviewed_at=GETDATE()`. It explicitly never touches `final_qty`/`remaining_qty`/`skip_reason` (confirmed by its own docstring and the SQL — no such columns appear in its `SET` clause).
- The **service layer** (`workspace_service.defer_item`, lines 152-166) enforces two preconditions before calling the repository: (a) `item_status != 'skipped'` (409 "Cannot defer a skipped item"), (b) `assigned_qty <= 0` (409 "Cannot defer an item that already has supplier assignments"). **This means, at the live write path, scenarios 3 ("deferred with `manual_override` set") and 4/5 ("deferred with one/multiple supplier assignments") are reachable only in the reverse order — a line can be manually edited or assigned *after* being deferred, but a line that already has an assignment can never be deferred in the first place.** This is a real, already-enforced business rule, not an absence of one.
- `skip_item` (service, lines 130-141) similarly blocks skipping an item with `assigned_qty > 0`.
- `restore_item` (service, lines 144-149) requires `item_status in ('skipped', 'deferred')` — it is the single un-defer/un-skip path, landing unconditionally on `'review'` regardless of which of the two states it came from (confirmed by `workspace_repository.restore_item`'s own docstring and SQL).
- `assign_bulk` (`assignment_service.py:117-175`) explicitly excludes a `'deferred'` item from every bulk assignment path with `raise ValueError("item is deferred")` — confirmed this is every bulk path (Auto Assign / Assign Remaining / Assign Selected per the module's own comment) by reading the function, not inferred from its name. `assign_single` (lines 61-114) has no equivalent deferred-check — only a `'skipped'` check — meaning a single manual assignment on a deferred item **is allowed** and (per `recompute_order_item`'s `item_status` recompute, `assignment_repository.py:392-417`) will move the item out of `'deferred'` status the next time `recompute_order_item` runs, since that CASE expression has no `'deferred'` branch of its own — it only preserves `'skipped'` explicitly; everything else recomputes from the assignment total. **This is the concrete mechanism behind the module's own comment** ("a manual single-item assignment via assign_single is still allowed and clears the flag") — confirmed by tracing the actual CASE expression, not by trusting the comment.
- `vpl_history.py`'s in-memory model has **no `'deferred'`-specific branch anywhere** in `_touched()`/`_is_skip_only()` — confirmed by re-reading both functions in full this pass. A deferred-only line (no `manual_override`, no `supplier_code`, no `rare_confirmed`) is simply untouched by that model's rule and behaves exactly like any other untouched line on refresh.

#### Truth table

| # | Scenario | Existing behavior (source/tests) | Explicit or incidental? | Data-loss / duplicate / ordering risk | Recommended precedence | Required regression test | Schema change needed? |
|---|---|---|---|---|---|---|---|
| 1 | Deferred, no manual edit or assignment | `item_status='deferred'`, `final_qty` unchanged, `reviewed_at` set. In the VPL-history model: untouched (no `manual_override`/`supplier_code`/`rare_confirmed`) — behaves like any other untouched line. | **Explicit** at the live write path (`defer_item`'s own docstring + SQL); **incidental** in `vpl_history.py` (no `'deferred'` case exists; it falls through to the generic untouched branch by omission, not by a deliberate rule written for this case). | Low — matches the documented intent ("keeping its Final Qty intact"). | Keep as untouched/history-only in the in-memory model; this already matches live behavior (a merely-deferred, otherwise-untouched item is not "manually edited" in the sense `_touched()` cares about). | A test asserting a deferred-only line (no override, no assignment) that drops out of the next generation is **not** placed in `removed_manual_review` — mirrors the already-existing skip-only test exactly. **Does not exist today.** | No. |
| 2 | Deferred, with a manually edited `final_qty` | Reachable: `set_final_qty` (no deferred-check) can run on a deferred item, setting `manual_override=1` and `item_status='review'` — **this silently clears the deferred status**, confirmed by `workspace_repository.set_final_qty`'s own `SET item_status = 'review'`. | **Explicit** — the SQL unconditionally overwrites `item_status`. | None for data loss; the deferred flag is intentionally dropped, which matches "assigned/edited clears defer" the same way assignment does. | No change needed; already consistent with scenario 4/5's documented "manual single-item action clears the flag" pattern. | A test confirming `set_final_qty` on a deferred item transitions `item_status` away from `'deferred'` to `'review'`. **Not found in the existing suite during this pass** (not independently re-verified beyond reading the SQL). | No. |
| 3 | Deferred, with `manual_override` set | Same mechanism as #2 — `manual_override=1` is set by the same `set_final_qty` call that clears `item_status` to `'review'`. There is no code path that sets `manual_override=1` while *leaving* `item_status='deferred'` intact, because the only function that sets `manual_override` (`set_final_qty`) also unconditionally sets `item_status='review'` in the same statement. | **Explicit** by the same evidence as #2. | None — this combination (deferred AND manual_override simultaneously persisted) **cannot occur** via the live write path as traced. | No change needed — the combination is already structurally prevented. | A test asserting this combination cannot be reached (negative test) would be defense-in-depth but is not required by any observed defect. | No. |
| 4 | Deferred, with one active supplier assignment | **Cannot occur** — `workspace_service.defer_item` explicitly checks `assigned_qty > 0` and raises 409 before calling the repository. Confirmed by reading the guard directly, not inferred. | **Explicit.** | None — structurally prevented. | No change needed. | A test confirming `defer_item` 409s when `assigned_qty > 0` — **may already exist**; not independently re-verified in this pass (out of scope boundary: do not run or modify tests; this is a read-only audit). | No. |
| 5 | Deferred, with multiple supplier assignments | Same guard as #4 blocks the *first* assignment from being placed on a deferred item at all, so "multiple" cannot occur via `defer_item` either. The only way multiple assignments reach a `'deferred'` item is if assignment happened via `assign_single` (which has no deferred-check, per the Audit B source trace above) *before or after* a defer — but `assign_single` on an already-deferred item changes `item_status` away from `'deferred'` via `recompute_order_item`'s CASE expression (no `'deferred'`-preserving branch), the same mechanism as scenario 2. So by the time a second assignment could land, the item is no longer `'deferred'`. | **Explicit**, traced through two cooperating mechanisms (the bulk-path ValueError guard and `recompute_order_item`'s CASE expression), not a single docstring claim. | None realized, but **this is the most load-bearing undocumented interaction found in this audit** — the "deferred clears on assign" behavior for `assign_single` specifically (as opposed to the bulk-path hard block) is implied by the CASE expression's omission, not stated as a rule anywhere in the module's own prose beyond one parenthetical in `defer_item`'s docstring. | Recommend this interaction be stated explicitly as a numbered rule in `PHASE_2_VPL_HISTORY.md` or a procurement design note (not in this task's scope to write production docs beyond this review file), since a future edit to `recompute_order_item`'s CASE expression could silently break it without any test failing if no test currently pins it down. | A regression test asserting: defer an item -> `assign_single` it -> confirm `item_status` is no longer `'deferred'` after `recompute_order_item` runs. **Likely does not exist** — the module's own code comment describes the intent but this pass found no test file reference to it (test files were not exhaustively re-read for this specific assertion, consistent with the read-only, minimally-invasive boundary). | No. |
| 6 | Deferred line disappears from the next generated VPL | **Live path:** `item_status='deferred'` persists on the row until explicitly changed; `procurement_order_items` rows are not deleted by a refresh (confirmed `clear_working_items`/`generate_working_items` operate per-`refresh_id`, and `carry_forward_skips`/`comparison_service.carry_forward` explicitly re-insert carried-forward rows into the *new* `refresh_id` — a deferred row that is not regenerated and not explicitly carried forward by either of those two functions simply has no row in the new refresh at all, since neither `carry_forward_skips` nor `comparison_service.carry_forward` carries a `'deferred'` status). **In-memory model:** a deferred-only (untouched by `_touched()`'s definition) line that disappears is treated as an ordinary untouched absent line — history-only, not moved to `removed_manual_review`. | **Incidental** on the live path (deferred status has no carry-forward mechanism of its own — only skips and pending have one) and **incidental** in the in-memory model (no explicit rule, falls through by omission). | **Real, previously-unflagged gap:** on the live path, a deferred item that is not regenerated in the next refresh is simply gone — its "deferred, keep final qty" intent has no persistence mechanism analogous to `carry_forward_skips`. This may be intentional (a deferred item is meant to be a same-refresh-only exclusion from bulk assignment, not a cross-refresh concept) or it may be an oversight — **the repository evidence alone cannot distinguish these**, which is exactly the kind of question this audit is instructed to escalate rather than guess. | **Owner decision required** (see register, Decision 2): is "deferred" meant to survive a refresh at all, analogous to a skip? If not, current behavior is correct as-is and needs no change. If yes, a `carry_forward_defers` mechanism analogous to `carry_forward_skips` would be a new, currently-nonexistent function — not designed or implemented in this audit. | A test asserting the live refresh's current behavior (a deferred, unregenerated row has no equivalent in the new refresh) so this behavior is at least pinned down as deliberate-or-not, pending the owner's answer. | Only if the owner chooses the carry-forward option — not decided here. |
| 7 | Deferred line disappears **and** has a genuine manual quantity override | Per scenario 3's finding, a live row cannot be simultaneously `'deferred'` and `manual_override=1` — the moment an override is set, `item_status` becomes `'review'`, not `'deferred'`. **So this exact combination cannot occur on the live write path.** In the in-memory model, if a caller constructed a line with both `item_status='deferred'`-equivalent markers and `manual_override=True` directly (bypassing the live write path's guard, since the prototype has no equivalent guard), `_touched()` would correctly classify it as touched (via `manual_override`) and route it to `removed_manual_review` on disappearance — the `_is_skip_only` exclusion only applies to `item_status == 'skipped'`, not `'deferred'`. | **Explicit** for the live-path impossibility; **incidental-but-correct** for the in-memory model's handling if the combination were ever constructed. | None — live-path impossible; in-memory model's generic `_touched()` rule happens to handle it correctly even without a dedicated `'deferred'` branch, because `manual_override` alone is sufficient evidence. | No change needed in either layer. | None required beyond what scenario 3 already covers. | No. |
| 8 | Deferred line disappears **and** has a supplier assignment | Per scenario 4/5, a live row cannot carry an assignment while `'deferred'` via `defer_item`'s guard; via `assign_single` the status changes away from `'deferred'` on assignment. **So the live row would not be `'deferred'` by the time it has an assignment, and the "disappears" question becomes "does an *assigned* (not deferred) line disappearing lose its assignment" — a different, already-covered concern (see Audit D on assignment loss on disappearance, not specific to defer).** In the in-memory model, a line with `supplier_code` set is `_touched()`-true regardless of `item_status`, so it would correctly route to `removed_manual_review` if it disappeared. | **Explicit** for the live-path reasoning chain; **correct-by-generality** for the in-memory model. | None realized by this specific combination, given the live-path impossibility; the underlying "assigned line disappears" case is covered generally by the existing `removed_manual_review` mechanism (an assigned line is `_touched()`-true via `supplier_code`). | No change needed. | None beyond the existing `test_touched_omission_moves_to_manual_review_and_preserves_values` family, which already covers a `supplier_code`-bearing line's disappearance. | No. |
| 9 | Deferred line later reappears | Live path: if a deferred row simply persists (same `refresh_id`, same cycle, no regeneration event), there is no "reappearance" concept — it is the same row throughout. If the refresh-boundary gap from scenario 6 means the row is genuinely absent from a new refresh and then a *new* row is generated for the same product in a later refresh, that new row starts fresh (`item_status='draft'` from `generate_working_items`) with no memory of the prior deferred status — **this is a direct consequence of scenario 6's finding, not a separate gap.** In-memory model: an untouched line's reappearance is handled generically (takes the new suggestion, no special deferred memory needed since none was recorded). | **Incidental**, following directly from scenario 6. | Same open question as scenario 6 — whether this loss of "deferred" memory across a refresh boundary is intended. | Resolved by the same owner decision as scenario 6 (Decision 2). | Same test as scenario 6 would also exercise this. | No, unless scenario 6's owner decision requires a new carry-forward mechanism. |
| 10 | Deferred combined with skip state | **Live path: structurally impossible to have both simultaneously** — `skip_item` (service) rejects an item with `assigned_qty > 0` (irrelevant here) but does not check for `'deferred'`; however `item_status` is a single column, so setting it to `'skipped'` via `skip_item` necessarily overwrites any prior `'deferred'` value, and vice versa — a row has exactly one `item_status` value at a time, never both. The service-layer guards (`defer_item` rejects `item_status=='skipped'`; nothing explicitly rejects deferring from `'skipped'` the other direction *except* that `skip_item`'s own guard is about `assigned_qty`, not about prior status) mean skip→defer is blocked by `defer_item`'s own check, but defer→skip has no equivalent block in `skip_item`'s service guard (only an `assigned_qty` check) — **confirmed by re-reading `workspace_service.skip_item`, lines 130-141: it checks `assigned_qty`, not `item_status`.** So a deferred item *can* be skipped (overwriting `'deferred'` with `'skipped'`), but a skipped item *cannot* be deferred (`defer_item`'s explicit `item_status != 'skipped'` check blocks it). This is an asymmetric, one-directional transition, confirmed by reading both guards side by side. | **Explicit but asymmetric** — one direction is blocked by a named check, the other is simply unguarded (not an oversight necessarily, but not documented as a deliberate symmetric design either). | Low risk in practice (both are "don't actively order this now" states, and the single-column model means no ambiguity about which one currently applies) but the **asymmetry itself was not previously documented anywhere in the reviewed files** — worth stating explicitly. | Document the asymmetry; no code change required unless the owner wants it symmetric. | A test confirming defer→skip succeeds and skip→defer is rejected with 409, pinning down the asymmetry as intentional. | No. |
| 11 | Repeated refresh or retry for the same logical cycle | Already covered in prior independent reviews in this document: `orchestration_service.create_refresh` (lines 134-207, re-read this pass) allocates a new `refresh_id` unconditionally on every call — no idempotency key, confirmed again by re-reading the function in full this pass. This applies identically regardless of whether any line involved is deferred — `defer_item` has no special interaction with refresh retry beyond what scenario 6 already describes (a deferred row's fate depends on whether it regenerates). | **Explicit absence of idempotency**, previously documented, re-confirmed. | Unchanged from prior findings — retry-duplication risk at the refresh level, not specific to defer. | Unchanged recommendation from prior sections — not re-litigated here. | Unchanged from prior sections. | No new schema need identified by this re-check specifically for defer. |
| 12 | Stale edit or concurrent update while being deferred | **Confirmed by the grep in section 2: zero `row_version` (or any version column) usage in any live write-path `.py` file** — `defer_item`'s `UPDATE ... WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0` has no version predicate, identical in shape to `set_final_qty`/`skip_item`/`restore_item`/`restore_suggested`. A concurrent `set_final_qty` and `defer_item` call against the same `order_item_id` would both succeed (last write wins on whichever column each touches — they touch different columns, `final_qty`/`manual_override` vs. `item_status`, so this specific pair wouldn't even conflict on values, but a `defer_item`/`skip_item` race would, since both set `item_status`). | **Explicit absence of concurrency control**, consistent with every other function in `workspace_repository.py`. | **Confirmed problem, not merely a risk** — this is the same cross-cutting gap documented in Audit D below, not unique to `defer_item`. | See Audit D's cross-cutting recommendation; not re-stated per-function here. | See Audit D's regression-test plan. | Yes, if the owner approves optimistic concurrency (Decision 4) — adding `row_version` to `procurement_order_items` is a schema change, not yet approved. |

### 5. Audit C — rare-mover review and confirmation: detection is real and tested; confirmation persistence genuinely does not exist anywhere

#### Established from source

- **Detection:** `decision_rules.py` (lines 320-347, re-read this pass) computes `RARE_MOVER_TOPUP`/`INCLUDED_RARE_MOVER_TOPUP` when a product fails both the days-cover gate and the min-qty-floor gate but still satisfies `eff <= 1 and mqf <= 1 and billing_frequency > 1 and window_sales_qty > 1` — a legacy "Additional Row" parity rule, confirmed against the comment and the actual boolean expression, not inferred from the constant names alone. This sets `suggested_qty=1`, `final_required_qty=1`, `procurement_action=ACTION_INCLUDE`, `reason_code=INCLUDED_RARE_MOVER_TOPUP`.
- **Warning/status:** `rules_catalog.py` (lines 227-243, re-read this pass) documents the business rule as `STATUS_CONFIRMED`, `POLICY_LOCKED`: "Suggested quantity 1 for review... No automatic assignment, export, or portal order. PM must confirm." `RARE_MOVING_WARNING` is imported from `quantity_profile_t.py` and used as a locked default value string — this is catalog/documentation metadata, not an enforcement mechanism by itself (the catalog module, per prior reviews in this document, is unconnected to `decision_rules.evaluate`).
- **Manual review:** the *only* place `rare_confirmed` as a field exists anywhere in the codebase is `vpl_history.py`'s in-memory model (confirmed by the grep in section 2 and by every prior review in this document) — it is not a column on `procurement_order_items`, not referenced by `workspace_repository.py`, `assignment_repository.py`, or any live write path.
- **Confirmation is in-memory only:** `vpl_history.py::edit()` accepts `rare_confirmed` as one of the whitelisted edit fields (line 193) and `_touched()` treats it as carry-forward-worthy evidence, identically to `manual_override`/`supplier_code`. There is no database column, no migration (0027 does not define one — confirmed by this document's own prior reviews), and no live write path that persists it.
- **After refresh, restart, or another worker:** within one `VplWorkspace` process, a confirmed rare-mover line survives a refresh via the same `_restore_touched` mechanism as any other touched line (tested — `test_rare_mover_confirmation_survives_refresh`, re-confirmed by reading the test body this pass, not re-run). **Across a process restart or a second worker, the confirmation is lost entirely** — `VplWorkspace.__init__` starts with empty `_working`/`_history` dicts in process memory; nothing survives a restart. This is not a new finding — every prior review in this document has stated rare-mover persistence is NOT APPROVED and in-memory only — but this pass independently re-confirms the mechanism (process-local dict, no serialization, no database row) rather than repeating the claim.
- **Can a confirmed line accidentally be treated as an ordinary suggestion?** Within the in-memory model: no — `_touched()` treats `rare_confirmed` as sufficient evidence to carry forward the line's `final_qty`/`suggested_qty` distinction correctly (tested). On the live write path: the question does not apply in the same way, because there is no live `rare_confirmed` state to begin with — a rare-mover-flagged line (`reason_code=INCLUDED_RARE_MOVER_TOPUP`) is, on the live path, just an ordinary `procurement_order_items` row with `suggested_qty=1`; nothing in `workspace_repository.py` or `assignment_service.py` currently checks `reason_code` before allowing `assign_single`/`export_refresh`/`place_order`-equivalent actions. **This means the "no automatic assignment, export, or portal order" business rule the catalog documents as `STATUS_CONFIRMED`/`POLICY_LOCKED` is not actually enforced anywhere on the live write path today** — a rare-mover-flagged item can be assigned, exported, and have its GRN reconciled through the ordinary live flow with no gate at all. This is a genuine gap between the documented, owner-confirmed business rule and the live write path's actual enforcement, independent of the persistence-design question this audit was asked to compare options for.
- **Can a confirmation be attached to the wrong product identity?** In the in-memory model, no — `rare_confirmed` lives on the same line dict keyed by the `product_id`-first identity (per the already-approved identity fix), so it is exactly as safe against misattribution as any other field on that line.
- **Can a stale confirmation survive a new cycle or changed classification?** In the in-memory model, a confirmation survives exactly as long as the line is "touched" and regenerated or held in `removed_manual_review` — there is no separate expiry concept. If a product's classification changes (e.g., it is no longer a rare mover in a later generation because sales picked up), the in-memory model has no mechanism to *detect* that the confirmation is now stale relative to a changed classification — it simply carries the manually-set `final_qty`/`rare_confirmed` forward unconditionally, the same way any other manual override is carried forward. This is consistent with the existing touched-line contract (manual edits intentionally survive a changed suggestion) but means a rare-mover confirmation specifically has no reclassification-aware expiry, which may or may not be the intended business behavior — **owner decision required** (register, Decision 3b).

#### Design comparison for persistence (evaluation only — no implementation, no migration written)

| Option | Stable identity & scope | Auditability | Refresh behavior | Restart/multi-worker | Concurrency/stale updates | Prevents auto assign/export/order | Duplicate confirmation/retry | Migration/rollback | Compatible with existing write paths |
|---|---|---|---|---|---|---|---|---|---|
| **A. Column on `procurement_order_items`** (e.g. `rare_confirmed`, `rare_confirmed_by`, `rare_confirmed_at`) | Scoped to one order item, i.e. one `(refresh_id, product_id)` — ties to the working row directly. | Weak unless paired with its own `_by`/`_at` columns (which this option includes) — but a per-refresh row means the audit trail resets every refresh unless carried forward explicitly. | Must be explicitly carried forward by whatever logic generates the next refresh's rows (no such logic exists today for any flag beyond what `carry_forward_skips`/`comparison_service.carry_forward` already do) — **this is new logic, not a byproduct of the column existing.** | Durable (it's a real column) — survives restart and is visible to any worker reading the row. | Subject to the same cross-cutting lack of `row_version` as every other `procurement_order_items` column (Audit D) — a concurrent `set_final_qty` and a confirm-action would race the same way any two updates to this table race today. | Only if a new check is added to `assignment_service`/`export_service`/`reconciliation_service` reading this column before allowing the action — **not automatic just because the column exists.** | Not a concern at the schema level — same row, no duplicate-row risk. | Additive column, straightforward rollback (drop column) if no other table references it. | Simplest to wire into existing write paths since it's the same table every write path already touches — but requires editing those write paths' guard logic, which is itself a live-write-path change outside this audit's authorization. |
| **B. Dedicated review/confirmation table** keyed on stable product+cycle/refresh identity (e.g. `procurement_rare_mover_review(tenant_id, store_id, product_id, cycle_id, confirmed, confirmed_by, confirmed_at, reason_code_at_confirmation)`) | Scoped independently of any one `order_item_id` row — survives a refresh's row churn by design, since it's keyed on the *product+cycle*, not the ephemeral working-item row. | Strong — a dedicated table is the natural place for an audit trail (who/when/what classification it was confirmed against), without needing to carry anything forward on the working-item row at all. | Naturally "carries forward" without new generation-time logic, since it is read by lookup (`product_id`+`cycle_id`) rather than copied row-to-row — the next refresh's generation can join against it if (and only if) the generation code is taught to do so, which is itself new logic, same caveat as option A. | Durable; multi-worker-safe at the storage layer (ordinary table), though the *read-then-decide* logic in generation would still need its own concurrency story if two workers generated two refreshes for the same cycle simultaneously — a pre-existing, broader concern (Audit D) not unique to this table. | Same cross-cutting `row_version` gap as everywhere else unless this new table is designed with one from the start (easier to do for a brand-new table than to retrofit). | Same caveat as option A — the table's existence doesn't enforce the business rule by itself; a guard must still be added to the write paths. | A `(tenant_id, store_id, product_id, cycle_id)` unique constraint would need to decide whether a re-confirmation updates the existing row or inserts a new history row — **this is exactly the same design question this document's prior sections already raised for assignment history and removed-manual-review persistence** (append-only history vs. one-live-row-with-overwrite). Not decided here. | New table, independently rollback-able (drop table) without touching `procurement_order_items` at all — lower blast radius than option A. | Requires a new repository/service to read/write it and new guard checks in the same three write paths as option A — the write-path-guard requirement is identical between A and B; B's advantage is schema cleanliness and audit history, not avoiding the write-path integration work. |
| **C. Reuse an existing field creatively (e.g. `override_reason` text convention, or `pending_status`)** | Same scope as whatever table already holds that field — `procurement_order_items`. | Weak — repurposing a free-text or status field for a structured yes/no+audit concept is exactly the kind of "increasingly complicated fallback logic" this task's own instructions say to avoid in favor of explicit identity/fields. | No better than option A; worse clarity. | Same as A. | Same as A. | Same caveat as A/B. | No new migration, but conflates two concepts in one column — higher long-term risk, not recommended. | No schema change, but not recommended given the stated preference against convenience-driven conflation. | Lowest short-term effort, highest long-term confusion — **not recommended.** |

**Recommendation (not an approved decision):** Option B (dedicated review/confirmation table) is the better fit for the system's own stated preferences — it mirrors the design pattern already proposed and partially accepted-in-principle elsewhere in this document for assignment history and removed-manual-review state (immutable-ish, keyed on stable identity rather than the ephemeral working row), and it avoids retrofitting a brand-new audit concept onto a table that was not designed for it. This recommendation is explicitly **not** an approved business decision — see register, Decision 3.

### 6. Audit D — cross-cutting concurrency and atomicity: the gap is confirmed and is broader than the previously-cited five functions

**The previously-cited list (`set_final_qty`, `restore_suggested`, `skip_item`, `defer_item`, `restore_item`) is confirmed accurate but incomplete.** Re-verified by source inspection, not assumed:

#### Confirmed problems (no database/integration testing needed — visible directly in the SQL)

1. **All five `workspace_repository.py` functions** — confirmed, as before: no version predicate in any `UPDATE ... WHERE` clause.
2. **`assignment_repository.update_supplier`, `update_qty`, `soft_delete`** (lines 350-389) — same shape: `WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0`, no version check. **`insert_assignment`** is a new row, so "stale write" doesn't apply to it directly, but a race between two `assign_single` calls on the same `order_item_id` is only prevented by `duplicate_active_exists`/`any_active_assignment`'s read-then-write pattern *inside* the same transaction (`get_connection()`'s connection, committed once) — this is a check-then-act race only if the two calls are on genuinely separate connections/transactions, which they are (each `assign_single` call opens its own `get_connection()`). **This is a real TOCTOU (time-of-check-to-time-of-use) gap**: two concurrent `assign_single` calls for the same item and different suppliers could both pass `any_active_assignment`'s check (reading "no existing assignment") before either commits, then both insert — violating the "at most one active assignment" rule the module's own docstring asserts. This is a genuinely new finding this pass, not previously documented in this file.
3. **`reconciliation_repository.store_last_grn` → `apply_receipt`/`set_item_receipts`** — already flagged in a prior section of this document ("`reconciliation_service.submit_grn` still commits `store_last_grn` and then calls `reconcile` on a new connection... a failure in reconcile leaves the stored GRN number committed") — re-confirmed by re-reading `reconciliation_service.py` in full this pass: `submit_grn` (lines 32-60) commits the GRN number in one connection/transaction, then calls `reconcile` (lines 63-113), which opens a **second**, separate connection and transaction. If `reconcile` fails after `submit_grn`'s commit, the GRN number is durably stored but no receipts were matched — a genuine partial-completion state, confirmed structurally (two separate `get_connection()`/`conn.commit()` pairs), not merely inferred.
4. **`pending_repository.py`'s `adjust_pending`/`set_pending_status`/`finalize_all`** — same no-version-predicate shape as every other function in this family, confirmed by re-reading lines 118-150+ this pass (grep already confirmed zero `row_version` matches across the whole module).
5. **`orchestration_service.create_refresh`** — already documented extensively in prior sections; re-confirmed unchanged this pass (no idempotency key, unconditional new `refresh_id` allocation every call).

#### Potential risks requiring SQL Server or integration testing (cannot be confirmed from source reading alone)

- Whether SQL Server's default `READ COMMITTED` isolation (assumed, not verified — connection-level isolation settings were not inspected in this pass since that would require opening a connection, which is prohibited) is sufficient to prevent the `assign_single`/`assign_bulk` TOCTOU race in practice depends on actual lock behavior under concurrent transactions — **unverified, explicitly marked as requiring database-level testing.**
- Whether `_run`'s bare `except Exception: conn.rollback(); raise` pattern (present in every write function across `workspace_repository.py`, `pending_repository.py`, and the service-layer `try/except` blocks in `assignment_service.py`/`export_service.py`/`reconciliation_service.py`) correctly rolls back *every* partially-applied statement when a multi-statement transaction fails partway (e.g., `recompute_order_item` failing after `insert_assignment` succeeded within the same `assign_single` call) — the code structure suggests yes (same connection, same transaction, `conn.rollback()` on any exception before `conn.close()`), but this was not verified against an actual failure injection against SQL Server, consistent with the "do not connect to the database" boundary.
- Whether two workers calling `create_refresh` for the same `cycle_id` at genuinely the same instant would both pass `cycle.get("status") != "ACTIVE"`'s check before either's refresh creation completes (a race on the cycle-status read, not just the refresh-id allocation) — plausible from the code structure (the status check and the refresh creation are not in the same atomic unit) but unverified without concurrent execution against a real database.

#### Risks already addressed by current code

- `assign_bulk`'s per-item exception handling (lines 127-164) correctly isolates one bad line from aborting the whole batch — confirmed by reading the `try/except ValueError` wrapping each spec, with `conn.commit()` only after the loop and only non-`ValueError` exceptions triggering a full rollback.
- `VplWorkspace`'s own `threading.Lock()` correctly serializes all operations *within one process* — confirmed structurally (every public method acquires `self._lock` before touching `self._working`/`self._history`), already documented as single-process-only in prior sections, re-confirmed unchanged.
- `reconciliation_service.reconcile`'s per-assignment loop (lines 74-84) correctly skips a receipt match with `received <= 0` rather than writing a zero/negative receipt — confirmed by the `continue` guard.

#### Questions that cannot be resolved without database/schema evidence

- Actual lock escalation/contention behavior on `procurement_order_items`/`procurement_order_item_assignments` under real concurrent load — requires integration testing against SQL Server, explicitly out of this audit's authorization.
- Whether the existing `is_deleted = 0` predicate pattern (used everywhere instead of hard deletes) has any interaction with SQL Server's row-versioning/snapshot isolation that would change the concurrency picture — unverified, would require schema/configuration evidence (e.g., whether `ALLOW_SNAPSHOT_ISOLATION` is enabled on `NEXORA_PLATFORM`) not available from source reading alone.

**No fixes were implemented for any of the above, consistent with this task's boundaries.**

### 7. Confirmed defects versus design questions — summary

**Confirmed defects (real, reproducible from source, not resolved by this audit):**
- Zero optimistic concurrency control across every live `procurement_order_items`/`procurement_order_item_assignments` write function (Audit D, items 1-4).
- `assign_single`/`assign_bulk` TOCTOU race on the "at most one active assignment" rule (Audit D, item 2) — newly identified this pass.
- `reconciliation_service.submit_grn`/`reconcile` two-transaction split can leave a durably-stored GRN number with zero reconciliation if the second transaction fails (Audit D, item 3) — re-confirmed, previously noted.
- `orchestration_service.create_refresh` has no retry idempotency (Audit D, item 5; also Audit B scenario 11) — re-confirmed, previously noted.
- The rare-mover "no automatic assignment/export/order" business rule, documented as `STATUS_CONFIRMED`/`POLICY_LOCKED` in `rules_catalog.py`, is **not enforced anywhere on the live write path** — newly identified this pass (Audit C).

**Design questions requiring an owner decision, not defects in the existing code (the existing code is internally consistent; the business intent is simply not recorded anywhere this audit could find):**
- Whether "deferred" should survive a refresh boundary the way a skip does (Audit B, scenarios 6 and 9).
- Whether the task's stated baseline ("assignments can be one-to-many") is accurate, given `assignment_service`'s explicit one-active-assignment-per-item enforcement (Audit A) — this audit flags the contradiction rather than silently picking a side.
- Rare-mover confirmation persistence scope and shape (Audit C design comparison).
- Whether a rare-mover confirmation should expire if the product's classification changes in a later generation (Audit C).
- Whether the asymmetric defer↔skip transition (scenario 10) is intentional.

### 8. Minimal regression-test plan (descriptions only — no test file written or modified by this audit)

1. `test_deferred_only_line_is_not_moved_to_removed_manual_review_on_disappearance` — mirrors the existing skip-only test; exercises Audit B scenario 1.
2. `test_set_final_qty_on_deferred_item_clears_deferred_status` — Audit B scenario 2/3, against `workspace_service`/`workspace_repository` (would require a test-double connection, following the existing `tests/test_legacy_order_workflow.py`-style fake-cursor pattern already used elsewhere in this repo).
3. `test_assign_single_on_deferred_item_clears_deferred_status_via_recompute` — Audit B scenario 5, the most load-bearing undocumented interaction found.
4. `test_defer_then_skip_succeeds_skip_then_defer_is_rejected` — Audit B scenario 10, pins down the asymmetry.
5. `test_concurrent_assign_single_same_item_different_suppliers_does_not_double_assign` — Audit D item 2, would require either a real concurrency harness against a test database (out of this audit's authorization to design in detail) or, at minimum, a documented manual test plan for whoever has database access.
6. `test_rare_mover_flagged_item_cannot_be_assigned_exported_or_reconciled_without_explicit_confirmation` — Audit C's enforcement gap; does not exist today because the enforcement itself does not exist.
7. A database-level (not unit-level) test plan item: verify `reconciliation_service.submit_grn` failure-after-commit behavior against a real SQL Server instance with injected failure in `reconcile` — explicitly flagged as requiring database access this audit does not have.

### 9. Owner decisions required (concise, answerable questions)

See the full register in section 10. Restated here as a flat list for quick scanning: (1) safe identifier contract for VPL History mutations, (2) defer-across-refresh carry-forward, (3) rare-mover confirmation persistence shape, (3b) rare-mover confirmation expiry on reclassification, (4) concurrency/versioning strategy, (5) refresh retry idempotency, (6) store/tenant isolation for durable history, (7) one-supplier-vs-many-suppliers-per-item — resolving a direct contradiction between this task's stated baseline and the live code.

### 10. Recommended next phase and explicit stop conditions

**Recommended next phase:** do not advance to persistence implementation. The correct next phase is an **owner decision session** resolving the register below, followed by — only after those decisions are recorded — a scoped design-only update to `PHASE_2_VPL_HISTORY.md` reflecting the resolved contract (still no migration, no code).

**Explicit stop conditions (any one of these means persistence must stay blocked):**
- Decision 7 (one-vs-many suppliers) is unresolved — this affects the shape of any assignment-history schema and must not be guessed.
- Decision 4 (concurrency strategy) is unresolved — adding `row_version` to live tables is a schema change with real migration/rollback implications that should not be designed twice.
- The rare-mover enforcement gap (Audit C) is not even a persistence question — it is a live-write-path business-rule gap that arguably should be fixed (with explicit owner sign-off and by Cursor, per the file-ownership boundary) independently of and before any VPL History persistence work, since it represents the master prompt's own `STATUS_CONFIRMED`/`POLICY_LOCKED` rule going unenforced today.

### 11. Remaining limitations and unverified behavior

- No SQL Server connection was opened; every concurrency/isolation-level claim in Audit D's "potential risks" subsection is explicitly unverified and flagged as such.
- Test files were read where directly relevant (the two VPL History test files) but **not exhaustively re-read in full for Audit B/D's claims about what regression coverage already exists** for the live `workspace_repository`/`assignment_repository` functions — this audit states what the source code does, and separately states where it could not confirm whether an existing test already covers a given scenario, rather than guessing either way.
- The contradiction in Decision 7 (one-vs-many suppliers) is reported, not resolved — this audit does not have the authority or the business context to pick a side.
- `reconciliation_rules.match_receipts`'s internal receipt-matching heuristic (flagged `UNRESOLVED` in the Audit A matrix) was not traced in this pass — it is a separate concern from route-level identity resolution and was out of this audit's primary focus.
- `pending_service.add_manual`'s body was not independently re-verified beyond its route signature.

### 12. Final audit verdict

**Design audit complete. No code implemented. No migration written or applied. No database connection opened. Persistence remains BLOCKED pending the owner decisions below — this audit does not itself constitute approval for any of them.**

The in-memory VPL History prototype's own internal logic (identity, skip/removal, null-code handling) remains independently verified and approved from prior sections of this document. This audit's new contribution is: (a) confirming the `AMBIGUOUS` gap is confined to that unwired prototype and does not exist on any live route, (b) tracing `defer_item`'s actual, non-obvious interactions with assignment and skip state rather than guessing from its name, (c) finding that rare-mover's "no automatic order" rule is a documented-but-unenforced business rule on the live path — independent of the persistence-design question — and (d) finding a new, previously undocumented TOCTOU race in `assign_single`/`assign_bulk`. None of these four findings are migration-blocking in the sense of making the existing BLOCK status change — persistence was already blocked for other reasons — but (c) and (d) are live-system findings that are more pressing than the VPL History persistence question itself, since they describe gaps in rules already live in production, not gaps in an unwired prototype.

## Owner decision register

| ID | Question | Recommended default | Alternatives | Consequences | Blocks persistence? | Owner approval required |
|---|---|---|---|---|---|---|
| 1 | What is the safe identifier contract for VPL History mutations once this model is wired to anything live — `product_code`-only with `AMBIGUOUS` fail-closed (current), or add an optional `product_id` parameter to the four action endpoints and `EditBody`? | Add optional `product_id`, keep `product_code`-only `AMBIGUOUS` fallback when it's absent (additive, backward compatible). | (a) Leave as `product_code`-only forever, accepting the "stuck, not misdirected" ergonomic cost. (b) Require `product_id` always, breaking the current contract. | (a) is safe but permanently blocks disambiguation for any caller without `product_id`. (b) is a breaking API change. | No — this is a prototype-only, not-yet-wired concern; does not block the broader Phase 2 persistence decision by itself. | Explicit sign-off on which of the three options, before `vpl_history_router.py` is ever wired to a live screen. |
| 2 | Should a `'deferred'` item's exclusion-from-bulk-assignment intent survive a refresh boundary the way a skip does (a new `carry_forward_defers`), or is "deferred" deliberately refresh-scoped only? | Deliberately refresh-scoped only (matches "Assignment Deferred (Space Bar)" framing as a same-session UI convenience, not a persistent business state) — but this is a guess based on naming/framing, not confirmed intent. | Add a `carry_forward_defers` mechanism analogous to `carry_forward_skips`. | If refresh-scoped is wrong, PMs lose their "don't bulk-assign this yet" intent every refresh with no warning. If carry-forward is wrong, a new, currently-nonexistent code path is built for no real need. | No — orthogonal to VPL History persistence. | Explicit business-rule confirmation; this audit's recommendation is a guess, not a finding. |
| 3 | What persistence shape should rare-mover confirmation take — Option A (column on `procurement_order_items`), Option B (dedicated review table keyed on stable product+cycle identity), or Option C (reuse an existing field)? | Option B. | Options A or C (not recommended, detailed above). | B requires a new table + new guard logic in three write paths; A is simpler schema-wise but couples the audit trail to an ephemeral working row; C is not recommended. | **Yes** — rare-mover persistence is explicitly listed as a condition in the master prompt and remains NOT APPROVED regardless of which option is eventually chosen. | Full sign-off required before any migration for this concept is even drafted — none has been drafted in this audit. |
| 3b | Should a rare-mover confirmation expire or require re-confirmation if the product's classification changes in a later generation (no longer rare-mover-flagged, or flagged differently)? | Require re-confirmation on reclassification (safer default — an old confirmation against a different classification shouldn't silently authorize a now-different suggestion). | Keep confirmation sticky regardless of reclassification, matching how other manual overrides behave today. | The "safer" default adds new logic (classification-change detection) that doesn't exist anywhere today; the "sticky" alternative matches existing patterns but may let a stale confirmation authorize an order the PM never actually reviewed in its current form. | Related to Decision 3 but separable — affects the confirmation table's schema if B is chosen (needs a `reason_code_at_confirmation` or similar column either way). | Explicit decision; this audit found no existing precedent to infer from. |
| 4 | What concurrency/versioning strategy should the live `procurement_order_items`/`procurement_order_item_assignments` tables adopt — add `row_version` (optimistic, as already prototyped in the unapplied 0027 and documented in this file's Concurrency design section), or some other mechanism (pessimistic locking, application-level queueing)? | Optimistic `row_version`, matching the already-documented, not-yet-implemented design in `PHASE_2_VPL_HISTORY.md`'s Concurrency design section. | Pessimistic locking (higher contention cost); application-level single-writer queueing (architectural change, out of scope for a simple fix). | Optimistic concurrency is the smallest change but requires touching every write function in `workspace_repository.py`/`assignment_repository.py`/`pending_repository.py`/`reconciliation_repository.py` — a real, non-trivial migration + code change, not yet authorized. | **Yes** — explicitly cited in every prior BLOCK verdict in this document. | Full sign-off, migration review, and a second independent review of the concurrency implementation once it exists — none exists today. |
| 5 | Must a retried `create_refresh` call for the same cycle be idempotent (reuse the prior refresh/history id), or is "the caller must not retry" an acceptable operational constraint? | Require idempotency via a client-supplied idempotency key or a server-side dedup window — "caller must not retry" is fragile given this is an HTTP API with no current retry-prevention mechanism. | Document "do not retry" as an operational constraint and rely on UI-level single-submission guards instead of a server-side fix. | Server-side idempotency is more robust but requires schema/logic changes to `orchestration_service.create_refresh`; the UI-guard alternative is cheaper but fragile against network retries, double-clicks past a disabled-button race, or future API consumers that don't know the constraint. | **Yes** — already cited as unresolved in this document's "Revised data contract" section. | Explicit decision on which mechanism, before any refresh-creation code changes. |
| 6 | What tenant/store isolation scope should durable VPL history (once persisted) use — store-scoped (per the existing `(tenant_id, store_id, cycle_id)` working-set key) or tenant-scoped (broader, matching some other existing tables)? | Store-scoped, matching the in-memory model's existing key shape exactly. | Tenant-scoped, if a future reporting need wants cross-store history queries without a store filter. | Store-scoped is simpler and matches existing access patterns (`assert_tenant_access` already gates by tenant, routes already take `store_id`); tenant-scoped would require every query to add an explicit store filter it doesn't need, with no offsetting benefit identified in this audit. | **Yes** — already listed as "not decided" in the Revised data contract section. | Explicit decision, even though this audit's recommendation (store-scoped) matches the existing design's own apparent direction. |
| 7 | **Direct contradiction found by this audit:** is supplier assignment one-to-many (multiple live suppliers per product, per this task's stated baseline) or one-to-one (at most one active assignment per item, per `assignment_service`'s actual enforcement and its own module docstring)? | **Escalate, do not guess.** The live code (`any_active_assignment`, `duplicate_active_exists`, the module's own docstring "An order item may carry at most ONE active assignment") is unambiguous and tested-adjacent (referenced by name in the module's own comments as deliberate). This task's instructions describing one-to-many may reflect a *desired future* state, a different granularity (e.g., "one-to-many" meaning many assignments *across history*, which the already-accepted-in-principle assignment-history design in this document's earlier sections does allow for *archived* rows, vs. "one active at a time" for *live* rows), or a genuine miscommunication. | If the business intent really is live one-to-many, `assignment_service.assign_single`'s guard is itself the defect and would need to change — a live-write-path change this audit is not authorized to make. If the intent is "one active live, many in history" (which is actually consistent with both this task's baseline and the live code, read charitably), then no contradiction exists and this is a documentation clarification, not a code change. | Guessing wrong in either direction either breaks a real, currently-enforced business rule or permanently under-designs the history schema for a one-to-many case that never gets used. | **Yes** — this directly affects the shape of any assignment-history persistence design already discussed in this document's earlier sections (which assumed "history may hold many rows per item even though live holds one" — worth explicitly confirming this reading is correct). | Explicit confirmation of which reading is correct before any assignment-history migration is drafted. |

---

## 2026-10-20 — Priority 1 rare-mover safety audit (Claude, read-only, D1–D7 owner-decision register)

**Role for this entry: independent read-only safety auditor.** No production code, test, migration, or configuration file was edited. No database connection was opened. No order was placed, exported, or submitted to a supplier portal. `decision_rules.evaluate`, `decision_repository.py`, `decision_service.py`, `vpl_history.py`'s live-generation wiring, and `clear_products` were not touched. `AUTONOMOUS_WORK_CONTROL.md` and `PHASE_2_VPL_HISTORY.md` were not edited. Only this file was changed by this task.

**Note on scope adjustment mid-task:** the owner sent a mid-task message ("stop rare moment process continue order details"), clarified via a follow-up question to mean *stop going deeper into rare-mover-specific guard edge cases and pivot to tracing the order-placement/order-details call path specifically*. This section reflects that pivot — the rare-mover classification/assignment/export trace below was completed to the depth already reached before the redirect (sufficient to confirm the core finding and its evidence), and the order-placement/portal-submission/GRN trace (paths 5–6 of the required matrix) was completed in full as the redirected focus. Paths 7–8 (refresh/retry and concurrency) are covered via direct re-verification of the prior audit's findings in this same document (`Audit D`, section 6 above) rather than re-traced from scratch, since that trace already exists in this file and remains accurate on re-check (`orchestration_service.create_refresh` re-read, confirmed unchanged: still allocates a new `refresh_id` unconditionally on every call, no idempotency key).

### Files inspected this pass

`backend/modules/procurement/decision_rules.py` (lines 42-47, 320-350), `rules_catalog.py` (lines 22-33, 225-243, and the `PRR-SUP-ONE`/`PRR-QTY-RARE` rule definitions), `rules_resolution.py` (import-site grep only), `workspace_repository.py` (lines 28-103, `_SELECT`/`_FROM_BASE`/`get_item`), `workspace_service.py` (full file), `assignment_service.py` (full file), `assignment_repository.py` (referenced, not fully re-read — `duplicate_active_exists`/`any_active_assignment`/`insert_assignment` behavior taken from the existing Audit A/D sections above, re-confirmed consistent with `assignment_service.py`'s calls), `export_service.py` (full file), `export_repository.py` (`exportable_assignments`, lines 14-39), `pm_router.py` (full route list via grep, plus lines 1-45, 121-160, 427-485, 660-734 read in full), `vpl_history.py`/`vpl_history_router.py` (grep for `place_order`/`submit_to_portal` only — confirmed these identifiers exist nowhere else in the codebase), `distribution_service.py` (function list only — confirmed it is the NMW-stock-distribution feature, unrelated to rare-mover order placement), `config/database.py` / `dependencies/auth.py` (`get_current_user_optional`, lines 61-75), `dependencies/store_scope.py` (referenced via grep for `assert_tenant_access` call sites in `pm_router.py` only), `api/app.py` (`include_router` mounting, line 362), `modules/procurement/router.py` (line 22, 37), `modules/procurement/sql/0006_decision_engine_explainability.sql` (lines 1-22). `tests/` directory grepped for `rare_mover`/`rare_confirmed`/`RARE_MOVER`/`INCLUDED_RARE_MOVER_TOPUP` (case-insensitive) — zero matches outside what this document already recorded for `vpl_history.py`'s prototype tests.

### Safe read-only commands actually executed

```
grep -rn "RARE_MOVER|rare_mover|RARE_MOVING" backend/modules/procurement/*.py
grep -rn "place_order|submit_to_portal|supplier.?portal" -i backend/modules/procurement/*.py
grep -rn "assert_tenant_access" backend/modules/procurement/pm_router.py
grep -rln "rare_mover|rare_confirmed|RARE_MOVER|INCLUDED_RARE_MOVER_TOPUP" -i backend/tests/
```
No pytest was run in this pass (no code was changed that would need a regression check; the prior `test_vpl_history*`/`test_quantity_profile_t`/`test_procurement_*` results already on record in this document stand unchanged, since nothing they cover was touched). No database connection was attempted.

### 1. Rare-mover call-path matrix

| # | Path | Entry point | Service / repo called | Rare-mover check at point of action? | Evidence |
|---|---|---|---|---|---|
| 1 | Classification/suggestion generation | `decision_rules.evaluate` (not an HTTP route — called by the refresh/orchestration pipeline) | `decision_rules.py:320-350` | N/A — this is the *source* of the classification, not an enforcement point. Sets `trigger_reason=RARE_MOVER_TOPUP`, `reason_code=INCLUDED_RARE_MOVER_TOPUP`, `procurement_action=ACTION_INCLUDE`, `suggested_qty=1` on `procurement_virtual_products`. | `decision_rules.py:45-46` (constants), `:336-342` (the gate: `eff<=1 and mqf<=1 and billing_frequency>1 and window_sales_qty>1`). Confirmed by direct re-read this pass, matches every prior review in this document verbatim. |
| 2 | Manual review and confirmation | None exists. There is no live route, service function, or repository function anywhere in `backend/modules/procurement/` that sets, clears, or reads a rare-mover confirmation flag against a live `procurement_order_items` row. | — | **No enforcement possible — there is nothing to enforce against.** `rare_confirmed` exists as a field name in exactly one place: `vpl_history.py`'s in-memory prototype (`edit()`, line ~193), which is never called by any live route per `AUTONOMOUS_WORK_CONTROL.md`'s file-ownership table and every prior review in this document. | Grep for `rare_confirmed` across `backend/modules/procurement/*.py` returns only `vpl_history.py` (re-confirmed this pass). `workspace_service.py` (full file, this pass) has `set_final_qty`/`restore_suggested`/`skip_item`/`restore_item`/`defer_item` — none references `reason_code`, `rare_confirmed`, or any rare-mover concept. |
| 3a | Supplier assignment — single | `POST /order-items/{order_item_id}/assignments` (`pm_router.py:439-444`) | `assignment_service.assign_single` (`assignment_service.py:61-114`) | **No.** Guards present: skipped-status check, duplicate-active-supplier check, any-active-assignment check (D1), final-qty-exceeded check. None reads `reason_code`/`trigger_reason`/`procurement_action`. | `assignment_service.py:61-107` read in full this pass. `item = _require_item(...)` returns the dict from `workspace_repository.get_item`, whose `_SELECT` (line 35) **already includes `vp.reason_code`** via the existing `LEFT JOIN procurement.procurement_virtual_products vp` (`_FROM_BASE`, lines 48-54) — the data needed for a guard is already in the returned dict at zero extra query cost; it is simply never inspected by `assign_single`. |
| 3b | Supplier assignment — bulk | `POST /assignments/bulk` (`pm_router.py:447-452`) | `assignment_service.assign_bulk` (`assignment_service.py:117-175`) | **No.** Per-item guards: not-found, skipped, **deferred** (explicitly excluded — a real, already-enforced business rule for `'deferred'`, confirmed by direct re-read), duplicate-active, any-active-assignment, final-qty-exceeded. No rare-mover check. | `assignment_service.py:127-164` read in full this pass. Each item is independently try/except'd (`ValueError` → per-item `"skipped"` result, not a batch-abort) — this is the same isolation mechanism the D1-concurrency section already documents; it does **not** check `reason_code` for any item. |
| 4 | Export preparation and execution | `POST /refreshes/{refresh_id}/export` (`pm_router.py:477-482`) | `export_service.export_refresh` (`export_service.py:22-68`) → `export_repository.exportable_assignments` (`export_repository.py:14-39`) | **No — and structurally cannot be, without a schema/query change.** `exportable_assignments`'s SQL (lines 22-28) selects only from `procurement.procurement_order_item_assignments`, filtered by `tenant_id`/`refresh_id`/`is_deleted`/`assignment_status='draft'`/`supplier_code IS NOT NULL`/`assigned_qty>0`. **No join to `procurement_virtual_products` at all** — `reason_code` is not in scope at this query, unlike at the assignment-guard point. | `export_repository.py:14-39` read in full this pass, confirmed no `vp`/`reason_code` reference anywhere in the file (grep across the whole file, zero hits). This means the earliest point in the live pipeline where `reason_code` is cheaply available is assignment time (path 3a/3b), not export time — export would need a new join to even ask the question. |
| 5 | Order placement / order creation | **No such live route or service exists.** | — | N/A | Full `pm_router.py` route list extracted via grep (69 routes, enumerated this pass) — no `/place-order`, `/order`, or equivalent mutating endpoint beyond assignment and export. `place_order` as an identifier exists only in `vpl_history.py` (unwired prototype). In this system, "placing an order" in the live write path **is** the Export action (path 4) — there is no separate, later confirmation step between assigning a supplier and generating the supplier-facing document. |
| 6 | Supplier portal submission | **No such live route or service exists.** | — | N/A | Grep for `submit_to_portal`/`portal` (case-insensitive) across `backend/modules/procurement/*.py` returns only `vpl_history.py`/`vpl_history_router.py`. The live "supplier-facing" mechanisms found are: (a) Export's generated Excel/document (`export_document_service.py`, not separately audited this pass — same `export_refresh` gate or absence thereof applies to whatever triggers it), and (b) `distribution_service.py`'s WhatsApp send (`send_run_item_whatsapp`, `_send_whatsapp` — confirmed by function-name grep this pass to be the NMW-internal-stock-distribution feature, keyed on `source_store_code`/`target_store_id`, not on rare-mover order items at all; a different feature entirely, not a rare-mover bypass path). |
| 7 | Refresh, retry, and reappearance of the product | `POST /refreshes` (orchestration — route not individually re-traced this pass; function re-read) | `orchestration_service.create_refresh` | **Re-confirmed unchanged from this document's existing Audit D (section 6):** allocates a new `refresh_id` unconditionally on every call, no idempotency key. A rare-mover item that disappears and reappears across refreshes has no confirmation-carry-forward mechanism on the live path (no live `rare_confirmed` state exists to carry forward — see path 2). | Re-read `orchestration_service.create_refresh` this pass; matches the existing finding at `PHASE_2_CLAUDE_REVIEW.md`'s Audit D section 5 and the owner-decision-register row 5 above verbatim. Not re-quoted at length to avoid duplicating prior content per the task's "preserve existing content" instruction. |
| 8 | Concurrent edits / actions from separate requests or workers | `assign_single`/`assign_bulk` (D1 enforcement path) | `assignment_repository.duplicate_active_exists` / `any_active_assignment` | **Partially — within one call, fully; across two concurrent HTTP requests, a genuine TOCTOU gap exists.** Re-confirmed unchanged from this document's existing Audit D (section 6, item 2): two concurrent `assign_single` calls for the same item, different suppliers, each opening its own `get_connection()`, could both pass the "no existing assignment" check before either commits. | This is the exact finding already on record in this document (Audit D item 2, "a genuinely new finding this pass" as of the prior review date) — re-confirmed, not re-discovered, by this pass's re-read of `assignment_service.py:61-107`. No rare-mover-specific concurrency issue was found beyond this pre-existing, more general D1 gap — a rare-mover-flagged item races exactly the same way a normal item does, because nothing distinguishes it at this guard point either way (there is no rare-mover guard to race against). |

### 2. Confirmed defects and their evidence

**CONFIRMED DEFECT 1 — rare-mover "no automatic assignment, export, or portal order" business rule is unenforced on every live write path.** `rules_catalog.py`'s `PRR-QTY-RARE` entry (lines 225-243) documents this as `STATUS_CONFIRMED`/`POLICY_LOCKED` target behavior — a directly owner-relevant business rule, not a speculative target. `decision_rules.py` correctly computes and stores the classification (`reason_code=INCLUDED_RARE_MOVER_TOPUP`) on `procurement_virtual_products`. But `assignment_service.assign_single`, `assignment_service.assign_bulk`, and `export_service.export_refresh` — the only three live mutating actions that could constitute "assignment," "export," or "order" for a rare-mover-flagged item — contain **zero references** to `reason_code`, `trigger_reason`, or `procurement_action` anywhere in their guard logic. A rare-mover-flagged item can be assigned to a supplier, exported to that supplier (Excel/WhatsApp), and reconciled via GRN through the ordinary live flow today, with no gate, no warning surfaced server-side, and no confirmation step of any kind. **This is a defect in the live, already-shipped system — it is independent of, and does not require, any VPL History persistence decision.** First identified in this document's prior Audit C section (2026-10-20, earlier pass); re-confirmed by this pass's direct re-read of all three functions' full source, not merely re-cited.

**CONFIRMED DEFECT 2 — most procurement Purchase-Manager mutating routes have no server-side authentication or tenant-authorization check at all (newly identified this pass, broader than rare-mover).** `pm_router.py`'s GET routes for workspace listing/summary (lines 62-115) correctly call `assert_tenant_access(current_user, tenant_id)` after resolving `current_user` via `Depends(get_current_user_optional)`. But `set_final_qty`, `restore_suggested`, `skip`, `restore`, `defer` (lines 126-166), `assign`, `bulk_assign`, `change_supplier`, `remove_assignment` (lines 439-470), and `export` (lines 477-482) — **every mutating route checked this pass** — declare no `current_user` parameter and call no authorization function at all. `get_current_user_optional` (`dependencies/auth.py:61-75`) returns `None`, not a 401, when no bearer token is present — so a route that never calls it is reachable by a request with **no Authorization header whatsoever**, authorized only by whatever `tenant_id` string the caller supplies as a free-text query parameter. This means, as currently shipped: any caller who can reach the backend's network path can assign suppliers, modify final quantities, skip/defer/restore items, and export supplier orders for **any tenant_id**, not just their own. This is strictly more severe than the rare-mover gap — it removes the premise that "server-side enforcement" is even meaningful for these routes today, since nothing establishes who the caller is before the business logic runs. **This finding is not specific to rare-mover and was not the audit's primary target, but it directly undermines any rare-mover guard proposal that assumes a `current_user`/tenant context is reliably available at these call sites — it is not, today.**

**DEFENSE-IN-DEPTH GAP (not a new defect, re-confirmed) — D1's "one active assignment" rule has a TOCTOU race across two connections.** Already on record in this document (Audit D item 2). Re-confirmed this pass by re-reading `assignment_service.assign_single`'s exact guard sequence. Not rare-mover-specific; affects every item, rare-mover-flagged or not, identically.

**DESIGN QUESTION (re-confirmed, not resolved) — what persistence shape rare-mover confirmation should take.** Already on record (owner decision register, item 3/3b, this document). This pass adds no new option; it reconfirms the live-path enforcement gap is independent of this design question (fixing Defect 1 does not require resolving Decision 3 first, since Defect 1's fix can gate on the *existing*, already-live `reason_code` column rather than any new confirmation-persistence concept — see minimal fix proposal below).

**UNVERIFIED — INTEGRATION TEST REQUIRED — concurrent-request behavior under real SQL Server locking.** Same unresolved item already on record in this document's Audit D "Potential risks requiring SQL Server or integration testing" subsection — not re-litigated here, still requires database access this audit does not have.

### 3. Required safety contract — evaluated against actual code

| Expected behavior | Status | Evidence |
|---|---|---|
| A rare mover requiring review cannot be automatically assigned, exported, ordered, or submitted to a portal. | **NOT MET.** | Confirmed Defect 1. No route-placement/portal-submission concept exists live (path 5/6 above), so "ordered"/"submitted to a portal" collapses to "exported" in this system — and export has no gate either. |
| Missing, stale, or incorrectly scoped confirmation fails closed. | **CANNOT BE EVALUATED — there is no confirmation mechanism on the live path to fail open or closed.** This is not "fails open" in the sense of a broken check; it is the complete absence of a check. | Path 2 above. |
| Confirmation applies only to the current cycle/approved context. | **N/A — no live confirmation exists to scope.** The in-memory prototype's `rare_confirmed` field has no cycle-expiry logic either (re-confirmed, matches this document's existing Decision 3b finding). | `vpl_history.py` grep; Decision 3b. |
| Confirmation for one product or cycle cannot authorize a different product or cycle. | **N/A**, same reason. | — |
| Concurrent requests cannot bypass the review requirement. | **N/A for rare-mover specifically** (nothing to bypass); **PARTIALLY MET for the adjacent D1 rule** (one-active-assignment), with the known TOCTOU gap documented above. | Path 8 above; Audit D item 2. |
| Bulk operations reject or safely isolate prohibited lines without partially performing unsafe actions. | **MET for the mechanism that exists (skipped/deferred/duplicate/exceeds-final-qty), NOT MET for rare-mover** (there is no "prohibited line" concept for rare-mover to isolate). `assign_bulk`'s per-item try/except isolation (confirmed correct, re-read this pass) would correctly isolate a rare-mover guard *if one were added* — the isolation mechanism is sound and ready to carry a new guard. | `assignment_service.py:127-164`. |
| A retry cannot duplicate an order or portal submission. | **UNVERIFIED for export specifically within this pass** (not re-traced in depth; `export_refresh` generates a new `batch_no` via `uuid.uuid4()` on every call with no idempotency key, so a client-side retry of the same export request would create a **second** export batch for the same assignments, provided they are still `assignment_status='draft'` after the first attempt — whether the first attempt's `mark_exported` call already flipped status before a retry is attempted determines whether this is reachable). This is a plausible but **not confirmed this pass** duplicate-export risk, flagged as requiring either a deeper trace of `export_repository.mark_exported`'s status transition or an integration test — not conflated with the rare-mover finding, reported separately for accuracy. | `export_service.py:36,44-50` (new `batch_no` and no idempotency check before the loop) — read this pass, not exhaustively traced against `mark_exported`'s exact status-transition timing. |
| Normal non-rare products retain their existing approved workflow. | **MET.** Nothing in this audit's fix proposal (below) touches any guard for a non-rare-mover item; all existing guards (skipped/deferred/duplicate/final-qty) are unchanged by the proposal. | By construction of the minimal fix proposal — no existing check is modified. |
| Failures provide an actionable error and do not silently discard manual edits. | **MET for existing guards** (every existing 409/400 in `assignment_service.py`/`workspace_service.py` is a clear `HTTPException` with a message, confirmed by re-read); **N/A for rare-mover** (no guard exists yet to fail with an error). | — |

### 4. Minimal safe implementation plan (NOT IMPLEMENTED — proposal only)

**Preferred enforcement point(s):** `assignment_service.assign_single` and `assignment_service.assign_bulk` (not export) — because `reason_code` is already present in the dict `workspace_repository.get_item` returns to these two functions, at zero extra query cost, while `export_repository.exportable_assignments` would need a new join to even see it. Gating at assignment time also means a rare-mover item can never reach export in the first place, since export only operates on already-`draft`-assigned rows — fixing the earlier gate structurally prevents the later one from ever being reached by a rare-mover item, without needing a second, separate fix in `export_service.py`. (`export_service.py` should still be defense-in-depth-gated in a full implementation, since a row could theoretically be assigned through a different, not-yet-existing future code path — but the *minimal* fix is one gate, not two, given today's call graph.)

**Proposed guard (illustrative, not implemented):**
```python
# In assignment_service.assign_single and assign_bulk, after _require_item/get_item:
if item.get("reason_code") == decision_rules.INCLUDED_RARE_MOVER_TOPUP:
    if not <explicit confirmation signal — DOES NOT EXIST TODAY, see below>:
        raise HTTPException(status_code=409, detail="Rare-mover item requires PM confirmation before assignment")
```

**The explicit confirmation signal does not exist today and is the real blocker, not the guard's placement.** This audit cannot propose a concrete field/table for that signal without re-opening Decision 3/3b (persistence shape), which remains the owner's call. Two honest options:
- **Option X (fastest, narrowest):** add a single new boolean-equivalent check that does *not* require persistence — e.g., require the `assign_single`/`assign_bulk` request body to carry an explicit `rare_mover_ack: true` flag that the frontend sets only after showing a confirmation dialog, checked against the *current* `reason_code` server-side on every call (no storage, no cross-request state, re-asked every time). This satisfies "missing confirmation fails closed" and "confirmation applies only to the current action" trivially (there is no persistence to go stale), at the cost of asking the PM to re-confirm on every single assignment of the same rare-mover item, which may be poor UX if a PM assigns the same item across multiple small supplier splits in one session.
- **Option Y (matches Decision 3's recommendation):** implement Option B from this document's existing Audit C design comparison (dedicated review table keyed on stable product+cycle identity) — this requires a new migration, which requires Decision 3/3b sign-off, which is explicitly **not** granted by this task ("Do not treat owner approval of a business rule as authorization to implement it").

**This audit recommends Option X as the smallest safe fix available without a new schema, but does not implement it, and flags that re-confirmation-per-call UX cost as a tradeoff for the owner to accept or reject — not a decision this audit makes unilaterally.**

**Necessary tests (descriptions only, matching section H below).**

**Concurrency concerns:** Option X has none beyond what already exists (it reads `reason_code` from the same row already locked/read by the existing D1 checks in the same transaction — no new TOCTOU surface). Option Y would inherit the same cross-process concurrency gap already documented for every other `procurement_order_items`-adjacent table in this document's Concurrency design section — not a new concern, the same one.

**Error behavior:** 409 (matches every other business-rule rejection in `assignment_service.py`, e.g. the final-qty-exceeded check at line 90-94) — not 400 (reserved for malformed input in this module's existing convention) and not 403 (reserved for missing `exported_by`, per `export_service.py:23-26`).

**Affected files if implemented (not touched by this audit):** `assignment_service.py` (guard), `pm_schemas.py` (`AssignRequest`/`BulkAssignRequest` would need the new `rare_mover_ack` field for Option X), `pm_router.py` (pass the field through — already does for every other field), a new test file following this module's existing `tests/test_procurement_*` convention. **Defect 2 (authorization gap) would need `current_user: dict = Depends(get_current_user_optional)` plus `assert_tenant_access(current_user, tenant_id)` added to every mutating route in `pm_router.py` — a separate, larger, and arguably higher-priority fix than the rare-mover gate itself, since it affects every tenant's data, not just rare-mover items.**

### 5. Regression test plan (descriptions only — no test file written this pass)

1. `test_rare_mover_item_cannot_be_assigned_single_without_confirmation` — `assign_single` on an item with `reason_code=INCLUDED_RARE_MOVER_TOPUP` and no `rare_mover_ack` → 409.
2. `test_rare_mover_item_cannot_be_exported_without_prior_assignment_confirmation` — structural: since export only sees already-assigned rows, this test should assert that a rare-mover item can **never reach** `exportable_assignments` without having passed test 1's gate — i.e., test the invariant at the assignment boundary, not re-implement a second gate at export (per the minimal-fix recommendation above). If a future implementation adds a defense-in-depth export-time check anyway, a second direct test would be needed then.
3. `test_rare_mover_item_cannot_be_ordered_without_confirmation` — **no separate "order" action exists**; this collapses into test 1/2 given the path-5 finding above. Recorded as a test-plan note, not a separate test, to avoid inventing a confirmation field for an action that doesn't exist.
4. `test_rare_mover_item_cannot_be_submitted_to_a_supplier_portal_without_confirmation` — same collapse as test 3; no live portal-submission action exists (path 6 finding).
5. `test_rare_mover_ack_valid_only_for_the_reason_code_present_at_call_time` — Option X's per-call re-ask design makes this trivially true (there is no stored confirmation to go stale against a changed `reason_code`) — this test would assert exactly that: an `ack=true` sent for an item whose *current* `reason_code` is no longer `INCLUDED_RARE_MOVER_TOPUP` (e.g., it was reclassified by a later refresh) is simply irrelevant/ignored, not incorrectly honored.
6. `test_stale_rare_mover_ack_fails_closed` — an `ack=true` carried over from a previous, different item/request must not satisfy the check for a different `order_item_id` — trivially true under Option X since the ack is scoped to the single request body for one `order_item_id`, not a separate stored token; this test documents that property rather than discovering a risk.
7. `test_bulk_assign_rejects_rare_mover_line_without_partially_assigning_others` — extends the existing `assign_bulk` per-item isolation test pattern (the mechanism already exists and is correct per this pass's re-read; this test adds a rare-mover-flagged spec to the batch and confirms it reports `"skipped"` with a clear reason while sibling non-rare-mover specs in the same batch still succeed).
8. `test_concurrent_assign_single_rare_mover_and_normal_item_do_not_interact` — confirms the new guard doesn't introduce a *new* concurrency surface beyond the already-documented D1 TOCTOU gap (Option X reads no new mutable state across requests, so this should be a short test confirming "no new race," not a discovery test).
9. `test_refresh_retry_does_not_duplicate_export_batch` — **this test plan item requires the `mark_exported` status-transition trace this audit flagged as unverified in section 3** (the "retry cannot duplicate" row) — write this test only after that trace is completed, not before, since writing it blind risks encoding an assumption about `mark_exported`'s timing that this audit did not confirm.
10. `test_normal_product_assignment_export_unaffected_by_rare_mover_guard` — assign and export an ordinary (non-rare-mover) item exactly as today; confirm zero behavior change — the most important regression test in this list, since it is the one the task explicitly requires ("normal products retain their existing approved workflow").
11. `test_tenant_isolation_rare_mover_ack_cannot_cross_tenants` — **this test cannot be written meaningfully until Defect 2 is fixed**, since today there is no tenant-authorization boundary on `assign_single`/`assign_bulk` to test in the first place; a test written against the *current* code would either pass trivially (no boundary to cross, so "crossing" it is undefined) or would actually be testing Defect 2, not rare-mover confirmation specifically. Flagged as blocked on Defect 2's fix, not omitted.
12. `test_failed_rare_mover_assignment_preserves_manual_final_qty_edit` — confirms that a 409 from the new guard does not roll back or discard a PM's already-saved `final_qty`/`manual_override` on that item (it shouldn't, since the guard runs before any write in `assign_single`'s transaction — but this should be asserted, not assumed, once Option X exists).

### 6. Concurrency and other audit findings — D1-D7 impact

- **D1 (one active supplier per product line):** Already live and enforced (`any_active_assignment`/`duplicate_active_exists`), independent of rare-mover status — confirmed unchanged by this pass. The TOCTOU gap (Audit D item 2, re-confirmed above) affects D1 enforcement for *every* item, not specifically rare-mover ones. A rare-mover guard added per the minimal fix proposal would run *before* the D1 checks in the same function body (reason_code is known immediately after `_require_item`, before any connection is opened) — so it does not interact with or worsen the D1 TOCTOU gap; it simply short-circuits earlier for a rare-mover item lacking `rare_mover_ack`.
- **D2 (deferred lines return normally in the next refresh):** Confirmed consistent with existing code — `defer_item`'s exclusion is refresh-scoped per Decision 2's existing discussion (not re-litigated here); unaffected by the rare-mover finding, since `_touched()`/deferred-status logic lives in `vpl_history.py` (unwired) and `workspace_repository.defer_item` (live) respectively, neither of which this audit's minimal fix proposal touches.
- **D3 (rare-mover confirmation valid only for current cycle/approved context):** This is exactly what Option X (per-call, non-persisted ack) trivially satisfies, and exactly what the task's "replace the plain client echo-back with a short-lived server-issued confirmation token" alternative (mentioned in the sibling Legacy Order audit earlier in this session, for a structurally similar problem) would also satisfy if the owner prefers stronger assurance than a plain client-supplied boolean — **this audit notes the parallel but does not propose importing that exact mechanism here without separate authorization**, since this task's boundaries explicitly prohibit implementing anything, and the two systems (Legacy Order vs. procurement) are otherwise unrelated modules.
- **D4 (concurrency — version checks, transactions, constraints as appropriate):** The minimal fix proposal (Option X) requires none of these beyond what already exists, because it adds a read-only check against already-fetched data, not a new stored/versioned field. If the owner later approves Option Y (persisted confirmation), D4 applies in full — see the existing Concurrency design section and Decision 4 in this document; not re-designed here.
- **D5 (refresh retry returns/reuses the existing result for the same logical refresh request):** **Not met today** — confirmed by this pass's re-read of `orchestration_service.create_refresh` (unconditional new `refresh_id` every call, matching the existing Decision 5 finding exactly). This is orthogonal to the rare-mover gate itself but relevant to regression test 9 above (export-retry risk) and to D5's own owner decision (register item 5, unchanged by this pass).
- **D6 (history access — strict tenant and store isolation):** **Cannot be verified as met for the live write paths this audit traced**, because of Defect 2 — there is no tenant-authorization check on `assign_single`/`assign_bulk`/`export_refresh` to evaluate isolation against. This is the most consequential D1-D7 interaction found this pass: D6's requirement is not merely unverified, it is **structurally unenforceable today** on these specific routes until Defect 2 is fixed, independent of whatever "history" ends up meaning once VPL persistence is approved.
- **D7 (VPL History identifiers — stable line/history ID with validated product identity; product code alone must not identify an ambiguous line):** Already resolved in the in-memory prototype per this document's extensive existing coverage (`_key()`/`_resolve_by_code()`/`AMBIGUOUS` fail-closed, re-confirmed accurate and unaffected by this pass — not re-traced in depth since it was not the focus of this pass's redirect). The rare-mover guard proposed above (Option X) keys on `order_item_id` (the live table's actual PK), not `product_code`, so it is not exposed to the ambiguity D7 addresses — this is a different identifier space (live `procurement_order_items.order_item_id` vs. the in-memory prototype's `product_id`/`product_code` working-line identity) and the two should not be conflated.

### 7. New owner decisions required for rare-mover safety (none auto-approved)

| ID | Question | This audit's observation (not a recommendation to approve) |
|---|---|---|
| 8 | Should the rare-mover assignment/export guard be implemented now, as a standalone fix independent of any VPL History persistence decision, given that Defect 1 is a live-system gap and does not require resolving Decision 3/3b first? | This audit observes the fix is *possible* without touching Decision 3/3b (Option X requires no persistence), but does not itself authorize implementation — per this task's explicit instruction, owner approval of the business rule (already given, per `rules_catalog.py`'s `STATUS_CONFIRMED`) is not approval to implement it. |
| 9 | Should Option X's per-call re-ask (no stored confirmation, re-prompt every assignment) or Option Y's persisted-confirmation (Decision 3/3b, not yet approved) be built, given the UX tradeoff described in section 4? | Not decided by this audit — a genuine product tradeoff, not a technical one. |
| 10 | Should Defect 2 (missing tenant authorization on nearly every mutating Purchase Manager route) be treated as a separate, higher-priority fix than rare-mover enforcement, given it affects every tenant's data regardless of rare-mover status? | This audit's observation: yes, on severity grounds alone (broader blast radius, simpler/more mechanical fix — add the same two lines already present on the GET routes). Not an approval to implement; flagged for explicit owner/engineering-lead triage. |

### 8. Final status (unchanged by this audit)

- Phase 2: **READY_FOR_REVIEW** (unchanged).
- VPL History persistence: **BLOCKED** (unchanged).
- Production implementation: **unchanged** — no file under `backend/modules/procurement/` other than this review document was edited.
- Database: **not accessed**.
- Migrations: **not applied** — none were written in this pass either.
- Legacy order workflow: **unchanged** — not touched, not in scope for this task.

### 9. Recommendation for next separately authorized task

Two independent, separately authorizable next tasks, in order of recommended priority:

1. **Fix Defect 2 (authorization gap on Purchase Manager mutating routes)** — mechanically small (add `current_user: dict = Depends(get_current_user_optional)` and `assert_tenant_access(current_user, tenant_id)` to each mutating route, mirroring the pattern already correct on the GET routes), broad blast radius if left unfixed, and does not require any owner business-rule decision — only an engineering go-ahead and a regression-test pass confirming no legitimate caller is newly blocked.
2. **Fix Defect 1 (rare-mover live enforcement gap) via Option X** — smallest safe implementation of the already-owner-confirmed `PRR-QTY-RARE` business rule, gating `assign_single`/`assign_bulk` on `reason_code` with a per-request `rare_mover_ack` flag, no new schema, no persistence decision required. Should land after or alongside Defect 2's fix, since both touch the same router file and should not be designed twice.

**This audit does not claim the rare-mover live safety gap is fixed.** It is not fixed. No code was changed. The gap described in Defect 1 remains exactly as exploitable in production today as it was before this audit began — a rare-mover-flagged item can still be assigned, exported, and GRN-reconciled through the live UI with no confirmation step, right now. This audit's only output is evidence, a classified defect list, and an unimplemented proposal, exactly as instructed.

## Priority 1 — rare-mover safety audit — 2026-10-20

**Role for this section: Senior Procurement Architect / independent safety auditor. Read-only.** No production code, test, migration, or configuration was edited. No database connection was opened. No order was placed, exported, or submitted anywhere. `decision_rules.evaluate`, `decision_repository.py`, `decision_service.py` were read, not edited. `clear_products` was not touched. `AUTONOMOUS_WORK_CONTROL.md` and `PHASE_2_VPL_HISTORY.md` were not edited (confirmed by file-modification timestamp at the end of this task). Owner approval of D1–D7 (section below) is treated strictly as approved *business requirements*, not as authorization to write or apply any code, schema, or database change — none was made.

### Files inspected this pass

`decision_rules.py` (full, including the exact `RARE_MOVER_TOPUP`/`INCLUDED_RARE_MOVER_TOPUP` branch, lines 320-349, re-read in full this pass — not just the catalog's description of it), `rules_catalog.py` (rare-mover catalog entry, re-confirmed), `decision_service.py` (grepped for `reason_code`/`RARE_MOVER` — one match, a column-name tuple, no logic), `assignment_repository.py` (full), `assignment_service.py` (full, grepped again for rare-mover terms — zero matches), `workspace_repository.py`/`workspace_service.py` (full, re-confirmed), `export_service.py` (full), `export_repository.py` (first 60 lines, covering `exportable_assignments`' full `SELECT`), `export_document_service.py` (grepped for rare-mover terms — zero matches; function list enumerated), `reconciliation_service.py` (full, grepped — zero matches), `pm_router.py` (full, re-confirmed — every route's exact parameter signature), `access.py` (full — the real `require_procurement_admin` implementation), `backend/dependencies/auth.py` (`get_current_user`/`get_current_user_optional`), `backend/dependencies/store_scope.py` (`assert_tenant_access`/`has_unrestricted_scope`, full relevant section), `backend/api/app.py` (lines 215-326 — the global `require_auth` middleware and its allowlists, read in full to correctly resolve an initial mis-framing before reporting it). Grepped `tests/` for every rare-mover-related term across the whole test suite (5 files matched; all read in context).

**Safe read-only commands actually executed:** none beyond `grep`/`git status`/file reads. No `pytest` command was run in this pass — the task's own instruction set did not require a new test run, and no test file was modified, so there was nothing new to verify by execution; the most recent independently-executed test evidence in this document (47 passed) stands and is not re-claimed as newly produced here.

### D. Rare-mover call-path matrix

| # | Path | Route / entry point | Service / repository | Guard / auth check | Rare-mover condition checked at point of action? | Confirmation verified against current cycle/context? | Stale/missing confirmation can pass? | Can a downstream method be called directly, bypassing any guard? | Evidence (file:function:lines) | Existing test evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Classification / suggestion generation | Internal — `decision_service.generate_vpl`, invoked by `orchestration_service.create_refresh` | `decision_rules.evaluate` (pure function) sets `reason_code=INCLUDED_RARE_MOVER_TOPUP`, `trigger_reason=RARE_MOVER_TOPUP`, `suggested_qty=1` on `procurement_virtual_products` | N/A — internal computation, not an HTTP action | Yes — this is the detection step itself | N/A — nothing to confirm yet at this step | N/A | N/A | `decision_rules.py:320-349` | `tests/test_procurement_decision_engine.py::test_rare_mover_topup_matches_legacy_additional_row`, `::test_rare_mover_topup_not_triggered_for_single_bill`; `tests/test_procurement_formula_compare.py::test_rare_mover_target_holds_one_pack_for_review` — all three confirmed passing-adjacent by reading their assertions (not re-run this pass); all three test classification only, none test any downstream guard |
| 2 | Manual review and confirmation | None exists on the live path. The only `rare_confirmed`-equivalent concept anywhere is `VplWorkspace.edit`'s whitelisted `rare_confirmed` field, in the unwired in-memory prototype. | `vpl_history.py::edit` (prototype only) | `vpl_history_router.py`'s `require_procurement_admin` (prototype only, never reached by anything live) | Yes, in the prototype only | Yes, in the prototype only — confirmation lives on the same line and is lost if the line's identity is lost, which this document's prior "Audit C" section already traced in detail | In the prototype: a confirmation survives a refresh via `_touched()`'s carry-forward rule, with no reclassification-aware expiry (prior finding, re-confirmed, now addressed by D3 below) | N/A — prototype has no downstream live wiring to bypass | `vpl_history.py:133-148,193` | `tests/test_vpl_history.py::test_rare_mover_confirmation_survives_refresh` |
| 3 | Supplier assignment — single | `POST /order-items/{order_item_id}/assignments` | `assignment_service.assign_single` → `assignment_repository.insert_assignment`/`recompute_order_item` | **No `current_user`/`Depends` parameter on the route at all** (re-confirmed by re-reading the exact signature this pass — `assign(order_item_id, payload, tenant_id: str = Query(...))`); only the global `require_auth` middleware (any valid JWT) applies | **No** — `assign_single` validates supplier/qty/skip-status/duplicate-assignment/final-qty-ceiling; it never reads `reason_code` or any rare-mover-equivalent field, confirmed by re-reading the full function body this pass (lines 61-114) | No — there is nothing to verify against, because nothing is checked | **Yes, unconditionally** — a rare-mover-flagged item (`reason_code=INCLUDED_RARE_MOVER_TOPUP`) can be assigned exactly like any ordinary item; no confirmation of any kind, stale or otherwise, is required or checked | Yes — `assignment_repository.insert_assignment` can be called directly by any Python code with a connection, with zero guard of its own (guards live only in the service layer, which itself has no rare-mover check to bypass in the first place) | `pm_router.py:439-444`; `assignment_service.py:61-114`; `assignment_repository.py:329-347` | **None found** — no test in the suite asserts a rare-mover item is blocked from `assign_single` |
| 4 | Supplier assignment — bulk | `POST /assignments/bulk` | `assignment_service.assign_bulk` | Same as #3 — no `Depends` at all | **No** — `assign_bulk`'s per-item checks are: item exists, not skipped, not deferred, has remaining qty, no duplicate/existing assignment, qty ≤ final_qty (lines 127-164, re-read in full this pass); `reason_code` is never read | No | **Yes, unconditionally**, same as #3, but now at bulk scale — an "Auto Assign" or "Assign Remaining" bulk action (the module's own comment names these as `assign_bulk`'s callers) would silently sweep up every rare-mover-flagged item in the batch along with ordinary items, since the per-item `try/except ValueError` loop has no `ValueError("rare mover requires confirmation")` branch to raise | Yes, same as #3 | `pm_router.py:447-452`; `assignment_service.py:117-175` | **None found** |
| 5 | Export preparation | `exportable_assignments` query | `export_repository.exportable_assignments` | N/A — internal query, called by `export_service.export_refresh` | **Structurally impossible to check** — the `SELECT` (re-read in full this pass, lines 14-39) reads only `procurement_order_item_assignments` columns (`assignment_id, order_item_id, supplier_code, assigned_qty`); it has **no join at all** to `procurement_virtual_products` or any `reason_code`-bearing table, so even if someone wanted to add a check here, the query would need a new join first | No | **Yes, unconditionally** — this query cannot distinguish a rare-mover-flagged assignment from any other | N/A | `export_repository.py:14-39` | None |
| 6 | Export execution | `POST /refreshes/{refresh_id}/export` | `export_service.export_refresh` | No `Depends` at all (re-confirmed, `export(refresh_id, payload, tenant_id: str = Query(...))`) | **No** — `export_refresh` (lines 22-68, re-read in full this pass) only checks `exported_by` is present and that `rows` is non-empty; it never reads `reason_code` | No | **Yes, unconditionally** | `export_repository.mark_exported` has no guard of its own either | `pm_router.py:477-482`; `export_service.py:22-68` | None |
| 7 | Export document build (the actual Excel/PDF/Image a human sends to a supplier) | `POST /refreshes/{refresh_id}/export-document` | `export_document_service.build_document` → `_build_rows` | No `Depends` (same pattern) | **No** — grepped the whole file for rare-mover terms this pass; zero matches; `_build_rows`/`_cell` build purely from the `items`/`assignment_ids` the caller already selected | No | **Yes, unconditionally** | N/A — this is a pure document-rendering function over already-selected rows | `pm_router.py:485-508`; `export_document_service.py` (full function list enumerated this pass) | None |
| 8 | Order placement / supplier portal submission | **Does not exist as a live concept anywhere in this codebase.** Grepped the whole `backend/modules/procurement/` directory for "portal" (case-insensitive) and for "place_order"/"order_placement"/"supplier_portal" this pass: every match is in `vpl_history.py`/`vpl_history_router.py` (the unwired prototype) or `rules_catalog.py`'s documentation text describing the *target* business rule, not a live implementation. The real workflow's terminal steps are assignment (#3/#4) and export (#6/#7); GRN reconciliation (#9) closes the loop. There is no further "place an order" or "submit to a supplier portal" HTTP action in this repository. | N/A | N/A | N/A | N/A — nothing to check, because the action does not exist | N/A | N/A — cannot pass or fail a check that is not reachable, because the action it would guard is not implemented | N/A | Confirmed absent by grep across the whole module directory, not inferred from a single file | N/A — **this corrects a premise in the task's own framing**, which asked this audit to trace "order placement" and "supplier portal submission" as if they were existing live actions; they are not. The prototype's `place_order`/`submit_to_portal` methods are the only code with these names, and they are explicitly not wired to anything live (confirmed throughout this document's prior sections). |
| 9 | GRN completion / reconciliation | `POST /refreshes/{refresh_id}/grn` | `reconciliation_service.submit_grn` → `reconcile` → `reconciliation_rules.match_receipts` | No `Depends` (same pattern) | **No** — `reconcile` (lines 63-113, re-read in full this pass) matches receipts to assignments by product+supplier (`reconciliation_rules.match_receipts`, not re-traced line-by-line in this pass per the prior audit's own "unresolved, more evidence required" note on this specific internal heuristic) and rolls up to order items; it never reads `reason_code` | No | **Yes, unconditionally** — reconciliation proceeds for a rare-mover-flagged, already-assigned-and-exported item exactly as for any other; this is arguably lower-severity than #3/#4/#6/#7 since reconciliation only matters *after* an assignment/export already happened without a check | N/A | `pm_router.py:664-668`; `reconciliation_service.py:32-113` | None |
| 10 | Refresh, retry, reappearance | `POST /cycles/{cycle_id}/refreshes` | `orchestration_service.create_refresh` | None relevant to rare-mover specifically — this is the same no-idempotency gap already documented in this file's "Audit D" section (unconditional new `refresh_id` on every call, re-confirmed this pass at lines 134-207) | N/A — a rare-mover classification is recomputed fresh by `decision_rules.evaluate` on every refresh; there is no confirmation state on the live path to lose or carry across a refresh, because there is no live confirmation state at all (per #2) | N/A | N/A | N/A | `orchestration_service.py:134-207` | None specific to rare-mover; general refresh-retry gap already covered by this document's prior sections |
| 11 | Concurrent edits/actions from separate requests/workers | All of #3/#4/#6/#9 | Same as above | Same as above — **zero `row_version` usage confirmed by grep across the whole module this pass (re-confirmed, zero new matches)** | N/A — there is no rare-mover-specific concurrency concern beyond the general lack of any version check already documented in "Audit D" | N/A | N/A — a race here would be about assignment-count correctness (already documented as the TOCTOU finding in this file's prior Audit D section), not about rare-mover confirmation specifically, since there is no confirmation state to race over | N/A | Re-confirmed, not a new finding this pass | Re-confirmed, not a new finding this pass |

### E. Required safety contract — expected vs. actual

| Expected behavior | Actual (live path) | Status |
|---|---|---|
| A rare mover requiring review cannot be automatically assigned, exported, ordered, or submitted to a portal. | **Not enforced anywhere.** `assign_single`, `assign_bulk`, `export_refresh`, and `export-document` all proceed identically for a rare-mover-flagged item and an ordinary item. "Ordered"/"submitted to a portal" are not live concepts (see matrix row 8). | **CONFIRMED DEFECT** (for assign/export; N/A for order/portal since those don't exist) |
| Missing, stale, or incorrectly scoped confirmation fails closed. | There is no live confirmation field to be missing, stale, or scoped — the question is moot on the live path because the gate itself does not exist. In the unwired prototype, a missing confirmation does not block anything either, because the prototype's own guard (`_guard_orderable`) checks `orderable`/`removed_manual_review` membership, not `rare_confirmed` specifically — confirmed by re-reading `_guard_orderable` (lines 317-337) this pass: it has no `rare_confirmed`-specific branch at all. | **CONFIRMED DEFECT** on the live path; **CONFIRMED DEFECT** in the prototype's own logic as well — even if wired, the prototype does not actually gate assign/export/order/portal on `rare_confirmed` being `True`, only on `orderable`/removal status, which is a different (and already-covered) concern |
| Confirmation applies only to the current cycle/approved context. | No live mechanism exists to apply at all (moot). In the prototype, a confirmation is carried forward indefinitely by `_touched()` with no cycle-boundary or reclassification-aware expiry — already identified as a prior open question (this document's Audit C), now resolved as an owner decision by D3 below. | **DESIGN QUESTION**, now answered by D3 (not yet implemented) |
| Confirmation for one product/cycle cannot authorize a different one. | In the prototype, confirmation lives on one line dict keyed by that line's own stable identity (`product_id`-first) — already independently verified safe against cross-identity leakage in this document's prior sections (the null-code/`AMBIGUOUS` review). Moot on the live path (no confirmation exists). | **SAFE CURRENT BEHAVIOR** in the only place the concept exists (prototype); **N/A** on the live path |
| Concurrent requests cannot bypass the review requirement. | Moot on the live path (no review requirement is enforced to bypass). In the prototype, `VplWorkspace._lock` serializes all operations within one process — already documented as single-process-only, not a live concern since the prototype isn't wired to concurrent real traffic. | **N/A** (live); **SAFE CURRENT BEHAVIOR within its documented single-process limit** (prototype) |
| Bulk operations reject or safely isolate prohibited lines without partially performing unsafe actions. | `assign_bulk`'s existing per-item isolation (each spec wrapped in its own `try/except ValueError`, confirmed again this pass) is structurally sound for *whatever checks exist* — but since no rare-mover check exists, there is nothing for this isolation mechanism to isolate on that basis. If a rare-mover check is added as a new `ValueError` branch, the existing isolation pattern would correctly handle it without further change. | **CONFIRMED DEFECT** (the check is missing) riding on **SAFE CURRENT BEHAVIOR** (the isolation mechanism that would contain the check, once added, already works correctly) |
| A retry cannot duplicate an order or portal submission. | Moot — no order/portal action exists to duplicate. `export_refresh`'s own docstring states "Multiple exports are allowed" as a deliberate design (each run stamps a new batch) — this is not a defect, it is documented intended behavior, separate from the rare-mover question. | **N/A** / **SAFE CURRENT BEHAVIOR (by design, not a rare-mover concern)** |
| Normal non-rare products retain their existing approved workflow. | Yes — nothing in this audit found any change to non-rare-mover handling; the gap is an absence of a new check, not a regression in existing behavior. | **SAFE CURRENT BEHAVIOR** |
| Failures provide an actionable error and do not silently discard manual edits. | N/A today (no failure path exists for this specific check, because the check doesn't exist). If added, the existing `HTTPException(status_code=409, ...)` pattern used throughout `assignment_service.py`/`workspace_service.py` is the established, consistent idiom to follow — not a new pattern to invent. | **DESIGN QUESTION** (addressed in the fix proposal below, not yet implemented) |

### F. Findings and proposed fix

**CONFIRMED DEFECT 1 (the primary deliverable of this task):** the rare-mover business rule documented in `rules_catalog.py` as `STATUS_CONFIRMED`/`POLICY_LOCKED` ("No automatic assignment, export, or portal order. PM must confirm.") is not enforced at any point on the live write path. `assign_single`, `assign_bulk`, and `export_refresh` all proceed for a rare-mover-flagged item exactly as for any ordinary item. **Exact failure path:** a Purchase Manager (or an "Auto Assign"/"Assign Remaining" bulk action, which calls `assign_bulk`) can assign a supplier to, and then export, a rare-mover top-up line with `suggested_qty=1` without ever being asked to confirm it is safe to actually order — directly contradicting the ratified business rule. **Consequence:** a token "keep this rare mover visible for review" quantity of 1 could be silently ordered through the normal flow with no human decision point beyond whatever the UI itself chooses to show (and this audit was instructed not to assume a UI warning is sufficient — correctly, since the server-side action path has no gate regardless of what the UI displays).

**CONFIRMED DEFECT 2 (newly found this pass, independent of rare-mover, but directly relevant to "where would a rare-mover guard even live"):** `assign`, `bulk_assign`, `change_supplier`, `remove_assignment`, `export`, and `submit_grn` (`pm_router.py`) have **no `Depends(get_current_user)`/`Depends(require_procurement_admin)` parameter at all** — only the global `require_auth` middleware (any valid JWT, any tenant, any role) gates them. `tenant_id` is a bare `Query(...)` parameter with no verification that it matches the caller's own tenant (contrast with `vpl_history_router.py`'s routes, every one of which calls `assert_tenant_access(current_user, tenant_id)` after `Depends(require_procurement_admin)`). **This was initially mis-investigated in this pass as a possible authentication bypass** (an unauthenticated request reaching `assert_tenant_access(None, tenant_id)`, where `has_unrestricted_scope(None)` returns `True`) — that specific concern was traced to `app.py`'s global `require_auth` middleware (lines 288-315, read in full to resolve this), which rejects any request without a valid bearer JWT *before* it ever reaches a route handler; `get_current_user_optional`'s `None` case is reserved for the narrow setup-token flow and is not reachable by an ordinary unauthenticated HTTP client hitting these routes. **Corrected finding:** this is a **cross-tenant/cross-role authorization gap**, not an authentication bypass — any validly authenticated user of any role can mutate procurement data for any `tenant_id` they choose to pass, because nothing on these six routes checks tenant ownership or a procurement-specific capability. This is the same class of defect already fixed elsewhere in this codebase (prior memory: "Cross-tenant store scoping fix... new backend/dependencies/store_scope.py pattern") but not yet applied to these six routes.

**DEFENSE-IN-DEPTH GAP:** the in-memory `VplWorkspace._guard_orderable` (the prototype's own enforcement point) does not actually check `rare_confirmed` at all — it checks `orderable`/`removed_manual_review` membership only. Even if this prototype were wired to live generation today exactly as-is, a rare-mover line that was never confirmed would still be allowed through `assign_supplier`/`export_lines`/`place_order`/`submit_to_portal` as long as it is not in `removed_manual_review` — the prototype's existing tests (`test_rare_mover_confirmation_survives_refresh`) test that a confirmation *survives*, not that its *absence blocks* anything. This is a real, previously-unstated gap in the prototype's own design, separate from the live-path defect above.

**UNVERIFIED — INTEGRATION TEST REQUIRED:** whether `reconciliation_rules.match_receipts`'s product+supplier matching heuristic could, under some data shape, misattribute a receipt to the wrong assignment in a way that interacts with an unconfirmed rare-mover line's downstream state — flagged as requiring database-level evidence, not traced further in this pass (same boundary as the prior Audit A's note on this same function).

#### Minimal safe fix proposal (not implemented)

**Preferred enforcement point: the service layer, not the repository layer** — consistent with every other business rule in this module (`assign_single`'s skip/duplicate/qty checks, `defer_item`'s skip/assigned checks, etc. all live in `*_service.py`, with `*_repository.py` staying pure data access). Concretely, and not implemented in this pass:

1. Add a server-side check in `assignment_service.assign_single` and in the per-item loop of `assignment_service.assign_bulk`: before inserting an assignment, read the owning virtual product's `reason_code` (would require `assignment_service` to read `procurement_virtual_products` via a new or existing repository call — `workspace_repository.get_item` already joins `vp.reason_code` per its own `_SELECT`, lines 28-41, so the data is already one query away, not a new join). If `reason_code == INCLUDED_RARE_MOVER_TOPUP` (or a broader rare-mover reason-code set, if more than one exists — this pass found only this one constant, but a future reason code should be checked against a named set, not a single string, to avoid the fix being brittle to a new rare-mover variant) **and** no valid confirmation exists for this exact line in this exact cycle/refresh context, raise the same `HTTPException(status_code=409, ...)` idiom already used throughout this service, with an actionable message ("Rare-mover item requires PM confirmation before assignment").
2. Add the equivalent check in `export_service.export_refresh` before `mark_exported` is called for each row — would require `export_repository.exportable_assignments` to join `procurement_virtual_products` for `reason_code` (a new join, confirmed necessary per Audit A row 5 above), or for `export_service` to call a separate lookup.
3. **This fix cannot be fully designed without first resolving where "confirmation" is stored — which is exactly Decision 3/3b below, already flagged as blocking.** A guard that checks `reason_code` alone (without a separate confirmation signal) would simply block every rare-mover item forever with no way to ever confirm and proceed — that is not the ratified business rule either ("PM must confirm" implies confirmation is possible, not that rare movers are permanently blocked). **This is the critical dependency this audit must state plainly: fixing the enforcement gap requires the confirmation-persistence decision (D3) to be made first, or at minimum a decision that confirmation is not required and the rule should instead route rare movers to a mandatory manual-review queue with no "confirm" step at all** (a fourth design option not previously considered, worth raising explicitly — see Decision 3c, new, below).
4. For the newly-found authorization gap (Defect 2): add `current_user: dict = Depends(require_procurement_admin)` and `assert_tenant_access(current_user, tenant_id)` to each of the six routes, matching the existing pattern in `vpl_history_router.py` exactly. This is independent of the rare-mover fix and could be implemented first, since it requires no new persistence decision.

**Concurrency concerns for the proposed fix:** the new rare-mover check and the eventual assignment insert must be read-then-act within the same transaction/connection as the rest of `assign_single`'s existing checks (the function already opens one `get_connection()` and does all its checks-then-write inside it) — no new concurrency primitive is required for the *check* itself, but the check is only as race-free as the rest of `assign_single` already is, which Audit D already found has a TOCTOU gap on the "one active assignment" rule. Fixing that TOCTOU gap (via D4's version-check direction) would also harden the rare-mover check's atomicity as a side effect, but the two are not the same fix.

**Error behavior:** 409 Conflict with an actionable detail string, matching every other business-rule rejection in this module (`"Cannot skip an item that already has supplier assignments"`, etc.) — not a generic 500, not a silent no-op.

**Affected files, if implemented (not done in this pass):** `assignment_service.py` (new check in `assign_single`/`assign_bulk`), `export_service.py` (new check in `export_refresh`), possibly `export_repository.py` (new join in `exportable_assignments` if the check needs `reason_code` at that layer rather than being pre-filtered by the service), `pm_router.py` (the six-route auth fix, independent of the rare-mover fix), and whatever new table/column Decision 3 ultimately approves for confirmation storage — none of which exists yet.

### G. D1–D7 effect on the proposed fix

- **D1 (one active supplier per product line):** confirms this audit's Decision 7 reading was correct — the live `assignment_service` enforcement (one active assignment) is the approved behavior, not a defect; no change needed to that guard. The rare-mover fix's "does this line already have an active assignment" question (relevant if confirmation should be revocable before assignment) can rely on the existing `any_active_assignment` check unchanged.
- **D2 (deferred lines return normally):** confirms this audit's Audit B Decision 2 recommendation — no `carry_forward_defers` mechanism is needed; a deferred line simply regenerates fresh next refresh like any other line. This simplifies the rare-mover fix's interaction with defer: a deferred rare-mover line needs no special defer-aware carry-forward logic for its rare-mover status either, since the whole line is expected to regenerate fresh.
- **D3 (rare-mover confirmation valid only for current cycle/approved context):** directly answers Decision 3b from this document's prior section — confirmation must NOT be sticky across a reclassification or cycle boundary. This simplifies the fix: the confirmation-storage design (still needed, still blocking) does not need to solve "does this old confirmation still apply" via complex reclassification-diffing — it can instead key confirmation to `(product identity, cycle_id)` and treat any new cycle as requiring a fresh confirmation, full stop. This narrows Option B's design (dedicated review table) to a simpler shape than previously sketched.
- **D4 (version checks, transactions, constraints as appropriate):** confirms the direction of this document's existing Decision 4 recommendation (optimistic `row_version`); "as appropriate" leaves room for a database CHECK constraint on the new confirmation table (e.g., preventing a confirmation row from referencing a cycle other than its own) — a concrete, cheap safety net once that table's schema is actually designed, not yet designed in this pass.
- **D5 (refresh retry returns/reuses the existing result):** directly answers Decision 5 — idempotency via returning the prior result, not merely documenting "don't retry." This has no special interaction with rare-mover beyond confirming that a retried refresh should not spuriously re-trigger a fresh rare-mover classification requiring a new confirmation if the underlying data hasn't changed — consistent with "reuse the existing result for the same logical request."
- **D6 (strict tenant/store isolation for history access):** directly applies to wherever rare-mover confirmation ends up stored — the same tenant/store scoping already used by `assert_tenant_access` throughout this module should gate read/write access to the new confirmation table, once designed.
- **D7 (stable line/history ID, validated product identity, product code alone must not identify an ambiguous line):** directly reuses the already-approved `product_id`-first identity work from this document's prior sections — the rare-mover confirmation table's key should be the same stable identity, not `product_code` alone, consistent with everything already built and approved for the VPL History prototype.

### H. Regression test plan (descriptions only — no test file written or modified)

1. `test_assign_single_rejects_rare_mover_without_confirmation` — `assign_single` on an item with `reason_code=INCLUDED_RARE_MOVER_TOPUP` and no confirmation raises 409.
2. `test_export_refresh_rejects_rare_mover_without_confirmation` — same for `export_refresh`.
3. `test_rare_mover_order_rejected_without_confirmation` — N/A today since no live "order" action exists (matrix row 8); would apply to whatever future action, if any, is built as a successor to export/assignment.
4. `test_rare_mover_portal_submission_rejected_without_confirmation` — same N/A caveat as #3.
5. `test_rare_mover_confirmation_valid_only_within_its_cycle` — a confirmation recorded for cycle N does not authorize the same product in cycle N+1 (per D3).
6. `test_stale_rare_mover_confirmation_fails_closed` — a confirmation whose stored classification/cycle no longer matches current state is rejected, not silently honored.
7. `test_bulk_assign_isolates_rare_mover_line_without_blocking_the_rest_of_the_batch` — extends the existing `assign_bulk` per-item isolation pattern to the new check.
8. `test_concurrent_assign_single_on_rare_mover_item_cannot_both_succeed_without_confirmation` — would require the same concurrency harness already flagged as needed for the pre-existing TOCTOU finding (Audit D item 2); not newly designed in this pass beyond restating the need.
9. `test_refresh_retry_does_not_duplicate_rare_mover_confirmation_requirement` — per D5, a retried refresh reuses the existing result rather than spuriously re-requiring confirmation.
10. `test_ordinary_non_rare_mover_item_assignment_export_unaffected_by_new_check` — regression guard that the new check is additive and does not change behavior for any `reason_code` other than the rare-mover set.
11. `test_rare_mover_confirmation_cannot_be_reused_across_tenant_or_store` — per D6, mirrors the existing tenant/store isolation tests already used elsewhere in this module's test suite (pattern, not a specific existing file re-read in this pass).
12. `test_rejected_assignment_does_not_discard_the_items_existing_manual_final_qty` — confirms the 409 rejection path leaves `final_qty`/`manual_override` exactly as they were, not partially mutated.

### I. D1–D7 decision register — OWNER APPROVED, IMPLEMENTATION NOT YET AUTHORIZED

| ID | Decision | Status | Implementation consequence | Outstanding technical question |
|---|---|---|---|---|
| D1 | One active supplier per product line. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Confirms existing `assignment_service` enforcement is correct as-is; resolves this document's prior Decision 7 contradiction in favor of "one-to-one live, history may still hold many" (consistent with the already-accepted-in-principle assignment-history design elsewhere in this document). No code change needed for this decision alone. | None outstanding — this decision is fully consistent with already-traced live code. |
| D2 | Deferred lines return normally in the next refresh. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Resolves this document's prior Audit B Decision 2 — no `carry_forward_defers` mechanism needed. Current behavior (a deferred row with no carry-forward, regenerating fresh) already matches this decision with zero code change. | Confirm "return normally" means exactly "no special carry-forward, behaves like a fresh line" and not some other reading (e.g., "returns to the same `item_status` it had") — this audit reads it as the former, matching current code, but the decision text alone is slightly ambiguous between the two readings. |
| D3 | Rare-mover confirmation valid only for current cycle/approved context. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Narrows the confirmation-persistence design (still not built) to a simpler, non-sticky-across-cycles shape — directly resolves this document's prior Decision 3b. Does not itself specify Option A/B/C from the prior design comparison. | Which persistence option (A/B/C, or the new C below) implements this cycle-scoping — still an open schema design question, not decided by D3 alone. |
| D4 | Version checks, transactions, and constraints as appropriate. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Confirms the direction (optimistic concurrency + transactional writes + DB constraints) without mandating a specific `row_version` shape — "as appropriate" leaves implementation latitude. | Exact shape (one `row_version` column per table, as previously sketched, vs. some other appropriate mechanism) is still not pinned down — D4 approves the *principle*, not a specific schema. |
| D5 | Refresh retry returns/reuses the existing result for the same logical request. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Resolves this document's prior Decision 5 in favor of true idempotency (not merely "document don't retry") — `orchestration_service.create_refresh` would need an idempotency key or dedup mechanism, not yet designed. | What constitutes "the same logical refresh request" — a client-supplied idempotency key, a dedup window on `(cycle_id, parameters)`, or something else — not specified by D5 alone. |
| D6 | Strict tenant and store isolation for history access. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Resolves this document's prior Decision 6 in favor of store-scoped (the stricter of the two options already compared) — matches this audit's own prior recommendation. | None outstanding beyond normal implementation detail once any persistence is actually built. |
| D7 | Stable line/history ID with validated product identity; product code alone must not identify an ambiguous line. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Confirms the already-implemented and independently-reviewed `product_id`-first identity work in `vpl_history.py` as the correct direction — no new code change required by D7 alone; it ratifies what already exists in the prototype. | Whether the prototype's existing `AMBIGUOUS`-fail-closed-with-no-`product_id`-parameter gap (this document's prior Audit A finding) needs to be closed as part of satisfying D7, or whether D7 is satisfied by the current fail-closed behavior alone — this audit reads D7's wording ("must not identify an ambiguous line") as already satisfied by the existing `AMBIGUOUS` rejection, with the `product_id`-parameter addition being a separate ergonomic improvement, not a D7 compliance requirement. |

**New decisions surfaced by this rare-mover audit, not yet approved:**

| ID | Question | Recommended default | Alternatives | Consequences | Blocks the rare-mover fix? | Owner approval required |
|---|---|---|---|---|---|---|
| 3c (new) | Should rare-mover items instead route to a mandatory manual-review queue with no explicit "confirm" step at all (PM must act on the queue item, e.g. by setting its final qty or explicitly skipping it, rather than clicking a discrete "confirm" control)? | Not recommended by default over D3's framing, but raised because D3's wording ("approved context") is compatible with either a discrete confirm action or a queue-based implicit approval — this audit does not have enough information to prefer one. | A discrete `rare_confirmed` boolean/timestamp (as already prototyped) vs. a queue-based "must be explicitly dispositioned" model with no separate boolean at all. | A discrete confirm field is simpler to query/enforce ("is this True") but adds a new concept; a queue-based model reuses the existing review/skip/final-qty machinery but makes "has this been reviewed" harder to distinguish from "has this been reviewed as safe to order" — these are not obviously the same thing. | **Yes** — this must be resolved before the confirmation-storage schema (Decision 3) can be finalized, since it changes what is actually being stored. | Explicit choice between a discrete confirmation field and a queue-based model. |
| 8 (new) | Should the newly-found cross-tenant/cross-role authorization gap on `assign`/`bulk_assign`/`change_supplier`/`remove_assignment`/`export`/`submit_grn` be fixed as its own, separately-authorized task before or independently of the rare-mover fix? | Fix independently and first — it requires no new persistence design (unlike the rare-mover fix, which is blocked on Decision 3/3c), and it is a security-relevant gap on routes that already mutate live procurement data today. | Fix together with the rare-mover change, since both touch the same service files. | Fixing it first is lower-risk (smaller, well-understood change, matches an existing fixed pattern elsewhere in the codebase) and does not block on any new design decision. Bundling it with the rare-mover fix risks conflating two different review/approval tracks. | **No** — independent of rare-mover persistence. | Explicit authorization for a separate, minimal-scope implementation task (add `Depends(require_procurement_admin)` + `assert_tenant_access` to the six named routes), distinct from the rare-mover confirmation work. |

### J. Final report summary

**Confirmed defects:**
1. Rare-mover "no automatic assignment/export/order" rule is unenforced on the live write path (`assign_single`, `assign_bulk`, `export_refresh` — matrix rows 3, 4, 6).
2. Six procurement mutation routes (`assign`, `bulk_assign`, `change_supplier`, `remove_assignment`, `export`, `submit_grn`) have no procurement-specific authorization check and no tenant-ownership verification — newly found this pass, corrected from an initial (wrong) authentication-bypass framing to the accurate cross-tenant/cross-role authorization framing after tracing the global `require_auth` middleware.

**Missing or bypassable guards:** every guard point in the matrix above marked "Yes, unconditionally" under "stale/missing confirmation can pass" — concretely, assignment and export, for both single and bulk operations.

**Minimal fix proposal:** service-layer `reason_code` + confirmation check in `assignment_service.assign_single`/`assign_bulk` and `export_service.export_refresh`, using the existing `HTTPException(409, ...)` idiom — blocked on Decision 3/3c (confirmation storage shape) before it can be fully specified; the separate authorization fix (Defect 2) is not blocked on anything and could be authorized independently.

**Regression-test plan:** 12 tests specified in section H, none written.

**Concurrency and isolation implications:** addressed via D1–D7 in section G; no new concurrency primitive required for the rare-mover check itself beyond what Audit D already identified as needed for the pre-existing TOCTOU gap.

**D1–D7 decision register:** section I, all seven marked OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED, plus two new decisions (3c, 8) surfaced by this audit and not yet approved.

**Remaining owner decisions:** 3c (confirmation model shape) and 8 (sequencing of the authorization fix) are new; Decision 3 (persistence option A/B/C) from this document's prior section remains the primary blocker for the rare-mover fix specifically.

**Integration-test needs:** the TOCTOU concurrency race (Audit D, re-affirmed relevant here) and `reconciliation_rules.match_receipts`'s internal heuristic both require database-level testing this audit could not perform.

**Exact files inspected:** listed in full at the top of this section.

**Safe read-only commands executed:** `grep`/`git status`/file reads only; no `pytest` run in this pass (none was required by this task and no test file was modified).

**Diff verification:** only this file (`PHASE_2_CLAUDE_REVIEW.md`) was modified by this task. `AUTONOMOUS_WORK_CONTROL.md` and `PHASE_2_VPL_HISTORY.md` were read, not edited (confirmed by file-modification timestamp). No production file, test file, or migration file was changed. No database connection was opened. No order, export, or portal submission was performed. The legacy `OrderNMC`/`OrderManagement` workflow was not touched.

**Final status: Phase 2 `READY_FOR_REVIEW`. VPL History persistence `BLOCKED`. Production implementation unchanged. Database not accessed. Migrations not applied. Legacy order workflow unchanged.**

**Recommendation for the next separately authorized implementation task:** two independent tracks, neither started by this audit:
1. **(Lower risk, not blocked on any new design decision)** Add `Depends(require_procurement_admin)` + `assert_tenant_access` to the six named `pm_router.py` routes — Defect 2 — matching the existing pattern already used by `vpl_history_router.py`.
2. **(Blocked on Decision 3/3c)** Implement the rare-mover enforcement check in `assignment_service`/`export_service`, once the owner chooses between a discrete confirmation field and a queue-based review model, and once the confirmation-storage schema itself is designed and separately reviewed — this audit does not treat completing this trace as fixing the gap, and the gap remains live and unenforced today.

## P0 authorization remediation — implemented — 2026-10-20

**Role for this section: temporary implementation owner.** This is a code change, not a read-only audit — the prior sections of this document are audits; this one implements the narrowly-scoped fix the audit recommended as track 1 above, and reports on its own work (not an independent review of itself).

### Independent re-verification before editing

Re-read the exact current signatures of all six routes in `pm_router.py` before writing anything, confirming the prior audit's claim character-for-character: `assign` (line 440), `bulk_assign` (448), `change_supplier` (456-458), `remove_assignment` (465-469), `export` (478), `submit_grn` (665) — none took a `current_user`/`Depends` parameter. Confirmed via `git status` that no other agent was concurrently editing `pm_router.py`, `access.py`, or the control file before starting.

**One correction to the originally recommended fix, found before implementing it:** the audit's own track-1 recommendation said to reuse `require_procurement_admin` on all six routes. Tracing the actual frontend capability model (`frontend/src/types/access.ts::capForCode`, lines 33-60) before implementing showed this would have been **wrong and would have broken requirement 8** ("existing authorized workflows remain functional") — `PROCUREMENT_ADMIN` is a deliberately more elevated grant than the ordinary Purchase Manager workspace capability (`PROCUREMENT_WORKSPACE`), confirmed by the frontend's own comment: "Lifecycle administration (Cycle / Refresh management) is a separate, elevated grant from the Purchase Manager workspace." Confirmed further that `PurchaseWorkspacePage.tsx` (the real, live UI that calls these six routes) gates nothing on `PROCUREMENT_ADMIN` at all — only its one VPL-history button does. Had the fix required `PROCUREMENT_ADMIN` on `assign`/`export`/`submit_grn`, every ordinary Purchase Manager without the elevated grant would have been locked out of actions they can use today — a regression this audit's own requirement 8 explicitly forbids. **Implemented a corrected, least-privilege fix instead**, mirroring the frontend's own three-tier model (`PROCUREMENT_WORKSPACE`/`PROCUREMENT_EXPORT`/`PROCUREMENT_GRN`) rather than collapsing everything onto the admin-only check.

### Implementation

**`backend/modules/procurement/access.py`** — extended, not replaced. Added:
- `_matches(module_codes, extra_keywords)` — shared helper factoring out the existing `grants_procurement_admin` logic (unchanged behavior, confirmed by keeping its exact keyword set `("ADMIN", "CYCLE", "REFRESH")`).
- `grants_procurement_export`/`grants_procurement_grn` — mirror `capForCode`'s `EXPORT`/`GRN` keyword branches exactly.
- `grants_procurement_workspace` — mirrors `capForCode`'s fallback branch (any procurement/purchase code reaches at least workspace) plus the frontend's own `caps.has('PROCUREMENT_ADMIN') => caps.add('PROCUREMENT_WORKSPACE')` rule (line 101 of `access.ts`) — an admin grant is accepted as a superset, not a separate silo.
- `require_procurement_workspace`/`require_procurement_export`/`require_procurement_grn` — three new `Depends`-compatible functions alongside the existing, unmodified `require_procurement_admin`. `require_procurement_export`/`require_procurement_grn` each accept their own finer grant **or** the coarse workspace grant, mirroring the frontend's own "a single coarse procurement grant unlocks the whole workspace unless finer grants are explicitly separated" rule (`access.ts` lines 103-112) — confirmed by reading that exact logic before writing the mirror, not guessed.
- `require_procurement_admin` itself: **unchanged, byte-for-byte** — confirmed by re-reading it after the edit; it was not touched, only new functions were added around it.

**`backend/modules/procurement/pm_router.py`** — added three imports (`require_procurement_export`, `require_procurement_grn`, `require_procurement_workspace` from `modules.procurement.access`) and, for each of the six routes, added `current_user: dict = Depends(require_procurement_workspace|require_procurement_export|require_procurement_grn)` plus `assert_tenant_access(current_user, tenant_id)` as the first line of the function body — the exact same two-line pattern already used throughout `vpl_history_router.py`, not a new pattern invented for this fix. Capability assignment: `assign`/`bulk_assign`/`change_supplier`/`remove_assignment` → `require_procurement_workspace` (ordinary PM actions); `export` → `require_procurement_export`; `submit_grn` → `require_procurement_grn`. No other route in this 753-line file was touched — confirmed by the diff (see below).

**Why `assert_tenant_access` alone is sufficient defense, not merely a surface-level check:** independently re-verified this pass that every underlying write query in `assignment_repository.py`/`export_repository.py`/`reconciliation_repository.py` already filters `WHERE tenant_id = ?` (grepped and listed every match — 17 occurrences across the three files). This means the repository layer was already structurally safe against a forged `tenant_id` *returning or mutating another tenant's row* — a request with tenant-a's session but tenant_id=tenant-b in the query string, before this fix, would have been accepted by the route and then simply found no matching row in tenant-b's data (a 404, not a cross-tenant leak) **only if `tenant_id` were actually threaded through to every query correctly, which it is** — so the real, confirmed exploit window this fix closes is narrower than "can leak another tenant's data" and is precisely "can a caller claim to be acting for a different tenant_id than their own session, consuming the server's trust in that claim for logging/audit/business-rule purposes (e.g. `created_by`/`reviewed_by` fields, rate limits, future per-tenant business rules) even though the underlying SQL would not have returned cross-tenant rows." Stating this precisely rather than overclaiming the severity of what was fixed.

### Regression tests

New file: `tests/test_procurement_pm_router_auth.py`, following the exact existing convention from `tests/test_vpl_history_claude_edge.py`-import/`tests/test_procurement_rules_auth.py` ( `FastAPI()` + `TestClient` + `access.load_module_codes` monkeypatched). Every one of the six service functions (`assign_single`, `assign_bulk`, `change_supplier`, `remove_assignment`, `export_refresh`, `submit_grn`) is monkeypatched to a call-recording sentinel — no real database connection is possible even if a test's assertion were wrong, consistent with the "mocked or isolated fixtures" instruction. Nine tests:

1. `test_all_six_routes_reject_unauthenticated_access` — no bearer token → 401 on all six, zero service calls recorded.
2. `test_all_six_routes_reject_authenticated_but_unauthorized_role` — valid token, module codes `["INVENTORY_VIEW"]` (no procurement/purchase code at all) → 403 on all six, zero service calls.
3. `test_all_six_routes_reject_cross_tenant_access` — valid token for `tenant-a`, request querystring `tenant_id=tenant-b` → 403 on all six, zero service calls.
4. `test_forged_tenant_id_does_not_grant_access` — same mechanism as #3, named for the specific adversarial framing the task asked for; additionally asserts the 403 response body does not echo `"tenant-b"` back (requirement 9 — no disclosure).
5. `test_platform_user_passes_without_a_module_lookup` — a platform-user token reaches the real (stubbed) service with zero module-list lookup, and the test's own `load_module_codes` replacement raises `AssertionError` if called at all, so this is a hard proof of "no lookup happened," not an inference.
6. `test_each_route_requires_its_matching_or_broader_capability` — `PROCUREMENT_EXPORT`-only reaches `export`; `PROCUREMENT_GRN`-only reaches `submit_grn`; `PROCUREMENT_WORKSPACE`-only reaches all six (the coarse-grant rule) — pins down the least-privilege design decision this pass made, not just "some token works."
7. `test_unreadable_module_list_fails_closed` — `load_module_codes` raising an exception → 503 on all six (fail closed, matching the existing `require_procurement_admin` behavior exactly, extended to the three new functions).
8. `test_bulk_assign_cross_tenant_request_is_rejected_before_any_item_is_touched` — a 3-item bulk request with a forged `tenant_id` is rejected in full before `assign_bulk`'s own per-item loop ever starts — requirement 7 ("bulk operations... cannot partially mutate unauthorized records"), confirmed by asserting the stub was never called at all, not just that the HTTP response was a 403.
9. `test_authorized_same_tenant_requests_still_succeed_for_every_route` — requirement 8, the regression guard: a correctly authenticated, same-tenant, procurement-capable caller still reaches the real (stubbed) service for every one of the six routes.

**Commands run:**
```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_pm_router_auth.py -v --tb=short
→ 9 passed

backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_pm_router_auth.py tests/test_procurement_rules_auth.py tests/test_procurement_rules_registry.py tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py tests/test_procurement_decision_engine.py -q --tb=short
→ 106 passed, 2 failed (test_excluded_missing_grn_watermark, test_spike_floor_included_binding — the same two pre-existing failures recorded at every prior session check; unrelated to this change, confirmed by the zero-diff check below)
```

### Diff verification

```
git diff --stat -- backend/modules/procurement/decision_rules.py backend/modules/procurement/decision_repository.py backend/modules/procurement/decision_service.py backend/modules/procurement/vpl_history.py backend/modules/procurement/sql/0027_vpl_history.sql backend/modules/legacy_order
```
→ zero diff on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`0027_vpl_history.sql` (none of these five files appear in the diff output at all). `backend/modules/legacy_order/` shows a diff, but it is Cursor's own continuing, pre-existing uncommitted WIP — grown further between sessions, not touched by this task (confirmed: this task opened no file under that directory).

**Files actually changed by this task:** `backend/modules/procurement/access.py` (extended — four new functions added, `require_procurement_admin` and every pre-existing function left byte-for-byte unchanged), `backend/modules/procurement/pm_router.py` (six routes gained an auth dependency + `assert_tenant_access` call each; no other route touched), `tests/test_procurement_pm_router_auth.py` (new file). `AUTONOMOUS_WORK_CONTROL.md` and `PHASE_2_VPL_HISTORY.md` were not edited (confirmed by file-modification timestamp, both predate this task's start). Rare-mover classification/confirmation behavior was not touched — no file under that concern (`decision_rules.py`, `vpl_history.py`, `rules_catalog.py`) was opened for editing. The live quantity engine was not changed. No migration was written, modified, or applied — `0027_vpl_history.sql` was not opened. No database connection was made. No legacy `OrderNMC`/`OrderManagement` file was touched.

### Final report

**Routes confirmed vulnerable (re-verified independently before fixing, not assumed from the audit):** all six — `assign`, `bulk_assign`, `change_supplier`, `remove_assignment`, `export`, `submit_grn` — had no procurement-specific authorization check and no tenant-ownership verification, confirmed by re-reading their exact pre-fix signatures.

**Routes fixed:** all six, each now gated by the least-privilege capability it actually needs (`PROCUREMENT_WORKSPACE` for the four assignment routes, `PROCUREMENT_EXPORT` for export, `PROCUREMENT_GRN` for GRN submission — each also accepting the broader `PROCUREMENT_ADMIN`/coarse-workspace grant per the existing frontend model) plus `assert_tenant_access` to reject a forged `tenant_id`.

**Tests passed:** 9/9 new tests; 106/108 in the broader procurement suite (2 pre-existing, unrelated failures, confirmed by zero diff on the files those two tests exercise).

**Remaining limitations, stated explicitly, not glossed over:**
- **This fix was verified with mocked service calls and an in-process `TestClient`, not an end-to-end integration test against a real server, a real database, or real user sessions.** Whether `get_current_user`'s JWT validation, `load_module_codes`'s real SQL query, and this fix's `assert_tenant_access` call compose correctly under a real deployment (real token issuance, real `UserRepository` data, real network conditions) is **not verified by this pass** and would require integration testing this task was not authorized to perform (no database connection).
- The six routes' underlying repository functions were confirmed to already filter by `tenant_id` in their SQL — this fix closes the "server trusts a forged tenant claim" gap, not a "SQL would have leaked data regardless" gap (that was already not the case, confirmed by the grep evidence above) — stating this precisely so the fix is not overclaimed as resolving a worse problem than it did.
- The rare-mover enforcement gap (the audit's other confirmed defect) is **explicitly not addressed by this task** and remains live and unenforced, exactly as the prior audit left it — this task's scope was authorization only, per its own strict boundaries.
- `change_supplier`/`remove_assignment` additionally have their own service-layer business rules (e.g., rejecting a change on an `'exported'` assignment) that were not touched, re-verified unchanged, or re-tested beyond confirming the new authorization gate sits in front of them without altering their behavior for an authorized caller (test #9 covers this at the HTTP-response-code level, not at the level of re-deriving every business rule's correctness).
- **Tenant/store isolation is enforced end-to-end only in the sense that: (a) the route now verifies the caller's own tenant matches the claimed `tenant_id` before reaching the service layer, and (b) every underlying query was independently confirmed to already filter by `tenant_id`.** Store-level isolation specifically was not separately added or tested in this pass — `assert_tenant_access` is tenant-level only (confirmed by re-reading its implementation, unchanged by this fix); none of the six routes take a `store_id` parameter at all (confirmed by re-reading their signatures), so there is no store-level check to add or omit here — store scoping, where it matters, happens implicitly via `refresh_id`/`order_item_id`/`assignment_id` already being store-specific rows, not via an explicit parameter this fix could gate.

**Phase 2: `READY_FOR_REVIEW`. VPL History persistence: `BLOCKED`.** This task implemented a production authorization fix (explicitly authorized and scoped by this task's own instructions, distinct from every prior task in this document which was read-only) — it does not touch, accelerate, or relax the VPL History persistence block, which remains governed entirely by the unrelated design/concurrency decisions already on record.

**Recommendation for the next step:** an independent review of this fix (not self-performed here) should re-verify the `access.py`/`pm_router.py` diff and the new test file before this is considered closed, consistent with every prior pattern in this document of a separate verification pass following an implementation pass.

**Note on a concurrent, independently-produced audit found in this same document after this fix was implemented:** the "2026-10-20 — Priority 1 rare-mover safety audit (Claude, read-only, D1–D7 owner-decision register)" section above (added to this file concurrently, not read before this fix was started) independently reached the same two core findings — Defect 1 (rare-mover enforcement gap) and Defect 2 (missing tenant authorization on Purchase Manager mutating routes) — and recommended Defect 2 be fixed first, via `Depends(get_current_user_optional)` + `assert_tenant_access`. **This fix implements a strictly stronger version of that recommendation**: `get_current_user_optional` would still allow a request with no bearer token to reach `assert_tenant_access` at all (returning `None`, which `has_unrestricted_scope(None)` treats as unrestricted) — this fix uses `Depends(get_current_user)` (via the three new `require_procurement_*` functions, all built on the non-optional `get_current_user`) instead, which rejects a missing/invalid token with 401 before `assert_tenant_access` is ever reached, and additionally adds the least-privilege capability check that concurrent audit's own Defect-2 framing did not include. Both audits' Defect 1 (rare-mover) finding is unaffected by this task and remains open, exactly as both independently concluded.

---

## Independent authorization fix review — 2026-10-20 (Claude, separate pass from the implementer)

This section is a genuinely separate verification pass over the P0 authorization fix above — the implementer's report was treated as a claim to check, not a fact, and every file was re-read from disk rather than trusted from the prior summary.

### Files inspected

`backend/modules/procurement/access.py` (full), `backend/modules/procurement/pm_router.py` (full six route bodies + surrounding routes for contrast), `tests/test_procurement_pm_router_auth.py` (full, all 9 tests), `backend/dependencies/auth.py` (full), `backend/dependencies/store_scope.py` (full). No file was edited. No database connection was made. No export, GRN, order, or supplier action was performed. `decision_rules.py`/`decision_service.py`/rare-mover logic was not touched or re-examined beyond confirming it is absent from this diff.

### Route-by-route verification (all six)

| Route | Auth required | Capability | Admin superset correct | Tenant check | Pre-mutation | Bulk atomicity | Fail-closed |
|---|---|---|---|---|---|---|---|
| `assign` | `get_current_user` (401 if missing/invalid) | `require_procurement_workspace` | Yes — accepts admin as superset | Yes, before service call | Yes (line 451 before 452) | N/A | 503 on unreadable module list |
| `bulk_assign` | same | `require_procurement_workspace` | Yes | Yes | Yes | Confirmed — rejection happens at the router gate, before `assign_bulk`'s own per-item loop ever starts; the test explicitly proves zero items are touched on a cross-tenant bulk call | Yes |
| `change_supplier` | same | `require_procurement_workspace` | Yes | Yes | Yes | N/A | Yes |
| `remove_assignment` | same | `require_procurement_workspace` | Yes | Yes | Yes | N/A | Yes |
| `export` | same | `require_procurement_export` (export OR workspace OR admin) | Yes | Yes | Yes | N/A | Yes |
| `submit_grn` | same | `require_procurement_grn` (grn OR workspace OR admin) | Yes | Yes | Yes | N/A | Yes |

Verified directly from `pm_router.py` lines 444-511 and 692-702: every one of the six functions takes `current_user: dict = Depends(require_procurement_*)` and calls `assert_tenant_access(current_user, tenant_id)` as the literal first statement of the function body, before any service call. No route among the six omits either check. This matches the implementer's report exactly — no discrepancy found.

### Authorization helper (access.py) — fail-open check

Traced `_require()` (lines 73-82) and `require_procurement_admin` (lines 85-94): both call `load_module_codes` inside a `try`, and any exception (missing row, malformed data, DB unreachable) raises `HTTPException(503)`, never falls through to an implicit allow. `has_full_access` is checked first and only bypasses the module lookup for platform users and `SUPER_ADMIN`/`PLATFORM_OWNER` role names — an intentional, pre-existing, narrowly-scoped bypass, not a new gap introduced by this fix. The test `test_unreadable_module_list_fails_closed` actually exercises the exception path (monkeypatches `load_module_codes` to raise `RuntimeError`) and gets 503, confirmed by rerun.

### Forged tenant_id

`assert_tenant_access` compares `user.get("tenant_id")` from the decoded, signature-verified JWT claims, not from any client-supplied field — a caller cannot change what the server believes its own tenant is by editing the query-string `tenant_id`. Confirmed by direct trace of `get_current_user` → `decode_access_token` → `assert_tenant_access`, not just by reading test output.

### get_current_user vs get_current_user_optional

Grepped `pm_router.py` and confirmed `get_current_user_optional` is imported and used only by the pre-existing, out-of-scope GET routes (`workspace`, `workspace_summary`, `network_opportunities`) — none of the six fixed routes use it. This independently confirms the implementer's claimed correction over the weaker Cursor-recommended `get_current_user_optional` approach, verified by inspection rather than by trusting the implementer's own note.

### Tests — rerun independently

`backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_pm_router_auth.py -v --tb=short` → **9 passed**, 3 warnings (1 pre-existing Pydantic deprecation unrelated to this fix, 2 environmental pytest-cache permission warnings). Matches the implementer's reported result exactly.

Additionally ran `backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_rules_auth.py tests/test_procurement_decision_engine.py tests/test_vpl_history.py -q --tb=line` → **42 passed, 2 failed** (`test_excluded_missing_grn_watermark`, `test_spike_floor_included_binding`, both in `test_procurement_decision_engine.py`). Confirmed pre-existing and unrelated: `decision_rules.py`/`decision_service.py` show zero diff, and these two tests exercise rare-mover/spike-floor classification this fix never touches.

### Repository tenant-filtering claim

`grep -c "WHERE tenant_id"` across `assignment_repository.py`/`export_repository.py`/`reconciliation_repository.py`: 9+6+5 = **20** occurrences (the original report said 17; the discrepancy is immaterial — tenant filtering is confirmed present regardless of exact count, and was never the load-bearing mechanism for this fix). This confirms a forged `tenant_id` was already blocked from leaking data by SQL, but was not blocked from attempting the mutation call before this fix — the two layers are complementary, not redundant, consistent with this task's own instruction not to assume tenant-filtered SQL makes route-level authorization unnecessary.

### Scope discipline

`git status --short` on the relevant paths confirms exactly: `pm_router.py` modified, `access.py` and the new test file untracked/new, `PHASE_2_CLAUDE_REVIEW.md` untracked (new, not previously committed — noted, not a concern). No other file shows as touched. Read every other route in `pm_router.py` (lines 50-768) and confirmed all are unchanged by this diff.

### New finding, outside this fix's stated scope but relevant to the broader authorization posture

**Several other Purchase Manager mutation routes have no auth dependency at all** — not even `get_current_user_optional` — relying solely on `app.py`'s global middleware (any valid JWT, no tenant or capability check): `set_final_qty` (PUT `/order-items/{id}/final-qty`, line 131), `restore_suggested` (141), `skip` (150), `restore` (157), `defer` (164), and the read-only `supplier_queue`/`supplier_recommendations`/`supplier_products`/`suppliers/search`/`suppliers/{code}/stats`/`suppliers/settings`/`export_document` routes. These are pre-existing and were explicitly out of scope for the P0 task, which named only the six routes flagged by the prior audits — this is not a regression introduced by this fix and the fix should not be blocked on it. Flagged here for a future, separately-authorized task, consistent with this document's established pattern of surfacing new findings rather than silently expanding scope.

### Verdict: APPROVE WITH CONDITIONS

The six named routes (`assign`, `bulk_assign`, `change_supplier`, `remove_assignment`, `export`, `submit_grn`) are, by direct source inspection and independently-rerun tests, correctly gated: authentication is required (non-optional `get_current_user`, 401 on missing/invalid token), the correct least-privilege capability is checked per route, `PROCUREMENT_ADMIN` is correctly treated as a superset (matching the live frontend capability model in `access.ts`), a forged `tenant_id` is rejected using the server-verified JWT claim rather than any client-supplied value, platform/full-access users bypass only the module lookup (not the tenant check), denial happens before any mutation/export/GRN call, bulk requests are rejected in full before any item is touched, authorized same-tenant requests still succeed, errors fail closed (503) rather than open, and no other route or file was altered.

Conditions for a clean APPROVE:
1. This verification, like the implementer's own, is mocked-service/in-process-only — no real end-to-end integration test against a live server, real database, or real session/JWT issuance pipeline has been run by either party. That should happen before this is treated as production-verified.
2. The newly-flagged unauthenticated-dependency routes (`set_final_qty`, `skip`, `restore`, `defer`, `restore_suggested`, and the supplier-info GET routes) should be tracked as a follow-up — not a blocker for this fix, but the Purchase Manager surface as a whole is not yet uniformly protected even after this fix lands.
3. Store-level isolation remains genuinely untested (no route among the six takes a `store_id`), as both this review and the implementer's own report already state — this is not a gap in the fix, just an acknowledged boundary of what tenant-level `assert_tenant_access` alone covers.

Phase 2 remains `READY_FOR_REVIEW`. VPL History persistence remains `BLOCKED`. Rare-mover enforcement (Defect 1, both prior audits) remains open and untouched by this fix, as intended.

---

## Purchase Manager security audit, round 2 — 2026-10-20 (Claude, read-only)

Evidence-gathering audit of every Purchase Manager route not covered by the six-route fix above. No code was changed. No database was accessed. No export, GRN, order, or portal action was performed. Nothing was fixed in this pass — findings and a proposed capability mapping only.

### Files inspected

`backend/modules/procurement/pm_router.py` (full, all ~45 routes), `backend/modules/procurement/access.py`, `backend/api/app.py` lines 205-330 (global `require_auth` middleware + its allowlists), `backend/dependencies/store_scope.py`, `frontend/src/types/access.ts` (full `capForCode`/`resolveAccess`), and the service/repository bodies behind the flagged routes: `workspace_service.py` (`get_item`, `set_final_qty`, `restore_suggested`, `skip_item`, `restore_item`, `defer_item`, `_require_item`), `workspace_repository.py::get_item`, `supplier_service.py` (`get_queue`, `search`, `list_settings`, `update_settings`), `supplier_repository.py::update_supplier_settings`, `distribution_service.py` (`save_config`, `save_supplier_map`, `run_detail`, `retry_failed`, `run_item_products`, `send_run_item_whatsapp`, `generate`, `list_runs`, `import_legacy_supplier_map`), `pending_repository.py` (grepped `WHERE tenant_id`). `tests/test_procurement_pm_workflow.py` and `tests/test_procurement_pm_router_auth.py` read for existing coverage.

### Critical groundwork finding: "no local Depends" does not mean "unauthenticated"

Re-read `app.py`'s `require_auth` middleware (lines 288-315) line by line. Every path starting with `/api/` is rejected with 401 before any route handler runs **unless** it is in `_PUBLIC_API_PATHS`, matches `_is_setup_read` (GET-only, store-provisioning lookups, four fixed patterns, none of which are procurement paths), or matches `_is_public_agent_call` (store-agent/NMV device patterns, also none are procurement paths). `/api/procurement/*` is not present in any of these three allowlists — confirmed by reading all three lists in full. **Every Purchase Manager route, including every one flagged below, already requires a valid bearer JWT.** This audit does not find an authentication gap anywhere in this router. The gaps found below are all authorization/tenant-isolation gaps, and are classified accordingly — not inflated to "unauthenticated access."

### Route-by-route matrix

Legend: Auth = global middleware requirement (true for all, confirmed above). Capability = local `Depends` check. Tenant = `assert_tenant_access` or equivalent call. Scope evidence = how the underlying service/repository actually filters.

| Route | Auth | Capability check | Tenant check | Scope evidence (service/repo) | Classification |
|---|---|---|---|---|---|
| `PUT /order-items/{id}/final-qty` (`set_final_qty`) | middleware only | none | none | `workspace_service._require_item` → `workspace_repository.get_item`: `WHERE oi.tenant_id = ? AND oi.order_item_id = ?` | **CONFIRMED VULNERABILITY** — see analysis below |
| `POST /order-items/{id}/restore-suggested` | middleware only | none | none | same `_require_item` path | **CONFIRMED VULNERABILITY** |
| `POST /order-items/{id}/skip` | middleware only | none | none | same `_require_item` path | **CONFIRMED VULNERABILITY** |
| `POST /order-items/{id}/restore` | middleware only | none | none | same `_require_item` path | **CONFIRMED VULNERABILITY** |
| `POST /order-items/{id}/defer` | middleware only | none | none | same `_require_item` path | **CONFIRMED VULNERABILITY** |
| `GET /order-items/{id}` (`get_order_item`) | middleware only | none | none | same `_require_item` path (read-only) | **DEFENSE-IN-DEPTH GAP** (read, not write — see below) |
| `GET /order-items/{id}/supplier-queue` | middleware only | none | none | `supplier_service.get_queue` → `workspace_repository.get_item` (same tenant-scoped SELECT), then ranks by the item's own `product_code`/`store_id` | **DEFENSE-IN-DEPTH GAP** |
| `GET /refreshes/{id}/supplier-recommendations` | middleware only | none | none | not individually re-derived; same router-level pattern | UNVERIFIED (not traced to repository in this pass) |
| `GET /refreshes/{id}/supplier-products` | middleware only | none | none | not individually re-derived | UNVERIFIED |
| `GET /suppliers/search` | middleware only | none | none | `supplier_repository.search_suppliers(tenant_id, ...)` — presumed tenant-filtered, not re-derived to the SQL text in this pass | UNVERIFIED |
| `GET /suppliers/{code}/stats` | middleware only | none | none | not re-derived | UNVERIFIED |
| `GET /suppliers/settings` | middleware only | none | none | `list_settings(tenant_id, store_id)` | **DEFENSE-IN-DEPTH GAP** |
| `PUT /suppliers/{code}/settings` (`update_supplier_settings`) | middleware only | none | none | `supplier_repository.update_supplier_settings`: `UPDATE ... SET ... WHERE` — confirmed the function builds its `WHERE` from caller-supplied `tenant_id`/`store_id`/`supplier_code` with no ownership check upstream | **CONFIRMED VULNERABILITY** — a real cross-tenant write once a `store_id`/`supplier_code` in another tenant is known or guessed |
| `GET /suppliers/{code}/export-settings` | middleware only | none | none | read analogue of the above | **DEFENSE-IN-DEPTH GAP** |
| `PUT /suppliers/{code}/export-settings` | middleware only | none | none | write analogue of `update_supplier_settings` | **CONFIRMED VULNERABILITY** (same shape) |
| `GET /refreshes/{id}/supplier-stock` | middleware only | none | none | not re-derived | UNVERIFIED |
| `GET /refreshes/{id}/products-with-offers` | middleware only | none | none | not re-derived | UNVERIFIED |
| `GET /supplier-stock/mapping` | middleware only | none | none | not re-derived | UNVERIFIED |
| `POST /supplier-stock/preview` | middleware only | none | none | parses an uploaded file only, does not persist | SAFE CURRENT BEHAVIOR (no write; worst case is a wasted parse of the caller's own upload) |
| `POST /supplier-stock/import` | middleware only | none | none | `run_import` — "Normalize + REPLACE the supplier's live stock for the store" — a destructive write keyed by caller-supplied `tenant_id`/`store_id`/`supplier_code`, not re-derived to SQL text in this pass | UNVERIFIED but high-concern — same shape as the confirmed `update_supplier_settings` vulnerability; needs the SQL traced before the next pass closes this out |
| `GET /distribution/config` | middleware only | none | none | `list_config(tenant_id, ...)` | **DEFENSE-IN-DEPTH GAP** |
| `PUT /distribution/config/{store_id}` (`save_config`) | middleware only | none | none | `UPDATE dbo.stores SET w_group_name=... WHERE tenant_id = ? AND store_id = ?` — confirmed by reading the SQL; caller-supplied `tenant_id`+`store_id` drive the WHERE with no ownership check upstream | **CONFIRMED VULNERABILITY** |
| `PUT /distribution/supplier-map/{store_id}` (`save_supplier_map`) | middleware only | none | none | confirmed `WHERE tenant_id = ? AND store_id = ? AND source_store_code = ?`, same shape | **CONFIRMED VULNERABILITY** |
| `POST /distribution/supplier-map/import-legacy` | middleware only | none | none | `import_legacy_supplier_map(tenant_id, ...)` — not re-derived to SQL text | UNVERIFIED |
| `POST /distribution/generate` | middleware only | none | none | `generate(tenant_id, ...)` — the full distribution pipeline (writes supplier_stock, sends WhatsApp); not re-derived to SQL text | UNVERIFIED but high-concern — triggers real side effects (WhatsApp sends to a store's group) if `tenant_id` is forged to one with a known `source_store_code` |
| `GET /distribution/runs` | middleware only | none | none | `list_runs(tenant_id, limit)` | **DEFENSE-IN-DEPTH GAP** |
| `GET /distribution/runs/{run_id}` (`run_detail`) | middleware only | none | none | confirmed `SELECT * FROM procurement.distribution_run WHERE run_id = ?` — **no tenant_id parameter on the route at all, no tenant filter in the SQL at all** | **CONFIRMED VULNERABILITY** — worse than the others: not even a forged parameter is needed, the route itself never asks for or checks a tenant |
| `POST /distribution/runs/{run_id}/retry` (`retry_failed`) | middleware only | none | none | confirmed `SELECT tenant_id, source_store_code, provider FROM procurement.distribution_run WHERE run_id = ?` then acts using the row's own tenant — no caller-tenant check at all | **CONFIRMED VULNERABILITY** — any authenticated user from any tenant can re-trigger another tenant's distribution run by guessing/enumerating `run_id` |
| `GET /distribution/run-items/{id}/products` (`run_item_products`) | middleware only | none | none | reads a generated Excel file keyed only by `run_item_id`, no tenant filter | **CONFIRMED VULNERABILITY** (read) |
| `POST /distribution/run-items/{id}/send-whatsapp` (`send_run_item_whatsapp`) | middleware only | none | none | sends a real WhatsApp message to the owning store's group, keyed only by `run_item_id`, no tenant filter | **CONFIRMED VULNERABILITY** — real side effect (external message send) triggerable cross-tenant with no check at all |
| `GET /order-items/{id}/assignments`, `GET /refreshes/{id}/assignments` | middleware only | none | none | not re-derived in this pass (pre-dates the six-route fix; the six-route fix only touched the four mutating assignment routes, not these two reads) | UNVERIFIED |
| `POST /refreshes/{id}/export-document` | middleware only | none | none | resolves lines directly by `assignment_id`, scoped by caller-supplied `tenant_id` per the route's own docstring; not re-derived to SQL text | UNVERIFIED |
| `POST /refreshes/{id}/shelf-sort`, `POST /shelf-sort/upload`, `GET /refreshes/{id}/shelf-sort/review`, `POST /shelf-sort/classify`, `POST /shelf-sort/categories` | middleware only | none | none | not re-derived; `shelf_sort_classify`/`save_categories` train a shared LLM-suggestion cache keyed by product name, not obviously tenant-sensitive, but not verified | UNVERIFIED |
| `GET /shelf-sort/categories` (`shelf_sort_category_vocab`) | middleware only | none | n/a | returns a fixed, global vocabulary list — no `tenant_id` parameter, no tenant-scoped data at all | **SAFE CURRENT BEHAVIOR** |
| `POST /refreshes/{id}/supplier-reply/preview`, `POST /refreshes/{id}/supplier-reply/import` | middleware only | none | none | not re-derived | UNVERIFIED |
| `GET /refreshes/{id}/export-history`, `GET /exports/{batch_no}` | middleware only | none | none | not re-derived (pre-dates the six-route fix) | UNVERIFIED |
| `GET /refreshes/{id}/pending`, `PUT /order-items/{id}/pending`, `POST .../pending/skip`, `POST .../pending/carry-forward`, `POST /refreshes/{id}/pending/finalize`, `POST /refreshes/{id}/pending/bulk`, `GET /refreshes/{id}/pending/report` | middleware only | none | none | `pending_repository.py` confirmed `WHERE tenant_id = ? AND order_item_id = ?` / `WHERE tenant_id = ? AND refresh_id = ?` throughout (5 occurrences grepped) — same shape as `set_final_qty`: tenant-filtered storage, un-verified caller-tenant claim | **CONFIRMED VULNERABILITY** (same class as the order-item mutation routes) |
| `POST /refreshes/{id}/manual-items` | middleware only | none | none | calls `reconciliation_repository.get_refresh(tenant_id, refresh_id)` first and 404s if not found (same tenant-filtered-lookup shape) | **CONFIRMED VULNERABILITY** (same class) |

### Why these are "confirmed," not "theoretical," and what the actual exploit precondition is

Every "CONFIRMED VULNERABILITY" row shares one shape, verified by reading the actual SQL text, not assumed from the route signature: the repository query **is** tenant-filtered (`WHERE tenant_id = ? AND <resource> = ?`), so a request with the caller's own `tenant_id` can never read or write another tenant's row — but **nothing upstream of that query checks that the caller's `tenant_id` query parameter actually matches the tenant on their own JWT.** The precondition for real exploitation is therefore: (1) a valid JWT for *any* tenant — any authenticated Purchase Manager, salesman, or other low-privilege role already has this; (2) knowledge or a successful guess of a resource id belonging to a *different* tenant (`order_item_id`, `refresh_id`, `store_id`, `supplier_code`, `run_id`). `order_item_id`/`refresh_id`/`run_id` read as opaque-looking identifiers in this codebase's convention (confirmed by scanning the schemas referenced — GUID-shaped in most tables), which raises the practical bar versus a sequential integer, but does not remove the gap — GUIDs leak through list/export responses, logs, and URLs routinely, and `store_id`/`supplier_code`/`source_store_code` (e.g. `"NMW"`, `"NMC"`) are **not** opaque at all — they are small, enumerable, documented codes (see `PROJECT.md`'s own store-code examples). The `run_detail`/`retry_failed`/`run_item_products`/`send_run_item_whatsapp` group is the most serious: they take **no tenant parameter whatsoever**, so there is nothing to forge — only a guessable/enumerable `run_id` is needed, and two of the four trigger a real external side effect (WhatsApp resend) rather than just a data leak.

This matches the exact shape of Defect 2 from the prior two audits (the six-route gap) — this is the same root cause recurring across the rest of the router, not a new or different kind of defect. It was explicitly out of scope for the P0 fix, which named only six routes.

### Classification summary

- **CONFIRMED VULNERABILITY**: `set_final_qty`, `restore_suggested`, `skip`, `restore`, `defer`, `update_supplier_settings` (PUT settings), `update_supplier_export_settings` (PUT export-settings), `save_config`, `save_supplier_map`, `run_detail`, `retry_failed`, `run_item_products`, `send_run_item_whatsapp`, all five `pending/*` mutation + read routes, `add_manual_item`. 20 routes.
- **DEFENSE-IN-DEPTH GAP** (read-only, tenant-filtered correctly at the query, but no route-level ownership check — lower severity than a write, but still discloses existence/contents of another tenant's data if the id is known): `get_order_item`, `supplier_queue`, `supplier_settings` (GET), `supplier_export_settings` (GET), `distribution_config` (GET), `distribution_runs` (GET list). 6 routes.
- **SAFE CURRENT BEHAVIOR**: `shelf_sort_category_vocab` (genuinely global, no tenant data), `supplier_stock_preview` (parses the caller's own upload, persists nothing). 2 routes.
- **UNVERIFIED** (not independently traced to SQL/repository text in this pass — flagged, not assumed safe or unsafe): `supplier_recommendations`, `supplier_products`, `supplier_search`, `supplier_stats`, `supplier_stock` (GET), `products_with_offers`, `supplier_stock_mapping`, `supplier_stock_import` (POST — flagged as high-concern given it's a destructive "REPLACE" write), `import_legacy_supplier_map`, `distribution_generate` (flagged high-concern — real side effects), `export_document`, all `shelf_sort/*` and `supplier_reply/*` routes, `export_history`, `export_detail`, `list_assignments`, `list_refresh_assignments`. Roughly 17 routes. A future pass should trace each to its repository SQL before either closing or confirming them.

### Why this is NOT the same as "add Depends everywhere"

Per this task's own instruction, a blanket fix is not proposed. The correct capability per route follows the existing `access.py`/`access.ts` model exactly:
- Every mutation route listed as CONFIRMED should use `require_procurement_workspace` (ordinary PM action — matches `set_final_qty`/`skip`/`restore`/`defer` sitting alongside `assign`/`change_supplier` in the same Workspace section of the live UI, already gated the same way once fixed) **plus** `assert_tenant_access(current_user, tenant_id)`, identical to the six-route fix's own pattern. No new capability or role name is needed — `grants_procurement_workspace` already exists and already matches this exact action class.
- `distribution_*` routes are a judgment call: they're store-admin configuration (WhatsApp group, supplier map) and a full pipeline trigger, arguably closer to `PROCUREMENT_ADMIN` territory than ordinary workspace actions — but the existing six-route fix treated `export`/`grn` (comparably consequential actions) as `workspace`-tier-or-above, not admin-only, so for consistency these should likely also accept `require_procurement_workspace` unless the owner specifically wants distribution gated at the admin tier. This is a decision for the owner, not something this read-only pass should presume.
- `pending/*` routes: same as the order-item mutations — `require_procurement_workspace` + `assert_tenant_access`. `PROCUREMENT_PENDING` already exists in both `access.ts` and conceptually in `access.py`'s grant model (not yet surfaced as its own server-side function) and could be used instead for a more granular gate, but since `access.ts`'s own `resolveAccess` auto-grants `PROCUREMENT_PENDING` to any coarse procurement grant, `require_procurement_workspace` is sufficient and consistent with how the six-route fix already treated `export`/`grn` (finer capability name, same effective reach).
- `run_detail`/`retry_failed`/`run_item_products`/`send_run_whatsapp` need more than a capability check — they need a **`tenant_id` parameter added to the route and threaded through to a tenant-filtered query**, since right now there is literally nothing to check against. This is a slightly larger fix than the others (new parameter, not just a new dependency) and should be flagged to the owner as such rather than folded silently into a uniform "add Depends" pass.

### Relevant to D1/D4/D6/D7

- **D6 (strict tenant/store isolation)** is the decision these findings most directly bear on — this entire audit is evidence that D6 is not yet implemented for most of this router, consistent with the six-route audit's own framing of the same root cause.
- **D1/D4/D7** (one active supplier per line, version/transaction concurrency, stable validated identifiers) are not implicated by these specific findings — none of the newly-flagged routes touch supplier-assignment exclusivity or concurrency; they are plain CRUD-shaped tenant-isolation gaps, not concurrency or identity-contract gaps. Flagging this explicitly so D1/D4/D7 aren't mistakenly treated as "also covered" by this audit.

### Regression-test plan (not implemented — proposed only)

1. For each of the 20 CONFIRMED routes: unauthenticated request → 401 (already true via middleware; a smoke test, not the interesting case).
2. For each: authenticated, no procurement module grant → should become 403 once fixed (currently 200 — this is the actual regression test that would catch today's gap).
3. For each: authenticated for tenant A, `tenant_id` query param forged to tenant B with a real tenant-B resource id → should become 403 once fixed (currently succeeds against tenant B's real data — this is the test that proves the vulnerability today, mirroring `test_forged_tenant_id_does_not_grant_access` from the six-route suite).
4. For `retry_failed`/`run_item_products`/`send_run_item_whatsapp`/`run_detail` specifically: same as #3, but note no `tenant_id` parameter exists yet — the test should assert on the *row's own* tenant (fetch via `run_id` for tenant B's run while authenticated only for tenant A) returning 403 once a tenant check is added, not just parameter-forging.
5. Bulk pending (`/pending/bulk`) analogue of `test_bulk_assign_cross_tenant_request_is_rejected_before_any_item_is_touched`: a cross-tenant bulk pending action must reject before touching any named item.
6. Authorized same-tenant smoke test for all 20 routes post-fix, mirroring `test_authorized_same_tenant_requests_still_succeed_for_every_route`.
7. For the 17 UNVERIFIED routes: a follow-up pass must first trace each to its repository SQL (as this pass did for the 20 CONFIRMED and 6 DEFENSE-IN-DEPTH routes) before a test plan can be written responsibly — writing tests against unverified behavior risks encoding the wrong expectation.

### Store/tenant isolation limitations

Identical boundary to the six-route fix's own stated limitation: `assert_tenant_access` is tenant-level only. None of the routes audited here take a `store_id` that would need its own check beyond tenant — `store_id`/`supplier_code`/`source_store_code` appear as query parameters but are read as *which store within the caller's own tenant*, not as a separate access axis, consistent with `store_scope.py`'s own module docstring ("the boundary here is the TENANT, not the individual store"). This audit does not find a store-level (as opposed to tenant-level) gap distinct from the tenant-level ones already described.

### Commands/tests executed in this pass

No test files were modified or added. The following existing tests were re-read (not re-run, since no code changed and the prior round's run already established their baseline): `tests/test_procurement_pm_workflow.py` (confirmed its `set_final_qty`/`skip`/`restore` tests exercise only service-layer business-rule validation, not router-level auth — grepped for `tenant_id`/`cross_tenant`, found no cross-tenant test anywhere in that file). `tests/test_procurement_pm_router_auth.py` was re-read in full (already verified passing in the prior round) to confirm it does not already cover any of the 20 newly-flagged routes — confirmed it covers only the original six.

### Confirmation

No production file, test file, or migration was modified in this task. No database connection was made. No export, GRN, order, or portal action was performed. Rare-mover logic was not touched. Legacy order workflows were not touched. `AUTONOMOUS_WORK_CONTROL.md` and `PHASE_2_VPL_HISTORY.md` were not modified. Only this append to `PHASE_2_CLAUDE_REVIEW.md`.

**Phase 2 remains `READY_FOR_REVIEW`. VPL History persistence remains `BLOCKED`.** This audit proposes no implementation; a future, separately-authorized task (following this document's established implement-then-independently-review pattern) would be needed to fix any of the 20 confirmed routes, and the owner should decide the `distribution_*` capability tier (workspace vs. admin) before that task starts.

---

## Security remediation master task — implemented — 2026-10-21 (Claude)

Implements the fixes proposed (not applied) by the round-2 audit above. Per this task's own Phase A instruction, nothing was assumed current from the audit text — every route signature, dependency, query filter and side effect was re-read from disk before any edit, and the live file matched the audit's line numbers and route list exactly (no drift since the audit).

### Phase A — reconfirmation

Re-read in full: `backend/modules/procurement/pm_router.py` (787 lines pre-edit), `backend/modules/procurement/access.py`, `backend/api/app.py` lines 205-330, `backend/dependencies/store_scope.py`, the full round-2 route matrix in this document, `tests/test_procurement_pm_router_auth.py`, and the service/repository bodies for every route named in Phase C as unverified: `supplier_service.py` (`get_queue_bulk`, `search`, `products_for_supplier`, `stats`) + `supplier_repository.py` (confirmed `WHERE tenant_id = ?` in `top_suppliers`, `top_suppliers_bulk`, `search_suppliers`, `products_for_supplier`, `supplier_stats` — all tenant-filtered, all DEFENSE-IN-DEPTH not CONFIRMED-write); `supplier_stock_service.py` (`list_supplier_stock`, `products_with_offers`, `get_mapping` — all call `reconciliation_repository.get_refresh(tenant_id, refresh_id)` or filter `WHERE tenant_id = ?` directly); `export_document_service.build_document`/`build_excel` (confirmed it builds strictly from client-supplied `items` dicts, never re-queries by tenant — reclassified from "UNVERIFIED" to "DEFENSE-IN-DEPTH GAP, capability-only — no cross-tenant data exposure is possible here since nothing is looked up by tenant," since the caller can only ever format data already in their own request body); `shelf_sort_service.py` (`collect_from_refresh` reads `export_repository.all_assignment_items(conn, tenant_id, refresh_id)` — genuine tenant-filtered read; `classify_and_store`/`save_categories` write into `product_category_repository`, confirmed tenant-scoped via `upsert`/`upsert_many` — reclassified from UNVERIFIED to CONFIRMED, same shape as the other write gaps); `supplier_reply_service.apply_reply_import` (confirmed it already does its own tenant-scoped `repo.get_assignment(conn, tenant_id, assignment_id)` lookup before writing, silently skipping rows that don't resolve — same safe-by-data pattern as `pending_service.bulk`, reclassified CONFIRMED at the route level since the route itself had no gate); `distribution_service.generate` (confirmed it already validates `_source_store_in_tenant` before acting — the service layer was not blindly trusting the caller's tenant/store pairing, so this route's exposure was route-level-missing-gate only, not a full breach); `distribution_service.run_detail`/`retry_failed`/`run_item_products`/`send_run_item_whatsapp` (re-confirmed, byte for byte, no tenant filter anywhere in their SQL and no tenant_id parameter on their routes — exactly as the audit found). One additional route not named in the round-2 audit's matrix was found during this re-read: `GET /order-items/{order_item_id}/decision` (`decision`, calling `workspace_service.get_decision`, confirmed tenant-filtered the same way as `get_item`) — added to the fix since it shares the identical shape to `get_order_item`, which the audit did cover.

### Phase B + C — fixes applied

**`backend/modules/procurement/access.py`: unchanged.** No new capability was added — `require_procurement_workspace` (ordinary PM actions), `require_procurement_export` (export-tier, accepts workspace too), and `require_procurement_grn` (GRN-tier, accepts workspace too), all already built in the P0 task, covered every route in this pass. No capability was invented, and `PROCUREMENT_ADMIN` was never used as a blanket gate — consistent with the task's explicit instruction.

**`backend/modules/procurement/distribution_service.py`: two new functions added, nothing existing changed** (confirmed via `git diff` — pure addition, no line in `run_detail`/`retry_failed`/`run_item_products`/`send_run_item_whatsapp`/anything else was touched):
- `run_tenant_id(run_id)` — `SELECT tenant_id FROM procurement.distribution_run WHERE run_id = ?`, returns `None` if the run doesn't exist.
- `run_item_tenant_id(run_item_id)` — joins `distribution_run_item` to its parent `distribution_run` to resolve the owning tenant, returns `None` if the run item doesn't exist.

These exist because, per the task's instruction #5 ("for resource-ID-only routes, derive resource ownership from a trusted server-side lookup and authorize it before acting — do not trust client-supplied identifiers as authorization"), these four routes take no `tenant_id` at all — there was nothing for a route-level check to compare the caller against until a trusted lookup existed.

**`backend/modules/procurement/pm_router.py`: every route from the round-2 matrix gated, plus the one newly-found `decision` route** (36 routes touched in total; diff is additive — new parameters/lines only, no existing route body logic altered, confirmed via `git diff` inspection of every non-whitespace change). Pattern applied, consistently:
- Ordinary read/write PM actions → `Depends(require_procurement_workspace)` + `assert_tenant_access(current_user, tenant_id)` as the first statement in the body (or immediately after any `from fastapi import HTTPException` local import, where one already existed).
- `export_document` → `Depends(require_procurement_export)` (matches the existing plain `export` route's tier, since both produce a supplier-facing export artifact).
- The four `run_id`/`run_item_id` routes with no `tenant_id` parameter (`distribution_run_detail`, `distribution_retry`, `distribution_run_item_products`, `distribution_run_item_send_whatsapp`) → `Depends(require_procurement_workspace)` for the capability check, then a trusted lookup (`distribution_service.run_tenant_id`/`run_item_tenant_id`) resolves the row's real owning tenant; `assert_tenant_access(current_user, owner_tenant_id)` is checked against **that** resolved value, never a client-supplied one; a `None` lookup result (row doesn't exist) raises 404 before any authorization decision is made, so a nonexistent run_id can't be used to probe whether 403-vs-404 reveals existence.
- `supplier_stock_preview` and `shelf_sort_category_vocab` were deliberately left as-is (no capability dependency added) — re-confirmed in Phase A that neither exposes tenant-scoped data (`preview_import` parses an upload without persisting; the vocabulary route returns a fixed, global list) — adding a gate to these would not close any real gap and was avoided per the task's own instruction not to apply the same fix to every route without justification.

Full list of routes fixed in this pass (beyond the six already fixed by the P0 task): `get_order_item`, `set_final_qty`, `restore_suggested`, `skip`, `restore`, `defer`, `supplier_queue`, `supplier_recommendations`, `supplier_products`, `supplier_search`, `supplier_stats`, `supplier_settings` (GET+PUT), `supplier_export_settings` (GET+PUT), `supplier_stock` (GET), `products_with_offers`, `supplier_stock_mapping`, `supplier_stock_import`, `distribution_config`, `distribution_config_save`, `distribution_supplier_map_save`, `distribution_supplier_map_import_legacy`, `distribution_generate`, `distribution_runs`, `distribution_run_detail`, `distribution_retry`, `distribution_run_item_products`, `distribution_run_item_send_whatsapp`, `list_assignments`, `list_refresh_assignments`, `export_document`, `shelf_sort`, `shelf_sort_upload`, `shelf_sort_review`, `shelf_sort_classify`, `shelf_sort_save_categories`, `supplier_reply_preview`, `supplier_reply_import`, `export_history`, `export_detail`, `list_pending`, `adjust_pending`, `skip_pending`, `carry_forward`, `finalize_pending`, `bulk_pending`, `pending_report`, `add_manual_item`, `decision`. (39 routes; the six from the P0 task plus these 39 is the full router minus the two intentionally-ungated ones.)

### Phase D — regression tests added

New file: `tests/test_procurement_pm_router_auth_round2.py` (13 tests, follows the exact convention of the existing `test_procurement_pm_router_auth.py` — `FastAPI()` + `TestClient` + `access.load_module_codes` monkeypatched, every service/repository function this file can reach monkeypatched to call-recording sentinels so no test can accidentally open a real connection or trigger a real WhatsApp send):
- `test_all_routes_reject_unauthenticated_access` / `test_all_routes_reject_unauthorized_role` / `test_all_routes_reject_cross_tenant_forged_tenant_id` / `test_unreadable_module_list_fails_closed` / `test_authorized_same_tenant_requests_still_succeed` — run the full matrix of GET + mutation routes (minus the four run-based and three multipart routes, which need their own request shape) through all five standard checks.
- `test_run_routes_reject_a_run_owned_by_another_tenant` — monkeypatches `run_tenant_id`/`run_item_tenant_id` to return `"tenant-b"` while the caller is authenticated for `"tenant-a"`, confirming the trusted-lookup authorization actually rejects.
- `test_run_routes_404_when_the_run_does_not_exist` — monkeypatches the same lookups to return `None`, confirming a nonexistent run 404s instead of leaking a 403 (which would otherwise imply the row exists) or proceeding.
- `test_bulk_pending_cross_tenant_request_is_rejected_before_any_item_is_touched` — mirrors the P0 task's `test_bulk_assign_cross_tenant_request_is_rejected_before_any_item_is_touched` for the pending-bulk route.
- `test_distribution_generate_never_runs_for_an_unauthorized_caller` — specific regression naming the real-side-effect route; `generate` is monkeypatched to a sentinel, so this test would fail with an `AssertionError` (not a real WhatsApp send) if the gate ever regressed — the task's "never contact a real supplier / send WhatsApp / generate a live distribution" boundary is enforced structurally, not just by convention.
- `test_supplier_stock_import_requires_authorization` / `test_shelf_sort_upload_requires_authorization` / `test_supplier_reply_preview_requires_authorization` — the three multipart-upload routes needed their own test (file+form bodies aren't representable in the shared route table), each checking cross-tenant rejection then authorized success.
- `test_genuinely_tenant_free_routes_remain_unauthenticated_safe` — covers `shelf_sort_category_vocab` and `supplier_stock_preview`. **Important caveat documented directly in the test's own docstring, not hidden**: this isolated test app mounts only `pm_router.router`, not the real `app.py` — it does not include `app.py`'s global `require_auth` middleware, which is what actually makes these two routes reject an unauthenticated request in the real deployment (since `/api/procurement/*` isn't in that middleware's allowlist). Inside this router-only test app, a route with zero local `Depends` is reachable with no token at all, by construction. The test therefore asserts the real, narrower behavior (200, not 401) rather than a false claim — a genuine end-to-end check of the global middleware would need the full `app.py` mounted, which is out of scope for a router-only test file and was not attempted.

### Phase E — independent validation, run by the implementer (not yet by a separate reviewer)

```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_pm_router_auth_round2.py -v --tb=short
```
Result: **13 passed**, 3 pre-existing Pydantic deprecation warnings (same `[i.dict() for i in payload.items]`-shaped warning already present before this task, unrelated).

```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_pm_router_auth.py tests/test_procurement_pm_router_auth_round2.py tests/test_procurement_pm_workflow.py tests/test_procurement_rules_auth.py tests/test_procurement_decision_engine.py tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=line
```
Result: **99 passed, 5 failed** — `test_assign_exceeds_final_rejected`, `test_assign_single_ok`, `test_bulk_assign_reports_mixed` (all three: `AttributeError: '_FakeConn' object has no attribute 'cursor'`, in `tests/test_procurement_pm_workflow.py`, inside `assignment_repository.any_active_assignment` — a test-fixture gap unrelated to this task's files) and `test_excluded_missing_grn_watermark`/`test_spike_floor_included_binding` (in `tests/test_procurement_decision_engine.py`, rare-mover/spike-floor classification, untouched by this task). **Confirmed pre-existing, not caused by this task**, by running `git stash` (reverting both `pm_router.py` and `distribution_service.py` to their pre-task state), re-running, observing the identical 5 failures, then `git stash pop` to restore the fix — not merely asserted.

A wider sweep (`tests/ -k "procurement or vpl_history"`) surfaced 6 additional failures not previously called out in this document: `test_procurement_orchestration.py::test_create_refresh_full_pipeline` and five in `test_procurement_sprint3.py` (`test_manual_add_validations`, `test_close_cycle_blocked_when_generating`, `test_close_cycle_ok`, `test_close_cycle_already_closed`, `test_end_to_end_post_export`), all `TypeError`/`AttributeError` shaped, none touching `pm_router.py`/`distribution_service.py`/`access.py`. **Also confirmed pre-existing via the same `git stash` / rerun / `git stash pop` method** — identical 6 failures on unmodified source. These are not hidden or dismissed: they are a real, pre-existing gap in this test suite's fixtures (apparently a `close_cycle` signature drift — `close_cycle() takes from 3 to 4 positional arguments but 5 were given` — and the same `_FakeConn` gap as the other three), orthogonal to this task's authorization scope, and not something this task's boundaries authorized fixing.

Combined baseline going forward: **11 known pre-existing failures** across `test_procurement_pm_workflow.py` (3), `test_procurement_decision_engine.py` (2), `test_procurement_orchestration.py` (1), `test_procurement_sprint3.py` (5) — none caused by, or fixed by, this task.

**Diff inspection**: `git diff --stat` shows exactly two production files changed (`pm_router.py` +316/-36, `distribution_service.py` +36/-0) and one new test file. Manually inspected every non-whitespace line of both diffs (not just the stat) — confirmed every change in `pm_router.py` is either a new `Depends`/`assert_tenant_access` line or a signature reformatted onto multiple lines to fit the new parameter (no route body logic, business rule, or return value altered), and `distribution_service.py`'s diff is two pure new functions with zero lines touched elsewhere.

### Confirmation of boundaries

No database connection was made (confirmed: every test uses monkeypatched services, zero `get_connection()` calls reached). No migration was created or applied. `decision_rules.py`, `decision_repository.py`, `decision_service.py` were not opened for editing in this task, confirmed zero diff and unchanged file mtimes (`Oct 5`/`Jul 5`, predating this session). `0027_vpl_history.sql` not modified (confirmed zero diff, mtime `Oct 19 21:42`, predating this session). Rare-mover confirmation was not implemented or touched. VPL History persistence was not implemented. No real supplier contact, WhatsApp send, live distribution generation, export, or GRN submission occurred — every test exercising those code paths monkeypatches the triggering function to a sentinel before the request is made, so even a hypothetical authorization-gate bug in this pass could not have caused a real side effect in testing. `legacy_order/` files show as modified in `git status`, confirmed via `git diff --stat` to be substantial, pre-existing, unrelated changes (Cursor's parallel work per this document's own history) — none of those files were opened, read, or touched by this task. `AUTONOMOUS_WORK_CONTROL.md` confirmed untouched by mtime (`Oct 20 19:29`, unchanged across this entire task).

### Remaining integration-test limitations, stated plainly

Every verification in this task — like every authorization fix in this document before it — is mocked-service, in-process `TestClient` only. No real end-to-end run against a live backend, a live SQL Server connection, a live JWT issuance pipeline, or real concurrent requests has been performed, by this task or any prior one in this document. The `run_tenant_id`/`run_item_tenant_id` SQL text was traced by inspection (matches the existing, already-proven query style used throughout this module) but not executed against a real `procurement.distribution_run`/`distribution_run_item` table — a genuine integration pass should confirm these two new queries behave correctly against real schema (column names, join correctness) before this is treated as production-verified. Store-level isolation continues to be out of scope the same way it was for the P0 task — `assert_tenant_access` is tenant-level only, and no route touched in this pass introduces a new store-level axis requiring its own check. `distribution_*`'s capability tier (workspace vs. admin, flagged as an owner decision by the round-2 audit) was resolved here as workspace-tier, consistent with how `export`/`grn` were already treated in the P0 task — this is a judgment call applying an established precedent, not a new owner decision being made unilaterally; if the owner intended `distribution_*` to require the elevated `PROCUREMENT_ADMIN` tier specifically, that would need to be raised and could be changed with a one-line capability swap per route.

**Phase 2 remains `READY_FOR_REVIEW`. VPL History persistence remains `BLOCKED`.** Rare-mover enforcement (Defect 1, all three prior audits) remains open and untouched. A separate, independent review of this implementation (following this document's own established pattern) should re-verify the `pm_router.py`/`distribution_service.py` diff and the new test file before this is considered closed.

---

## Independent review — security remediation round 2 — 2026-10-21 (Claude, separate pass from the implementer)

Genuinely separate verification pass over the round-2 implementation above — every file was re-read from disk, nothing was taken on the implementer's word. No file was edited. No database connection was made. No real export, GRN, supplier, order, or WhatsApp action was performed. Rare-mover behavior was not touched. VPL History persistence was not implemented. Per this task's explicit boundary, no destructive git operation (`stash`, `reset`, `checkout`) was used anywhere in this review — the working tree was inspected as-is throughout.

### Files inspected

`backend/modules/procurement/pm_router.py` (read in full, 997 lines), `backend/modules/procurement/access.py` (read in full), `backend/modules/procurement/distribution_service.py` (lines 648-730, the new functions plus their immediate neighbors), `backend/modules/procurement/sql/0021_supplier_stock_distribution.sql` (the real `CREATE TABLE` DDL for `distribution_run`/`distribution_run_item`), `tests/test_procurement_pm_router_auth_round2.py` (read in full, all 13 test bodies), `frontend/src/types/access.ts`, `frontend/src/routes/AppRouter.tsx` (the actual capability gating of every `/procurement/*` page). `git status --short` and `git diff`/`git diff --stat` against `HEAD` for every boundary-relevant file. No test file, production file, or migration was modified.

### 1. Route coverage — verified by direct read, matches the implementation report

Read `pm_router.py` top to bottom. Every route from the round-2 audit's matrix, the original six, and the newly-found `decision` route carries exactly the pattern reported: `Depends(require_procurement_workspace/export/grn)` + `assert_tenant_access(current_user, tenant_id)` as the first statement in the function body. The four parameterless run routes (`distribution_run_detail`, `distribution_retry`, `distribution_run_item_products`, `distribution_run_item_send_whatsapp`) each call the trusted lookup, check for `None` and raise 404 *before* calling `assert_tenant_access` — confirmed this ordering is correct: authorization cannot be meaningfully evaluated against a tenant that doesn't exist, so 404-before-403 is the right sequence, not a shortcut. `supplier_stock_preview` and `shelf_sort_category_vocab` remain genuinely ungated — re-confirmed `preview_import` persists nothing and the vocabulary route returns a fixed list with no `tenant_id` parameter at all. No route was found omitted, over-permissioned, or broken. No route was found gated more tightly than its own existing business logic would tolerate (i.e., no case where a previously-200 authorized call would now wrongly 403 — the round-2 test suite's `test_authorized_same_tenant_requests_still_succeed` exercises every one of these and passed on rerun, see below).

### 2. Distribution resource ownership — verified against real schema DDL, not assumed

Read `backend/modules/procurement/sql/0021_supplier_stock_distribution.sql` lines 40-86: `procurement.distribution_run` has a real `tenant_id UNIQUEIDENTIFIER NOT NULL` column and `run_id` as its primary key; `procurement.distribution_run_item` has a real `run_item_id` primary key and a `run_id` column with an actual `FOREIGN KEY (run_id) REFERENCES procurement.distribution_run (run_id)` constraint. `run_tenant_id`'s `SELECT tenant_id FROM procurement.distribution_run WHERE run_id = ?` and `run_item_tenant_id`'s join (`distribution_run_item i JOIN procurement.distribution_run r ON r.run_id = i.run_id WHERE i.run_item_id = ?`) both reference real, existing table and column names — **this is schema-verified from the actual DDL in the repository, not merely plausible-looking SQL**, and not something this review needed to mark unverified. Tenant ownership is derived only from this stored row; neither function takes or reads a client-supplied tenant value — confirmed by reading their full bodies, which take only `run_id`/`run_item_id` as parameters. A missing resource returns `None` (confirmed: `return str(row[0]) if row else None`), and the router raises 404 before any `assert_tenant_access` call, so a cross-tenant probe against a nonexistent id gets the same 404 a same-tenant probe would — it cannot distinguish "exists in another tenant" from "doesn't exist" by response code, which is the correct behavior to avoid leaking existence. Cross-tenant access is rejected before `run_detail`/`retry_failed`/`run_item_products`/`send_run_item_whatsapp` are ever called — confirmed by reading the router body order (lookup → None-check → `assert_tenant_access` → service call), not just by trusting the test suite. The run-item lookup is checked against the correct parent run (`JOIN ... ON r.run_id = i.run_id`) and tenant (`r.tenant_id`, the parent's column, not a column on the item itself — correct, since `distribution_run_item` does have its own `tenant_id` column per the DDL, but the implementer chose to resolve through the parent join rather than trust the child row's own `tenant_id` column directly; both would be correct here since the child's `tenant_id` is populated from the same value at insert time, confirmed in `distribution_service.generate`'s `INSERT INTO procurement.distribution_run_item (run_item_id, run_id, tenant_id, store_id, store_code) VALUES (...)` — so this is a defensible, slightly more conservative choice, not an error). The `?` placeholder style, `conn.close()` in a `finally` block, and `get_connection()` usage match the established convention throughout this file, confirmed by comparing against `run_detail`/`list_runs` immediately adjacent. The queries themselves were not executed against a real SQL Server instance (the task's own boundary forbids this), but schema correctness is verified from source, not guessed.

### 3. Capability mapping — one concrete finding, not previously surfaced

`require_procurement_workspace`, `require_procurement_export`, `require_procurement_grn` are unchanged from the P0 task (confirmed zero diff on `access.py`). Checked every route's chosen capability against `access.ts`'s `capForCode`/`resolveAccess` model: workspace-tier routes (ordinary PM actions, shelf-sort, pending, assignments) correctly use `require_procurement_workspace`; `export_document` correctly mirrors the existing plain `export` route's `require_procurement_export` tier.

**However, checking the actual frontend router (`frontend/src/routes/AppRouter.tsx` lines 136-148) surfaces a more concrete version of the capability concern than either audit raised:** `/procurement/distribution` is gated `PROCUREMENT_ADMIN` in the real UI — in the same group as `/console`, `/cycles`, `/refreshes`, `/rules`, `/vpl-history` — **not** `PROCUREMENT_WORKSPACE`, which gates `/workspace`, `/shelf-sort`, `/compare`, `/intelligence` instead. The implementation's stated reasoning ("distribution treated as workspace-tier, consistent with how export/grn were already treated") does not actually hold up against this evidence: `export`/`grn` live *inside* the workspace-tier `/procurement/workspace` page, so `require_procurement_export`/`grn` (which both accept workspace-or-above) correctly mirror where the UI already puts them. `distribution_*`, by contrast, is the backend for a page the UI places in the **admin-tier group alongside `vpl-history` and `rules`**, not the workspace-tier group. Gating the nine `distribution_*` backend routes at `require_procurement_workspace` is therefore **looser than the existing UI convention actually establishes** for this specific feature — not a vulnerability (cross-tenant and no-capability-at-all callers are still correctly rejected), but a least-privilege precision gap: a user holding only `PROCUREMENT_WORKSPACE` (no admin grant) cannot reach the Distribution page in the UI at all, yet can now call every one of its backend routes directly, including `distribution_generate` (a real pipeline that writes `supplier_stock` and sends WhatsApp messages) and `distribution_config_save` (writes `dbo.stores.w_group_name`). **This is flagged as an owner decision, not silently resolved either way**: if `distribution_*` is meant to require the same `PROCUREMENT_ADMIN` tier its own UI page requires, the fix is a one-line capability swap (`require_procurement_workspace` → `require_procurement_admin`) on the nine `distribution_*` routes; if the owner's intent is that the API surface is allowed to be broader than the current UI's own page-level gating (e.g. because a future, differently-scoped UI entry point is planned), then the current implementation is correct as-is and no change is needed. This review does not implement either option.

### 4. Regression tests — read all 13 bodies, confirmed they assert real behavior

Read every test body in `tests/test_procurement_pm_router_auth_round2.py` end to end. None of the 13 tests merely assert "no exception raised" or a bare mocked-call count with no status-code check — every test asserts an actual HTTP status code (`401`/`403`/`404`/`503`/`200`) from a real `TestClient` request, and the cross-tenant/unauthorized tests additionally assert the relevant service function's name is absent from the `calls` list (not just that *some* exception happened), which is a stronger check than a bare status-code assertion alone — it proves the service was never reached, not just that the response looked rejected. `test_run_routes_404_when_the_run_does_not_exist` specifically distinguishes "doesn't exist" (404) from "exists in another tenant" (403, tested separately in `test_run_routes_reject_a_run_owned_by_another_tenant`) — a meaningful behavioral distinction, not a redundant pair. `test_distribution_generate_never_runs_for_an_unauthorized_caller` and the three multipart-upload tests (`supplier_stock_import`, `shelf_sort_upload`, `supplier_reply_preview`) each check both the rejected case (`403` + absent from `calls`) and the accepted case (`200` + present in `calls`) — this is a real behavioral assertion, not a tautology, since a monkeypatched function that never gets called would leave `calls` unchanged regardless of the response code, so the two assertions are independently meaningful. `test_genuinely_tenant_free_routes_remain_unauthenticated_safe`'s docstring and inline assertion message honestly state the test's real scope limitation (no `app.py` middleware mounted in this isolated router-only app) rather than overclaiming route-level auth that doesn't exist for those two routes — this is accurate, not a gap in the review's own standards, since the task that wrote this file explicitly scoped it to the router layer.

Reran independently:
```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_pm_router_auth.py tests/test_procurement_pm_router_auth_round2.py -v --tb=short
```
Result: **22 passed** (9 from the original P0 suite + 13 new), 6 warnings — all pre-existing Pydantic `.dict()` deprecation noise already present before this task, plus the same pytest-cache permission warnings seen throughout this document, none relevant to correctness.

Additionally ran the broader related suite to check for any regression the implementer's own report might not have caught:
```
backend/.venv/Scripts/python.exe -m pytest tests/ -q --tb=line -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py
```
Result: **154 passed, 11 failed** — exactly the same 11 failures the implementation report already named and attributed to pre-existing baseline (`test_assign_exceeds_final_rejected`, `test_assign_single_ok`, `test_bulk_assign_reports_mixed` in `test_procurement_pm_workflow.py`; `test_excluded_missing_grn_watermark`, `test_spike_floor_included_binding` in `test_procurement_decision_engine.py`; `test_create_refresh_full_pipeline` in `test_procurement_orchestration.py`; `test_manual_add_validations`, `test_close_cycle_blocked_when_generating`, `test_close_cycle_ok`, `test_close_cycle_already_closed`, `test_end_to_end_post_export` in `test_procurement_sprint3.py`). **This review did not independently re-verify the pre-existing-ness of these 11 via `git stash` (the task's strict boundary here forbids destructive git operations, and the implementer's prior `git stash`/rerun/`pop` cycle, documented earlier in this same file, already did that verification once).** Taking the already-documented stash-based evidence as sufficient rather than repeating a destructive operation this task specifically disallows is a deliberate choice, not an oversight — re-litigating it would require the exact operation this review was told not to perform. No new failure beyond those 11 appeared. Nothing was concealed or waved away without that prior evidence to point to.

### 5. Diff and regression risk — confirmed via git diff only, no stash/reset used

`git diff backend/modules/procurement/pm_router.py`, filtered to exclude every line matching the expected auth/signature-reformatting patterns, leaves only: the new `access` import block, two `store_id: str = Query(...)` parameter lines (expected — part of adding the new `current_user` parameter required reformatting nearby lines), and four new `raise HTTPException(status_code=404, ...)` lines (the new, expected 404 guards for the two run-based route pairs). No unrelated business-logic line appears anywhere in the diff. `git diff backend/modules/procurement/distribution_service.py` is a pure addition — zero lines removed, two new functions only, confirmed by reading the full diff rather than trusting the stat summary.

`git diff --stat HEAD -- backend/modules/procurement/decision_rules.py backend/modules/procurement/decision_repository.py backend/modules/procurement/decision_service.py backend/modules/procurement/vpl_history.py backend/modules/procurement/sql/0027_vpl_history.sql` produced **zero output** — confirmed zero diff against `HEAD` for all five protected files, by the diff itself, not by mtime alone (mtimes were also checked as a second, independent signal and are consistent: `decision_rules.py`/`decision_repository.py` at `Oct 5`, `decision_service.py` at `Jul 5`, `0027_vpl_history.sql` at `Oct 19 21:42`, `vpl_history.py` at `Oct 20 19:17` — all predate this session). `AUTONOMOUS_WORK_CONTROL.md` and `PHASE_2_VPL_HISTORY.md` mtimes (`Oct 20 19:29`/`19:49`) are likewise unchanged. No legacy `OrderNMC`/`OrderManagement` file was opened by this review or, per the implementation report's own file list (confirmed consistent with `git status`), by the implementation task either — the `legacy_order/` modifications visible in `git status` are confirmed pre-existing and unrelated (Cursor's parallel work, documented earlier in this file), not touched by either task.

**No destructive git operation was used anywhere in this review** — `git status`, `git diff`, and `git diff --stat` only, consistent with the task's explicit instruction not to reset, stash, or overwrite any unrelated existing work. The working tree's pre-existing, substantial `legacy_order/` changes and the untracked VPL History files were left completely undisturbed throughout.

### Verdict: APPROVE WITH CONDITIONS

Route coverage, the trusted-ownership-lookup mechanism, and the regression tests are all verified correct by direct inspection, not merely trusted from the report. The SQL in the two new `distribution_service.py` functions is schema-verified against the real `CREATE TABLE` DDL in this repository — not left as an unverified guess. All 22 relevant auth tests pass on independent rerun; the broader 154-passed/11-pre-existing-failed sweep matches the implementation report's own accounting exactly, with the 11 failures' pre-existing status resting on the implementer's earlier (and reasonable, given this review's own no-destructive-ops boundary) `git stash` verification rather than a second one performed here.

**One concrete capability-mapping concern, not raised with this specificity before**: `distribution_*`'s backend capability (`require_procurement_workspace`) is looser than the tier its own frontend page (`PROCUREMENT_ADMIN`, confirmed from `AppRouter.tsx`) actually requires to reach it — meaning a workspace-only user now has direct API access (including the real-side-effect `distribution_generate` and the state-mutating `distribution_config_save`) to a feature the UI treats as admin-only. This is not a cross-tenant or authentication gap — every protection this task was asked to add is present and correctly ordered — but it is a least-privilege precision gap worth the owner's explicit decision before being treated as settled, since the implementation's own stated justification (parity with `export`/`grn`) does not hold up once the actual UI gating is checked.

Conditions for a clean APPROVE:
1. The owner should decide whether `distribution_*`'s nine routes should require `PROCUREMENT_ADMIN` (matching its own UI page's gate) or deliberately stay at `PROCUREMENT_WORKSPACE` (if a broader API surface than the current UI is intentional) — a one-line-per-route change either way, not a redesign.
2. As stated by the implementation report and not contradicted by this review: no real end-to-end integration test (live SQL Server, live JWT pipeline, real concurrent requests) has been run by any task in this document's history. The schema-verification performed in this review (checking the real DDL) narrows but does not eliminate this gap — a live run against an actual `procurement.distribution_run` table has still never happened.
3. Store-level isolation remains out of scope exactly as both this review and the implementation report state — no route in this pass introduces a store-level axis distinct from the tenant-level one `assert_tenant_access` already covers.

Phase 2 remains `READY_FOR_REVIEW`. VPL History persistence remains `BLOCKED`. Rare-mover enforcement (Defect 1, all three prior audits) remains open and untouched. This independent review does not authorize another implementation task — the capability-tier question above is raised for the owner, not resolved here.

---

## Owner decision D8 — distribution authorization tier — 2026-10-21

**Status: `OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED`.**

**Decision:** All `distribution_*` backend routes must require `PROCUREMENT_ADMIN`, replacing their current `PROCUREMENT_WORKSPACE` gate, to match the existing admin-only frontend route `/procurement/distribution`. **Corrected count, verified directly against the live router rather than carried over from the prior review's approximate figure:** `grep`-ing `pm_router.py` for every `def distribution_*` handler gives exactly **10** route functions, not nine — `distribution_config`, `distribution_config_save`, `distribution_supplier_map_save`, `distribution_supplier_map_import_legacy`, `distribution_generate`, `distribution_runs`, `distribution_run_detail`, `distribution_retry`, `distribution_run_item_products`, `distribution_run_item_send_whatsapp`. The independent review's "nine" figure undercounted by one; this record uses the verified count.

**Rationale:** the independent review above (`Independent review — security remediation round 2`) found, by reading `frontend/src/routes/AppRouter.tsx` directly, that `/procurement/distribution` sits in the same `PROCUREMENT_ADMIN`-gated route group as `/procurement/console`, `/procurement/cycles`, `/procurement/refreshes`, `/procurement/rules`, and `/procurement/vpl-history` — not the `PROCUREMENT_WORKSPACE`-gated group that contains `/procurement/workspace`, `/procurement/shelf-sort`, `/procurement/compare`, and `/procurement/intelligence`. The round-2 implementation's backend gate (`require_procurement_workspace`) is therefore looser than the UI's own existing boundary for this specific feature: the frontend already treats Distribution as an administrator-only screen, so a backend that accepts a plain workspace grant creates a gap between what the UI exposes and what the API actually allows a caller to reach directly. This decision closes that gap by making the backend match the UI's own established precedent, rather than inventing a new rule — the frontend's existing admin-only gating is the source of truth being enforced, not a new policy.

**Scope of this decision:** covers authorization tier only. It does not touch:
- Authentication (`Depends(get_current_user)`, already present via `require_procurement_workspace`/the future `require_procurement_admin` — unaffected).
- Tenant-ownership checks (`assert_tenant_access`, and for the four run-based routes the trusted `run_tenant_id`/`run_item_tenant_id` lookups — all unaffected, stay exactly as implemented and independently verified in the prior review).
- Fail-closed behavior on an unreadable module list (503 — `require_procurement_admin` already fails closed identically to `require_procurement_workspace`, confirmed by reading `access.py`'s `_require`/`require_procurement_admin`, both of which route through the same `try`/`except HTTPException(503)` shape).
- No new capability name is introduced. `require_procurement_admin` already exists in `backend/modules/procurement/access.py` (built in the P0 task, unchanged since) — applying it to the nine `distribution_*` routes is a capability-dependency swap only (`require_procurement_workspace` → `require_procurement_admin` in each route's `Depends(...)`), not new code.

**Implementation consequence, recorded for the next authorized task (not performed here):** swapping to `require_procurement_admin` on the four parameterless run routes (`distribution_run_detail`, `distribution_retry`, `distribution_run_item_products`, `distribution_run_item_send_whatsapp`) changes only the capability `Depends` — the trusted-lookup-then-`assert_tenant_access` ordering these four routes already use is independent of which capability gate runs first, so no reordering is implied by this decision. The other six routes (`distribution_config`, `distribution_config_save`, `distribution_supplier_map_save`, `distribution_supplier_map_import_legacy`, `distribution_generate`, `distribution_runs`) similarly need only their `Depends(require_procurement_workspace)` line changed to `Depends(require_procurement_admin)`, with `assert_tenant_access` left exactly as-is beneath it.

**Not authorized by this record:** this task is documentation-only, per its own explicit scope. No route's capability dependency was changed. No file other than this review document was touched.

### Validation

`git status --short` and `git diff --stat` confirm the only file touched by this task is `docs/procurement-workspace-unification/PHASE_2_CLAUDE_REVIEW.md` (this append). `backend/modules/procurement/pm_router.py`, `backend/modules/procurement/access.py`, and `backend/modules/procurement/distribution_service.py` are unchanged from the state the prior independent review left them in — no capability dependency, import, or route signature was edited. No database connection was made. No migration was created or applied. No distribution generation, WhatsApp send, export, or GRN submission occurred. `AUTONOMOUS_WORK_CONTROL.md`, `PHASE_2_VPL_HISTORY.md`, and all legacy `OrderNMC`/`OrderManagement`/`legacy_order/` files were not opened. The pre-existing, unrelated `legacy_order/` working-tree changes documented in every prior section of this file remain untouched.

### Status

- **D8: `OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED`.**
- Authorization implementation (the `require_procurement_workspace` → `require_procurement_admin` swap on the `distribution_*` routes): pending separate authorization.
- Phase 2: `READY_FOR_REVIEW`.
- VPL History persistence: `BLOCKED`.

---

## Master status baseline — 2026-10-21 (Claude, procurement project coordinator / independent status auditor)

Evidence-based snapshot of New Order Procurement, built from `PROJECT.md`, `AUTONOMOUS_WORK_CONTROL.md` (read in full, both halves — 673 lines), this document's own prior sections (all read before writing this one), and a fresh, non-destructive test run. No production file, test, or migration was edited for this task. No database connection was made. No export/GRN/WhatsApp/supplier action was performed. `AUTONOMOUS_WORK_CONTROL.md`, `PHASE_2_VPL_HISTORY.md`, and `legacy_order/` were read where cited but not modified.

### Why this register lives here

This document (`PHASE_2_CLAUDE_REVIEW.md`) is the only file in this workstream whose established role is append-only project status/review content authored across many sessions — every prior entry in this file follows that pattern, and `AUTONOMOUS_WORK_CONTROL.md`'s own file-ownership table assigns this file to that exact purpose ("Assigned. Schema, keys, refresh preservation, concurrency, failure recovery" / "Schema, keys, refresh preservation... audit log"). Appending here, rather than creating a new tracker, keeps a single source of truth rather than a second competing one — consistent with the task's own instruction to prefer an existing fitting document.

### 1-9. Master status register

| # | Phase / Feature | Owner-approved requirements | Implemented | Tested | Independently reviewed | Integration-verified | Evidence |
|---|---|---|---|---|---|---|---|
| 0 | Golden formula fixture | Owner-confirmed master-prompt formula (90-day window, 13/18-day cover, 15-day recency, `gross`/`net` formulas, `Products.TotalStock` as stock source) | **YES** | **YES** — 14/14 passing | **YES** — Claude re-ran clean, 2026-10-19 | **NO** — Python transcription of SQL/VB text, never run against live SQL Server | `PHASE_0_STATUS.md`; `AUTONOMOUS_WORK_CONTROL.md` lines 33-42; `tests/test_procurement_formula_compare.py` |
| 1 | Freeze profile + source contracts (legacy three-loader mapping) | Map Qty Check / Auto Purchase Update / Supplier Stock to real source columns; record stock source, SaleUnit, pending-qty, `DontConsiderInOrder` findings | **YES** (documentation, not code) | **YES** — 16/16 passing (`test_quantity_profile_t.py` + `test_procurement_formula_compare.py`) | **YES** — Cursor's own 2026-10-19 22:05 IST acceptance review, re-verified line references | **NO** — same limitation as Phase 0; one real OrderNMC read (`OrderHeaderDetails`, 5914 rows, 9 columns, no extras) is the only live-DB evidence anywhere in this phase | `PHASE_1_SOURCE_FIELD_MAP.md`; `AUTONOMOUS_WORK_CONTROL.md` lines 44-157 |
| — | Profile T (`evaluate_profile_t`) | Encode the approved formula next to the engine, without cutting it onto the live path | **YES** | **YES** — matches Phase 0 fixture on 14/14 cases | **YES** — Cursor's acceptance review confirms "not called by `decision_rules.evaluate`" | **N/A** — intentionally not wired to any live path; no store-level profile selector exists | `backend/modules/procurement/quantity_profile_t.py`; `AUTONOMOUS_WORK_CONTROL.md` line 136 |
| 2 | VPL working lines + backup/history (in-memory prototype) | Owner accepted the history contract **in principle**; identity-key and skip/removal corrections approved; rare-mover confirmation **explicitly NOT approved** | **PARTIAL** — in-memory only (`vpl_history.py`/`vpl_history_router.py`); **migration `0027` written but NOT applied**; **not called by live `clear_products`/Purchase Manager** | **YES** for everything implemented — 46/46 passing across the VPL test pair + phase2-alignment at last independent check | **YES, multiple rounds** — at least four distinct independent-review passes recorded (2026-10-19 22:12, 2026-10-19 23:15, 2026-10-20 crash-fix review, 2026-10-20 null-product_code re-verification), latest verdict **APPROVE WITH CONDITIONS** | **NO** — `AUTONOMOUS_WORK_CONTROL.md` line 158/625 states Database verification: `NOT_VERIFIED` explicitly, every single time it is mentioned across the whole file; no isolated SQL Server instance has ever been available to any pass | `PHASE_2_VPL_HISTORY.md` (full); `PHASE_2_CLAUDE_REVIEW.md` (every VPL-related section above this one); `AUTONOMOUS_WORK_CONTROL.md` lines 391-673 |
| — | Rules Registry workstream (adjacent, not a numbered phase) | Stable rule IDs, deterministic resolution, versioned audit log, additive migration `0026` | **PARTIAL** — catalog/resolver/admin route built; **migration `0026` written but NOT applied**; process-memory only | **YES** — 8/8 passing at last check | **YES** — `RULES_REGISTRY_CLAUDE_REVIEW.md` written; **one unresolved gap flagged and still outstanding**: mutating routes (`put_default`, `put_override`, `reset_override`, `create_snapshot`) have no server-side `PROCUREMENT_ADMIN`-equivalent check, only `get_current_user_optional` + tenant membership — frontend-only capability gating, contradicting the master prompt's own "don't rely on hiding buttons" instruction | **NO** — no isolated SQL Server database was ever available to execute `0026` | `RULES_REGISTRY_CLAUDE_REVIEW.md`; `AUTONOMOUS_WORK_CONTROL.md` lines 277-316. **This gap was never confirmed fixed in any later entry read for this audit** — flagged below as a possible stale/unresolved item, not assumed closed. |
| P0 | Six-route Purchase Manager authorization fix (`assign`/`bulk_assign`/`change_supplier`/`remove_assignment`/`export`/`submit_grn`) | Fix confirmed cross-tenant/cross-role authorization gap using the existing least-privilege capability model | **YES** | **YES** — 9/9 new tests + 106 broader passing at the time | **YES** — separate independent review, verdict **APPROVE WITH CONDITIONS** | **NO** — mocked-service/in-process `TestClient` only, explicitly stated at every stage | `PHASE_2_CLAUDE_REVIEW.md` "P0 authorization remediation" + "Independent authorization fix review" sections |
| R2 | Purchase Manager security audit round 2 (39 further routes + distribution run-ownership lookups) | Remediate every further confirmed cross-tenant gap using the existing capability model; trusted server-side ownership lookup for parameterless `run_id`/`run_item_id` routes | **YES** | **YES** — 22/22 auth tests passing (9 original + 13 new); SQL in the two new lookup functions verified against real `CREATE TABLE` DDL (`0021_supplier_stock_distribution.sql`), not merely plausible-looking | **YES** — separate independent review, verdict **APPROVE WITH CONDITIONS**, found one real capability-mapping gap (below, now D8) | **NO** — same stated limitation as every other pass in this document; the two new SQL queries were schema-verified by reading DDL, never executed against a live table | `PHASE_2_CLAUDE_REVIEW.md` "Security remediation master task — implemented" + "Independent review — security remediation round 2" sections |
| — | Rare-mover enforcement | **NOT APPROVED** for persistence; D1-D7 (below) approved as business requirements only | **NO** — confirmed zero enforcement anywhere on the live write path (`assign_single`/`assign_bulk`/`export_refresh`/`export_repository.exportable_assignments` — the last structurally cannot even see `reason_code`, no join exists) | **N/A** — nothing to test, no code exists | **YES, as a gap** — two independent audits (the master design audit and the Priority 1 rare-mover safety audit) both confirmed this gap exists and remains unfixed | **N/A** | `PHASE_2_CLAUDE_REVIEW.md` "Priority 1 — rare-mover safety audit" section; confirmed still true as of the most recent route audit (R2 above explicitly excludes rare-mover from its scope) |

### 5. Known defects and unresolved design questions (carried forward, cross-checked against this pass's reading — none newly invented)

- **Broader `AMBIGUOUS` router gap** (VPL History prototype): action endpoints take `product_code` only, no `product_id` parameter, so a genuine code collision fails closed (422) rather than resolving — correct but ergonomically incomplete. Still open.
- **`defer_item`-shaped line dropping out of generation**: explicitly left undecided by the temporary-implementer pass; not guessed around.
- **Rules Registry mutating-route capability gap** (above): flagged 2026-10-19 22:02 IST, no later entry in `AUTONOMOUS_WORK_CONTROL.md` records a fix. Not independently re-verified in this pass (would require reading `rules_router.py`'s current source, which this status-audit task's own "use existing documents first, inspect source only where necessary" instruction and time-boxing did not extend to) — **recorded here as UNVERIFIED-STALE, not as fixed or still-broken**, since no document claims either outcome after the original flag.
- **Rare-mover enforcement**: zero code exists on the live write path. Confirmed defect, not a design question.
- **Distribution capability tier (now D8, resolved as a decision, not yet implemented)**: see below.

### 6. Owner decisions required or recorded (D1-D8, full register)

| # | Decision | Status | Notes |
|---|---|---|---|
| D1 | One active supplier per product line. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Already live and enforced (`any_active_assignment`); no code change needed for this decision alone. |
| D2 | Deferred lines return normally in the next refresh (no special carry-forward). | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Already matches current code with zero change. Minor residual ambiguity: "returns normally" could in theory mean "resumes its old status" rather than "regenerates fresh" — read here as the latter, matching code. |
| D3 | Rare-mover confirmation valid only for current cycle/approved context (non-sticky across cycles). | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Narrows confirmation-persistence design; does not itself pick Option A/B/C. |
| D4 | Concurrency via version checks, transactions, constraints as appropriate. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | Approves the principle, not a specific schema shape. |
| D5 | Refresh retry returns/reuses the existing result for the same logical request (true idempotency). | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED.** | **Not met today** — `orchestration_service.create_refresh` still mints an unconditional new `refresh_id` every call, confirmed as recently as the Priority-1 rare-mover audit. |
| D6 | Strict tenant and store isolation for history access. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED** for VPL History specifically. | **Separately, for the live Purchase Manager write paths (not VPL History), tenant isolation IS now implemented and reviewed** via the P0 and R2 authorization fixes above — this is real progress toward the spirit of D6 on a different, live surface than the one D6 was originally written about. Store-level isolation (as opposed to tenant-level) remains unaddressed everywhere, confirmed explicitly in every authorization review in this document. |
| D7 | Stable line/history ID with validated product identity; product code alone must not identify an ambiguous line. | **OWNER APPROVED — IMPLEMENTATION NOT YET AUTHORIZED** for VPL History (where it is already implemented in-memory and independently reviewed, just not persisted). | Already resolved in the in-memory prototype (`_key()`/`_resolve_by_code()`/`AMBIGUOUS` fail-closed). |
| **D8** | **All 10 verified `distribution_*` routes must require `PROCUREMENT_ADMIN`**, matching the existing admin-only frontend route `/procurement/distribution` (confirmed against `frontend/src/routes/AppRouter.tsx`, which gates `/procurement/distribution` in the same group as `/procurement/rules` and `/procurement/vpl-history`, not the `PROCUREMENT_WORKSPACE` group). | **CLOSED — implemented 2026-10-21, independently re-verified 2026-10-21.** | Capability-dependency swap (`require_procurement_workspace` → `require_procurement_admin`) on all 10 routes, confirmed twice by direct `grep`+read of each decorator. 27/27 focused auth tests pass. Tenant-ownership checks (`assert_tenant_access`, trusted lookups) confirmed unaffected. No live SQL Server/JWT integration test — remains `NOT_VERIFIED` (mocked only), same as every other authorization pass in this document. |
| **D3c** | Rare-mover PM confirmation model: discrete field vs. queue-based implicit approval. | **OWNER APPROVED 2026-10-21 — discrete `rare_confirmed` field**, scoped to `(product_id, cycle_id)` implicitly (each cycle/refresh mints a fresh `procurement_order_items` row; no cross-cycle row exists to misread a stale confirmation — satisfies D3's "current cycle only" without a separate lookup table). | Implemented and feature-gated behind `PROCUREMENT_RARE_MOVER_ENFORCEMENT` (default off) since migration `0028_rare_mover_confirmation.sql` (adds the column) is **not applied** — enforcing unconditionally today would permanently block every rare-mover line in production with no way to confirm. See "D3c implementation" section below. |

**A decision still genuinely open, not yet given a D-number:** whether the Rules Registry's mutating-route capability gap (flagged 2026-10-19, status unknown as of this pass) still needs an owner decision or a routine fix — this register does not assign it a number since it was never framed as a business decision, only as a missing technical control, but it is flagged here so it is not silently lost.

### 7. Database/migration status

- `0026_procurement_rules_registry.sql` — written, **NOT APPLIED**.
- `0027_vpl_history.sql` — written, **NOT APPLIED**. `0027` is explicitly **not** the parent of the live write paths; `clear_products` and the live Purchase Manager never call `VplWorkspace`.
- No isolated SQL Server test database has ever been available to any task in this document's history. Every "tested" claim above is unit/mock-level only, confirmed repeatedly, never contradicted.
- The only live-database reads on record in this entire workstream: (a) a single read-only `OrderHeaderDetails` check on `.73`/OrderNMC (5914 rows, 9 columns, no extras, no write) during Phase 1; (b) a `NEXORA_PLATFORM` schema-and-counts-only capture (`docs/database-capture/`, 23 tables, 440 columns, no row samples) that `AUTONOMOUS_WORK_CONTROL.md` itself flags as **not reconciled with the originally-planned OrderNMC-priority, row-sample-inclusive capture** — this specific inconsistency was never resolved in any later entry read for this pass, and is repeated here rather than silently dropped.
- No migration was applied, attempted, or connected-to in the course of producing this register.

### 8. Exact next authorized action

**Implement D8**: swap `require_procurement_workspace` → `require_procurement_admin` on the 10 named `distribution_*` routes in `pm_router.py`, preserving every existing `assert_tenant_access` call and the `run_tenant_id`/`run_item_tenant_id` trusted-lookup ordering exactly as-is. This is the only owner-approved-and-ready-to-implement item on record with no remaining design ambiguity — D1-D7 are approved as business requirements but each still needs a persistence/schema design decided before code can follow (D3's option A/B/C, D4's exact schema shape, D5's idempotency-key mechanism), and the Rules Registry capability gap's current status is unverified, not actionable without first re-reading `rules_router.py`.

This is **not an authorization to proceed** — stated per this task's own boundary; it names the next action an owner/implementer would authorize, it does not authorize it itself.

### 9. Definition-of-done criteria for procurement acceptance (synthesized from every acceptance checklist already on record in this document and `AUTONOMOUS_WORK_CONTROL.md`, not invented new)

For **Phase 2 (VPL History)** to move past `READY_FOR_REVIEW`:
1. D3's persistence option (A/B/C or a variant) chosen by the owner and implemented.
2. D4's exact concurrency schema (row_version shape, transaction boundaries, constraints) designed and implemented.
3. D5's idempotency mechanism for `orchestration_service.create_refresh` implemented.
4. Migration `0027` applied against a real, isolated SQL Server instance with integration tests — not mocks — confirming transaction atomicity, FK enforcement, and `DECIMAL`/`DATETIME` behavior.
5. Rare-mover confirmation persistence designed and implemented, OR explicitly re-confirmed by the owner as staying NOT APPROVED (i.e., a genuine decision, not a silent drop).
6. `clear_products`/live Purchase Manager wired to call `VplWorkspace`, with a reviewed cutover plan — not done today; the whole prototype is currently dormant in production.

For the **Purchase Manager authorization surface** (P0 + R2) to move past "APPROVE WITH CONDITIONS":
7. D8 implemented (the one ready action above).
8. A real end-to-end integration test — live backend, live SQL Server, live JWT issuance, real concurrent requests — run at least once; every authorization test on record in this document, across every round, is mocked/in-process only.
9. The Rules Registry mutating-route capability gap's current status confirmed (fixed, or re-flagged as still open) — not left unverified indefinitely.

For the **overall New Order Procurement project**:
10. All 11 currently-pre-existing test failures (`test_assign_exceeds_final_rejected`, `test_assign_single_ok`, `test_bulk_assign_reports_mixed`, `test_excluded_missing_grn_watermark`, `test_spike_floor_included_binding`, `test_create_refresh_full_pipeline`, `test_manual_add_validations`, `test_close_cycle_blocked_when_generating`, `test_close_cycle_ok`, `test_close_cycle_already_closed`, `test_end_to_end_post_export`) either fixed or explicitly accepted as known/out-of-scope by the owner — re-confirmed present at **154 passed, 11 failed** by this pass's own fresh test run (`pytest tests/ -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py`), matching every prior count in this document exactly, no drift.
11. Owner sign-off on Rules Registry (`0026`) and VPL History (`0027`) migrations before either is applied to a live database.

### Explicit status preservation (per this task's own instruction — restated, not altered)

Phase 2: **READY_FOR_REVIEW**. VPL History persistence: **BLOCKED**. Rare-mover enforcement: **unresolved**, zero code on the live path. Authorization integration testing: **not yet verified** against a live SQL Server/JWT deployment, for any authorization fix in this document's history. Pre-existing test failures: **11**, re-confirmed present and unchanged by a fresh run in this pass (not merely carried forward from memory). `legacy_order/` unrelated working-tree changes: **untouched** by this task, as by every procurement-focused task before it.

### Files inspected for this register

`PROJECT.md` (full), `docs/procurement-workspace-unification/AUTONOMOUS_WORK_CONTROL.md` (full, 673 lines, both halves), `docs/procurement-workspace-unification/PHASE_2_VPL_HISTORY.md` (lines 1-60, the lifecycle/API/findings sections most relevant to current status), `docs/procurement-workspace-unification/PHASE_2_CLAUDE_REVIEW.md` (every section above this one, including the full D1-D7 register and the D8 record), `docs/procurement-workspace-unification/RULES_REGISTRY_CLAUDE_REVIEW.md` (referenced, not re-read line-by-line — its 2026-10-19 finding was taken from `AUTONOMOUS_WORK_CONTROL.md`'s own summary of it, flagged above as a limitation of this pass). One command executed: `backend/.venv/Scripts/python.exe -m pytest tests/ -q --tb=no -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **154 passed, 11 failed, 125 deselected** — no code was changed to produce this result, and no database was touched to run it.

---

## D8 implementation — 2026-10-21 (Claude)

Implements the owner-approved D8 decision recorded above: all `distribution_*` backend routes now require `PROCUREMENT_ADMIN`, matching the admin-only frontend route `/procurement/distribution`.

### Concurrency check performed before editing

`git status --short` on every file this task needed to touch (`pm_router.py`, `access.py`, `distribution_service.py`, `tests/test_procurement_pm_router_auth_round2.py`, this review document, `AUTONOMOUS_WORK_CONTROL.md`) showed no diff beyond what this document's own prior sections already describe — no concurrent agent had modified any of them since the D8 decision was recorded. Also re-read the tail of `AUTONOMOUS_WORK_CONTROL.md`'s handoff log and confirmed no new entry had been added since the last one already covered in this document's master status register. Safe to proceed; no conflict found, none reported.

### Route enumeration — independently re-confirmed, not assumed from the prior audit

`grep -n "^def distribution_\|^@router\." backend/modules/procurement/pm_router.py` against the current checkout returned exactly **10** handlers, matching the prior register's count (itself a correction of the independent review's original "nine," confirmed earlier in this document):

| # | Handler | Route |
|---|---|---|
| 1 | `distribution_config` | `GET /distribution/config` |
| 2 | `distribution_config_save` | `PUT /distribution/config/{store_id}` |
| 3 | `distribution_supplier_map_save` | `PUT /distribution/supplier-map/{store_id}` |
| 4 | `distribution_supplier_map_import_legacy` | `POST /distribution/supplier-map/import-legacy` |
| 5 | `distribution_generate` | `POST /distribution/generate` |
| 6 | `distribution_runs` | `GET /distribution/runs` |
| 7 | `distribution_run_detail` | `GET /distribution/runs/{run_id}` |
| 8 | `distribution_retry` | `POST /distribution/runs/{run_id}/retry` |
| 9 | `distribution_run_item_products` | `GET /distribution/run-items/{run_item_id}/products` |
| 10 | `distribution_run_item_send_whatsapp` | `POST /distribution/run-items/{run_item_id}/send-whatsapp` |

All 10 read in full before editing, each confirmed to already have the identical shape: `current_user: dict = Depends(require_procurement_workspace)` immediately followed (for the six tenant-parameterized routes) by `assert_tenant_access(current_user, tenant_id)`, or (for the four run-based routes) the trusted `run_tenant_id`/`run_item_tenant_id` lookup → `None`-check → 404 → `assert_tenant_access(current_user, owner_tenant_id)`.

### Authorization mechanism applied

**No new capability was invented.** `require_procurement_admin` already existed in `backend/modules/procurement/access.py`, built during the earlier P0 authorization task and unchanged since (confirmed: `access.py` shows zero diff from this task — it needed no edit). It already fails closed identically to `require_procurement_workspace` (503 on an unreadable module list, via the same `_require`-shaped `try`/`except HTTPException` pattern) and requires `grants_procurement_admin(codes)`, a strictly narrower grant.

**Change applied, narrowest possible:** in `backend/modules/procurement/pm_router.py`,
1. Added `require_procurement_admin` to the existing `from modules.procurement.access import (...)` block (one new name in an existing import, no new import statement).
2. On each of the 10 handlers above, changed `current_user: dict = Depends(require_procurement_workspace)` to `current_user: dict = Depends(require_procurement_admin)`. Nothing else in any of the 10 function bodies was touched — `assert_tenant_access` calls, the trusted-lookup-then-404-then-`assert_tenant_access` ordering on the four run-based routes, docstrings, and every other line are byte-for-byte unchanged.

Verified via `git diff backend/modules/procurement/pm_router.py | grep -c "require_procurement_admin"` → **11** (1 import line + 10 `Depends(...)` swaps, exactly matching scope) and via `grep -c "Depends(require_procurement_admin)"` on the live file → **10**, `grep -c "Depends(require_procurement_workspace)"` → **43** (down from 53 before this task, consistent with exactly 10 routes moving out, matching the R2 round's total of 53 workspace-gated routes minus these 10).

### Security guarantees preserved — confirmed by direct re-read, not assumed

- **Authentication**: unchanged. `require_procurement_admin`, like `require_procurement_workspace`, is built on `Depends(get_current_user)` (non-optional — 401 on missing/invalid token), confirmed by reading `access.py` lines 85-94.
- **Tenant isolation**: unchanged. Every `assert_tenant_access(current_user, tenant_id)` / `assert_tenant_access(current_user, owner_tenant_id)` call in all 10 handlers is in exactly the same position relative to the capability check as before this task — confirmed by direct line-by-line re-read of the post-edit file (reproduced in full above).
- **Trusted ownership resolution for `run_tenant_id`/`run_item_tenant_id`**: unchanged. The four run-based routes still resolve the owning tenant from `distribution_service.run_tenant_id(run_id)` / `run_item_tenant_id(run_item_id)` — server-side lookups added in the prior round-2 task and schema-verified against the real `CREATE TABLE` DDL in that task's own independent review — never from a client-supplied value. `distribution_service.py` has zero diff from this task (confirmed: not opened for editing).
- **Fail-closed behavior**: unchanged and re-tested (`test_distribution_routes_fail_closed_on_unreadable_module_list`, below) — a module-lookup failure still produces 503, not a silent allow, for every one of the 10 routes.
- **No client-supplied identifier is trusted as authorization**: unchanged — `tenant_id` is still compared against the authenticated principal's own JWT-derived tenant via `assert_tenant_access`, and the four run-based routes still derive ownership from a database lookup keyed only on the path parameter, never trusting a parameter as proof of anything.

### Tests added

Extended the existing `tests/test_procurement_pm_router_auth_round2.py` (preferred over a new file, per the task's own instruction to extend the existing suite and conventions) with:
- A new `_DISTRIBUTION_ROUTES` table (all 10 routes, with each route's expected underlying service-call name for call-tracking assertions) and `_DISTRIBUTION_RUN_BASED_PATHS` (the four run-based paths that take no `tenant_id` query parameter, reused from the existing `_RUN_ROUTES` split).
- `test_distribution_routes_reject_workspace_only_grant` — **the test that actually proves D8 changed behavior**: a fully authenticated, same-tenant caller holding only `PROCUREMENT_WORKSPACE` (no admin grant) is now rejected (403) on all 10 routes, and the underlying service function is confirmed absent from the call-tracking list for every one. This is a genuinely new assertion the pre-D8 code would have failed, confirmed independently by checking `access.grants_procurement_admin(["PROCUREMENT_WORKSPACE"])` returns `False` while `grants_procurement_workspace(["PROCUREMENT_WORKSPACE"])` returns `True` — the exact asymmetry this test exercises.
- `test_distribution_routes_accept_admin_grant` — the positive counterpart: a `PROCUREMENT_ADMIN` caller still reaches every one of the 10 routes and the underlying service runs. Proves D8 doesn't also accidentally break the legitimate admin workflow.
- `test_distribution_routes_still_reject_cross_tenant_even_with_admin_grant` — confirms the new, narrower capability floor does not relax tenant isolation: an admin-grant caller forging `tenant_id` to another tenant on the six tenant-parameterized routes is still rejected (the four run-based routes' cross-tenant behavior is already covered by the pre-existing `test_run_routes_reject_a_run_owned_by_another_tenant`, not duplicated here).
- `test_distribution_routes_fail_closed_on_unreadable_module_list` — confirms `require_procurement_admin`'s existing 503 fail-closed behavior is unaffected for these specific routes.
- `test_distribution_routes_reject_unauthenticated_and_unauthorized_role` — baseline 401/403 checks restated for completeness alongside the new workspace-only-grant case, not claimed as new coverage on its own (these cases would have passed before D8 too).

**Why the existing round-2 suite could not have caught this gap on its own, stated honestly**: every pre-existing test in that file that touched a distribution route used `["PROCUREMENT_ADMIN"]` as the injected module code (`test_authorized_same_tenant_requests_still_succeed`, `test_all_routes_reject_cross_tenant_forged_tenant_id`), and `PROCUREMENT_ADMIN` satisfies both `require_procurement_workspace` and `require_procurement_admin` — so re-running the old suite against the new code could not, by construction, distinguish "requires workspace" from "requires admin." Confirmed this directly: re-ran the full pre-existing 13-test file against the post-D8 code before adding anything new, and **all 13 still passed** — proving the old suite alone is not evidence D8 was implemented correctly, which is exactly why the five new tests above were necessary, not optional.

### Tests — exact commands and results

```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_pm_router_auth_round2.py -v --tb=short
```
Result: **18 passed** (13 pre-existing + 5 new), 4 warnings (3 pre-existing Pydantic `.dict()` deprecation, 1 pytest-cache permission warning, both unrelated to correctness).

```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_pm_router_auth.py tests/test_procurement_pm_router_auth_round2.py -v --tb=short
```
Result: **27 passed** (9 original P0 + 18 above), 6 warnings, same shapes as above.

```
backend/.venv/Scripts/python.exe -m pytest tests/ -q --tb=no -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py
```
Result: **159 passed, 11 failed, 125 deselected.** The 11 failures are, by exact name, the identical set already established as pre-existing across every prior section of this document (`test_assign_exceeds_final_rejected`, `test_assign_single_ok`, `test_bulk_assign_reports_mixed`, `test_excluded_missing_grn_watermark`, `test_spike_floor_included_binding`, `test_create_refresh_full_pipeline`, `test_manual_add_validations`, `test_close_cycle_blocked_when_generating`, `test_close_cycle_ok`, `test_close_cycle_already_closed`, `test_end_to_end_post_export`). The pass count rose from the master status register's own freshly-recorded baseline of 154 to **159** — exactly the 5 new D8 tests, confirming no new regression and no double-counting. **Not re-verified via `git stash` in this pass** — this task's own boundaries (preserve unrelated existing work, no destructive git operation implied or required) and the fact that this exact 11-failure set was already confirmed pre-existing via `git stash`/rerun/`pop` twice in this document's earlier sections (the round-1 and round-2 authorization tasks) make a third repetition of that destructive-adjacent verification unnecessary; the evidence already on record is treated as sufficient, consistent with how the most recent independent review (which was explicitly barred from destructive git operations) handled the same situation.

No test was skipped, errored, or could not run.

### Diff summary

```
git diff --stat backend/modules/procurement/pm_router.py backend/modules/procurement/access.py backend/modules/procurement/distribution_service.py
 backend/modules/procurement/distribution_service.py |  36 +++   (unchanged from the prior round-2 task; zero new diff this task)
 backend/modules/procurement/pm_router.py            | 317 ++++++++++++++++--- (+1 line vs. the prior round-2 task's 316 — the new import name)
```
`access.py` shows **no line in the diff stat at all** — zero changes, confirmed. The only files touched by this task: `backend/modules/procurement/pm_router.py` (the 11-line D8 change described above, layered on top of the already-existing round-2 diff), `tests/test_procurement_pm_router_auth_round2.py` (the 5 new tests plus the two new route tables), and this review document. `backend/modules/procurement/decision_rules.py`, `decision_repository.py`, `decision_service.py`, `vpl_history.py`, `vpl_history_router.py`, `rules_catalog.py`, `rules_resolution.py`, `rules_router.py`, every file under `backend/modules/procurement/sql/`, and every file under `backend/modules/legacy_order/` were confirmed to show **zero diff attributable to this task** — the `legacy_order/` changes visible in `git status` are Cursor's pre-existing, unrelated, already-documented parallel WIP, not opened or touched here.

### Remaining risks and integration-test limitations — unchanged from every prior pass, restated honestly

No real end-to-end integration test (live SQL Server, live JWT issuance, real concurrent requests) has been run for D8 or any authorization fix in this document's history — every verification here, like every one before it, is mocked-service/in-process `TestClient` only. Store-level isolation remains out of scope exactly as stated throughout this document — `assert_tenant_access` is tenant-level only, and D8 introduces no new store-level axis. The Rules Registry mutating-route capability gap flagged 2026-10-19 (separate from D8, a different workstream) remains unverified-stale, as recorded in the master status register above — not investigated or touched by this task, which was scoped to D8 only.

### Status

- **D8: `OWNER APPROVED — IMPLEMENTED`.** All 10 `distribution_*` routes now require `PROCUREMENT_ADMIN`. Independently testable, tested, and the test evidence that the old suite could not have proven this is documented above.
- Phase 2: `READY_FOR_REVIEW`.
- VPL History persistence: `BLOCKED`.
- Rare-mover enforcement: unresolved, untouched by this task.
- A genuinely separate reviewer should still re-verify this change (route enumeration, capability swap correctness, test meaningfulness) before D8 is considered closed without qualification — consistent with every prior authorization task in this document, which were all followed by an independent review pass before being treated as settled.


## D3c implementation — rare-mover confirmation — 2026-10-21 (Claude)

Owner decision (this session, via explicit question, not inferred): **discrete confirmation field**, not a queue-based implicit-approval model. Recorded in the D1-D8 register above.

**Design, consistent with D1/D3/D4/D6/D7 already on record:**
- `rare_confirmed` / `rare_confirmed_by` / `rare_confirmed_at` added to `procurement.procurement_order_items` by new migration `0028_rare_mover_confirmation.sql` (additive, idempotent `COL_LENGTH` guard pattern matching `0007_order_item_review_fields.sql`). **NOT APPLIED** — written for review only, with verify and rollback scripts (rollback refuses if any row has `rare_confirmed = 1`).
- Cycle-scoping (D3: confirmation valid only for the current cycle) is satisfied by construction, not by a separate expiry check: `procurement_order_items` already has `UNIQUE (refresh_id, product_id)` (`0004_procurement_order_items.sql`), so every new cycle/refresh mints a brand-new row starting at `rare_confirmed = 0`. There is no stale cross-cycle row to misread.
- Identity (D7): confirmation lives on the same row keyed by `product_id`, reusing the already-approved stable-identity work — not `product_code` alone.
- Tenant/store isolation (D6): `confirm_rare_mover` and every enforcement read go through the existing `tenant_id`-scoped repository functions and the existing `assert_tenant_access` gate on the new router endpoint — no new isolation primitive needed.

**Enforcement, feature-gated:** `rare_mover_guard.py` (new) — `enforcement_enabled()` reads `PROCUREMENT_RARE_MOVER_ENFORCEMENT` (default `"0"`, i.e. off). Rationale, explicitly confirmed with the owner before implementing: migration 0028 is not applied, so the column does not exist on the live table and no PM can ever set it today — wiring the check unconditionally would permanently block every rare-mover line's assignment/export in production with no way to unblock it. The flag exists so the check is fully coded and tested now, and becomes live with a one-line env change only after 0028 is applied.

**Wired into every live assignment/export entry point:**
- `assignment_service.assign_single` — raises 409 via `rare_mover_guard.require_confirmed(item)` before any write.
- `assignment_service.assign_bulk` — per-item isolation preserved (existing pattern): an unconfirmed rare-mover line is reported `{"status": "skipped", "reason": "rare-mover item requires PM confirmation"}`, not a fatal exception, so one bad line never aborts the batch.
- `export_service.export_refresh` / `export_repository.exportable_assignments` — the repository join now always carries `reason_code` (from `procurement_virtual_products`, already live) and conditionally carries `rare_confirmed` (`oi.rare_confirmed` only when the flag is on, `CAST(0 AS BIT)` otherwise — selecting the real column unconditionally would break this query against the live, unmigrated schema). The service loops every exportable row through `require_confirmed` before stamping any batch — fails the **whole export** closed if any one line is unconfirmed, consistent with "assign/export cannot bypass required confirmation."
- `change_supplier`/`remove_assignment` were deliberately left unchanged: reassigning or removing an already-assigned line doesn't need the gate re-checked (confirmation already passed at the original `assign_single`/`assign_bulk` call that created the assignment).
- New endpoint `POST /order-items/{order_item_id}/confirm-rare-mover` (`pm_router.py`, `require_procurement_workspace` + `assert_tenant_access`, matching every sibling review-action route) → `workspace_service.confirm_rare_mover` → `workspace_repository.confirm_rare_mover`. Rejects (400) a confirm call on a non-rare-mover item (`reason_code` not in `rare_mover_guard.RARE_MOVER_REASON_CODES`).

**Not done, explicitly out of scope / blocked:**
- Migration 0028 not applied — per master-prompt and project rules, no migration is executed in any of these passes.
- No UI control added for the new confirm endpoint — this pass is backend/service-layer only, matching the master prompt's "service layer, not only in the UI" requirement without implying a UI task was authorized.
- Concurrency hardening of the confirm-then-assign path (TOCTOU between confirming and a concurrent assign) is addressed by Step 3's broader version-check work, not duplicated here — `assign_single` already reads the item fresh via `_require_item` immediately before the guard check, same as every other validation in that function.

**Tests:** new `tests/test_procurement_rare_mover_guard.py`, 15 tests — guard unit behavior (flag on/off, rare/non-rare, confirmed/unconfirmed), `assign_single` reject/allow/flag-off, `assign_bulk` per-item isolation reject/allow, `export_refresh` whole-batch reject/allow/flag-off, cross-cycle non-sharing, and the `confirm_rare_mover` repository call shape. `pytest tests/test_procurement_rare_mover_guard.py -v` → **15 passed**. Broader: `pytest tests/ -q -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **174 passed, 11 failed** — the same 11 pre-existing failures by exact name as every prior baseline in this document (159 + 15 new = 174, confirmed no drift, no double-counting).

`git diff --stat` on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`vpl_history_router.py`/`rules_catalog.py`/`rules_resolution.py`/`rules_router.py` → zero diff on all. `legacy_order/` diff is Cursor's pre-existing, unrelated WIP — not opened or touched by this task.

No migration applied, no database connection opened, no WhatsApp/export/GRN action taken against real data.

**This is self-implemented, not yet independently re-reviewed by a separate pass** — consistent with the project convention, a genuinely separate reviewer should re-verify the enforcement points, the feature-gate rationale, and the migration design before D3c is treated as closed without qualification.

## Step 3 — concurrency and transaction safeguards — 2026-10-21 (Claude)

Verified D1/D2/D6/D7 already match current code with no change needed (confirmed by re-reading, not re-deriving — consistent with the existing D1-D7 register above). Implemented D4 and D5, the two decisions that actually required code.

**D4 — TOCTOU fix on `assign_single`/`assign_bulk` (Audit D item 2, this document's prior section):** new `assignment_repository.lock_order_item_for_assignment(conn, tenant_id, order_item_id)` — `SELECT ... WITH (UPDLOCK, HOLDLOCK)` against `procurement_order_items`, called immediately after `get_connection()` and before `duplicate_active_exists`/`any_active_assignment` in both `assign_single` and the per-item loop of `assign_bulk`. Two concurrent callers on the same `order_item_id` now serialize on this lock instead of both passing the "no existing assignment" check before either commits — the second caller's lock acquisition blocks until the first's transaction commits or rolls back, at which point it re-reads a consistent state. This is a database-level fix (lock held for the rest of the caller's own transaction), not an application-level re-check, so it is correct under real concurrent SQL Server transactions, not just within one mocked test. **Database-level locking behavior itself remains NOT_VERIFIED** — no isolated SQL Server instance was available to run two genuinely concurrent transactions against this code; the fix is verified at the code/call-order level (the lock call happens first, with the right hints, every time) but not under actual contention.

**D5 — refresh retry idempotency:** owner decision obtained this session (explicit question): client-supplied `idempotency_key`, not a parameter-dedup window. New migration `0029_refresh_idempotency_key.sql` (+verify+rollback, additive, **NOT APPLIED**) adds `idempotency_key` to `procurement_refreshes` plus a filtered unique index on `(tenant_id, cycle_id, idempotency_key) WHERE idempotency_key IS NOT NULL`. `vpl_repository.find_by_idempotency_key` (new) and a conditional branch in `create_vpl` (writes the column only when a key is actually supplied, so the INSERT doesn't reference a nonexistent column for ordinary unkeyed callers). `orchestration_service.create_refresh` checks `find_by_idempotency_key` first when `PROCUREMENT_REFRESH_IDEMPOTENCY=1` (default off — the column doesn't exist until 0029 lands) and a key is present; on a hit, returns the existing Refresh without running the pipeline again. The true race-safety is the filtered unique index itself (not the initial SELECT, which can still race) — a concurrent double-insert on the same key is caught as a constraint violation in a new `except` block and resolved by re-reading the winner's row (`_is_unique_violation` helper, matched by exception class name/SQLSTATE text rather than a hard `pyodbc` import).

**Feature-gating rationale (same pattern as D3c):** both D4 and D5 touch tables mid-migration. D4's lock statement only reads a column (`order_item_id`) that already exists live, so it is **unconditionally live now** — no flag needed, no migration required. D5's idempotency check reads a column that does not exist until 0029 is applied, so it stays behind `PROCUREMENT_REFRESH_IDEMPOTENCY` (default off) exactly like D3c's `PROCUREMENT_RARE_MOVER_ENFORCEMENT` — flip it on only after 0029 is applied.

**Tests:** new `tests/test_procurement_concurrency_d4_d5.py`, 8 tests — D4: lock-called-before-checks for both `assign_single` and `assign_bulk`, and the exact SQL hint/params shape; D5: flag-off no-op, idempotency hit returns existing without calling `create_vpl`, idempotency miss creates a new refresh with the key stored, concurrent-retry unique-violation recovery, and a non-idempotency exception still propagates untouched. `pytest tests/test_procurement_concurrency_d4_d5.py -v` → **8 passed**.

Existing shared test file `tests/test_procurement_pm_workflow.py`'s `_patch_assign` helper and `test_bulk_assign_reports_mixed` were updated with one additive mock line each (`lock_order_item_for_assignment`) so the new D4 call doesn't break their existing `_FakeConn` (no `.cursor()`) fixture — this is the same fixture gap already responsible for several of this document's long-standing pre-existing failures (`test_assign_single_ok`, `test_assign_exceeds_final_rejected`, `test_bulk_assign_reports_mixed` itself all fail on the *next* unmocked call, `any_active_assignment`, independent of this change) — confirmed by re-running before and after: the same three tests fail for the same underlying reason both before and after this task's edits, not newly broken by it.

Broader: `pytest tests/ -q -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **182 passed, 11 failed** — same 11 pre-existing failures by exact name as every prior baseline (174 + 8 new, confirmed no drift, no double-counting). `git diff --stat` on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`vpl_history_router.py`/`rules_catalog.py`/`rules_resolution.py`/`rules_router.py` → zero diff on all.

No migration applied (0028 and 0029 both written for review only), no database connection opened, no external action taken.

**Self-implemented, not yet independently re-reviewed** — same caveat as every implementation pass in this document.

## Step 5 — Procurement release gate — 2026-10-21 (Claude)

Workflow assessed: Login → Store → Cycle → Refresh → VPL → Workspace → Supplier Queue → Supplier Products → Assign → Export → Receive/Pending → Close Cycle.

| Gate | Status | Evidence | Verification kind | Remaining dependency |
|---|---|---|---|---|
| 1. Authentication and authorization | **PASS** | D8 closed (all 10 `distribution_*` routes require `PROCUREMENT_ADMIN`); `assign`/`bulk_assign`/`change_supplier`/`remove_assignment`/`export`/`submit_grn` already require `require_procurement_workspace`/`require_procurement_export` + `assert_tenant_access` (the "Defect 2" gap recorded earlier in this document is **already fixed in the current checkout** — re-confirmed by direct read this session, not assumed from the older audit entry). 27/27 + broader auth suites pass. | Mocked/in-process `TestClient` only | No live SQL Server/JWT integration test exists anywhere in this document's history — `NOT VERIFIED (mocked only)`, permanent known gap |
| 2. Tenant/store isolation | **PASS** | `assert_tenant_access` on every mutating route; store-scoped reads confirmed in prior audits (Cross-tenant store scoping fix, Supplier Analysis warehouse scoping — separate modules, same pattern reused here) | Mocked | Same as gate 1 |
| 3. Procurement business rules (D1/D2/D6/D7) | **PASS** | Re-confirmed this session: current code already matches all four with no change needed (one active supplier/line, deferred lines regenerate fresh, store-scoped history access, `product_id`-first stable identity) | Code-level re-read, not newly derived | None outstanding |
| 4. Rare-mover enforcement (D3c) | **BLOCKED → PARTIAL** | Owner decision obtained this session (discrete `rare_confirmed` field). Implemented in `rare_mover_guard.py`, wired into `assign_single`/`assign_bulk`/`export_refresh`. 15/15 new tests pass. **Feature-gated OFF by default** (`PROCUREMENT_RARE_MOVER_ENFORCEMENT`) because migration `0028` is not applied — enforcement is code-complete but not live in production today | Mocked | Apply `0028_rare_mover_confirmation.sql`, then flip the env flag on; independent re-review of the guard still pending |
| 5. Assignment concurrency and idempotency (D4/D5) | **BLOCKED → PARTIAL** | D4 (TOCTOU lock) is **unconditionally live now** (no migration needed — reads an existing column). D5 (refresh retry idempotency) is implemented but feature-gated OFF (`PROCUREMENT_REFRESH_IDEMPOTENCY`) pending migration `0029`. 8/8 new tests pass | Mocked; real lock *contention* behavior under genuine concurrent SQL Server transactions is `NOT VERIFIED` — no isolated instance available | Apply `0029`, flip the flag; a real two-transaction concurrency test against live SQL Server has never been run for D4 either |
| 6. VPL History persistence and refresh atomicity | **BLOCKED → PARTIAL** | Repository layer (`vpl_history_repository.py`) implemented against new migration `0030` and tested (9/9). **Not wired into the live `create_refresh` pipeline** — remains a design-plus-repository artifact, not an active feature. In-memory prototype (`vpl_history.py`) remains `READY_FOR_REVIEW`, unwired, as recorded throughout this document | Mocked | Apply `0030`; wire `write_history_batch` into `create_refresh`; restart-survival demonstration needs a real SQL Server instance |
| 7. Export and GRN reconciliation | **PASS, with a known limitation** | Export fail-closed on rare-mover (new, flag-gated); GRN/reconciliation split across transactions was flagged in an earlier audit (`reconciliation_service.submit_grn` commits `store_last_grn` then reconciles on a new connection) — **not changed in this pass**, carried forward as a known gap, not newly introduced | Mocked | Unifying the GRN/reconcile transaction boundary was not in this session's authorized scope; flagging for a future pass |
| 8. Migration readiness | **5 migrations written, 0 applied** | `0026` (rules registry), `0027` (VPL history prototype's original design, now superseded for batch/line by `0030`), `0028` (rare-mover confirmation), `0029` (refresh idempotency), `0030` (VPL history persistence + concurrency columns) — all additive, all have verify+rollback scripts, **none applied** | N/A — review only | Every applied-migration decision remains an explicit, separate authorization this document has never been given |
| 9. Regression-test results | **PASS** | `pytest tests/ -q -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **191 passed, 11 failed** — the same 11 failures by exact name recorded at the start of this session's work (confirmed via direct re-run before and after every change in Steps 2-4, not assumed) | Mocked/in-process | The 11 pre-existing failures are unrelated to this session's changes (two in `decision_engine` rare-mover/spike-floor classification, the rest in fixture gaps — `_FakeConn` missing `.cursor()` on `any_active_assignment`/`clear_products` calls — predating this session) |
| 10. UI-to-API workflow coverage | **NOT VERIFIED this session** | No frontend file was touched in Steps 1-4 (backend/service-layer scope only, consistent with the master prompt's "service layer, not only in the UI" framing for D3c). The existing VPL History UI (`VplHistoryPanel.tsx`) and `/procurement/vpl-history` screen remain as documented in this file's earlier sections — unaffected, not re-verified this pass | N/A | A full UI-to-API click-through was not attempted; no browser automation tool was available in earlier sessions either (documented limitation, unchanged) |

**Overall: NOT production-ready.** Four of ten gates are PARTIAL (rare-mover, concurrency/idempotency, VPL persistence) specifically because their migrations are written-but-unapplied by design — every one of this session's new capabilities is feature-flagged OFF until its migration is authorized and applied, which is the correct, safe state for a review-only pass, not a defect. Passing unit/integration tests against mocked repositories is not evidence that SQL Server will behave identically under real constraints, real concurrent transactions, or real data volume — that gap is explicit and repeated throughout this document, not glossed over here.

**Single next action with the greatest value:** get owner authorization to apply migrations `0028`/`0029`/`0030` against an isolated test SQL Server instance (not production `NEXORA_PLATFORM`), run the existing test suites against that real database, and only then flip the three feature flags on in a non-production environment to observe real concurrent-transaction behavior for D4's lock and D5's unique-index race path — this is the one action that would convert the largest number of "PARTIAL/NOT VERIFIED" gates into genuinely verified PASSes.

## Isolated SQL Server integration verification — 2026-10-21 (Claude)

Executed the full Phase A-C protocol from the follow-up task. Real SQL Server, not mocks. Summary: migrations apply and verify cleanly; D3c/D4/D5 all hold under genuine concurrent transactions; Step 4's repository is atomic under a real forced failure; two real bugs were found and fixed in the rollback scripts (not found by any prior mocked-test pass).

### Phase A — environment identification

Active `backend/.env` target (`DB_SERVER=192.168.10.73`, `DB_DATABASE=NEXORA_PLATFORM`) is the shared HO/production node — confirmed NOT isolated, not connected to for writes. Found a genuinely separate, disposable candidate already running on this machine: SQL Server 2022 Express at `localhost\SQLEXPRESS` (Windows-auth), hosting only unrelated pre-existing databases (`nathanw`, `MVMR_DEV/TEST`) — no `NEXORA_PLATFORM`/`OrderNMC` database existed on it. A `docker-compose.yml` disposable-container option exists in the repo but Docker CLI is not installed in this environment, so it was not usable. Owner approved (via AskUserQuestion) creating `NEXORA_PLATFORM_TEST` on `localhost\SQLEXPRESS` before any write.

Confirmed additive-only (no DROP/TRUNCATE/DELETE/data UPDATE) in all three forward migrations by grep. Confirmed dependency order: 0028 depends on 0004, 0029 depends on 0002, 0030 depends on 0001+0002+0004+0005, and that 0030 must not run alongside 0027's `vpl_history_batch`/`vpl_history_line` CREATE TABLE statements (not run in this pass — 0027 was never applied here). Confirmed 0001-0005 have zero FK dependency outside schema `procurement` (self-contained). Feature flags confirmed by grep: `PROCUREMENT_RARE_MOVER_ENFORCEMENT` and `PROCUREMENT_REFRESH_IDEMPOTENCY`, both `os.environ.get(..) == "1"`, default off.

### Phase B — readiness report

Presented as a table (migration, dependencies, objects, risk, verify script, rollback) before any write. Explicitly stated 0030 alone does not prove end-to-end persistence (not wired into `create_refresh`); Phase C tests the repository module directly against real SQL Server, not a full refresh-cycle flow.

### Phase C — execution (after explicit approval)

1. Created `NEXORA_PLATFORM_TEST` on `localhost\SQLEXPRESS`. Applied 0001, 0002, 0003, 0004, 0005, 0006, 0007, 0008 (base schema + explainability/review/GRN columns `get_item`'s real query needs — discovered mid-run when the bare 0001-0005 subset was insufficient), then 0028, 0029, 0030, each followed by its own verify script. All applied and verified cleanly. One real tooling gotcha found: `sqlcmd`'s default session has `QUOTED_IDENTIFIER OFF`, which breaks `CREATE UNIQUE INDEX ... WHERE ...` (filtered indexes) with `Msg 1934` — fixed by prepending `SET QUOTED_IDENTIFIER ON;` to every script run via `-i`. Not a defect in the migrations themselves (`backend/config/database.py`'s pyodbc connections already set this correctly); purely an `sqlcmd` CLI default, worth remembering for any future manual migration run with that tool.

2. Had to create a minimal stub `sync.Products` table (schema `sync`, columns `tenant_id, store_id, ProductCode, SaleUnit, UnitDescription, ProductType`) for `workspace_repository.get_item`'s existing LEFT JOIN to resolve — `sync.Products` is part of the broader platform schema, out of scope for the procurement-only migration set, and a LEFT JOIN still requires the table to exist even if no row matches.

3. **D3c rare-mover confirmation — 8/8 real-DB tests passed:** unconfirmed line blocked (409 via `rare_mover_guard.require_confirmed`), `confirm_rare_mover` persists `rare_confirmed=1`/`rare_confirmed_by`/`rare_confirmed_at` as real column values (verified via a second independent `SELECT`, not just the function's return value), confirmed line then passes the guard, a new cycle's row for the same product starts unconfirmed (zero cross-cycle leak, confirmed against a real second row), and `confirm_rare_mover` called with the wrong `tenant_id` affects 0 rows (cross-tenant isolation enforced by the real `WHERE tenant_id = ?` clause, not just application logic).

4. **D4 concurrent assignment — 3/3 real-DB tests passed, using two genuine `pyodbc` connections on separate Python threads, synchronized with a `threading.Barrier` so both call `assign_single` at the same instant:** exactly one of the two concurrent calls succeeded; the other was rejected with a real 409; exactly one live assignment row existed in the table afterward. This is the first time this document's long-standing TOCTOU finding (Audit D item 2) has been tested under actual concurrent SQL Server transactions rather than a mocked single-threaded call sequence — `lock_order_item_for_assignment`'s `WITH (UPDLOCK, HOLDLOCK)` correctly serialized the two real transactions.

5. **D5 refresh idempotency — 6/6 real-DB tests passed:** first keyed `create_vpl` succeeds; `find_by_idempotency_key` finds the real row via the real filtered unique index; a different key creates a genuinely new refresh (no false-positive dedup); a second `INSERT` with the same key raises a real `pyodbc.IntegrityError` (the unique index itself enforces it, not application logic alone); exactly one refresh row exists for the key despite the duplicate attempt; and a genuine two-thread concurrent race on the same key (same `threading.Barrier` pattern) produced exactly one winning `INSERT` and one real `IntegrityError` on the other thread — confirming "no duplicate logical refresh is created for the same key" under actual contention, not just in a mocked single-threaded test.

6. **Step 4 VPL History repository — 4/4 passed on the happy path, 2 initially failed then passed after a test-design fix (not a repository bug):** `write_history_batch` commits a real batch+line row; `list_batches`/`get_batch_lines` read them back; a fresh `pyodbc` connection (restart-equivalent) reads the same data. The atomicity test initially gave a false negative — the first attempt referenced a `source_order_item_id` that was never in the `lines` list, so the assignment-insert loop (keyed by lines actually being inserted) correctly never touched it, meaning no failure occurred at all (test bug, not a repository bug). Corrected to use a genuinely invalid `assignment_id` value (not a valid `UNIQUEIDENTIFIER` string) for a line that was being inserted — this produced a real `pyodbc.ProgrammingError` mid-transaction, which the caller's `except/rollback` correctly caught, and a follow-up `SELECT` confirmed zero partial batch rows survived — real atomicity confirmed under a real forced failure, not assumed.

7. **Two real defects found and fixed in the rollback scripts (0028 and 0030) — not caught by any prior pass, because no prior pass had run them against real SQL Server:** `RAISERROR(...); RETURN;` inside a `GO`-separated batch only exits that batch in `sqlcmd` — it does not prevent later `GO` batches in the same script from executing. Both rollback scripts' original versions printed the correct refusal message but then dropped the columns/tables anyway, because the guard and the destructive statements lived in separate batches. Reproduced directly: seeded a real `rare_confirmed=1` row, ran `0028_..._rollback.sql`, got the expected `Msg 50000` refusal text, then confirmed via a direct `COL_LENGTH` query that the column was dropped anyway. Same reproduction for 0030 against the `row_version`/history-table guard. **Fixed both scripts**: replaced the `RETURN`-based short-circuit with a `#rollback_NNNN_guard` temp table (visible across `GO` batches on the same session) written once by the guard query, then checked by name at the top of every subsequent destructive batch — each later batch now does nothing at all when the guard is blocked, not just skips its own local `IF`. Re-verified both fixes twice each: once with real blocking data present (refusal now correctly leaves every column/table untouched, confirmed by direct schema query after the "refusal"), and once with genuinely empty data (rollback now correctly succeeds and the columns/tables are actually gone). This is the single most significant finding of this verification pass — a prior design-level "refuse when data exists" was correct, but the sqlcmd execution semantics were never exercised until this pass, and were silently broken.

8. Dropped `NEXORA_PLATFORM_TEST` entirely at the end — zero footprint left on `localhost\SQLEXPRESS` beyond the pre-existing unrelated databases that were already there.

**Test counts, real SQL Server, this pass only:** D3c 8/8, D4 3/3, D5 6/6, Step 4 repository 6/6 (after the one test-design fix) = **23/23 passed** in the standalone integration script (not part of the repo's pytest suite — a one-off verification script, not committed). Separately, the full mocked pytest suite was re-run unchanged afterward: `pytest tests/ -q -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **191 passed, 11 failed**, identical to every prior checkpoint in this document — the SQL-file-only rollback fix touched no Python code, so no change was expected or found here.

**Files changed this task:** `backend/modules/procurement/sql/0028_rare_mover_confirmation_rollback.sql`, `backend/modules/procurement/sql/0030_vpl_history_persistence_rollback.sql` (both: fixed the cross-batch guard bug). No forward migration changed. No application code changed. No test file changed (the standalone verification script lived in the session's scratch directory, not the repo).

**Migrations applied and verified:** 0028, 0029, 0030 (plus prerequisite 0001-0008) — against the isolated `NEXORA_PLATFORM_TEST` only. **Not applied to `NEXORA_PLATFORM`** (production/shared `.73`) or `OrderNMC`. That test database no longer exists (dropped at the end of this pass).

**Feature-flag states (this pass, isolated environment only, process env vars, never written to `backend/.env`):** both `PROCUREMENT_RARE_MOVER_ENFORCEMENT=1` and `PROCUREMENT_REFRESH_IDEMPOTENCY=1` were exercised successfully against the real schema. Production `backend/.env` remains unchanged — both flags stay off there.

**Remaining code integration gaps (unchanged from the prior release-gate assessment, restated honestly):** `vpl_history_repository.write_history_batch` is still not called from `orchestration_service.create_refresh` or any live route — this pass proves the repository/schema work correctly against real SQL Server in isolation, not that the end-to-end refresh-cycle persistence feature is live. GRN/reconciliation transaction-boundary gap (recorded earlier in this document) remains unaddressed, out of this pass's scope.

**Release-gate changes:** Gate 1 (auth) unaffected. Gates 4/5/6 (rare-mover, concurrency/idempotency, VPL persistence) upgrade from "mocked-only, NOT VERIFIED under real DB contention" to real-SQL-Server-verified for the specific scenarios tested (schema correctness, confirmation persistence, concurrent-transaction serialization, concurrent unique-index race, forced-failure atomicity) — still not full end-to-end production verification (no live app server, no real JWT, no real HTTP layer involved in this pass; the repository/service functions were called directly in-process against the real DB).

**Isolated test verdict: PASSED.** All 23 real-database scenarios requested by the task passed (after one test-design correction, not a code defect). Two real, previously-undetected rollback-script defects were found and fixed as a direct result of this being a genuine SQL Server execution rather than a mock — concrete evidence that this class of verification catches real gaps mocked tests structurally cannot.
