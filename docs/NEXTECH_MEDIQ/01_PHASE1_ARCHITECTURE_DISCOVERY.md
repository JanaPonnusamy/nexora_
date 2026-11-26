# NexTech MediQ — Phase 1: Architecture Discovery

Status: **PHASE 1 COMPLETE.** Read-only investigation of both existing
Electron clients. No files created, modified, or deleted in either
existing client. No new project has been scaffolded yet — this report is
the discovery/proposal artifact for review before Phase 2 begins.

---

## 0. Repository/git state recorded before any work (per §8 of the brief)

```
Branch: nexora-mediq-implementation
```

- `desktop/supplier-stock-client/` — tracked, git history exists (latest:
  `ac92f01 feat(desktop): keep Stock Enquiry and Procurement as the single
  screens`). Working tree has **pre-existing uncommitted changes** from
  before this conversation (electron/main.cjs, index.html, package.json,
  App.jsx, ProcurementWorkspace.jsx, UserManagementScreen.jsx,
  procurementWorkspaceView.js/.test.js, state/session.js, styles.css,
  syncLive.css, theme.js — all modified; theme.test.js untracked/new).
  **None of these were touched by this investigation.**
- `desktop/quick-stock-client/` — **entirely untracked** (`git log` returns
  zero commits for this path). It is new, in-progress work by someone else,
  not yet committed. **Not touched by this investigation.**
