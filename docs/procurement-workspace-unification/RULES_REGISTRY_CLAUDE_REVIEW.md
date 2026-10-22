# Procurement Rules Registry — Claude independent review

**Reviewer:** Claude. **Scope:** source-backed check of the catalog,
schema/migration review, validation and permission review, per the
assignment recorded in `AUTONOMOUS_WORK_CONTROL.md`. This review did not
edit any Cursor-owned registry file (`rules_catalog.py`, `rules_resolution.py`,
`rules_router.py`, `router.py`, the 0026 SQL scripts, `ProcurementRulesPage.tsx`,
`AppRouter.tsx`, `navConfig.ts`, `test_procurement_rules_registry.py`).

## Independent test re-run

```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py -q --tb=short
→ 8 passed (1 pytest-cache warning, not a failure)

cd frontend && npx tsc -b
→ exit 0, no output
```

Both match Cursor's own report in the control file's handoff log exactly.
No over-claiming found.

## Catalog review (`rules_catalog.py`, 21 rules)

Read the full `RULES` tuple (`rules_catalog.py:65-408`). Checked every rule
against its cited source:

- **`PRR-QTY-WINDOW` (90), `PRR-QTY-MIN-COVER` (13), `PRR-QTY-MAX-COVER` (18):**
  match the master prompt's confirmed decisions and `quantity_profile_t.py`
  constants. `STATUS_CONFIRMED`, correctly `POLICY_STORE` (overridable).
