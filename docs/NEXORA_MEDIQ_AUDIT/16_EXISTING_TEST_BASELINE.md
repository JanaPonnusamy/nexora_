# 16 — Existing Test Baseline
**NEXORA MEDIQ — Phase 1 Baseline Stabilization**

Per Part E boundaries: non-destructive tests only were run. No test requiring a live DB connection with mutation risk was executed.

## Desktop (Node) — EXECUTED

No `test` script exists in `desktop/supplier-stock-client/package.json` (only `dev`/`build`/`preview`/`start`/`dist`). Ran directly:

```
cd E:\Nexora\desktop\supplier-stock-client
node --test src/*.test.js src/state/*.test.js
```

**Result: 61 tests run, 61 pass, 0 fail, 0 skipped. Duration ~1362ms.**

Coverage observed across the 7 test files: quantity-check/summary logic, Order Workspace grid column/layout persistence, supplier assignment guards, GRN fact display, discount/offer calculations, quote-paste parsing, label matching, cross-store sync (the BRIV-family GREEN/BLUE state machine, built from real captured API responses per its own test comments), web-panel URL/site handling, and HO-login-shape validation (confirms no password field leaks into that shape).

**This is a genuine, currently-clean baseline.** Any Phase 2 refactor work should re-run this exact command before and after each extraction step and expect 61/61 to continue passing — a regression here is an immediate signal.

## Backend (pytest) — NOT EXECUTED, environment gap found

`backend/tests/` contains **37 test files** — a correction to Phase 0, which had only incidentally found 3 via an unrelated AI-keyword grep. Notably includes `test_procurement_store_trends.py` and 10 `test_legacy_order_*` files directly relevant to the actively-developed modules this project will touch.

**COULD NOT VERIFY — pytest is not installed in the project's environment.** `.venv38\Scripts\python.exe -m pytest` → `No module named pytest`. No other project-specific virtual environment was found; a system Python 3.12 exists on PATH but is not the project's environment, and installing pytest into either was not done in this phase (installing a package is a mutation to the environment, which Part E's non-destructive mandate counsels against doing unprompted).

**Backend tests were not run.** This is reported honestly as a gap, not papered over.

Separately, read-only inspection of the 37 test files found that at least 2 (`test_agent_ops_schema.py`, `test_legacy_order_store_access.py`) call `get_connection()` directly — a real live-database dependency with unknown mutation risk. These should be excluded from any future "run everything" pass, or run only against a disposable/test database, never against production — this applies even once pytest is installed.

## Honest summary (per the master prompt's explicit instruction not to overclaim)

- **Desktop test suite: executed, 61/61 passing.** This is a real, current, verified result.
- **Backend test suite: not executed.** 37 files exist; none were run; pytest needs to be installed in a proper project environment first, and 2 of the 37 need DB-isolation consideration before being included in any automated run.
- **This is not "existing automated tests pass"** in the complete sense the master prompt's §9 asks for — only the desktop half of that claim can currently be made with evidence.

## Recommended next action

Before Phase 2 begins: stand up a proper backend test environment (e.g. `pip install -r requirements.txt` plus `pytest` into a dedicated venv, or confirm which venv is actually meant to be used) so the 37 backend tests can actually be run and form a real baseline, not an inferred one. This is infrastructure work, not source-code modification, and is lower-risk to do before Phase 2 than to defer.
