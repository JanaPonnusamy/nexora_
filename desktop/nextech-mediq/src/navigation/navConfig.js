// Explicit navigation/route identity registry. Per Phase 8 §8: "Only
// display modules that have a working implementation or a clearly
// identified development status" — every entry's `status` must be honest.
// Do not flip a module to 'ready' until its vertical slice actually works.

export const MODULE_STATUS = Object.freeze({
  READY: 'ready',
  IN_PROGRESS: 'in_progress',
  PLANNED: 'planned',
});

export const NAV_GROUPS = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: 'dashboard',
    items: [
      {
        id: 'dashboard',
        label: 'Dashboard',
        path: '/dashboard',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'dashboard',
        description: 'Workspace overview and module status.',
      },
    ],
  },
  {
    id: 'inventory',
    label: 'Inventory',
    icon: 'inventory',
    items: [
      {
        id: 'quick-stock',
        label: 'Quick Stock',
        path: '/quick-stock',
        status: MODULE_STATUS.READY,
        icon: 'bolt',
        description: 'Fast cross-store product lookup from the existing Quick Stock page. Search, chart, batches, purchases and sales stay on that screen.',
      },
      {
        id: 'stock-enquiry',
        label: 'Stock Enquiry',
        path: '/stock-enquiry',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'search',
        description: 'Search product stock across branches.',
      },
      {
        id: 'non-moving-stock',
        label: 'Non-Moving Stock',
        path: '/inventory/non-moving',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'pause',
        description: 'Dwell-days non-moving stock for the selected store.',
      },
      {
        id: 'stock-check',
        label: 'Stock Check',
        path: '/inventory/stock-check',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'search',
        description: 'Sublocation physical-count sheet.',
      },
      {
        id: 'stock-integrity',
        label: 'Stock Integrity',
        path: '/inventory/stock-integrity',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'boxes',
        description: 'Batch stock compared with product totals.',
      },
      {
        id: 'product-mapping',
        label: 'Product Mapping',
        path: '/inventory/product-mapping',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'network',
        description: 'Store product search for mapping.',
      },
      {
        id: 'label-export',
        label: 'Label Export',
        path: '/inventory/label-export',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'tags',
        description: 'Review products for labelling, assign box locations, and export/print label sheets.',
      },
      {
        id: 'store-health',
        label: 'Store Health',
        path: '/sync/store-health',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'monitor',
        description: 'Per-store agent reachability and staleness.',
      },
    ],
  },
  {
    id: 'procurement',
    label: 'Procurement & Suppliers',
    icon: 'procurement',
    items: [
      {
        id: 'supplier-stock',
        label: 'Supplier Stock',
        path: '/supplier-stock',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'boxes',
        description: 'Supplier list, product search, warehouse-stock filter, and detail (offer, mapping, stock, near expiry, purchase history). Excel import and mapping/assignment writes are not sent.',
      },
      {
        id: 'supplier-stock-list',
        label: 'Supplier Stock List',
        path: '/supplier-stock-list',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'supplier',
        description: 'Current supplier stock rows by tenant and supplier, every store or one.',
      },
      {
        id: 'rate-analysis',
        label: 'Rate Analysis',
        path: '/supplier-intelligence/rate-analysis',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'chart',
        description: 'Supplier purchase-value list. Quote runs stay off this screen.',
      },
      {
        id: 'procurement-workspace',
        label: 'Procurement Workspace',
        path: '/procurement',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'workspace',
        description: 'Read-only procurement cycle list.',
      },
      {
        id: 'order-entry',
        label: 'Order Review (Qty Check)',
        path: '/procurement/order-entry',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'edit',
        description: 'Admin qty-review queue. Reads order-entry readiness. Does not start an order.',
      },
      {
        id: 'pm-order-entry',
        label: 'Purchase Entry Complete',
        path: '/procurement/order-entry-submit',
        status: MODULE_STATUS.READY,
        icon: 'edit',
        description: 'Purchase Manager: last bill + last GRN submit for your store, with automated-queue status, Automation settings (queue delay, production mode, message-type targets), and Received/Not-Ordered.',
      },
      {
        id: 'order-gap-review',
        label: 'Pending Supply Review',
        path: '/procurement/order-gap-review',
        status: MODULE_STATUS.READY,
        icon: 'edit',
        description: 'Purchase Manager: reconciliation since the store\'s last placed order -- ordered-but-not-received, received-but-not-ordered, and a persisted pending-reminder list.',
      },
      {
        id: 'legacy-order',
        label: 'Legacy Order',
        path: '/procurement/legacy-order',
        status: MODULE_STATUS.READY,
        icon: 'archive',
        description: 'Generate OrderNMC orders for stores in every tenant. Super admin only.',
      },
      {
        id: 'previous-order-comparison',
        label: 'Previous Order Comparison',
        path: '/procurement/previous-order-comparison',
        status: MODULE_STATUS.READY,
        icon: 'archive',
        description: 'Compare a store’s current order against a previous backup order, review supplier-by-supplier, and restore. Purchase Manager and super admin.',
      },
      {
        id: 'procurement-rules',
        label: 'Procurement Rules',
        path: '/procurement/rules',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'settings',
        description: 'Rules catalog. Overrides are not saved.',
      },
      {
        id: 'received-not-ordered',
        label: 'Received, Not Ordered',
        path: '/procurement/received-not-ordered',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'inbox',
        description: 'Supplier GRN lines received for products the app put on none of its orders. Read-only, as of the last sync.',
      },
    ],
  },
  {
    id: 'sales-reports',
    label: 'Sales & Reports',
    icon: 'reports',
    items: [
      {
        id: 'warehouse-bill-export',
        label: 'Warehouse Bill Export',
        path: '/inventory/warehouse-bill-export',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'reports',
        description: 'Warehouse dispatch bills.',
      },
      {
        id: 'sales-reports',
        label: 'Sales & Reports',
        path: '/sales-reports',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'reports',
        description: 'Report catalog. Sample-row report runs are not shown.',
      },
      {
        id: 'sale-analysis',
        label: 'Sale Analysis',
        path: '/sales-reports/sale-analysis',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'chart',
        description: 'Product lookup for sale analysis.',
      },
      {
        id: 'expiry-report',
        label: 'Expiry Report',
        path: '/sales-reports/expiry',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'pause',
        description: 'Store summary of supplier expiry.',
      },
      {
        id: 'expiry-stock',
        label: 'Expiry Stock',
        path: '/sales-reports/expiry-stock',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'pause',
        description: 'Cutting-expiry report for the selected store. A different report from Expiry Report.',
      },
      {
        id: 'time-report',
        label: 'Time Report',
        path: '/tools/time-report',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'monitor',
        description: 'Attendance source metadata.',
      },
    ],
  },
  {
    id: 'ai-intelligence',
    label: 'AI Intelligence',
    icon: 'spark',
    items: [
      {
        id: 'ai-intelligence',
        label: 'AI Intelligence',
        path: '/ai-intelligence',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'spark',
        description: 'Assisted pharmaceutical intelligence.',
      },
    ],
  },
  {
    id: 'system-administration',
    label: 'System & Administration',
    icon: 'admin',
    items: [
      {
        id: 'live-queries',
        label: 'Live Queries',
        path: '/sync/live-queries',
        status: MODULE_STATUS.READY,
        icon: 'network',
        description: 'Currently-executing requests on central OrderNMC, longest-running first, with a Kill action to release stuck locks. Super admin only.',
        sectionLabel: 'Synchronization',
      },
      {
        id: 'order-automation',
        label: 'Order Automation',
        path: '/administration/order-automation',
        status: MODULE_STATUS.READY,
        icon: 'network',
        description: 'Automated Order Entry settings (queue delay, production mode) and per-message-type WhatsApp targets, per store. Moved off the PM-facing Order Entry screen -- super admin only.',
        sectionLabel: 'Administration',
      },
      {
        id: 'sync-live',
        label: 'Sync Live',
        path: '/sync/live',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'network',
        description: 'Live per-store sync status and control-center snapshot.',
        sectionLabel: 'Synchronization',
      },
      {
        id: 'sync-history',
        label: 'Sync History',
        path: '/sync/history',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'archive',
        description: 'Completed sync runs and their statistics.',
      },
      {
        id: 'order-cache-monitor',
        label: 'Order Cache Monitor',
        path: '/sync/order-cache',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'network',
        description: 'Per-store local SQLite order cache: file age, last write-back, unsynced rows, force pull/push/import.',
        sectionLabel: 'Synchronization',
      },
      {
        id: 'device-control',
        label: 'Device Control',
        path: '/sync/device-control',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'monitor',
        description: 'Start, stop, pause, restart and update Nexora apps on enrolled PCs. Commands are the ones Device Control already sends.',
      },
      {
        id: 'remote-terminal',
        label: 'Remote Terminal',
        path: '/sync/terminal',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'monitor',
        description: 'Terminal session for an enrolled device.',
      },
      {
        id: 'administration',
        label: 'Administration',
        path: '/administration',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'admin',
        description: 'User directory for this login. No user is created here.',
        sectionLabel: 'Administration',
      },
      {
        id: 'platform-admin',
        label: 'Platform',
        path: '/administration/platform',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'identity',
        description: 'Roles and stores visible to this login. No role, store, user, or tenant is created, edited, or deactivated here.',
      },
      {
        id: 'document-extraction',
        label: 'Document Extraction',
        path: '/tools/document-extraction',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'scan',
        description: 'Invoice import history. Upload, OCR, review edits, and save/export are not sent from here.',
        sectionLabel: 'Tools',
      },
      {
        id: 'pass-gen',
        label: 'Pass Gen',
        path: '/tools/pass-gen',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'key',
        description: 'Generates a real store ordering passcode. This is a real generate call, not a dry run.',
      },
      {
        id: 'whatsapp',
        label: 'WhatsApp',
        path: '/tools/whatsapp',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'chat',
        description: 'Read-only WhatsApp bridge status (profiles, targets, send log). No message is composed or sent here.',
      },
      {
        id: 'settings',
        label: 'Settings',
        path: '/settings',
        status: MODULE_STATUS.IN_PROGRESS,
        icon: 'settings',
        description: 'Session and application details.',
      },
    ],
  },
];

