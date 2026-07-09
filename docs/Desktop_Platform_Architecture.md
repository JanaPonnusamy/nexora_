# UniNex Desktop Platform — Architecture Reference

Status: Frozen (Phase 2.5). Future desktop work adds modules on top of this; it does not change the platform itself unless a defect is found.

## 1. What this is

A reusable Electron-wrapped shell that every future desktop module (Purchase Manager, Inventory, Sales, Supplier Management, Administration, Dashboard, ...) is hosted in, sitting on top of the existing, unchanged FastAPI backend. It reuses the same React/Vite/Bootstrap frontend the browser deployment uses — Electron is an additional client, not a replacement; the browser-tab SPA keeps working unmodified.

```
frontend/
  electron/                  Electron main process + preload (Node context)
    main.ts
    preload.ts
  src/
    platform/                 The reusable framework — everything on this page
      modules/                 ModuleRegistry, ModuleLifecycleController, ModuleHost, ModuleDefinition types
      shell/                   PlatformShell (composes everything below)
      ribbon/                  Ribbon
      navigation/              NavigationRail
      workspace/               WorkspaceTabs, WorkspaceHost, DockGroup/DockPanelItem/DockSeparator
      statusbar/                PlatformStatusBar
      events/                  EventBus
      logging/                 Logger
      errors/                  ErrorService, ErrorBoundary, GlobalErrorDialog
      session/                 SessionContext (tenant/store/acting-user)
      keyboard/                KeyboardManager
      layout/                  LayoutPersistence (generic localStorage save/load)
      services/                Platform Services barrel (Dialog/Settings/Clipboard + re-exports)
      ui/                      Shared component library (UniGrid, UniNotification, ...)
    pages/PlatformShellPreviewPage.tsx   mounts PlatformShell at /platform-shell-preview
```

Nothing under `platform/` references a specific business module. The deliberate exceptions are the `*.module.ts` files — `reports.module.ts` (Phase 2.4 proof-of-concept) and `purchase-manager.module.ts` (Phase 3 MVD) — plus `registerModules.ts`, which is where real modules get added. Both wrap their existing page component completely unmodified; the same components still serve their original `/reports` and `/procurement/workspace` browser routes identically.

## 2. Module lifecycle

Every module implements a subset of:

```ts
interface ModuleLifecycle {
  initialize?(ctx: ModuleContext): void | Promise<void>
  load?(ctx: ModuleContext): void | Promise<void>
  activate?(ctx: ModuleContext): void | Promise<void>
  deactivate?(ctx: ModuleContext): void | Promise<void>
  saveState?(ctx: ModuleContext): void | Promise<void>
  restoreState?(ctx: ModuleContext): void | Promise<void>
  dispose?(ctx: ModuleContext): void | Promise<void>
}
```

`ModuleLifecycleController` (in `platform/modules/`) drives this — all hooks are optional, called only if implemented:

- **mount()** — `initialize → load → activate`, called when `ModuleHost` mounts the module (i.e. its tab becomes the active workspace tab for the first time).
- **deactivate()** — `deactivate → saveState`, called when the module's tab loses focus. *(Not currently wired at the shell level — today `WorkspaceHost` only ever renders the single active module, so switching tabs unmounts the previous one entirely rather than deactivating-in-place. See §7, known limitations.)*
- **reactivate()** — `restoreState → activate`.
- **unmount()** — `deactivate → saveState → dispose`, called when the tab closes.

The controller refuses to skip states out of order and is idempotent (calling `deactivate()` twice is a no-op the second time) — verified by `ModuleLifecycleController.test.ts` and a 120-iteration open/close stress test (Phase 2.5) that showed zero DOM-node growth and non-linear (bounded) heap growth across repeated mount/unmount cycles.

`ModuleHost` (React component) is the only thing that actually calls the controller — modules never manage their own lifecycle.

## 3. Registering a module