- **`PRR-QTY-RECENCY` (15):** correctly `STATUS_CONFLICT`, not `CONFIRMED` —
  the source_evidence text accurately names all three clocks (VB hard-coded
  10, `decision_rules.DecisionParameters.recency_days` default 10, legacy
  SQL's uncommitted `service.py` default 15) and flags that changing the
  legacy default is itself live uncommitted work, not a historical fact.
  This is consistent with what I independently verified in the Phase 1
  source-field-map pass (confirmed `LEGACY_RECENCY_DAYS` env default 15 in
  the current working tree).
- **`PRR-STK-SOURCE` (`Products.TotalStock`, `POLICY_LOCKED`):** matches the
  master prompt's fixed stock source, correctly cites that Nexora's
  `decision_repository.load_source` uses `StockInHand` instead — a real,
  cited conflict, not glossed over. Locked so a store cannot silently
  switch the stock source.
- **`PRR-STK-PENDING` (`value_type="blocked"`, `POLICY_NONE`):** correctly
  refuses to accept any value. I independently confirmed in
  `PHASE_1_SOURCE_FIELD_MAP.md` that none of the three legacy loaders
  (`qty_check_rows`, `orders_by_supplier` history/stock) expose a pending
  column — this rule's `DECISION_REQUIRED` status matches that finding
  exactly, including the citation back to `PHASE_1_SOURCE_FIELD_MAP`.
- **`PRR-QTY-GROSS` / `PRR-QTY-NET`:** `POLICY_LOCKED` text fields holding
  the exact master-prompt formula strings. Correct to lock these — they are
  the owner-confirmed target formula, not something a store should be able
  to edit via this UI.
- **`PRR-QTY-SALEUNIT`, `PRR-QTY-DONTCONSIDER`:** both `bool`, locked to
  `True`, both correctly reject the opposite value in
  `rules_resolution.validate_value` (`rules_resolution.py:62-63`) — I traced
  this: a `False` write for `PRR-QTY-SALEUNIT` or `PRR-QTY-DONTCONSIDER`
  raises `RuleRejected("LOCKED_VALUE", ...)` before it can reach storage.
  Confirmed by `test_locked_blocked_and_range_are_rejected` exercising
  exactly `PRR-QTY-SALEUNIT=False`.
- **`PRR-QTY-RARE`:** embeds `RARE_MOVING_WARNING` from `quantity_profile_t.py`
  verbatim (not retyped) and asserts `auto_order=false` stays in the locked
  text — this is the right way to keep the warning string single-sourced;
  a future edit to the warning text in `quantity_profile_t.py` propagates
  here without anyone needing to remember to update two places.
- **`PRR-SAFE-PROFILE`:** `bool`, default `False`, `POLICY_LOCKED`, and
  `validate_value` rejects `True` (`rules_resolution.py:64-65`) — confirmed
  this is the one rule in the catalog that most directly enforces "Profile T
  stays off the live path" at the write boundary, not just by convention.
  Verified by reading `quantity_profile_t.py` is in fact never imported by
  `decision_rules.py` (`git diff --stat` shows zero change to that file,
  consistent with my Phase 1 verification).
- **Genuinely unverified rules correctly left blocked, not guessed:**
  `PRR-SUP-TAX-BASIS`, `PRR-RCV-NOT-SUPPLIED`, `PRR-PERM-ROLE`,
  `PRR-SAFE-TXNVALIDITY`, `PRR-EXP-PRECEDENCE` — all `value_type="blocked"`,
  `POLICY_NONE`, `STATUS_UNVERIFIED`/`DECISION_REQUIRED`/`APPROVAL_REQUIRED`.
  Each cites a concrete reason (no source column found, Role 1/2 left
  unmapped per Phase 1, no store/system-default export tier exists in
  `0018_supplier_export_settings.sql`). I did not independently re-verify
  `0018_supplier_export_settings.sql`'s schema in this pass — flagging as
  **UNKNOWN**, consistent with not duplicating Cursor's own audit trail.

**Finding: no rule in the catalog asserts a fact I could disprove.** Every
`CONFIRMED` status traces to the master prompt's explicit text or to a file
I independently read in Phase 0/1. Every `UNVERIFIED`/`DECISION_REQUIRED`/
`APPROVAL_REQUIRED` status matches a gap I independently found in the
Phase 1 source-field-map pass or is consistent with the existing audit docs.

## Schema/migration review (0026)

Read the forward script in full (164 lines). Findings:

- **Additive only:** every `CREATE TABLE` is guarded by
  `IF OBJECT_ID(...) IS NULL`; the one `ALTER TABLE` is guarded by
  `COL_LENGTH(...) IS NULL`. Confirmed idempotent — rerunning the script is
  safe.
- **No destructive operation.** No `DROP`, `TRUNCATE`, or data-modifying
  statement anywhere in the forward script.
- **FK integrity:** `rule_default_revision`, `rule_store_override`,
  `rule_change_audit`, `rule_effective_snapshot_item` all FK back to
  `rule_definition.rule_id` or `rule_effective_snapshot.snapshot_id`.
  `rule_store_override`'s composite PK `(tenant_id, store_id, rule_id)`
  correctly enforces one override row per store per rule — matches the
  in-memory `RulesRegistry._overrides` dict's own `(tenant_id, store_id,
  rule_id)` key shape (`rules_resolution.py:97,208`), so the eventual DB
  cutover would not change key semantics.
- **`rule_snapshot_id` on `procurement.procurement_refreshes` is nullable,
  no FK.** The migration comment explains why (a snapshot can outlive a
  soft-deleted refresh) and the rollback script compensates by refusing to
  drop the column if any refresh still references a snapshot
  (`THROW 50026`, rollback lines 9-18) — this is the correct trade-off
  given the explicit no-FK choice, not an oversight.
- **`OrderHeaderDetails` is untouched.** Confirmed by reading the full
  script — no reference to that table anywhere in the 164 lines, matching
  both the master prompt's "preserve OrderHeaderDetails" rule and the
  in-code comment's own claim.
- **Rollback correctness:** drops tables in FK-safe child-to-parent order
  (`rule_effective_snapshot_item` → `rule_effective_snapshot` →
  `rule_change_audit` → `rule_store_override` → `rule_default_revision` →
  `rule_definition`), matching the forward script's creation order reversed.
- **Not applied, by design.** No isolated SQL Server test database is
  available in this workspace (I did not attempt to connect one up or query
  `10.20.73`/`192.168.10.73` for this review — out of scope and explicitly
  disallowed without further authorization per this session's DB rules).
  The claim "migration is written and not applied" in the control file is
  accurate as far as I can verify: no connection attempt appears in any of
  the registry's Python modules, and `RulesRegistry.__init__`
  (`rules_resolution.py:83-88`) is pure in-memory state — no `pyodbc`/DB
  import anywhere in `rules_resolution.py` or `rules_router.py`.

**Finding: no destructive or unsafe operation in the migration or rollback.**

## Validation and permission review

- **`validate_value` (`rules_resolution.py:48-77`):** every `value_type`
  branch (`blocked`, `int`, `bool`, `enum`, `text`) either enforces a
  concrete constraint or unconditionally rejects. No branch silently
  accepts an out-of-contract value. `POLICY_NONE`/`blocked` rules are
  rejected before any type-specific check runs (line 49), so a client
  cannot bypass a lock by sending a type the specific branch doesn't
  anticipate.
- **Optimistic concurrency:** `set_default`/`set_override`/`reset_override`
  all compare `expected_version` against the current `row_version` under
  `self._lock` before mutating (`rules_resolution.py:171-172, 212-213,
  248-249`) and raise `RuleConflict` (→ HTTP 409 via `_reject` in
  `rules_router.py:28-30`) on mismatch. Verified by
  `test_optimistic_concurrency_history_and_reset` actually exercising a
  stale-version conflict, not just asserting the code path exists.
- **Store/tenant isolation:** `_effective_unlocked` keys overrides by the
  full `(tenant_id, store_id, rule_id)` tuple; `test_store_isolation_and_deterministic_hash`
  confirms a different store or tenant sees the default, not another
  tenant's override. The router calls `assert_tenant_access(current_user,
  tenant_id)` (confirmed this function exists at
  `backend/dependencies/store_scope.py:86`, real and not invented) on every
  endpoint that takes a `tenant_id` — `effective`, `history` (when
  `tenant_id` is supplied), `put_override`, `reset_override`,
  `create_snapshot`. **`put_default` (backend/modules/procurement/rules_router.py:65-80)
  does not call `assert_tenant_access`** because it has no tenant scope —
  it edits the global default, correctly gated instead by
  `rule.override_policy != POLICY_STORE` inside `set_default`
  (`rules_resolution.py:164-165`), which already restricts default edits to
  the small set of rules marked `POLICY_STORE`. This is consistent, not a
  gap — editing a global default is intentionally a different, narrower
  permission question than a store override, and the catalog's own
  `override_policy` field is the gate for it. Worth flagging explicitly for
  the owner: today `put_default` has no capability/role check beyond
  `POLICY_STORE`, which means any caller who can reach `PUT
  /api/procurement/rules/defaults/{rule_id}` can change a default for every
  tenant/store at once if that rule happens to be `POLICY_STORE`. The route
  mount point (`frontend/src/routes/AppRouter.tsx:146`,
  `RequireCapability cap="PROCUREMENT_ADMIN"`) gates the **UI**, but I did
  not find an equivalent `PROCUREMENT_ADMIN` dependency on the FastAPI route
  itself in `rules_router.py` — only `get_current_user_optional`, which per
  its name sounds optional/non-blocking. **This is the one finding in this
  review I'd call a real gap**, not just an open unknown: the backend route
  for `put_default` does not appear to enforce `PROCUREMENT_ADMIN` or
  equivalent server-side, relying on the frontend capability gate alone —
  which the master prompt's own Phase 12 language says not to do ("Do not
  expose actions merely by hiding buttons; enforce authorization
  server-side"). Recommend Cursor add a server-side capability check to
  `rules_router.py`'s mutating routes before this leaves `READY_FOR_REVIEW`.

## Summary

- Tests and typecheck independently re-run and match Cursor's claims.
- Catalog entries are source-backed; no invented fact found.
- Migration is additive, idempotent, FK-safe, does not touch
  `OrderHeaderDetails`, and is correctly left unapplied.
- Validation and concurrency logic is correct and tested.
- **One real gap found:** mutating registry routes (`put_default` in
  particular, and arguably `put_override`/`reset_override`/
  `create_snapshot` too, since they only check tenant *membership* via
  `assert_tenant_access`, not a `PROCUREMENT_ADMIN`-equivalent role) rely on
  the frontend route's `RequireCapability` gate rather than a server-side
  capability check in `rules_router.py` itself. Recommend fixing before
  this workstream is marked complete, per the master prompt's explicit
  "enforce authorization server-side" instruction.

This review does not mark the workstream `COMPLETE` — that decision is
Cursor's as integration owner, after the capability-check gap above is
addressed or explicitly accepted as a known risk by the owner.
