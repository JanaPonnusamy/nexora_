import type { NavEntry } from '../../types/navigation'

/** Grouped navigation sections (UI-02 — stronger operational hierarchy). */
export const NAV_ENTRIES: NavEntry[] = [
  {
    kind: 'group',
    label: 'Platform',
    icon: 'bi-grid-1x2',
    cap: 'PLATFORM',
    children: [
      { label: 'Overview', to: '/overview', icon: 'bi-speedometer2', cap: 'PLATFORM' },
      { label: 'Platform Management', to: '/platform/manage', icon: 'bi-buildings', cap: 'PLATFORM' },
    ],
  },
  {
    kind: 'group',
    label: 'Inventory',
    icon: 'bi-box-seam',
    cap: 'INVENTORY',
    children: [
      { label: 'Stock Availability', to: '/stock-availability', icon: 'bi-box-seam', cap: 'INVENTORY' },
      { label: 'Stock Check Report', to: '/stock-check-report', icon: 'bi-clipboard-check', cap: 'INVENTORY' },
      { label: 'Label Exporter', to: '/label-exporter', icon: 'bi-tags', cap: 'INVENTORY' },
      { label: 'Box Workspace', to: '/label-exporter/box-workspace', icon: 'bi-grid-3x3-gap', cap: 'INVENTORY' },
      { label: 'NMW Sales Report', to: '/nmw-sales-report', icon: 'bi-receipt', cap: 'INVENTORY' },
      { label: 'Non-Moving Report', to: '/non-moving-report', icon: 'bi-hourglass-bottom', cap: 'INVENTORY' },
      { label: 'Sale Analysis', to: '/sale-analysis', icon: 'bi-graph-up-arrow', cap: 'INVENTORY' },
      { label: 'Stock Integrity Check', to: '/stock-integrity', icon: 'bi-shield-check', cap: 'INVENTORY' },
    ],
  },
  {
    kind: 'group',
    label: 'Procurement',
    icon: 'bi-cart-check',
    cap: 'PROCUREMENT_WORKSPACE',
    children: [
      { label: 'Cycle & Refresh', to: '/procurement/console', icon: 'bi-arrow-repeat', cap: 'PROCUREMENT_ADMIN' },
      { label: 'Purchase Manager', to: '/procurement/workspace', icon: 'bi-cart-check', cap: 'PROCUREMENT_WORKSPACE' },
      { label: 'Product Intelligence', to: '/procurement/intelligence', icon: 'bi-cpu', cap: 'PROCUREMENT_WORKSPACE' },
      { label: 'Refresh Compare', to: '/procurement/compare', icon: 'bi-arrow-left-right', cap: 'PROCUREMENT_WORKSPACE' },
      { label: 'Shelf Sorting & Excel Split', to: '/procurement/shelf-sort', icon: 'bi-signpost-split', cap: 'PROCUREMENT_WORKSPACE' },
      { label: 'Shelf Category Training', to: '/procurement/shelf-categories', icon: 'bi-mortarboard', cap: 'PROCUREMENT_WORKSPACE' },
      { label: 'Pharmacy Reports', to: '/procurement/reports', icon: 'bi-bar-chart', cap: 'REPORTS' },
      { label: 'Supplier Stock Distribution', to: '/procurement/distribution', icon: 'bi-broadcast', cap: 'PROCUREMENT_ADMIN' },
    ],
  },
  {
    kind: 'group',
    label: 'Master Data',
    icon: 'bi-diagram-3',
    cap: 'PRODUCT_MAPPING',
    children: [
      { label: 'Product Mapping', to: '/product-mapping', icon: 'bi-diagram-3', cap: 'PRODUCT_MAPPING' },
    ],
  },
  {
    kind: 'group',
    label: 'Document Extraction',
    icon: 'bi-file-earmark-medical',
    cap: 'DOCUMENT_EXTRACTION',
    children: [
      { label: 'Workspace', to: '/document-extraction/review', icon: 'bi-file-earmark-medical', cap: 'DOCUMENT_EXTRACTION' },
      { label: 'History', to: '/document-extraction/history', icon: 'bi-clock-history', cap: 'DOCUMENT_EXTRACTION' },
    ],
  },
  {
    kind: 'group',
    label: 'Sync',
    icon: 'bi-arrow-repeat',
    cap: 'SYNC',
    children: [
      { label: 'Sync Live', to: '/sync/live', icon: 'bi-broadcast-pin', cap: 'SYNC' },
      { label: 'Sync Schedules', to: '/sync/schedules', icon: 'bi-calendar-event', cap: 'SYNC' },
      { label: 'Sync Config', to: '/sync/config', icon: 'bi-table', cap: 'SYNC' },
      { label: 'Sync Mapping', to: '/sync/mapping', icon: 'bi-diagram-3', cap: 'SYNC' },
      { label: 'Sync Agents', to: '/sync/agents', icon: 'bi-router', cap: 'SYNC' },
    ],
  },
  {
    kind: 'group',
    label: 'Administration',
    icon: 'bi-sliders',
    cap: 'ADMINISTRATION',
    children: [
      { label: 'Modules', to: '/administration/modules', icon: 'bi-boxes', cap: 'ADMINISTRATION' },
      { label: 'Permissions', to: '/administration/permissions', icon: 'bi-shield-lock', cap: 'ADMINISTRATION' },
      { label: 'Audit Logs', to: '/administration/audit-logs', icon: 'bi-journal-text', cap: 'ADMINISTRATION' },
    ],
  },
  {
    kind: 'group',
    label: 'Expiry Report',
    icon: 'bi-calendar-x',
    cap: 'REPORTS',
    children: [
      { label: 'Expiry Report', to: '/expiry-report', icon: 'bi-calendar-x', cap: 'REPORTS' },
      { label: 'Expiry Stock', to: '/expiry-stock', icon: 'bi-scissors', cap: 'REPORTS' },
    ],
  },
  {
    kind: 'group',
    label: 'System',
    icon: 'bi-gear',
    children: [
      { label: 'Reports', to: '/reports', icon: 'bi-bar-chart', cap: 'REPORTS' },
      { label: 'Time Report', to: '/time-report', icon: 'bi-clock-history', cap: 'TIME_REPORT' },
      { label: 'Pass Gen', to: '/pass-gen', icon: 'bi-key', cap: 'PASS_GEN' },
      { label: 'Legacy Order', to: '/legacy-order', icon: 'bi-database-gear', cap: 'LEGACY_ORDER' },
      { label: 'Order Workspace', to: '/legacy-order/workspace', icon: 'bi-grid-3x3-gap', cap: 'LEGACY_ORDER' },
      { label: 'WhatsApp', to: '/whatsapp', icon: 'bi-whatsapp', cap: 'SETTINGS' },
      { label: 'Settings', to: '/settings', icon: 'bi-gear', cap: 'SETTINGS' },
    ],
  },
]
