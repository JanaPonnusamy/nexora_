# NexTech MediQ Workspace — Phase 3 Premium UI Implementation

**Date:** 2026-11-14  
**App path:** `desktop/nextech-mediq`  
**Product:** NexTech MediQ Workspace  
**Tagline:** Intelligent Pharmaceutical Workspace

This document records the premium desktop shell built on top of the Phase 2/3
foundation. It does **not** claim live backend login or Stock Enquiry results.
Those remain blocked on the NEXORA API / SQL host (see the master tracker).

## Scope

Implemented the application chrome, grouped navigation, shared page layout,
theme switching, and honest planned-module destinations. No fake operational
modules were added. Neither `desktop/supplier-stock-client` nor
`desktop/quick-stock-client` was modified.

## Visual system

- Tokens in `src/themes/tokens.css` / `src/themes/tokens.js`: deep navy
  (`#0B1728` / `#10243A`) and teal (`#12B8A6`).
- Dark default, light, and system preferences (`ThemeProvider` + icon
  selector in the top bar).
- Restrained radii (4–6px), compact density, Segoe UI / system sans.
- Single stroke icon family in `src/ui/icons.jsx` (no mixed icon packs).
- Brand lockup from `src/assets/branding/svg/nextech-mediq-standard.svg`
  (light) and `nextech-mediq-standard-dark.svg` (dark); collapsed sidebar
  uses `nextech-mediq-app-icon.svg`.
- Shared loading / empty / error states retained and restyled as dashed
  panel surfaces, not oversized cards.

## Application shell

| Feature | Implementation |
|---|---|
| Main frame | `AppShell` — sidebar + column with toolbar and scrollable content |
| Sidebar | Grouped nav from `NAV_GROUPS`, collapse toggle, planned badges |
| Top toolbar | Breadcrumbs, global search, tenant/store, theme, notifications, user |
| Breadcrumbs | `breadcrumbsForPath()` from the nav registry |
| Global search | Ctrl/Cmd+K palette; jumps only to **enabled** destinations; planned items listed but disabled |
| Notifications | Honest system note (no fake operational alerts) |
| User menu | Name from session `user`; Settings + Sign out |
| Tenant/store | `user.tenant_id` and primary `roles[].store_name` / `store_code` |
| Theme selector | Dark / light / system |
| Page layout | `PageLayout` / `ntm-page` header + lede used by Dashboard, Settings, Stock Enquiry, planned pages |

## Navigation groups

All entries live in `src/navigation/navConfig.js`. Status is honest:

| Group | Destinations | Status |
|---|---|---|
| Dashboard | Dashboard | in progress (shell overview only) |
| Inventory | Stock Enquiry | in progress (API wired, not live-verified) |
| Inventory | Network Stock, Non-Moving Stock | planned |
| Supplier Intelligence | Supplier Stock, Quick Stock, Rate Analysis | planned |
| Procurement | Procurement Workspace, Order Workspace, Order Entry, Legacy Order | planned |
| Sales & Reports | Sales & Reports | planned |
| AI Intelligence | AI Intelligence | planned |
| Tools | Tools | planned |
| Administration | Administration | planned |
| Settings | Settings | in progress (API base URL only) |

Planned routes render `PlannedModulePage`: reserved destination copy, **no**
backend calls.

Enabled (`isNavItemEnabled`) remains only: Dashboard, Stock Enquiry, Settings.

## Electron security (unchanged)

`electron/security/windowDefaults.cjs` still sets:

- `contextIsolation: true`
- `nodeIntegration: false`
- `sandbox: true`
- `webSecurity: true`

Preload (`electron/preload/index.cjs`) still exposes only `window.nextechMediq`
(`app.*`, `theme.*`). The renderer does not access Node or any database.

Electron remains pinned at **22.3.27**.

## Validation

| Check | Result |
|---|---|
| `npm test` | **27/27 pass** (22 existing + 5 nav registry tests) |
| `npm run build` | Vite production build **exit 0** (73 modules) |
| Electron launch | Window title **NexTech MediQ Workspace** (`Get-Process`) |
| Rendered screens | Login; Dashboard (dark); Stock Enquiry empty state; Network Stock planned empty state; light theme; global search palette |

Inspection used a **local session stub** only so the shell could be viewed
without a live login. That stub is not a product feature. Live
`POST /api/auth/login` was not re-attempted in this phase.

## Files added / updated (nextech-mediq only)

Added:

- `src/ui/icons.jsx`
- `src/layouts/PageLayout.jsx`, `Breadcrumbs.jsx`, `GlobalSearch.jsx`,
  `NotificationArea.jsx`, `TenantContext.jsx`, `UserMenu.jsx`, `ThemeSelector.jsx`
- `src/modules/planned/PlannedModulePage.jsx`
- `tests/navConfig.test.js`

Updated:

- `src/navigation/navConfig.js`
- `src/layouts/AppShell.jsx`, `Sidebar.jsx`, `TopBar.jsx`, `shell.css`
- `src/app/App.jsx`, `login.css`
- `src/themes/tokens.css`
- `src/modules/dashboard/DashboardPage.jsx`
- `src/modules/settings/SettingsPage.jsx`
- `src/modules/stock-enquiry/StockEnquiryPage.jsx`

## What this phase does not do

- Does not implement Supplier Stock, Quick Stock, Procurement, reports, AI,
  tools, or administration business logic.
- Does not invent backend endpoints.
- Does not verify live login or live stock search.
- Does not change packaging / installer.

## Next recommended work

Re-run live login against a reachable NEXORA API + SQL host (tracker Phase 4
gap), then Phase 6 Supplier Stock against an existing API — still without
touching the two operational Electron clients.