- `desktop/order-management-client/` — exists as a third, separate legacy
  client (C# WinForms, per prior investigation context), out of scope for
  this discovery pass; noted only for completeness of the `desktop/` layout.

No clean/reset/stash was performed. Nothing was staged or committed.

---

## 1. supplier-stock-client — the real architectural reference

This is the mature, actively-developed app and the one worth learning from
in depth.

### Main process (`electron/main.cjs`, 333 lines)
- Single `BrowserWindow` (1366×768 design target).
- `contextIsolation: true`, `nodeIntegration: false`, **`sandbox: false`**
  (deliberately off, to support `webviewTag: true` for the Procurement "Web
  panel" supplier-portal iframes — isolation for those is handled
  separately in a `webPanel.cjs` module).
- IPC handlers: dev helpers, per-screen UI-session JSON persistence in
  `userData`, Excel/CSV export-to-disk + "reveal in Explorer", native
  folder picker, theme-preference bridge to Electron's `nativeTheme`,
  Device Controller enrollment (local Ed25519 keypair, POSTs to
  `/api/auth/device/register`).
- Auto-update is a deliberate no-op — updates are pushed by a separate
  SYSTEM-level watchdog/Device Controller service, not electron-updater's
  self-install path.
- No native menu bar (reclaims vertical space on a 1366×768 laptop target).
- Electron pinned at **22.3.27** for Windows 7/8 compatibility (per prior
  memory: default modern builds fail on Win7).

### Preload (`preload.cjs`, 62 lines)
Exposes `window.nexoraDesktop` via `contextBridge`: platform/version info,
a machine fingerprint (sha256 of hostname+platform+arch+username),
theme/viewport/session-file bridges, export-to-disk, a `whatsapp.*`
namespace (per-store local WhatsApp Web session), a `web.*` namespace
(webview partition/login management for supplier portals), and
`enrollController`.

### Build tooling
Vite + `electron-builder`. `appId: com.nexora.desktop.stock`.
**`productName` is already set to `"NexTech MediQ"`** in this app's
`package.json` — branding groundwork was already partially (and, per the
new architecture decision, now incorrectly-scoped) started inside this
existing client rather than in a separate new app. NSIS installer
(per-machine, choosable install dir, desktop+start-menu shortcuts). React
`latest` + `@tanstack/react-query` + `@tanstack/react-virtual`,
`xlsx-js-style` for exports. `asar: false`.

### Frontend architecture
**Not component-split in any meaningful sense**: `App.jsx` is **10,784
lines** and `styles.css` is **11,646 lines**, together acting as shell,
router, and most screen logic. It imports ~25 sibling files for specific
screens (`ProcurementWorkspace.jsx`, `DashboardScreen`,
`LegacyOrderGeneration.jsx`, `RateAnalysis.jsx`, `NonMovingStock.jsx`,
`SyncLive`, `TimeReport`, `UserManagementScreen.jsx`,
`RoleManagementScreen`, `SchemaSyncPage`, `PmOrderEntry`, etc.). Navigation
is a manual `screens` array (17 entries grouped into
`stock`/`purchase`/`reports`/`tools`/`system`) driving a custom
`ErpSidebar`/`NavMenu`/`ErpBreadcrumb` — **no router library**.

**This monolith is explicitly flagged as "do not copy wholesale."** Per
the brief's own instruction ("do not assume all existing screens can be
copied directly"), `App.jsx`'s shape is the clearest example of
architecture to learn from, not transplant.

### Theme system (`theme.js`, 25 lines)
Three preferences (`dark`/`light`/`system`), resolved via
`prefers-color-scheme`, applied as `data-theme`/`data-theme-preference`
attributes + `colorScheme` on `<html>`, bridged to Electron's native theme
via IPC. Small, clean, has its own test file (`theme.test.js`) — **this is
directly portable** to the new app with minimal adaptation.

### API client (`api/client.js`)
A `fetch` wrapper with retry-on-transient-status (408/425/429/502/503/504),
a two-tier timeout (fast 8s probe on retryable attempts, full budget on the
last try), Bearer-token auth header injection from session storage, and
FastAPI-aware error-detail extraction. Base URL from
`loadSettings().apiBaseUrl` (default `http://192.168.10.73:8000`,
overridable). **Directly portable pattern** — the new app should build an
equivalent client rather than reinvent retry/timeout semantics from zero.

### Session (`state/session.js`)
Plain `localStorage`, two keys: `nexora.desktop.settings` (API base URL,
tenant/store IDs, theme preference) and `nexora.desktop.session` (token,
invalidated daily via a `loginDate` check). No encryption, no OS keychain.

### Branding assets found
`src/assets/` currently holds: `axythic-logo-mark.png`,
`axythic-logo-white.svg`, `axythic-logo.jpg`, `axythic-logo.png`,
`axythic-logo.svg` (all **old Axythic brand**, predating NEXORA MEDIQ) and
one `nexora-mediq-mark.svg` (already in active use in `App.jsx`). **No
`.ico` file found** outside `node_modules`/`release` — electron-builder is
presumably falling back to a default/unconfigured icon for the actual
Windows executable today.

### Styling
Plain CSS, one giant stylesheet, no CSS modules/Tailwind/CSS-in-JS.

### Tests
Node's built-in `node:test`, ~9 files — mostly pure-function view-logic
tests (`procurementWorkspaceView.test.js`, `orderWorkspaceView.test.js`,
`rateAnalysisView.test.js`, `siteCheck.test.js`, `theme.test.js`) plus
`api/client.test.mjs`.

### Backend API surface called
Broad: `/api/auth`, `/api/legacy-order`, `/api/procurement`,
`/api/desktop-client`, `/api/bootstrap`, `/api/ho-routes`,
`/control-center`, and more — essentially the full backend surface a
unified app would eventually need.

---

## 2. quick-stock-client — NOT a code-reuse source, but a useful pattern reference

This app is architecturally unrelated to supplier-stock-client and
contributes no transplantable React/component code.

- **Total footprint**: one 83-line `electron/main.cjs` + `package.json`.
  No preload script, no `src/`, no renderer bundle, no build tooling of
  its own. The file's own comment states the design directly: *"the page
  IS the app."*
- **Main process**: single `BrowserWindow` (1200×800, min 760×560),
  `nodeIntegration: false`, `contextIsolation: true`, **`sandbox: true`**
  (tighter than supplier-stock-client, since there's no webview need), no
  menu, no IPC handlers at all.
- It `loadURL()`s a live backend-hosted page directly — `CANDIDATE_URLS`
  tries LAN HO (`192.168.10.73:8000`) first, then a public fallback
  (`122.252.246.181:8443`), with a `--ho=` CLI override for dev. A
  `probe()` function (2.5s timeout HEAD-equivalent check) picks the first
  reachable URL — **this LAN-first-with-public-fallback pattern is worth
  reusing** in the new app's backend-discovery logic, matching the
  established `store_agent`/HO-multi-URL convention already used
  elsewhere in this codebase.
- **Branding note**: `appId: com.nexora.desktop.quickstock`,
  **`productName: "NexTech Quick Stock"`** — confirms the "NexTech" brand
  name was already in informal use in this repo before this conversation's
  rebrand request, independently of supplier-stock-client's
  "NexTech MediQ" `productName`. Two different apps, two different
  "NexTech"-prefixed names, neither coordinated with the other.
- The actual Quick Stock UI lives entirely in `frontend/src/pages/quick-stock/*`,
  served by the backend as a normal web page and simply displayed in a
  chromeless window — no local renderer code exists to reference for
  component/theme/navigation design.
- **Maturity**: a working, already-packaged shell
  (`release/QuickStock-Setup-1.0.0.exe` exists) but not a "real" Electron
  app in the architectural sense relevant to this discovery.

---

## 3. Backend integration surface (for the new app to target)

Both existing clients ultimately talk to the same FastAPI backend. Route
prefixes observed in use across the two clients and the broader codebase
(from this and the earlier Phase 7C investigation):

- `/api/auth` — login, JWT, device enrollment
- `/api/legacy-order` — Order Workspace / order generation
- `/api/procurement` — Procurement Workspace, Cycle/Refresh, PM workspace
- `/api/quick-stock` — kiosk stock lookup (PIN-gated, no JWT)
- `/api/desktop-client`, `/api/bootstrap`, `/api/ho-routes` — desktop
  app bootstrapping, HO route discovery/failover
- `/control-center` — admin/ops surface

A new independent app should talk to these same existing, unmodified
routes. No backend change is implied or needed by this rebrand/discovery
phase, consistent with §6 of the brief ("Do not add direct database access
to the Electron renderer," "No production database changes are
authorized").

---

## 4. Duplicate functionality identified (authoritative-implementation question, not yet resolved)

| Capability | Where it exists today | Authoritative? |
|---|---|---|
| Stock lookup UI | `frontend/src/pages/quick-stock/*` (web, embedded via quick-stock-client's shell) AND conceptually overlaps with Stock Availability screens inside supplier-stock-client's `App.jsx` | **Not resolved in this pass** — quick-stock-client's version is a PIN-gated, no-login kiosk variant; supplier-stock-client's is full-auth. These likely serve different use cases (kiosk vs. logged-in operator) rather than being a true duplicate — flag for Phase 1 sign-off, not an assumption either way. |
| Theme preference system | supplier-stock-client's `theme.js` (dark/light/system, portable) vs. quick-stock-client (none — no theme system exists there at all) | supplier-stock-client's is authoritative; quick-stock-client has nothing to reconcile against. |
| Backend URL discovery/failover | supplier-stock-client's `api/client.js` (settings-based, user-configurable) vs. quick-stock-client's `CANDIDATE_URLS` probe (LAN-first, automatic) | **Neither is strictly superior** — quick-stock-client's automatic LAN/public failover is arguably better UX for a kiosk device with no settings UI; supplier-stock-client's user-configurable approach suits an operator workstation. The new app likely wants both: automatic probing with a settings override, per Phase 1 recommendation below. |
| Branding/productName | supplier-stock-client: `"NexTech MediQ"`; quick-stock-client: `"NexTech Quick Stock"` | **Neither should be treated as the new app's identity going forward** — per the corrected architecture, NexTech MediQ is a *third*, new app. These two existing `productName` values are now stale/incidental naming that predates this decision; they are not touched by this discovery (existing apps preserved unchanged per §2 of the brief), but the new app must mint its own distinct `appId`/`productName` rather than inherit either. |

---

## 5. Proposed new application structure (proposal only — nothing created)

```
desktop/
├── order-management-client/      (existing, untouched, out of scope)
├── quick-stock-client/           (existing, untouched — reference only)
├── supplier-stock-client/        (existing, untouched — primary reference)
└── nextech-mediq/                (NEW — to be created in Phase 2, pending sign-off)
    ├── electron/
    │   ├── main.cjs              (adapt supplier-stock-client's shape: BrowserWindow,
    │   │                          sandbox:false only if webview/portal support is
    │   │                          carried over, theme bridge, export-to-disk IPC)
    │   └── preload.cjs           (adapt contextBridge surface; drop whatsapp.*/web.*
    │                              namespaces unless/until those features are migrated)
    ├── src/
    │   ├── App.tsx                (shell + navigation only — explicitly NOT a
    │   │                           10k-line monolith; delegate to modules/)
    │   ├── theme/                 (ported from supplier-stock-client/src/theme.js,
    │   │                           dark default per §5 of the brief)
    │   ├── services/
    │   │   └── apiClient.ts       (ported retry/timeout/auth pattern from
    │   │                          supplier-stock-client/src/api/client.js)
    │   ├── state/
    │   │   └── session.ts         (ported from state/session.js)
    │   └── modules/                (one folder per functional area, populated
    │                               incrementally in Phase 4 — Supplier Stock,
    │                               Quick Stock, Procurement, Stock Intelligence)
    ├── assets/
    │   └── branding/              (new NexTech MediQ logo/icon/banner —
    │                               NOT the old Axythic or nexora-mediq-mark files,
    │                               which stay where they are inside
    │                               supplier-stock-client)
    ├── shared/                     (design tokens, shared UI components — new,
    │                               built from scratch per the brief's "do not
    │                               assume screens can be copied directly")
    ├── package.json                (new appId, e.g. com.nexora.desktop.nextech-mediq;
    │                               productName "NexTech MediQ" minted fresh here,
    │                               not inherited from supplier-stock-client's
    │                               current config)
    └── documentation/
```

This mirrors the brief's own proposed layout, adjusted for what actually
exists on disk today (no top-level `nextech-mediq/` outside `desktop/` —
keeping the new app as a sibling inside `desktop/`, matching the existing
three-client pattern, per your Phase 1 placement decision).

## 6. What Phase 1 recommends carrying forward vs. rebuilding

**Carry forward (pattern, not code import)**:
- supplier-stock-client's main/preload/IPC shape, theme system, and API
  client retry/timeout logic — proven, small, portable.
- quick-stock-client's LAN-first/public-fallback URL probing — proven,
  useful for a kiosk-adjacent discovery flow, complementary to (not a
  replacement for) supplier-stock-client's settings-based override.
- The window/webPreferences security posture from both
  (`contextIsolation: true`, `nodeIntegration: false`) as a hard floor.

**Rebuild from scratch, not copy**:
- `App.jsx`'s 10,784-line monolith shell/router/screen-logic structure —
  explicitly flagged by the brief as not to be assumed copyable; the new
  app should have a real component tree and (if desired) an actual router
  library instead of a manual `screens` array driving conditional renders.
- Branding assets — new NexTech MediQ logo/icon/banner, not the old
  Axythic files or the `nexora-mediq-mark.svg` currently embedded inside
  supplier-stock-client.
- `appId`/`productName` — minted fresh for the new app; not inherited from
  either existing client's current (now-stale, per §4 above) values.

## 7. Open items for owner sign-off before Phase 2

1. Confirm the stock-lookup-UI question in §4 is intentionally two
   different use cases (kiosk vs. operator), not a duplicate to
   deduplicate.
2. Confirm `appId`/`productName` for the new app (proposed:
   `com.nexora.desktop.nextech-mediq` / `"NexTech MediQ"` — noting this
   reuses the string already sitting, unused-as-intended, in
   supplier-stock-client's config; worth deciding whether to leave that
   stale reference in place there or clean it up as a separate, explicitly
   authorized small change to the existing app, since the brief forbids
   this discovery phase from touching existing apps).
3. Confirm Electron version target — supplier-stock-client pins 22.3.27
   for Windows 7/8 support (per existing memory on build constraints); the
   new app should state explicitly whether it inherits that same OS
   support floor or can target a newer Electron given different hardware
   assumptions.
4. Confirm whether the new app's first integrated module (per Phase 4) is
   Supplier Stock, Quick Stock, or a new Dashboard shell first — this
   discovery does not sequence Phase 4, only inventories what exists.

---

**This concludes the authorized Phase 1 scope.** No project files for
`desktop/nextech-mediq/` have been created. Both existing applications
(`supplier-stock-client`, `quick-stock-client`) remain exactly as they were
at the start of this investigation — confirmed via `git status`/`git log`
before and no modifying tool calls issued against either path during this
investigation.