/** Flat list kept for tests and callers that previously used NAV_SECTIONS. */
export const NAV_SECTIONS = NAV_GROUPS.flatMap((group) =>
  group.items.map((item) => ({ ...item, groupId: group.id, groupLabel: group.label }))
);

export function isNavItemEnabled(item) {
  return item.status !== MODULE_STATUS.PLANNED;
}

export function findNavItemByPath(pathname) {
  const normalized = pathname.replace(/\/$/, '') || '/';
  return NAV_SECTIONS.find((item) => item.path === normalized) ?? null;
}

export function breadcrumbsForPath(pathname) {
  const item = findNavItemByPath(pathname);
  if (!item) {
    return [{ label: 'Workspace', path: '/dashboard' }];
  }
  const crumbs = [{ label: item.groupLabel, path: item.groupId === 'dashboard' ? item.path : null }];
  if (item.label !== item.groupLabel) {
    crumbs.push({ label: item.label, path: item.path });
  }
  return crumbs;
}

export function searchNavItems(query) {
  const q = query.trim().toLowerCase();
  if (!q) return NAV_SECTIONS;
  return NAV_SECTIONS.filter(
    (item) =>
      item.label.toLowerCase().includes(q) ||
      item.groupLabel.toLowerCase().includes(q) ||
      (item.description || '').toLowerCase().includes(q)
  );
}

export function statusLabel(status) {
  if (status === MODULE_STATUS.READY) return 'Ready';
  if (status === MODULE_STATUS.IN_PROGRESS) return 'In progress';
  return 'Planned';
  if (pathname === '/help') return [{ label: 'Help & Guide', path: null }];
}