```ts
// platform/modules/my-module.module.ts
import MyPage from '../../pages/MyPage'
import type { ModuleDefinition } from './types'

export const myModule: ModuleDefinition = {
  id: 'my-module',
  title: 'My Module',
  icon: 'bi-something',
  nav: { id: 'my-module', label: 'My Module', icon: 'bi-something', group: 'System', path: '/my-module', capability: 'SOME_CAP' },
  ribbon: { tab: 'My Module', groups: [...] },   // optional
  component: MyPage,                              // React.ComponentType<ModuleContext> — a zero-prop page component works fine
  lifecycle: { initialize: () => {...}, dispose: () => {...} }, // optional
}
```

```ts
// platform/modules/registerModules.ts
import { myModule } from './my-module.module'
const modules = [reportsModule, myModule]
for (const m of modules) if (!moduleRegistry.has(m.id)) moduleRegistry.register(m)
```

`registerModules.ts` is imported once (as a side effect) by `PlatformShellPreviewPage.tsx` before `PlatformShell` first renders — ES module caching makes this idempotent regardless of remounts. The `has()` guard additionally protects against Vite HMR re-executing the module's top-level code without a full reload.

`nav.capability` reuses the exact same `Capability`/`useAccess()`/`RoleContext` system the browser app already uses — no new gating mechanism.

## 4. Platform Services — the only door to Electron/browser APIs

Business module code must never touch `window.uninex`, `navigator.clipboard`, `localStorage`, or any other host API directly. Import from `platform/services` instead:

| Service | Wraps | Notes |
|---|---|---|
| `logger` | `window.uninex.log` (Electron) / `console.*` (browser fallback) | Only file in the whole codebase allowed to call `console.*` directly is `platform/logging/Logger.ts` itself. |
| `errorService` | — | `.report(scope, message, cause)`. Everything unhandled funnels here: render errors via `ErrorBoundary`, and `window.onerror`/`unhandledrejection` are wired at the shell level (`PlatformShell`) so nothing silently vanishes into the console. |
| `notify` / `notificationService` | — | User-facing toasts (`notify.success('Saved')`, etc.), rendered by `<UniNotification/>`. Distinct from `errorService` — this is for expected, non-error feedback. |
| `useSession` / `getSessionSnapshot` / `withSessionDefaults` | — | Centralizes `tenant_id`/`store_id`/acting-user GUID (today manually threaded per call site everywhere — see `useActingUser.ts`). Not yet wired into `apiClient.ts`'s request path automatically; that's a deliberate follow-up once real modules exist to validate against. |
| `dialogService` | `window.confirm`/`window.alert` | Swap point for OS-native Electron dialogs later (would need an IPC channel to the main-process `dialog` module) — module code doesn't need to change when that happens. |
| `settingsService` | `localStorage` (namespaced `uninex.settings.*`) | Per-user preferences (report defaults, page sizes). Distinct from `platform/layout/LayoutPersistence` (`uninex.layout.*`), which is shell/workspace layout, not user settings. |
| `clipboardService` | `navigator.clipboard` | — |

`FileService`, `PrintService`, `UpdateService` are **not built** — no module needs them yet, and stub files with no real implementation would just be unused code. Add them to `platform/services/` following the same thin-wrapper pattern when a module actually needs one.

## 5. Cross-module communication — EventBus

```ts
import { eventBus } from '../events/EventBus'
eventBus.emit('module.activated', { moduleId: 'reports' })
const unsubscribe = eventBus.on('module.activated', (payload) => {...})
```

`PlatformEventMap` (in `EventBus.ts`) intentionally contains **only** `module.activated`/`module.deactivated` — the two events the platform itself owns. A module adds its own typed events via TypeScript declaration merging in its own file, not by editing `EventBus.ts`:

```ts
declare module '../../platform/events/EventBus' {
  interface PlatformEventMap {
    'purchase.saved': { cycleId: string }
  }
}
```

