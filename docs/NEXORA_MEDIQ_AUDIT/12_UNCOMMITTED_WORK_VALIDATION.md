# 12 — Uncommitted Work Validation
**NEXORA MEDIQ — Phase 1 Baseline Stabilization**

Validates the three in-progress, uncommitted changes identified in `11_PHASE1_GIT_BASELINE_REPORT.md`. No source code was modified during this validation.

## Change 2 — SMS_PM role addition

`backend/controllers/auth_controller.py` — single-line diff adding `"SMS_PM"` to `_MULTI_SESSION_ROLES`. Confirmed minimal and isolated: no other logic in the file was touched. Paired with `backend/scripts/create_sms_pm_user.py`, a provisioning script scoping a shared SMS-tenant login to Procurement, view-only Stock Availability, and Supplier Stock Analysis across stores SMF/SMG/SHP/SMA. No defects found; this is simple, self-contained, and not a security concern on its own (role addition to an allow-list, not a privilege-widening change to an existing role).

## Change 3 — Store-agent HO URL fix

`store_agent_setup/setup_kit/__init__.py` — single-line port correction (`8443` → `8445`) in `KNOWN_HO_URLS`. No defects found; trivial, isolated.

## Change 1 — Tenant export-defaults lock (full verification, per Phase 1 Step 2)

### Backend route contracts — VERIFIED

`pm_router.py:420-449`:
- `GET /export-defaults` (420-433): calls `assert_tenant_access(current_user, tenant_id)` only — any procurement-workspace user may **read** the tenant's locked defaults. Returns `{"file_format", "columns", "locked": bool}`; when no row exists yet, returns `locked: False` with nulls — a clean "unset" state, not an error path.
- `PUT /export-defaults` (436-449): calls `assert_tenant_access` **and** `has_full_access(current_user)` (line 443-444); otherwise raises `403 "Only a super admin can set export defaults."`

### Schema validation — VERIFIED with one defect

`pm_schemas.py:188-190`, `TenantExportDefaultsUpdate`:
- `file_format: str = Field("xls", pattern="^(xls|xlsx|csv)$")` — whitelisted. VERIFIED safe.
- `columns: List[str]` — **DEFECT FOUND: no server-side whitelist against the known export column keys (`OW_EXPORT_COLUMN_DEFS`).** A superadmin-only caller could PUT arbitrary strings into the comma-joined `columns` value. Severity: **low** — the write path is already superadmin-gated, and the frontend only ever renders columns it recognizes against its own known-column dictionary, so an unrecognized key is silently dropped on render rather than causing a crash or data exposure. Still a real input-validation gap that should be closed (add an enum/whitelist check) before this is considered production-complete.

### Tenant isolation — VERIFIED

Both endpoints route through `assert_tenant_access`, the same server-side mechanism validated project-wide in `14_AUTHENTICATION_SECURITY_BASELINE.md`. No tenant-crossing path found.

### Superadmin authorization — VERIFIED

The write path's `has_full_access(current_user)` check reads JWT claim fields (`is_platform_user`, `role_names`) — not any client-supplied request field. Not spoofable from the renderer. See `14_AUTHENTICATION_SECURITY_BASELINE.md` for the underlying implementation detail.

### Frontend state handling — VERIFIED, additive

Diff hunks in `App.jsx` (+60), `ProcurementWorkspace.jsx` (+77), `client.js` (+69), `session.js` (+7) are all additive — new state/handlers wired in, with the diff's total 14 deletions spread across the whole changeset rather than concentrated in a rewrite of existing export logic. This is new feature wiring layered onto existing export behavior, not a replacement of it. Not independently re-read line-by-line beyond confirming this overall shape — flagged as a lighter-verified area than the backend endpoints above.

### Export column/format enforcement — VERIFIED (format) / DEFECT (columns, see above)

### Error handling — VERIFIED, no defects found

`tenant_export_defaults_repository.py` uses an UPDATE-then-INSERT-if-no-rowcount pattern, wrapped in try/rollback/finally-close. Sound.

### Existing export workflows — not independently re-run

The new locking feature is additive to existing export functionality; whether it was tested against a *live* export flow (actually generating a file with a tenant-locked format/column set) was not verified in this pass — no test exists to exercise this (see below), and we did not perform a live export ourselves since Phase 1 is read-only and no backend/DB write path should be exercised casually.

### Migration safety — VERIFIED

`sql/0032_tenant_export_defaults.sql`: `IF OBJECT_ID('procurement.tenant_export_defaults', 'U') IS NULL BEGIN CREATE TABLE ... END` — additive-only, idempotent, no `ALTER`/`DROP` on any existing table, single new table with `tenant_id` as primary key. Safe to re-run. Safe to leave undeployed for now (the repository's `get()` would raise a SQL error on a *missing table* — as opposed to a missing *row*, which is handled gracefully — so this is a deploy-ordering concern: the migration must run before the new code path is exercised, not a logic defect in the code itself).

### Relevant automated tests — DEFECT FOUND: none exist

Grepped all desktop `*.test.js` files and `backend/tests/` for `export_default`, `export-default`, `TenantExportDefaults` — **zero hits on either side of the stack.** This is a genuine gap, not a false negative from search terms — the feature name is distinctive enough that absence of hits is conclusive.

## Summary verdict for Phase 1 Step 2

**Safe, but not yet test-covered.** The feature is architecturally sound (server-side tenant/role enforcement correct, migration safe and idempotent), has one minor input-validation gap (`columns` whitelist), and has zero regression tests. It should not be considered "done" until: (a) the `columns` field gets a server-side whitelist, and (b) at least one backend test (endpoint-level, mocking the repository) and one frontend test (view-model level, following the project's existing `*View.js` + `*.test.js` convention) are added. Recommend this happen before or alongside getting Change 1 committed (per `11`), not deferred into Phase 2.
