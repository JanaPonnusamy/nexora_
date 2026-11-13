// NEXORA MEDIQ Phase 6B: ERP navigation hierarchy data. Pure data/lookup
// module (no JSX) so both the sidebar component and App.jsx's breadcrumb
// header can share one source of truth, same pattern as navMenu.jsx's
// NAV_GROUPS but one level deeper (section > screen, not just group > screen).
//
// Every entry's `screen` id must exist in App.jsx's `screens` array. This
// does not replace that array or any existing visibility-gating function
// (isSuperAdmin, isSmsPurchaseManagerOnly, etc.) -- it only maps each
// already-permitted screen id to its place in the new ERP hierarchy. A
// screen the session's existing navItems filter excludes is simply not
// rendered here either (see buildErpSections in ErpSidebar.jsx).
//
// Section keys match doc 28A S4's mapping table exactly.
export const ERP_SECTIONS = [
  {
    key: 'dashboard',
    label: 'Dashboard',
    icon: 'dashboard',
    screens: ['dashboard'],
  },
  {
    key: 'masters',
    label: 'Masters',
    icon: 'masters',
    screens: ['user_management', 'role_management', 'permission_management'],
  },
  {
    key: 'procurement',
    label: 'Procurement',
    icon: 'procurement',
    screens: [
      'procurement_workspace',
      'order_workspace',
      'order_entry',
      'legacy_order',
      'analysis',
      'rate_analysis',
    ],
  },
  {
    key: 'inventory',
    label: 'Inventory',
    icon: 'inventory',
    screens: ['stock', 'stock_vertical', 'network_stock', 'non_moving', 'nmw_sales'],
  },
  {
    key: 'sales_reports',
    label: 'Sales & Reports',
    icon: 'reports',
    screens: ['time_report'],
  },
  {
    key: 'tools',
    label: 'Tools',
    icon: 'tools',
    screens: ['whatsapp', 'sync_live', 'label_exporter', 'schema_sync'],
  },
  {
    key: 'administration',
    label: 'Administration',
    icon: 'admin',
    screens: ['settings', 'audit_logs'],
  },
];

// Short section label shown in the breadcrumb/header when a screen is open.
export function erpSectionForScreen(screenId) {
  return ERP_SECTIONS.find((section) => section.screens.includes(screenId)) || null;
}

// Builds the sidebar's actual render list: each section paired with only
// the screens from `allItems` (the session's already-permission-filtered
// nav items) that belong to it, in ERP_SECTIONS' declared order. A screen
// present in allItems but not mapped to any section (should not happen --
// every id in App.jsx's `screens` array has a home above) falls into a
// trailing 'Other' section instead of silently disappearing.
export function buildErpSections(allItems) {
  const byId = new Map(allItems.map((item) => [item.id, item]));
  const used = new Set();
  const sections = [];

  for (const section of ERP_SECTIONS) {
    const items = section.screens
      .map((id) => byId.get(id))
      .filter(Boolean);
    items.forEach((item) => used.add(item.id));
    if (items.length) sections.push({ ...section, items });
  }

  const leftover = allItems.filter((item) => !used.has(item.id));
  if (leftover.length) {
    sections.push({ key: 'other', label: 'Other', icon: 'other', items: leftover });
  }

  return sections;
}