This was a real finding from the Phase 2.5 shared-component review — the original version hardcoded business event names (`purchase.saved`, `export.finished`, ...) directly in platform code, which is exactly the kind of hidden module-specific assumption this freeze phase exists to catch.

## 6. Keyboard shortcuts

`keyboardManager.register(combo, handler)` throws if `combo` is already registered — that's the actual conflict-prevention mechanism (not a hardcoded list). `PlatformShell` attaches one `document`-level `keydown` listener that consults the registry.

Only one combo has an unambiguous **shell-level** meaning and is wired by `PlatformShell` itself:
- **F5** — remounts the active module (forces its full lifecycle to re-run) instead of the browser's native page reload (`preventDefault()`'d).

**Esc is deliberately *not* a shell-level shortcut.** An earlier version bound Esc to "close the active tab," reasoning that a module's own `event.stopPropagation()` would naturally pre-empt it. That assumption broke in practice: wrapping Purchase Manager (Phase 3) surfaced that its `ProductGrid` uses Esc for "skip this row" — a core, frequent workflow action — and calls `preventDefault()` but not `stopPropagation()` (a very common, reasonable pattern; React's `preventDefault()` only suppresses the browser's default action, not DOM bubbling). Every Esc-to-skip would therefore also have bubbled up and closed the entire Purchase Manager tab. Esc is one of the most commonly module-owned keys (cancel an edit, dismiss a popover, skip a row) and a shell-level default for it is unsafe in general, not just for this one module. Closing a tab is the explicit "×" button in `WorkspaceTabs` only.

