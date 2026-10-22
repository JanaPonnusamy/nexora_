# 11 — Phased implementation plan

Operational status lives in `AUTONOMOUS_WORK_CONTROL.md`, not in this audit plan.
Master-prompt Phase 0 is complete. The Procurement Rules Registry is a separate workstream in that control file. This document stays the original phase list.

## Phase 0 — Lock the formula with fixtures

- **Scope:** Tests T-01 through T-08 and T-12 as pure functions. No API.
- **Reuse:** `decision_rules.evaluate` as the oracle for current Nexora, not as the target.
- **New:** a test-only transcription of the agreed formula.
- **DB:** none.
- **UI:** none.
- **Acceptance:** the two rulebook examples match the agreed column and do not match VB or Nexora where the matrix says they differ.
- **Rollback:** delete tests.
- **Gate:** owner accepts the rulebook numbers.

## Phase 1 — Read models for the three modes

- **Scope:** Read-only endpoints that return Qty Check rows, purchase-history rows, and supplier-stock rows for one store. Same filters as `LoadQtyCheckData`, `LoadDataForSupplier`, `LoadDataForSupplierStock`.
- **Reuse:** legacy repository queries where they already match those SQL shapes.
- **DB:** none.
- **UI:** none.
- **Acceptance:** row counts for one store match the VB grid for each mode on a read-only check. If the database cannot be read, this phase stays blocked.
- **Gate:** sample store sign-off.

## Phase 2 — Isolated Electron shell

- **Scope:** New screen, feature flag off by default. Header, mode combo, grid, collapsed drawer. No save.
- **Reuse:** purchase-manager CSS, Stock Client session.
- **UI:** 1280×640 usable. Old Order Workspace still opens.
- **Acceptance:** store switch clears rows; flag off leaves current users on the old screen.
- **Gate:** layout review at 1366×768.

## Phase 3 — Auto-save and keys

- **Depends:** Phase 2 and C-27/C-30 contract.
- **Scope:** final qty save, focus, Delete filter gate, Esc = zero.
- **Tests:** T-25, T-26.
- **Rollback:** flag off.
- **Gate:** keyboard script on Qty Check.

## Phase 4 — Assignment, cost, suggestion box

- **Depends:** Phase 3, T-14–T-17.
- **Scope:** manual assign; Auto Assign Remaining only on Auto Purchase Update; stock mode uses stock eligibility; cost warning; mapping suggestions.
- **Reuse:** `assignment_service`, `product_mapping`.
- **Gate:** manual supplier is never overwritten by a test run.

## Phase 5 — Export templates

- **Depends:** decision on store-level and system-default tiers (settings table is store+supplier only today).
- **Scope:** Excel from the precedence chain. Re-export writes a second file record and does not call the portal.
- **Tests:** T-18, T-19.
- **Gate:** one supplier file compared to the current Excel.

## Phase 6 — Portal worker

- **Depends:** Phase 5 batch id.
- **Scope:** Playwright PharmaRack adapter in a worker. Headed. No `main.py` import. Unknown stock blocks submit.
- **Tests:** T-20, T-21 against a stub page, not the live site.
- **Rollback:** button hidden; OrderBot still runnable by hand.
- **Gate:** one supervised order on a test distributor, outside this audit.

## Phase 7 — Pending, Not Supplied, close

- **Depends:** schema approval if current columns cannot store the decision.
- **Scope:** pending view, bulk confirm, release, close summary.
- **Tests:** T-09, T-10, T-29.
- **Gate:** PM bulk action on a copy of one order.

## Phase 8 — Roles and parallel run

- **Depends:** Role 1/2 meaning confirmed.
- **Scope:** Admin start/close, PM submit, reopen before the next fresh order.
- **Tests:** T-22, T-23.
- **Cutover:** only after one store’s Profile T quantities are accepted beside the VB screen. VB Form1 stays installed.

Dependency order is 0 → 1 → 2 → 3 → 4 → 5 → 6 and 7. Phase 6 and 7 can swap only if portal placement is not required for the first store.
