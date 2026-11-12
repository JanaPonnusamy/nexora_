# 07 — Security and Tenant Audit
**NEXORA MEDIQ Unification — Phase 0 Audit**

## Finding: tenant/store authorization is enforced server-side, not just in the UI

This is the most important finding in this section, directly answering the master prompt's §8 requirement.

- `backend/modules/procurement/pm_router.py`: every sampled endpoint handler uses `Depends(require_procurement_workspace)` and then explicitly calls `assert_tenant_access(current_user, tenant_id)` before touching data. This is a server-side guard, independent of anything the renderer sends or claims.
- The new (uncommitted) tenant export-defaults write endpoint checks `has_full_access(current_user)` server-side and returns `HTTPException(403)` otherwise — again not a client-side-only check.
- **Client-side module gating exists too** (`App.jsx:132, 420-434` — matches `user.modules`/`permissions`/`allowedModules` against each screen's `module` key, with three additional hardcoded role-based narrowings), but this is UX convenience (hide screens a user can't use), not the actual security boundary. The actual boundary is the backend's per-endpoint tenant/role checks described above.

**Conclusion:** the existing security model already satisfies the master prompt's requirement ("backend authorization is authoritative," "renderer cannot bypass authorization"). A UI redesign does not need to — and must not — change this enforcement pattern; it only needs to continue calling the same backend endpoints, which will continue to enforce tenant/role scope regardless of what the new UI looks like.

## Finding: no privileged credentials or direct DB access reach the renderer or Electron main process

- No SQL/ODBC client library exists anywhere in the Electron app's main process, preload, or renderer dependencies.
- The preload script (`preload.cjs`) exposes only: platform/machine info, dev-viewport helpers, theme setting, a UI-state JSON file read/write scoped to `userData`, export file write restricted to `.xls/.xlsx/.csv` plus explicit folder dialogs, store-WhatsApp controls, Web-panel helpers, and Device Controller enrollment calls. **No arbitrary file read/write, no SQL, no credential material.**
- All business data access is HTTP calls carrying a bearer token, made from the renderer through `src/api/client.js` to the FastAPI backend.

## Finding: session/auth shape

- `backend/controllers/auth_controller.py` (254 lines) implements JWT-based auth with a `_MULTI_SESSION_ROLES` allow-list (currently `{"STOCK_VIEWER"}`, with an **uncommitted** change adding `"SMS_PM"` — unrelated to MEDIQ, tied to ongoing SMS-tenant onboarding) and a `_SESSION_LEASE_MINUTES` heartbeat-lease pattern.
- Renderer-side, `src/state/session.js` stores settings and session payload in `localStorage` (keys `nexora.desktop.settings` / `nexora.desktop.session`). Sessions auto-expire same-day (`loginDate !== todayKey()` clears state) — a "log in fresh daily" model.
- Exact field-level contents of the stored session payload (e.g., whether the raw JWT sits in `localStorage` vs. a cookie) were not independently re-confirmed field-by-field in this pass — flagged as a follow-up item rather than assumed.

## Finding: supplier-portal webviews are isolated

The Procurement "Web panel" feature (browsing real supplier ordering portals inside the app) uses Electron `<webview>` tags that are individually configured with no preload and no Node integration, sandboxed, HTTP(S)-only (`webPanel.cjs`, per comment in `main.cjs:246`). This matters because it's the one place in the app that loads third-party, un-trusted web content — and it is already isolated correctly.

## Recommendations carried into implementation planning

1. Preserve the existing server-side tenant/role enforcement pattern exactly as-is; do not introduce any new client-side-only authorization check as a "simplification" during redesign.
2. Any new AI Intelligence Centre backend endpoints (net-new, per `03`/`04`) must follow the same `require_*` + `assert_tenant_access` pattern already established in `pm_router.py` — this is the project's existing convention, not something to redesign.
3. No change needed to the preload surface for a UI redesign; if new Electron-level capability is ever needed (e.g., for a dashboard requiring new export formats), extend the existing restricted-scope pattern (explicit per-feature preload methods) rather than broadening `nodeIntegration` or adding general file/DB access.
