// Permission-aware navigation. This hides entries the signed-in role is not
// meant to see. It is not authorization. Every API call is still checked
// server-side (tenant scope, role dependencies, module grants).
//
// Role order matches supplier-stock-client's nav gates for the screens this
// app actually has. Planned entries stay planned; a grant never marks them ready.

import { NAV_GROUPS, NAV_SECTIONS, isNavItemEnabled } from './navConfig.js';

const STOCK_FAMILY = new Set(['stock-enquiry', 'network-stock']);
const INVENTORY_READS = new Set(['stock-check', 'stock-integrity', 'product-mapping', 'warehouse-bill-export', 'quick-stock', 'label-export']);
const SALES_FAMILY = new Set(['sales-reports', 'expiry-report', 'sale-analysis']);
const PURCHASE_FAMILY = new Set([
  'procurement-workspace',
  'procurement-rules',
  'order-workspace',
  'order-entry',
  'rate-analysis',
  'non-moving-stock',
  'previous-order-comparison',
]);
const SUPER_ONLY = new Set(['administration', 'platform-admin', 'legacy-order', 'sync-live', 'sync-history', 'store-health', 'device-control', 'remote-terminal']);

function normalizedRoleNames(user) {
  return (user?.roles || [])
    .map((role) => String(role?.role_name || role?.role || '').toLowerCase().replace(/[^a-z]/g, ''))
    .filter(Boolean);
}

export function isSuperAdmin(user) {
  if (user?.is_platform_user) return true;
  return normalizedRoleNames(user).some((name) => name.includes('superadmin') || name.includes('platformowner'));
}

export function isStockViewerOnly(user) {
  const names = normalizedRoleNames(user);
  return names.length > 0 && names.every((name) => name.includes('stockviewer'));
}

export function isLabelReviewOnly(user) {
  const names = normalizedRoleNames(user);
  return names.length > 0 && names.every((name) => name.includes('labelreview') || name.includes('reviewonly'));
}

export function isStockAndLabelViewer(user) {
  const names = normalizedRoleNames(user);
  if (!names.length) return false;
  return names.every((name) => name.includes('stockviewer') || name.includes('labelreview'));
}

export function isSmsPurchaseManagerOnly(user) {
  const names = normalizedRoleNames(user);
  return names.length > 0 && names.every((name) => name.includes('smspurchasemanager'));
}

export function isSalesmanOnly(user) {
  const names = normalizedRoleNames(user);
  if (!names.length) return false;
  return names.every((name) => name.includes('salesman'));
}

export function canViewPurchase(user) {
  return (user?.roles || []).some((role) =>
    String(role?.role_name || role?.role || '').toLowerCase().includes('purchase')
  );
}

export function isSupplierAnalysisBlocked(user) {
  const names = (user?.roles || []).map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  if (!names.length) return false;
  return names.every((name) => name.includes('purchase') || name.includes('salesman') || name.includes('sales man'));
}

// A module entry with can_view:false is an explicit denial, not merely
// "not granted" — it must be tracked separately from the allowed set, or
// a user with ONLY denied modules ends up with an empty allow-list, which
// (per the "no grants at all" fallback below) reads as "ungated," unlocking
// exactly the module that was denied.
export function viewableModuleCodes(user) {
  const modules = user?.modules || [];
  return modules
    .filter((item) => {
      if (typeof item === 'string') return true;
      if (item?.can_view === false) return false;
      return Boolean(item?.module || item?.module_code);
    })
    .map((item) => String(typeof item === 'string' ? item : item.module || item.module_code).toLowerCase());
}

export function deniedModuleCodes(user) {
  const modules = user?.modules || [];
  return modules
    .filter((item) => typeof item !== 'string' && item?.can_view === false)
    .map((item) => String(item.module || item.module_code || '').toLowerCase())
    .filter(Boolean);
}

function hasModule(modules, codes) {
  return codes.some((code) => modules.includes(String(code).toLowerCase()));
}

