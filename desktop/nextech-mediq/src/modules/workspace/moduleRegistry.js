import { apiGet, apiPost } from '../../api/client.js';

function query(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value == null || value === '') return;
    search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

function pinHeaders(pin) {
  return { 'x-quick-stock-pin': pin };
}

export const WORKSPACE_MODULES = {
  'network-stock': {
    title: 'Network Stock',
    description: 'Branches returned by the non-moving analysis store list. The heavier per-store dashboard is not loaded here because it did not return within the client timeout.',
    needsTenant: true,
    needsStore: false,
    autoLoad: true,
    load: ({ tenantId }) => apiGet(`/api/non-moving-analysis/stores${query({ tenant_id: tenantId })}`),
  },
  'stock-check': {
    title: 'Stock Check',
    description: 'Sublocation lookup, then the physical-count sheet for that range. Nothing is written.',
    needsTenant: true,
    needsStore: true,
    fields: [{ name: 'q', label: 'Sublocation', placeholder: 'Search a sublocation' }],
    load: ({ tenantId, storeId, q }) => {
      if (!q) return apiGet(`/api/stock-check-report/sublocations${query({ tenant_id: tenantId, store_id: storeId })}`);
      return apiGet(`/api/stock-check-report/rows${query({ tenant_id: tenantId, store_id: storeId, sublocation_from: q, sublocation_to: q })}`);
    },
  },
  'stock-integrity': {
    title: 'Stock Integrity',
    description: 'Compares batch stock with product total stock for the selected store. The repair route is not called.',
    needsTenant: true,
    needsStore: true,
    autoLoad: true,
    load: ({ tenantId, storeId }) => apiGet(`/api/stock-integrity/report${query({ tenant_id: tenantId, store_id: storeId })}`),
  },
  'product-mapping': {
    title: 'Product Mapping',
    description: 'Store product search used by the mapping workspace. Approvals and remaps are not sent.',
    needsTenant: true,
    needsStore: true,
    fields: [{ name: 'q', label: 'Product', required: true }],
    load: ({ tenantId, storeId, q }) => apiGet(`/api/product-mapping/products/search${query({ tenant_id: tenantId, store_id: storeId, q, limit: 50 })}`),
  },
  'warehouse-bill-export': {
    title: 'Warehouse Bill Export',
    description: 'Warehouse dispatch bills already on the server. Approval and purchase-entry writes are not sent.',
    needsTenant: true,
    needsStore: false,
    autoLoad: true,
    load: ({ tenantId, storeId }) => apiGet(`/api/nmw-sales-report/bills${query({ tenant_id: tenantId, store_id: storeId, status: 'all' })}`, { timeoutMs: 90000 }),
  },
  'quick-stock': {
    title: 'Quick Stock',
    description: 'Kiosk search. It uses the passcode header on the existing quick-stock routes, not a purchase or stock change. The passcode is kept in this page only.',
    needsTenant: true,
    needsStore: false,
    fields: [
      { name: 'pin', label: 'Passcode', type: 'password', required: true },
      { name: 'q', label: 'Product', required: true },
    ],
    load: async ({ tenantId, pin, q }) => {
      await apiPost('/api/quick-stock/verify', {}, { skipAuth: true, headers: pinHeaders(pin) });
      return apiGet(`/api/quick-stock/products/search${query({ tenant_id: tenantId, q, only_stock: 0 })}`, {
        skipAuth: true,
        headers: pinHeaders(pin),
      });
    },
  },
  'rate-analysis': {
    title: 'Rate Analysis',
    description: 'Suppliers with purchase value over the last 30 days. A 90-day pull did not return inside 20 seconds, so this screen uses the window that completed. Quote compare is not sent.',
    needsTenant: true,
    needsStore: false,
    autoLoad: true,
    load: ({ tenantId }) => apiGet(`/api/rate-analysis/suppliers${query({ tenant_id: tenantId, days: 30 })}`, { timeoutMs: 60000 }),
  },
  'procurement-workspace': {
    title: 'Procurement Workspace',
    description: 'Existing procurement cycles. This screen does not open a cycle, refresh, or submit a purchase order.',
    needsTenant: true,
    needsStore: false,
    autoLoad: true,
    load: ({ tenantId, storeId }) => apiGet(`/api/procurement/cycles${query({ tenant_id: tenantId, store_id: storeId, page: 1, page_size: 50 })}`),
  },
  'procurement-rules': {
    title: 'Procurement Rules',
    description: 'Rules catalog. Overrides are not saved. The decision engine is unchanged.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: () => apiGet('/api/procurement/rules/catalog'),
  },
  'order-workspace': {
    title: 'Order Workspace',
    description: 'Reads the current legacy order grid for one branch. It does not finalize, assign, export, or submit.',
    needsTenant: false,
    needsStore: false,
    choices: {
      load: async () => {
        const stores = await apiGet('/api/legacy-order/stores?active_only=true');
        const rows = Array.isArray(stores) ? stores : [];
        return rows.map((store) => ({
          value: store.store_name,
          label: store.display_name || store.store_name,
        }));
      },
      name: 'storeName',
      label: 'Branch',
    },
    load: ({ storeName }) => apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}`),
  },
  'order-entry': {
    title: 'Order Entry',
    description: 'Shows whether a legacy branch can start an order. The start-order route is not called.',
    needsTenant: false,
    needsStore: false,
    choices: {
      load: async () => {
        const stores = await apiGet('/api/legacy-order/stores?active_only=true');
        const rows = Array.isArray(stores) ? stores : [];
        return rows.map((store) => ({
          value: store.store_name,
          label: store.display_name || store.store_name,
        }));
      },
      name: 'storeName',
      label: 'Branch',
    },
    load: ({ storeName }) => apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/order-entry`),
  },
  'legacy-order': {
    title: 'Legacy Order',
    description: 'Database health and branch list. Recovery, repair, sync, and order process are not called.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: async () => {
      const [health, stores] = await Promise.all([
        apiGet('/api/legacy-order/db/health'),
        apiGet('/api/legacy-order/stores?active_only=true'),
      ]);
      const status = {};
      if (health && typeof health === 'object') {
        Object.entries(health).forEach(([key, value]) => {
          if (value == null || ['string', 'number', 'boolean'].includes(typeof value)) status[`db_${key}`] = value;
        });
      }
      const rows = Array.isArray(stores) ? stores : [];
      return { rows: rows.map((store) => ({ ...status, ...store })) };
    },
  },
  'sales-reports': {
    title: 'Sales & Reports',
    description: 'Report catalog only. Running a report is withheld: that API substitutes unlabeled sample rows when a query comes back empty.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: () => apiGet('/api/reports'),
  },
  'expiry-report': {
    title: 'Expiry Report',
    description: 'Store summary of supplier expiry. Settlement writes are not sent.',
    needsTenant: true,
    needsStore: false,
    autoLoad: true,
    load: ({ tenantId }) => apiGet(`/api/expiry-report/store-summary${query({ tenant_id: tenantId })}`),
  },
  'sale-analysis': {
    title: 'Sale Analysis',
    description: 'Product lookup for the selected store. Saving analysis groups is not sent.',
    needsTenant: true,
    needsStore: true,
    fields: [{ name: 'q', label: 'Product', required: true }],
    load: ({ tenantId, storeId, q }) => apiGet(`/api/sale-analysis/products${query({ tenant_id: tenantId, store_id: storeId, q, limit: 50 })}`),
  },
  'time-report': {
    title: 'Time Report',
    description: 'Attendance source metadata. Daily and monthly sheets load only after this call succeeds.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: () => apiGet('/api/time-report/meta'),
  },
  'sync-live': {
    title: 'Sync Live',
    description: 'Live per-store sync status from the control-center snapshot. No sync task is queued from here.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: () => apiGet('/api/sync/control-center'),
  },
  'sync-history': {
    title: 'Sync History',
    description: 'Completed sync runs and their statistics. Nothing here re-runs or cancels a sync.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: async () => {
      const [history, stats] = await Promise.all([
        apiGet('/api/sync/history?limit=50'),
        apiGet('/api/sync/history/statistics').catch(() => null),
      ]);
      const rows = Array.isArray(history) ? history : history?.items || history?.rows || [];
      if (stats && typeof stats === 'object' && !Array.isArray(stats)) {
        return { rows: rows.map((row) => ({ ...row })), summary: stats };
      }
      return { rows };
    },
  },
  'store-health': {
    title: 'Store Health',
    description: 'Per-store agent reachability and staleness, as used for sync alerting. Read-only.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: () => apiGet('/api/sync/store-health'),
  },
  'device-control': {
    title: 'Device Control',
    description: 'Devices enrolled with Device Controller. No command, revoke, or terminal session is sent from here.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: () => apiGet('/api/device-controller/devices'),
  },
  administration: {
    title: 'Administration',
    description: 'Users visible to this login. Creating users, roles, or permissions is not sent.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    fields: [{ name: 'q', label: 'Search users', placeholder: 'Username or name' }],
    load: ({ tenantId, q }) => apiGet(`/api/users${query({ tenant_id: tenantId, search: q })}`),
  },
  'document-extraction': {
    title: 'Document Extraction',
    description: 'Invoice import history for the selected tenant/store. Upload, OCR, review edits, and save/export are not sent from here.',
    needsTenant: true,
    needsStore: false,
    autoLoad: true,
    fields: [{ name: 'q', label: 'Store ID', placeholder: 'Optional store_id filter' }],
    load: ({ tenantId, q }) => apiGet(`/api/document-extraction/imports${query({ tenant_id: tenantId, store_id: q, page: 1, page_size: 25 })}`),
  },
  'expiry-stock': {
    title: 'Expiry Stock',
    description: 'Cutting-expiry report for the selected store. Supplier and date-range filters are read from the server; nothing is settled or exported from here.',
    needsTenant: true,
    needsStore: true,
    fields: [{ name: 'q', label: 'Supplier code', placeholder: 'Optional supplier filter' }],
    load: ({ tenantId, storeId, q }) => apiGet(`/api/expiry-stock/report${query({ tenant_id: tenantId, store_id: storeId, supplier_code: q })}`),
  },
  'pass-gen': {
    title: 'Pass Gen',
    description: 'Generates a real store ordering passcode from the live backend for the chosen store/day-window. This performs the same generate call as the web Pass Gen page — it is not a dry run.',
    notice: 'This generates a live ordering passcode. It is not a dry run.',
    needsTenant: false,
    needsStore: false,
    choices: {
      load: async () => {
        const stores = await apiGet('/api/pass-gen/stores');
        const rows = Array.isArray(stores) ? stores : [];
        return rows.map((store) => ({ value: store.store_id, label: `${store.store_code} - ${store.store_name || ''}` }));
      },
      name: 'storeId',
      label: 'Store',
    },
    fields: [
      { name: 'minDays', label: 'Min days', placeholder: '13' },
      { name: 'maxDays', label: 'Max days', placeholder: '18' },
    ],
    load: ({ storeId, minDays, maxDays }) => apiPost('/api/pass-gen/generate', {
      order_no: 1,
      target_date: new Date().toISOString().slice(0, 10),
      rows: [{
        row_id: 'r1',
        store_ids: storeId ? [storeId] : [],
        min_days: Number(minDays) || 13,
        max_days: Number(maxDays) || 18,
        order_yes: 1,
        compare_last_order: 0,
      }],
    }),
  },
  'platform-admin': {
    title: 'Platform',
    description: 'Roles and stores visible to this login. No role, store, user, or tenant is created, edited, or deactivated here.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: async () => {
      const [roles, stores] = await Promise.all([
        apiGet('/api/roles'),
        apiGet('/api/stores'),
      ]);
      const roleRows = Array.isArray(roles) ? roles : [];
      const storeRows = Array.isArray(stores) ? stores : [];
      return {
        rows: roleRows.map((role) => ({
          kind: 'role',
          role_name: role.role_name || role.name,
          is_active: role.is_active,
          id: role.role_id || role.id,
        })).concat(storeRows.map((store) => ({
          kind: 'store',
          role_name: store.store_code || store.store_name,
          is_active: store.is_active,
          id: store.store_id,
        }))),
      };
    },
  },
  'received-not-ordered': {
    title: 'Received, Not Ordered',
    description: 'Supplier GRN lines received since the previous active day\'s first order for products the app put on none of its orders. Reads central OrderNMC as of the last sync; nothing is written.',
    needsTenant: false,
    needsStore: false,
    choices: {
      load: async () => {
        const stores = await apiGet('/api/legacy-order/stores?active_only=true');
        const rows = Array.isArray(stores) ? stores : [];
        return rows.map((store) => ({ value: store.store_name, label: store.display_name || store.store_name }));
      },
      name: 'storeName',
      label: 'Branch',
    },
    fields: [{ name: 'productType', label: 'Product type', placeholder: 'pharma / non_pharma / all' }],
    load: ({ storeName, productType }) => apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/received-not-ordered${query({ product_type: productType || 'pharma' })}`),
  },
  whatsapp: {
    title: 'WhatsApp',
    description: 'Read-only session/profile status from the store-level WhatsApp bridge (profiles, targets, capabilities, send log). No message is composed or sent from this screen.',
    needsTenant: false,
    needsStore: false,
    autoLoad: true,
    load: () => apiGet('/api/whatsapp/state'),
  },
};

export function workspaceModule(id) {
  return WORKSPACE_MODULES[id] || null;
}
