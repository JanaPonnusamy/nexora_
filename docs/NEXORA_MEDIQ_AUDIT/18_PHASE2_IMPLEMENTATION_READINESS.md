# 18 — Phase 2 Implementation Readiness
**NEXORA MEDIQ — Phase 1 Baseline Stabilization — Executive Summary**

## 1. Executive summary

Phase 1 re-verified the Phase 0 audit at implementation depth and found the overall picture holds, with several corrections that make the project *more* tractable than Phase 0 suggested, plus a few concrete gaps to close before Phase 2 structural refactoring begins.

## 2. Git working-tree state

Unchanged since Phase 0: 11 modified + 3 untracked files, 343 insertions / 14 deletions. **Correction:** this is not one coherent feature — it's three unrelated, independently self-contained changes (tenant export-defaults lock; SMS_PM role onboarding; a store-agent HO URL fix) plus one non-code log diff. Nothing was stashed, reset, or discarded. Full detail: `11_PHASE1_GIT_BASELINE_REPORT.md`.

## 3. Is the tenant export-defaults feature safe and testable?

**Safe: yes, with one minor fix needed. Testable: not yet — zero tests exist today.**
- Server-side tenant isolation and superadmin gating are both genuinely enforced (JWT-claim-based, not client-trusted).
- Migration is additive-only and idempotent.
- One real defect: the `columns` field has no server-side whitelist (low severity — superadmin-only write path, frontend already ignores unrecognized keys on render).
- Zero backend or frontend tests cover this feature. Recommended test list provided in `13_TENANT_EXPORT_FEATURE_TEST_REPORT.md`.
Full detail: `12_UNCOMMITTED_WORK_VALIDATION.md`, `13_TENANT_EXPORT_FEATURE_TEST_REPORT.md`.

## 4. Test results

- **Desktop:** executed, **61/61 passing** (`node --test`, ~1.4s). Clean, current, real baseline.
- **Backend:** **not executed** — pytest is not installed in the project's environment (`.venv38` lacks it; no other project venv found). 37 backend test files exist (correcting Phase 0's incidental finding of only 3); 2 of them touch a live DB connection directly and need isolation consideration before ever being run in an automated pass.
Full detail: `16_EXISTING_TEST_BASELINE.md`.

## 5. Watchdog rebranding dependencies

**Correction to Phase 0:** the Watchdog's source is in this repository (`store_agent_setup/stock_client_watchdog_service.py`), not an external unknown. Its filename-pattern matching (`Axythic-Supplier-Stock-Setup-*.exe`) is a hard, mechanical dependency — changing the installer artifact-name template without updating the Watchdog's glob pattern in lockstep will break fleet update/rollback. A full, concrete list of every identifier needing synchronized change (appId, productName, artifactName template, window title, in-app copy, Watchdog state-dir path, Watchdog filename glob, logo asset) is now documented. One open item remains: how the Watchdog service itself gets updated on store PCs was not traced.
Full detail: `15_WATCHDOG_REBRANDING_DEPENDENCY_MAP.md`.

## 6. Order Workspace extraction plan

**Correction to Phase 0:** `OrderWorkspace` is already a single, named, top-level component (lines 4040–5978 of `App.jsx`), with a well-bounded ~1,540-line helper cluster (5995–7535) and a small shared-with-Procurement control cluster (3578–4039) that must go to a new shared module rather than either workspace exclusively. An existing `orderWorkspaceView.js` view-model file already follows the right pattern and should be grown, not replaced. A 4-step sequencing plan is proposed, re-running the 61-test desktop suite after each step.
Full detail: `17_ORDER_WORKSPACE_EXTRACTION_MAP.md`.

## 7. Outstanding risks

1. Backend test suite cannot currently be run — needs a working pytest environment before Phase 2 relies on backend regression coverage.
2. Export-defaults feature has zero tests — should get at least minimal coverage before or during Phase 2, since Phase 2 will touch two of the files it's wired into (`App.jsx`, `ProcurementWorkspace.jsx`).
3. Export-defaults `columns` field lacks a server-side whitelist — low severity, but worth a one-line fix before calling this feature production-complete.
4. The three unrelated uncommitted changes currently sit together in the working tree — recommend committing them separately before Phase 2 starts touching the same files, to avoid a future diff conflating unrelated changes.
5. Watchdog's own update/deployment mechanism on store PCs is untraced — needed before Phase 3 (rebranding) can execute safely, not needed to start Phase 2.
6. Legacy Order backend (`legacy_order/*`) is the most actively committed module and is also what Order Workspace's extraction depends on — Phase 2 sequencing should expect to rebase against ongoing churn there.

## 8. GO / NO-GO recommendation for Phase 2

**GO, with two preconditions:**
1. Commit (or otherwise formally separate) the three unrelated in-progress changes currently mixed in the working tree, so Phase 2's own diffs stay clean and attributable.
2. Stand up a working backend test environment (install pytest into a proper project venv) so the 37 existing backend tests can actually run as a baseline before Phase 2 touches `pm_router.py`-adjacent code.

Neither precondition blocks *starting* Phase 2 planning, but both should be resolved before Phase 2's first code change lands. The Order Workspace extraction itself (`17`) is well-scoped and lower-risk than Phase 0 estimated — recommend it proceed using the 4-step sequence with the 61-test desktop suite as the regression gate at each step.

**STOP — awaiting explicit owner authorization for Phase 2, per Part F.**
