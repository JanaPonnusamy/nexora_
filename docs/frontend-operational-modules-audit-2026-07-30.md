# Nexora Operational Modules Audit

Date: 2026-07-30

## Scope

Audit of the remaining operational workspaces after the design-system foundation pass.

Modules inspected:

- Procurement
- Sync
- Supplier Stock / Procurement live stock views
- Inventory / Stock Availability
- Document Extraction
- Reports-related operational pages

## Custom page CSS

- Procurement:
  `frontend/src/components/procurement/purchase-manager.css`
  `frontend/src/components/procurement/intelligence/product-intelligence.css`
- Sync:
  `frontend/src/components/sync/sync-ui.css`
- Inventory:
  `frontend/src/components/stock/stock-ui.css`
- Document Extraction:
  `frontend/src/components/document-extraction/document-extraction.css`
- Reports:
  `frontend/src/pages/reports.css`
  `frontend/src/pages/timeReport.css`
  `frontend/src/pages/procurement/pharmacy-reports.css`

## Duplicated toolbars

- Procurement:
  `pm-toolbar`
  `pm-sq__toolbar`
  `pm-cmp__bar`
  `pm-cmp__filters`
- Sync:
  `sx-toolbar`
  `sx-search`
  `sx-seg`
- Inventory:
  `sa-search`
- Document Extraction:
  `dx-topbar`
  `dx-viewer__toolbar`

## Duplicated headers

- Procurement:
  `pm-top`
  `pm-launch__brand`
  `pm-admin__panel-title`
- Sync:
  `sx-head`
  `sx-card__head`
- Inventory:
  `sa-head`
  `sa-branches-head`
- Document Extraction:
  `dx-topbar`
  `dx-section-title`

## Duplicated cards / stat tiles

- Procurement:
  `pm-selbar__item`
  `pm-sxcard`
  `pm-stat`
- Sync:
  `sx-stat`
  `sx-card`
- Inventory:
  branch cards
  summary panels
- Document Extraction:
  `dx-stat`
  `dx-tile`
  `dx-job`

## Duplicated split layouts

- Procurement:
  `pm-split`
  `pm-sq__split`
- Sync:
  `sx-split`
  mapping split
- Inventory:
  search/results/detail regions behave like a custom split view
- Document Extraction:
  `dx-workspace`
  viewer + main review layout

## Duplicated panels

- Procurement:
  detail panel
  supplier recommendation panel
  supplier queue detail panel
  drawers
- Sync:
  cards, drawers, side mapping list/detail panels
- Inventory:
  waiting panels
  detail panels
- Document Extraction:
  header panel
  validation panel
  history detail panel
  processing queue cards

## Duplicated tabs

- Procurement:
  stage tabs
  view tabs
  drawer tabs
- Sync:
  top navigation tabs
  segmented controls
- Inventory:
  search mode tabs
- Document Extraction:
  implicit queue/review mode separation and viewer controls

## Duplicated filters / search bars / buttons

- Search fields appear in procurement, sync, stock, and document extraction with separate local CSS.
- Small action buttons and ghost buttons are duplicated across procurement and sync.
- Status / movement / mode filters are implemented as local controls rather than shared design-system components.

## Duplicated AG Grid / grid wrappers

- No AG Grid package exists in the current frontend dependency graph.
- Current repeated grid/table layers:
  `UniGrid`
  `SxTable`
  procurement custom tables
  stock custom tables
  document extraction custom item grids

## Architectural findings

- Operational modules currently run on at least four parallel UI systems:
  `pm-*`
  `sx-*`
  `sa-*`
  `dx-*`
- Shared admin pages were migrated, but high-density operational workspaces still own layout, cards, panels, and grid behavior locally.
- The safest migration path is:
  1. shared operational shell
  2. shared KPI/cards
  3. shared data-grid contract
  4. shared inspector/split primitives
  5. incremental module adoption

## Shared component targets

Repeated patterns that should be centralized:

- Workspace shell
- KPI/stat row
- Data grid wrapper
- Inspector panel
- Split view
- Workspace status strip
- Filter/search surface
- Tabs / segmented navigation
