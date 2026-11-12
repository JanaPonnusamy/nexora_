# 02 — Application Architecture
**NEXORA MEDIQ Unification — Phase 0 Audit**

Scope: `E:\Nexora\desktop\supplier-stock-client` (the actual target app) and, briefly, `E:\Nexora\desktop\order-management-client` (out-of-scope legacy tool, documented for completeness).

## 2.1 Electron process model

Location: `desktop/supplier-stock-client/electron/`
- `main.cjs` (333 lines) — single `BrowserWindow`, fixed `1366×768` content size, `minWidth:1024 / minHeight:700`, native application menu removed (`Menu.setApplicationMenu(null)`) — a kiosk-style single-purpose desktop app, not a general-purpose multi-window shell.
- `preload.cjs` (62 lines)
- `webPanel.cjs` (257 lines) — manages the `<webview>` tag used only by the Procurement "Web panel" (supplier portal browsing)
- `whatsapp.cjs` (651 lines) — store-level WhatsApp session management (headless browser automation per prior project memory)
- `enrollmentGuard.cjs` (11 lines) — Device Controller enrollment check

**Security posture (main.cjs:242-244):**
- `contextIsolation: true`
- `nodeIntegration: false`
- `sandbox: false`
- `webviewTag: true` — enabled only because Procurement's supplier-portal feature needs it; every `<webview>` instance is independently locked down in `webPanel.attach()` (no preload, no Node integration, sandboxed, http/https only — per in-code comment at main.cjs:246).

**Preload surface** (`contextBridge.exposeInMainWorld('nexoraDesktop', …)`): platform/machine/fingerprint info, dev-viewport helpers, theme-set, session-state file read/write (UI state only, JSON file in `userData`), export file write/open/choose-folder (restricted to `.xls/.xlsx/.csv` + directories, main.cjs:184-203), store-WhatsApp controls, Web-panel login/partition/bookmark helpers, Device Controller enrollment calls.

**No direct database or arbitrary filesystem access is exposed to the renderer.** No `mssql`/`odbc`/raw-SQL requires exist in `main.cjs` or `preload.cjs`. All business data flows through HTTP calls to the FastAPI backend from the renderer's `src/api/client.js`.

**Page loading:** dev mode probes `127.0.0.1:5173` (Vite dev server) and falls back to the built `dist/index.html` if unreachable; production always loads `dist/index.html` via `loadFile` (main.cjs:272-294). No React Router — `App.jsx` holds `activeScreen` state and switches rendering directly across the 17 screens.

**Auto-update:** `electron-updater` is a dependency but its self-update code path is **explicitly a no-op** in `main.cjs` (lines 297-309, with a comment explaining why). Update delivery is owned by a separate SYSTEM-level service, `NexoraStockClientWatchdog`, which polls HO, verifies a signed package (SHA-256 + Ed25519), and performs install/rollback out-of-process. The `electron-builder` publish-feed URL in `package.json` (`http://192.168.10.80:8000/updates`) is therefore **vestigial config, not an active update path** — do not assume changing it affects real update behavior.

## 2.2 Frontend structure

- React (no React Router). Single top-level `App.jsx` (~15.8k lines) owns navigation state, most of Order Workspace logic, and wiring for Procurement — i.e., Order Workspace and Procurement are **not cleanly module-separated in the frontend today**; `OW_EXPORT_COLUMN_DEFS` and other Order-Workspace-specific constants live directly in `App.jsx` rather than in `ProcurementWorkspace.jsx` or a dedicated module.
- `src/navMenu.jsx` — purely presentational; groups the 17 screens into 5 menubar dropdowns (`stock / purchase / reports / tools / system`) per a `NAV_GROUPS` map.
- `src/api/client.js` (1743 lines) — single `api` object, ~80+ methods, one `request()` wrapper, calling named `/api/...` backend paths. This is the single point of backend coupling for the whole renderer.
- `src/state/session.js` (77 lines) — `localStorage`-backed settings (API base URL, tenant/store IDs, theme) and session payload, keyed `nexora.desktop.settings` / `nexora.desktop.session`. Session auto-expires same-day.
- `src/theme.js`, `src/styles.css` — theme/styling; see `06_UI_UX_REDESIGN_PLAN.md` for design-system assessment.
- View-model modules kept separate from their `.jsx` screens for testability: `nonMovingView.js`, `orderWorkspaceView.js`, `procurementWorkspaceView.js`, `rateAnalysisView.js`, `siteCheck.js`, `webPanelView.js` — each paired with a `*.test.js`. This is a genuinely good existing pattern worth **preserving and extending**, not replacing, in any redesign (see `09_IMPLEMENTATION_PHASE_PLAN.md`).

## 2.3 Backend architecture

- FastAPI. Controllers under `backend/controllers/`, feature modules under `backend/modules/<name>/`.
- Procurement is the largest and most actively developed module: `backend/modules/procurement/pm_router.py` (1193 lines) backs supplier queue/assignment, GRN submission, pending-order adjustment, abnormal-sales review, the shelf-sort AI classifier, and (as of this audit, uncommitted) tenant export-defaults locking.
- Every procurement endpoint sampled uses `Depends(require_procurement_workspace)` then explicitly calls `assert_tenant_access(current_user, tenant_id)` — server-side enforcement, not just a UI-layer check. See `07_SECURITY_AND_TENANT_AUDIT.md`.
- Auth: `backend/controllers/auth_controller.py` (254 lines) — JWT-based, with a `_MULTI_SESSION_ROLES` allow-list and a `_SESSION_LEASE_MINUTES` heartbeat-lease pattern.
- SQL Server access happens only from the backend (never from the Electron renderer or main process) — confirmed by absence of any DB client library in the desktop app's dependencies or code.

## 2.4 order-management-client (documented, out of scope)

- Native C# WinForms, compiled directly via `csc.exe` (.NET Framework, no SDK/Visual Studio required) via `build.ps1` — a completely separate build pipeline from the Electron app, producing a single `NexoraOrderManagement.exe`.
- UI is a deliberate pixel-faithful replica of the legacy VB `Form1` (literal coordinates copied from `Form1.Designer.vb`), with every HO-only control (Sync/Pull/Mapping/Web Export/Import Stock/Split Excel) deliberately stripped — it exposes a single Export button. Purpose: let a store reach the legacy Order Management screen over the internet (outside the LAN) without exposing the full HO tool.
- Talks only to `/api/legacy-order/*` over HTTPS; per its own README it never opens a direct database connection (this claim was not independently re-verified against `HoApiClient.cs` line-by-line in this audit — see `01_PROJECT_STATUS_REPORT.md` "could not verify" section).
- **No shared UI, build pipeline, or branding surface with `supplier-stock-client` today.** Its only connection to the rest of the system is hitting the same backend API. Recommendation carried into `04_MODULE_INTEGRATION_MATRIX.md` and `09_IMPLEMENTATION_PHASE_PLAN.md`: leave this untouched.
