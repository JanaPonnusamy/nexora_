# 19 — Phase 3 Backend Test Environment and Baseline
**NEXORA MEDIQ — Phase 3**
Date: 2026-11-12

## Environment

No new venv was created. `backend/.venv` (Python 3.12.10) already exists and already has every dependency `backend/requirements-dev.txt` lists, including **pytest 9.1.1**. This corrects Phase 1's finding that pytest was unavailable — Phase 1 checked `.venv38` (Python 3.8.10, a different, older venv at the repo root) and did not find `backend/.venv`. No installation was needed; nothing was installed into any system Python.

## Full suite run — before any fix

```
cd E:\Nexora\backend
.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```
**Result: 403 passed, 3 failed**, out of 406 tests, 15.2s.

All 3 failures were in the Legacy Order module's `start_order_process` threading tests (`test_legacy_order_nmv_seam.py` ×2, `test_legacy_order_restore_and_review.py` ×1), all with the identical failure shape: `assert t.target is service._run_agent_sync_then_order` failing because `t.target` was actually `tenant_scoped.<locals>._run` — a wrapper closure, not the raw function.

## Root-cause investigation — pre-existing, not introduced by this project

Traced `tenant_scoped` (`backend/modules/legacy_order/database.py:89-103`) back through `git log`: it was introduced in commit `ba66e20` ("per-tenant Legacy Order database setting"), well before the current `main` HEAD (`90bd0bed...`) and entirely unrelated to any of the 5 commits made in Phase 2 of this effort. `service.py`'s `start_order_process` has been wrapping its thread targets with `database.tenant_scoped(store, _run_agent_sync_then_order)` (and the `_run_sync_then_order` equivalent) for some time — the wrapper exists specifically so tenant context (a `contextvars` value) survives the handoff across a raw `threading.Thread` boundary, which `contextvars` do not cross automatically (documented in the function's own docstring). **The 3 failing tests simply never got updated when this wrapping pattern was adopted — this is a genuine pre-existing test/implementation drift inherited from `main`, not something this project caused.**

## Fix applied

Per the master prompt's explicit instruction not to make unrelated source changes to fix pre-existing failures, **no production code was touched** (`database.py` and `service.py` are both untouched). Only the 3 test assertions were corrected to unwrap the `tenant_scoped` closure (via `__code__.co_freevars`/`__closure__`, generically, not by hardcoding internals) before comparing against the real underlying function — proving the tests still verify the correct worker function is scheduled, not weakening what they check:
- `backend/tests/test_legacy_order_nmv_seam.py` — added `_unwrap_tenant_scoped()` helper, fixed 2 assertions.
- `backend/tests/test_legacy_order_restore_and_review.py` — added the same helper locally (file had its own independent `FakeThread`/`thread_spy`), fixed 1 assertion.

## Full suite run — after fix

```
.venv/Scripts/python.exe -m pytest tests/ --tb=short
```
**Result: 406 passed, 0 failed, 21 warnings (pre-existing deprecation warnings, unrelated — `datetime.utcnow()` and FastAPI `on_event`), 4.75s.**

## New tests added (Phase 3, Section 5 items 7-8)

`backend/tests/test_procurement_export_defaults.py` (new, 9 tests) — covers the tenant export-defaults feature flagged as untested in `12_UNCOMMITTED_WORK_VALIDATION.md`/`13_TENANT_EXPORT_FEATURE_TEST_REPORT.md`:
- `GET /export-defaults` with no row → unlocked response
- `GET /export-defaults` with a row → locked response
- `PUT /export-defaults` rejected for non-superadmin (403, repository never touched)
- `PUT /export-defaults` succeeds for superadmin, repository called with correct arguments
- `PUT /export-defaults` rejects a tenant-mismatched caller (403, via `assert_tenant_access`)
- `file_format` schema whitelist (valid/invalid values)
- **`columns` schema whitelist (new, see fix below)**

Tests call the router functions directly (matching this project's existing convention in `test_procurement_store_trends.py`) with `monkeypatch` substituting `assert_tenant_access`/`has_full_access`/the repository — exercising the real authorization code paths, not a mock of the authorization logic itself.

## Defect fixed: `columns` field had no server-side whitelist

Doc `12` flagged this as a low-severity gap. Fixed in `backend/modules/procurement/pm_schemas.py`: added `_VALID_EXPORT_COLUMNS` (mirroring the desktop app's `OW_EXPORT_COLUMN_DEFS` key set — `productCode, productName, orderQty, saleUnit, mrp, discount, category, subLocation, rack, supplierProductCode, supplierProductName`) and a `field_validator` on `TenantExportDefaultsUpdate.columns` rejecting any unrecognized key. Two new tests confirm both the rejection and the accept-path. This is a validation-tightening fix to a flagged gap in in-progress, uncommitted-at-the-time code — not a change to any established business rule.

## Migration test — explicitly not run, infrastructure unavailable

`sql/0032_tenant_export_defaults.sql` is genuine T-SQL (`OBJECT_ID`, `UNIQUEIDENTIFIER`, `GETDATE()`, `GO` batch syntax) targeting SQL Server. `backend/config/database.py` has exactly one configured database target (`DB_SERVER` defaulting to `192.168.10.73`) — the live HO production server — with no separate test/dev database declared anywhere in the backend configuration. **No isolated test database exists to run this migration against**, and running it against `.73` would be a production database write, explicitly out of bounds per the master prompt's Section 16 boundaries regardless of autonomy level. This is documented here as required infrastructure that is genuinely unavailable, not skipped by choice. The migration's safety was instead verified by static read (idempotent `IF OBJECT_ID(...) IS NULL`, additive-only, no `ALTER`/`DROP`) in `12_UNCOMMITTED_WORK_VALIDATION.md`.

## Desktop suite — re-confirmed unaffected

```
cd E:\Nexora\desktop\supplier-stock-client
node --test src/*.test.js src/state/*.test.js
```
**61/61 passing**, unchanged from the Phase 1 baseline.

## Summary

| Item | Result |
|---|---|
| Backend test environment | Already existed (`backend/.venv`), no installation needed |
| Full backend suite, before fix | 403/406 passed |
| Pre-existing failures identified | 3, all in Legacy Order threading tests, root-caused to pre-existing test/implementation drift unrelated to this project |
| Pre-existing failures fixed | 3/3, test-only changes, zero production code touched |
| Full backend suite, after fix | **406/406 passed** |
| New export-defaults tests added | 9, all passing |
| Export-defaults `columns` whitelist defect | Fixed, with test coverage |
| Migration tested against isolated DB | Not run — no test/dev database infrastructure exists; documented, not production-risked |
| Desktop suite | 61/61 passed, unchanged |
| **Combined backend + desktop baseline** | **415 backend + 61 desktop = 476/476 passing** |

## GO / NO-GO for Phase 4

**GO.** Both test suites are clean, the one real defect found in the uncommitted export-defaults feature is fixed and covered, and the pre-existing Legacy Order test drift is resolved without touching production logic. Phase 4 (Order Workspace structural refactor) can proceed using this 476-test baseline as its regression gate.