`Ctrl+S`, `Ctrl+F`, `Ctrl+N`, `Ctrl+P`, `F2`, `Esc`, `Enter` are **reserved for modules** to register themselves once they need them — there is no generic shell-level meaning for "save" or "new" without a module. Register/unregister in your module's `initialize`/`dispose` lifecycle hooks (or a `useEffect` in the module's component) so the shortcut only exists while the module is actually open. Note that modules are also free to keep their own local `onKeyDown`/`addEventListener` handling entirely outside `keyboardManager` (as Purchase Manager's `ProductGrid`/`PurchaseWorkspacePage` already did before being wrapped, and still does, unmodified) — the registry only prevents conflicts *between things that register through it*, it does not force every module to migrate its existing keyboard handling to use it.

## 7. Layout & window persistence

- **Dock panel sizes** (a module's own internal split panes) — `DockGroup` wraps `react-resizable-panels`' `useDefaultLayout`, auto-persisted to `localStorage` under `uninex.layout.dock.<id>`. Nothing extra needed.
- **Open tabs / active module** — `PlatformShell` persists `{ openModuleIds, activeModuleId }` to `uninex.layout.workspace` (via `platform/layout/LayoutPersistence`) and restores it on next launch, dropping any module id that no longer exists in the registry.
- **Window size/position/maximized state** — handled entirely by `electron-window-state` (`electron/main.ts`), which also validates saved bounds against currently-connected displays and falls back to the primary display's defaults if the window was last on a monitor that's since been disconnected (multi-monitor safe, verified via source review — no extra code needed).
- **Theme** — already persisted via the existing `ThemeContext`/`localStorage` (`nexora.theme`), reused as-is.

**Known limitation:** because `WorkspaceHost` only ever mounts the single *active* module (background tabs aren't kept alive off-screen), a module's in-memory state does not survive switching away and back to its tab within the same session — only which tabs are open and which is active is remembered. True background-tab state retention (VS Code-style) is a larger feature, deliberately out of scope for this freeze.

## 8. Error handling

Three layers, all funneling into `errorService`:
1. **`ErrorBoundary`** (React) — catches render-tree exceptions. `WorkspaceHost` wraps every module in one; `PlatformShell` wraps the whole workspace in another as a last resort.
2. **`window.onerror` / `unhandledrejection`** (wired in `PlatformShell`) — catches anything that slipped past both a module's own try/catch and the ErrorBoundary (which only catches render errors, not async/event-handler errors).
3. **`apiClient.ts`** — logs (via the shared `logger`) on every request failure, both network-unreachable and non-2xx responses.

`<GlobalErrorDialog/>` is the one shared toast surface `errorService` reports to — no module should build its own top-level error dialog. Inline, field-level validation errors remain a module's own concern (different problem).

## 9. API Client

`services/apiClient.ts` is the single shared HTTP client — every module uses it, no module creates its own. As of Phase 2.5 it additionally supports (opt-in, zero behavior change for the ~40 existing call sites that don't pass these):

```ts
api.get<T>(path, { timeoutMs: 15000, retries: 2 })   // new: options-object form
api.get<T>(path, abortSignal)                         // unchanged: raw AbortSignal still works
```

- **Timeout** — `AbortSignal.timeout(ms)`, combined with any caller-supplied signal via `AbortSignal.any`. Omitted by default (existing calls never time out, exactly as before).
- **Retry** — only on total network failure (status 0 — server unreachable), never on a reached-but-erroring server (4xx/5xx), and only meaningful for `GET` (no retry option exposed on `post`/`put`/`patch`/`delete` — retrying a non-idempotent write automatically would risk duplicating it).
- **Logging** — every failure (network or HTTP) is logged via the shared `logger`, scope `api-client`.
- **Compression** — handled transparently by `fetch`/the browser's HTTP stack (`Accept-Encoding`); no client code needed.
- **Auth** — unchanged, Bearer token from `tokenStorage` attached when present.

See `src/services/apiClient.test.ts` for the retry/timeout/backward-compatibility test coverage.

## 10. Developer guidelines

- **A module never imports Electron/browser host APIs directly** — go through `platform/services`.
- **A module never edits shared platform files** to add its own vocabulary (event names, nav entries, ribbon tabs) — those are all contribution points (`ModuleDefinition`, declaration merging for `PlatformEventMap`), not places to hardcode business logic.
- **Reuse `Uni*` components** (`platform/ui`) instead of hand-rolling a table/toast/loading-spinner — `UniGrid` in particular replaces the pattern where 5+ existing modules each built their own `<table>`.
- **Existing browser-only pages are not modified** to become modules — they're *wrapped* (see `reports.module.ts`, `purchase-manager.module.ts`): the existing component is reused as-is via `ModuleDefinition.component`, so the same code continues to work identically at its original browser route.
- **Don't build ahead of need** — `FileService`/`PrintService`/`UpdateService` and dynamic/hot-loadable module loading are intentionally not built; add them when a real module needs them, not speculatively.
- **A wrapped page may assume the old AppShell's chrome height** (a hardcoded `calc(100vh - Npx)`, since it predates this shell). Override with a higher-specificity selector scoped to `.platform-workspace-host` in `platform-shell.css` (see the `.platform-workspace-host .pm` rule) — never edit the page's own CSS file, since it's still serving that page's original browser route unmodified.

## 11. What's verified vs. what needs your own machine

Phase 2.5 validated, in a real (headless, real backend) browser via Playwright: shell rendering, module open/close lifecycle (120-iteration stress test, zero DOM leak, bounded heap growth), event bus and keyboard-manager leak tests (500-cycle subscribe/unsubscribe), theme switching, zero console errors throughout.

**Not verifiable from the sandboxed dev environment this was built in** (it can reach npm and Playwright's CDN, but not Electron's own binary-release CDN): the native Electron window itself — startup/splash time, maximize/restore/minimize/close chrome, orphan-process check after quit, and the before-quit save-prompt flow end-to-end. The before-quit logic was corrected via careful code review during this phase (see git history — the original version only fired the save-prompt if `app.on('before-quit')` ran while `mainWindow` was still non-null, which is never true on the normal OS close-button path; it's now intercepted at the window level instead) but should be exercised manually: `npm run electron:dev`, open a module, close via the OS `[x]` button, confirm the app exits cleanly with no lingering `electron.exe`/`node.exe` process in Task Manager.