function stockModuleAllowed(superAdmin, modules, denied, moduleFilter) {
  if (!superAdmin && hasModule(denied, ['stock_availability', 'stock'])) return false;
  if (!moduleFilter) return true;
  return hasModule(modules, ['stock_availability', 'stock']);
}

export function visibleNavGroups(user) {
  const allowed = new Set(visibleNavItems(user).map((item) => item.id));
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => allowed.has(item.id)),
  })).filter((group) => group.items.length > 0);
}

export function visibleNavItems(user) {
  if (!user) return [];
  if (isLabelReviewOnly(user)) {
    return NAV_SECTIONS.filter((item) => item.id === 'settings' || item.id === 'label-export');
  }
  if (isStockViewerOnly(user)) {
    return NAV_SECTIONS.filter((item) => STOCK_FAMILY.has(item.id));
  }
  if (isStockAndLabelViewer(user)) {
    return NAV_SECTIONS.filter((item) => STOCK_FAMILY.has(item.id) || item.id === 'label-export');
  }
  if (isSmsPurchaseManagerOnly(user)) {
    const ids = new Set([
      'stock-enquiry',
      'network-stock',
      'procurement-workspace',
      'supplier-stock',
      'supplier-stock-list',
      'order-entry',
      'previous-order-comparison',
      'settings',
    ]);
    return NAV_SECTIONS.filter((item) => ids.has(item.id));
  }

  const superAdmin = isSuperAdmin(user);
  const purchase = canViewPurchase(user);
  const salesmanOnly = isSalesmanOnly(user);
  const modules = viewableModuleCodes(user);
  const denied = deniedModuleCodes(user);
  const moduleFilter = modules.length > 0 && !superAdmin;

  return NAV_SECTIONS.filter((item) => {
    if (item.id === 'dashboard' || item.id === 'settings') return true;
    if (SUPER_ONLY.has(item.id)) return superAdmin;
    if (PURCHASE_FAMILY.has(item.id)) return superAdmin || purchase;
    if (SALES_FAMILY.has(item.id)) return !salesmanOnly;
    if (item.id === 'time-report') {
      if (salesmanOnly) return false;
      if (!moduleFilter) return true;
      return hasModule(modules, ['time_report', 'reports']);
    }
    if (INVENTORY_READS.has(item.id) || STOCK_FAMILY.has(item.id)) {
      return stockModuleAllowed(superAdmin, modules, denied, moduleFilter);
    }
    if (item.id === 'supplier-stock' || item.id === 'supplier-stock-list') {
      if (isSupplierAnalysisBlocked(user)) return false;
      if (!superAdmin && hasModule(denied, ['supplier_stock_analysis', 'analysis'])) return false;
      if (!moduleFilter) return true;
      return hasModule(modules, ['supplier_stock_analysis', 'analysis']);
    }
    if (moduleFilter) return false;
    return true;
  });
}

// Returns a path when the current route is not in the visible nav.
// Null means the current path can stay.
const EXTRA_PREFIXES = {
  'document-extraction': ['/document-extraction'],
  'legacy-order': ['/legacy-order'],
  'platform-admin': ['/platform'],
  'label-export': ['/label-exporter', '/inventory/box-workspace'],
  'order-entry': ['/procurement/order-workspace'],
  'non-moving-stock': ['/inventory/non-moving-report'],
  'sync-live': [
    '/sync/schedules',
    '/sync/config',
    '/sync/mapping',
    '/sync/agents',
    '/sync/devices',
    '/sync/mail-transfer',
    '/sync/ho-routes',
    '/sync/backend-update',
  ],
};

function pathMatches(item, path) {
  if (path === item.path || path.startsWith(`${item.path}/`)) return true;
  return (EXTRA_PREFIXES[item.id] || []).some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
}

export function resolvePathForUser(user, pathname) {
  const allowed = visibleNavItems(user);
  if (!allowed.length) return '/dashboard';
  const path = pathname || '/';
  if (allowed.some((item) => pathMatches(item, path))) return null;
  const next = allowed.find((item) => isNavItemEnabled(item)) || allowed[0];
  return next?.path || '/dashboard';
}
