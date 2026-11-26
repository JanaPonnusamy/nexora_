# 11 — Phase 1 Git Baseline Report
**NEXORA MEDIQ — Phase 1 Baseline Stabilization**
Date: 2026-11-12 · Read-only verification · No working-tree changes made

## Current state

- Branch: `main`
- `git status --short`: 11 modified files + 3 untracked files — **identical to the Phase 0 audit's snapshot**, plus the Phase 0 audit's own output (`docs/NEXORA_MEDIQ_AUDIT/`) now untracked. No drift, nothing lost, nothing force-reset.
- `git diff --stat`: 11 files changed, 343 insertions, 14 deletions.

**No destructive git operation was run.** No reset, stash, commit, push, or discard occurred during this phase.

## Correction to Phase 0: this is not one feature, it's three unrelated changes plus a log

The Phase 0 audit described the working tree as "one coherent in-flight feature." On full re-inspection, it is **three independent changes bundled together incidentally**, plus one non-code diff:

### Change 1 — Tenant export-defaults lock (the real target of Step 2 validation)
- `backend/modules/procurement/pm_router.py` (+43)
- `backend/modules/procurement/pm_schemas.py` (+7)
- `backend/modules/procurement/tenant_export_defaults_repository.py` (new, 53 lines)
- `backend/modules/procurement/sql/0032_tenant_export_defaults.sql` (new)
- `desktop/supplier-stock-client/src/App.jsx` (+60)
- `desktop/supplier-stock-client/src/ProcurementWorkspace.jsx` (+77)
- `desktop/supplier-stock-client/src/api/client.js` (+69)
- `desktop/supplier-stock-client/src/state/session.js` (+7)
- `desktop/supplier-stock-client/src/styles.css` (+28)
- `desktop/supplier-stock-client/package.json` (+2/-2, minor — not independently re-diffed for content beyond size)

Purpose: let a superadmin lock the desktop export file-format/columns per tenant for Procurement/Order Workspace exports.

### Change 2 — SMS_PM restricted-role onboarding (separate, unrelated to Change 1)
- `backend/controllers/auth_controller.py` — one line: `_MULTI_SESSION_ROLES = {"STOCK_VIEWER"}` → `{"STOCK_VIEWER", "SMS_PM"}`
- `backend/scripts/create_sms_pm_user.py` (new) — provisions a scoped "SMS" shared login limited to Procurement + Stock Availability (view-only) + Supplier Stock Analysis, across tenant SMS's 4 stores (SMF/SMG/SHP/SMA).

These two belong together; they are unrelated to the export-defaults work. Consistent with the user's own standing project context ("SMS SMA+SHP onboarding").

### Change 3 — Store-agent HO URL fix (standalone, unrelated to both above)
- `store_agent_setup/setup_kit/__init__.py` — one line: `KNOWN_HO_URLS` entry "Main HO - internet" port corrected `8443` → `8445`. Consistent with standing project memory on the dev public port.

### Not a code change
- `backend/storage/whatsapp/send_log.json` — pure runtime log growth (5 new WhatsApp send-attempt records dated 2026-11-10). Zero logic diff; irrelevant to any of the above.

## Assessment

None of these four items are destructive, abandoned, or half-finished — each is a complete, self-contained, intentional unit of in-progress work. **Nothing was stashed, discarded, or overwritten.** Recommendation: before Phase 2 structural refactor work touches `App.jsx`/`ProcurementWorkspace.jsx`/`client.js`/`session.js`/`pm_router.py`, get Change 1 (export-defaults) committed on its own, and Change 2/3 committed separately — they have no business being in the same commit, and leaving them mixed in the working tree increases the chance that a later refactor accidentally conflates unrelated changes in its diff.

## Explicitly not done (per Part E boundaries)

No reset, no checkout-to-discard, no stash, no commit, no push, no force operation of any kind was performed in this phase.
