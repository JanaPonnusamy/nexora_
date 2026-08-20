# Nexora Frontend Audit

Date: 2026-07-30

## Scope

Audit completed before redesign work for the frontend architecture modernization effort. This review covers the `frontend/src` application shell, routed pages, shared components, CSS assets, and current design-system maturity.

## 1. Current layout architecture

- The primary application uses `AppShell` with `Header`, `Sidebar`, `StatusBar`, and routed page content.
- A second shell exists under `platform/*` (`PlatformShell`, `uni-ui.css`, `platform-shell.css`) for preview and module-host experiments.
- Most routed pages sit inside the primary shell and depend on Bootstrap utility classes plus custom global CSS.
- Page containers commonly start with `container-fluid px-0`, then assemble page headers, toolbars, summary cards, tables, and mobile card lists.

## 2. Component hierarchy

- Shared components exist for `PageHeader`, `EmptyState`, `ErrorState`, `Skeleton`, `TableSkeleton`, and `StatusBadge`.
- Platform admin pages (`Tenants`, `Stores`, `Users`, `Roles`, `Modules`) reuse the same high-level flow:
  loading -> error -> empty -> filtered empty -> table + card list.
- Toolbars for admin pages are duplicated in separate files with nearly identical structure.
- Several domain modules build their own mini design systems:
  sync (`sync-ui.css`)
  mapping (`mapping-ui.css`)
  procurement (`purchase-manager.css`)
  stock (`stock-ui.css`)
  document extraction (`document-extraction.css`)

## 3. CSS architecture

- Styling is currently split between one large global stylesheet and many module-scoped CSS files.
- `frontend/src/index.css` is effectively both:
  shell theme
  component library
  dashboard styles
  page density overrides
  module-specific styling
- Large CSS files:
  `frontend/src/components/procurement/purchase-manager.css` ~100 KB
  `frontend/src/components/sync/sync-ui.css` ~43 KB
  `frontend/src/index.css` ~30 KB
- There is no centralized token layer for color, spacing, radius, motion, or typography.

## 4. Bootstrap dependency

- Bootstrap 5 is globally imported in `main.tsx`.
- Bootstrap Icons are also globally imported.
- The UI relies on Bootstrap variables such as `--bs-body-bg`, `--bs-border-color`, `--bs-primary`, and utility classes like `container-fluid`, `btn`, `form-select`, `d-md-none`, `ms-auto`, `small`, and `text-secondary`.
- This makes theming partially centralized, but component shape, spacing, hierarchy, and density remain inconsistent.

## 5. Duplicate components

- Duplicate toolbar components:
  `TenantToolbar`
  `StoreToolbar`
  `UserToolbar`
  `RoleToolbar`
  `ModuleToolbar`
- Repeated table + mobile card-list pairing across admin pages.
- Repeated empty-state patterns with only copy and icon changes.
- Repeated tab-card pattern in platform/admin workspaces.

## 6. Duplicate CSS

- Search fields, filter selects, and create buttons all repeat the same toolbar structure.
- Navigation cards, quick-action cards, KPI cards, status chips, and compact grid rows are all hand-styled in multiple places.
- Similar responsive behaviors are rewritten separately in multiple page or module stylesheets.
- The preview platform shell repeats many concepts already present in the main shell.

## 7. Hardcoded colors

- Hardcoded hex and rgba values are present across CSS and inline styles.
- Examples include gradients, shadows, accent tones, inline chart swatches, row highlight colors, and drawer z-index overlays.
- Color ownership is fragmented between Bootstrap variables, module-level CSS variables, and direct inline style values.

## 8. Hardcoded spacing

- Spacing is mostly expressed as ad hoc `rem`, `px`, and Bootstrap utility classes.
- The global stylesheet mixes shell spacing, card spacing, and data-grid density directly in selectors instead of semantic tokens.
- Inline styles also contain one-off `margin`, `maxWidth`, `width`, and `padding` values.

## 9. Hardcoded font sizes

- Font sizing is spread across global CSS, module CSS, Bootstrap heading classes, and inline style objects.
- Small labels and dense data tables frequently use literal `0.7rem`, `0.78rem`, `0.82rem`, `11.5`, etc.
- There is no formal typography scale enforcing hierarchy across modules.

## 10. Fixed widths

- Fixed widths are used in shell dimensions, table columns, dialogs, progress bars, and inline table `<col>` definitions.
- Login uses a fixed card width.
- Several data-heavy modules depend on exact column widths embedded in JSX.

## 11. Mobile issues

- The main shell handles mobile nav with an off-canvas sidebar, but many data-dense modules still assume desktop width.
- Platform management tabs only partially adapt and depend on a page-specific stylesheet.
- Large tables often fall back to separate card lists, but the system is not centralized.
- Heavy inline widths and `<col>` sizing increase the risk of clipping on smaller screens.

## 12. Accessibility issues

- Some icon-only controls rely only on visuals or Bootstrap defaults instead of shared focus states.
- Focus styling is inconsistent across custom interactive elements.
- Dense table UIs use low-contrast secondary text in many places.
- A large number of inline styles and custom controls makes consistent keyboard and contrast review harder.

## 13. Performance issues

- The biggest page (`PurchaseWorkspacePage.tsx`) is ~130 KB and mixes extensive logic and UI in one file.
- Large CSS payloads increase parsing cost and make style invalidation harder to reason about.
- Repeated component patterns raise the cost of future fixes because changes must be applied in multiple places.
- The frontend carries two parallel shell systems, which increases maintenance overhead.

## 14. Components needing redesign

- Primary shell header/sidebar/status bar
- Shared page header
- Shared empty/error/loading surfaces
- Repeated admin list toolbars
- Platform management tabs
- Data-table wrappers and density rules
- Bootstrap-first buttons/inputs/selects that currently lack a common component contract

## 15. Reusable components that already exist

- `PageHeader`
- `EmptyState`
- `ErrorState`
- `Skeleton`
- `TableSkeleton`
- `StatusBadge`
- `StatCard`
- `ToggleCheck`
- `DonutChart`

## 16. Pages using duplicated code

- `TenantsPage`, `StoresPage`, `UsersPage`, `RolesPage`, and `ModulesPage`
- `ReportsPage` and `TimeReportPage` have related reporting UI concerns but separate styling paths
- Multiple procurement and sync views implement their own local toolbar, drawer, and panel systems

## 17. Technical debt summary

- No centralized design tokens
- Overloaded global stylesheet
- Two shell systems with overlapping concepts
- Repeated admin components
- Large module-specific CSS islands
- Inline styles used for layout and presentation
- Bootstrap dependency without a consistent component layer

## Recommended redesign order

1. Establish centralized semantic tokens and shared shell/layout primitives.
2. Replace repeated admin page patterns with reusable toolbar, header, tab, and surface components.
3. Move page-level visual styling into shared component contracts.
4. Tackle large module islands (`procurement`, `sync`, `stock`, `mapping`) incrementally after the shared system is stable.
