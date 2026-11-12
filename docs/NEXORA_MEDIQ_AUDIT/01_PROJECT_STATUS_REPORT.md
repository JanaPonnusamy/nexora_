# 01 — Project Status Report
**NEXORA MEDIQ Unification — Phase 0 Audit**
Date: 2026-11-12 · Status: Phase 0 (read-only audit) · No source code modified

## Headline finding

The master prompt's premise is **"combine two separate Electron applications into one."** That premise does not match the current repository. There is only **one** Electron desktop app with Purchase-Manager and Supplier-Stock-Client functionality already living together in it:

- `E:\Nexora\desktop\supplier-stock-client` — single Electron shell, single `package.json` (`nexora-supplier-stock-client`, v0.1.71, productName **"Axythic Supplier Stock"**), single `src/` tree, 17 navigable screens including `ProcurementWorkspace.jsx`, `PmOrderEntry.jsx`, and `LegacyOrderGeneration.jsx` side-by-side with the original supplier-stock screens (`supplierCompare.jsx`, `harvestReview.jsx`, etc.).

There is a second desktop client in the repo, but it is not a Purchase Manager app and is not a merge candidate:

- `E:\Nexora\desktop\order-management-client` — a small native C# WinForms `.exe`, purpose-built as a **remote-access-only replica of one legacy screen** (the old VB `Form1` Order Management form), used by stores reaching HO over the internet rather than LAN. It never touches the database directly; it calls the same `/api/legacy-order/*` backend API. Per the project's own standing decision, the legacy Order Workspace this tool mirrors is **frozen** ("old OW FROZEN after final rule" — see `keep-legacy-order-workspace-unchanged` memory).

**Conclusion:** "unify two apps" has already happened at the code level. What remains to actually execute on is: (1) a product rebrand from "Axythic Supplier Stock" to "NEXORA MEDIQ" across window title, installer, and branding assets; (2) a UI/UX modernization pass over an already-functional but monolithic frontend; (3) an honest accounting of which proposed "AI Intelligence Centre" features are real vs. aspirational; (4) explicit exclusion of `order-management-client` from this effort.

This reframing does not reduce the scope of useful work — the UI modernization, AI honesty pass, and rebrand are all substantial — but it changes the shape of the project from "integration of two systems" to "rebrand + modernize + selectively extend one system."

## Current development status

| Area | Status |
|---|---|
| Electron shell (main/preload) | Stable, in production use across stores (`main.cjs`, `preload.cjs`, `webPanel.cjs`, `whatsapp.cjs`) |
| Frontend (React, no router, single `App.jsx`) | Functional, all 17 nav screens wired to real components — but `App.jsx` is ~15.8k lines and mixes Order Workspace + Procurement logic together (not cleanly modularized) |
| Backend (FastAPI, `backend/modules/procurement/pm_router.py` = 1193 lines) | Actively developed; most recent 15 commits touch `legacy-order`, `procurement-website` (supplier portal automation), `ordernmc-mirror`, `web-panel` |
| Auth/tenant model | Server-enforced (`assert_tenant_access`, `require_procurement_workspace`), not just UI gating — see `07_SECURITY_AND_TENANT_AUDIT.md` |
| AI features | **One** real LLM-backed feature exists (`shelf_sort_service.py`, Claude-based product-category classifier with honest `llm_available` degrade). Everything else labeled "AI" in the UI today is rule-based aggregation, not model-backed — see `03_COMPLETE_FEATURE_INVENTORY.md` §AI |
| Tests | 7 `node --test` view-model unit tests in the desktop app (`node --test`, no Jest/RTL/Playwright); a few unrelated backend test files (`test_device_controller.py`, etc.); none specific to procurement or auth found |
| Build/installer | NSIS installer via electron-builder, `asar: false`, bundles `NexoraDeviceController.exe`; 16 prior installer versions retained in `release/`, all branded "Axythic Supplier Stock" |
| Uncommitted work on `main` right now | `main` is **not** a clean snapshot — see below |

## Working-tree state at audit time (important caveat)

`git status` at the start of this audit showed 11 modified files and 3 new untracked files, forming one coherent in-flight feature unrelated to MEDIQ:

- **Tenant-wide desktop export lock** (superadmin can lock export file-format/columns per tenant for Procurement/Order Workspace exports): spans `backend/modules/procurement/pm_router.py` (+43 lines), `pm_schemas.py` (+7), new `tenant_export_defaults_repository.py` (53 lines), new migration `sql/0032_tenant_export_defaults.sql`, and matching frontend changes in `App.jsx` (+60), `ProcurementWorkspace.jsx` (+77), `client.js` (+69), `session.js` (+7), `styles.css` (+28).
- Two one-line, unrelated changes: `auth_controller.py` (adds `SMS_PM` to the multi-session-allowed role set) and `setup_kit/__init__.py`.
- `backend/scripts/create_sms_pm_user.py` — a new onboarding script for the SMS tenant, tied to the `auth_controller.py` change above.

**Implication for this audit and for any later implementation phase:** treat the current branch as a system under active, concurrent development, not a frozen baseline. The most recent 15 commits concentrate in `legacy-order`, `procurement-website`, and `ordernmc-mirror` — any MEDIQ implementation phase touching `App.jsx`, `ProcurementWorkspace.jsx`, or `pm_router.py` will be editing files that other in-flight work also touches, and should expect to rebase/merge against that churn rather than assume a quiet codebase.

## What could not be verified in this pass

- Exact runtime behavior of `/api/time-report`, `/api/rate-analysis`, `/api/nmw-sales-report` backend routers — inferred present from consistent naming convention and absence of broken-call symptoms in the frontend, not individually re-read line by line.
- Whether any backend test directory covers procurement/auth beyond the three unrelated test files found (`test_device_controller.py`, `test_remote_order_agent.py`, `test_nmv_enrollment.py`) — a dedicated listing of `backend/tests/` was not exhaustively enumerated.
- `order-management-client`'s HttpClient code was not read line-by-line; its "never touches the DB directly" claim is taken from its own README, not independently re-verified against `HoApiClient.cs`.

These are flagged explicitly rather than assumed in the documents that follow.
