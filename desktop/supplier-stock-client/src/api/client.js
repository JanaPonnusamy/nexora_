import { loadSettings } from '../state/session.js';

function joinUrl(baseUrl, path) {
  const base = String(baseUrl || '').replace(/\/+$/, '');
  const suffix = String(path || '').replace(/^\/+/,'');
  return `${base}/${suffix}`;
}

function authHeaders(session) {
  const token = session?.token || session?.accessToken || session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const TRANSIENT_STATUS = new Set([408, 425, 429, 502, 503, 504]);
const RETRY_DELAYS_MS = [350, 1000];

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    if (!signal) return;
    signal.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

// FastAPI error bodies aren't always a plain string: 422 validation errors send
// `detail` as a list of {loc, msg, type} objects, and some handlers raise
// HTTPException(detail=<dict>). Passing any of those straight into `new
// Error(x)` silently stringifies it to the useless literal "[object Object]"
// (or comma-joined objects for arrays) - extract real, readable text instead.
function detailToMessage(data) {
  const detail = data?.detail ?? data?.message ?? data?.error;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'string' ? item : `${(item?.loc || []).join('.')}: ${item?.msg || JSON.stringify(item)}`))
      .join('; ');
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail);
  return detail || '';
}

async function request(path, options = {}) {
  const settings = loadSettings();
  const session = options.session;
  const timeoutMs = options.timeoutMs ?? 45000;
  const method = String(options.method || 'GET').toUpperCase();
  const retries = options.transientRetries ?? (method === 'GET' ? RETRY_DELAYS_MS.length : 0);
  const { session: _session, timeoutMs: _timeoutMs, transientRetries: _transientRetries, ...fetchOptions } = options;
  let response;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
    const onCallerAbort = () => controller.abort();
    if (options.signal) {
      if (options.signal.aborted) controller.abort();
      else options.signal.addEventListener('abort', onCallerAbort, { once: true });
    }
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, path), {
        ...fetchOptions,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
          ...authHeaders(session),
          ...(options.headers || {})
        }
      });
      if (!TRANSIENT_STATUS.has(response.status) || attempt === retries) break;
      // Drain the body so Chromium can reuse the keep-alive connection.
      await response.arrayBuffer().catch(() => {});
    } catch (err) {
      if (options.signal?.aborted) throw err;
      if (timedOut) throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
      if (attempt === retries) throw err;
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', onCallerAbort);
    }
    await delay(RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)], options.signal);
  }

  const text = await response.text();
  const data = text ? safeJson(text) : null;

  if (!response.ok) {
    const message = detailToMessage(data) || `Request failed with ${response.status}`;
    // A 401 here means the stored token is missing/expired/invalid for a
    // request that did carry a session - the UI would otherwise sit showing
    // "Request failed with 401" on every panel forever with no way out. Let
    // the app shell know so it can drop back to the login screen.
    if (response.status === 401 && session) {
      window.dispatchEvent(new CustomEvent('nexora:unauthorized'));
    }
    throw new Error(message);
  }

  return data;
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function toQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, value);
    }
  });
  const value = query.toString();
  return value ? `?${value}` : '';
}

export const api = {
  login(credentials) {
    return request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials)
    });
  },

  // Release the server-side active session on explicit sign-out so the user can
  // immediately sign in on another PC (single-session policy) instead of waiting
  // for the lease to lapse. Best-effort - callers ignore failures.
  logout(session) {
    return request('/api/auth/logout', { method: 'POST', session });
  },

  async testConnection({ apiBaseUrl, bootstrapUrl }) {
    const target = bootstrapUrl || apiBaseUrl;
    const response = await fetch(joinUrl(target, bootstrapUrl ? '' : '/health'), {
      method: 'GET',
      headers: { Accept: 'application/json' }
    });
    if (!response.ok) {
      throw new Error(`Connection failed with ${response.status}`);
    }
    return { ok: true, status: response.status };
  },

  // Public discovery (no session, hits a caller-specified host rather than the
  // saved apiBaseUrl - this is how Settings can probe a candidate HO before
  // the user commits to it).
  async getBootstrapRoutes(baseUrl) {
    const response = await fetch(joinUrl(baseUrl, '/api/bootstrap/routes'), {
      method: 'GET',
      headers: { Accept: 'application/json' }
    });
    if (!response.ok) throw new Error(`Discovery failed with ${response.status}`);
    return response.json();
  },

  // Super-admin maintenance of the HO route list itself (add/edit/delete),
  // against whichever HO the device is currently pointed at.
  listHoRoutes(session) {
    return request('/api/ho-routes', { session });
  },

  createHoRoute(payload, session) {
    return request('/api/ho-routes', { method: 'POST', session, body: JSON.stringify(payload) });
  },

  updateHoRoute(routeId, payload, session) {
    return request(`/api/ho-routes/${routeId}`, { method: 'PUT', session, body: JSON.stringify(payload) });
  },

  deleteHoRoute(routeId, session) {
    return request(`/api/ho-routes/${routeId}`, { method: 'DELETE', session });
  },

  listTenants(session) {
    return request('/api/tenants', { session });
  },

  listStores(session) {
    // Inactive stores are hidden from every selector in the client.
    return request('/api/stores', { session }).then((rows) => (
      Array.isArray(rows) ? rows.filter((s) => s.is_active !== false) : rows
    ));
  },

  requestActivation(payload, session) {
    return request('/api/desktop-client/activate/request', {
      method: 'POST',
      session,
      body: JSON.stringify(payload)
    });
  },

  // Public (no session): a freshly-installed PC polls its own config by
  // client_id to learn when HO has approved it and which store it was bound to.
  getDesktopConfig(clientId) {
    return request(`/api/desktop-client/config${toQuery({ client_id: clientId })}`);
  },

  listDesktopDevices(session) {
    return request('/api/desktop-client/devices', { session });
  },

  approveDesktopDevice(clientId, payload, session) {
    return request(`/api/desktop-client/devices/${clientId}/approve`, {
      method: 'POST',
      session,
      body: JSON.stringify(payload)
    });
  },

  getWhatsAppState(session) {
    return request('/api/whatsapp/state', { session });
  },

  saveWhatsAppSettings(payload, session) {
    return request('/api/whatsapp/settings', {
      method: 'PUT',
      session,
      body: JSON.stringify(payload)
    });
  },

  saveWhatsAppProfile(payload, session) {
    return request('/api/whatsapp/profiles', {
      method: 'POST',
      session,
      body: JSON.stringify(payload)
    });
  },

  launchWhatsAppProfile(profileId, session) {
    return request(`/api/whatsapp/profiles/${profileId}/launch`, {
      method: 'POST',
      session,
      body: JSON.stringify({})
    });
  },

  deleteWhatsAppProfile(profileId, session) {
    return request(`/api/whatsapp/profiles/${profileId}`, {
      method: 'DELETE',
      session
    });
  },

  searchStockProducts(query, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/search${toQuery({
      tenant_id: settings.tenantId,
      q: query,
      only_stock: filters.onlyStock ? 1 : 0
    })}`, { session });
  },

  // Compact full-catalogue index (code/name/unit/stock) that seeds + refreshes
  // the permanent local cache (see lib/productIndexCache.js). Larger payload, so
  // a generous timeout; called in the background, not on the keystroke path.
  getProductIndex(session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/index${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: filters.storeId || ''
    })}`, { session, timeoutMs: filters.timeoutMs || 120000 });
  },

  // Tab 2 of the web Stock Availability screen — search by batch number, MRP
  // and/or product name across branches (same {stores:[...]} shape as
  // searchStockProducts, so callers can render either result identically).
  searchStockBatches(query, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/batches/search${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      batch: query.batch || '',
      mrp: query.mrp || '',
      product: query.product || ''
    })}`, { session });
  },

  getProductDashboard(productCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/products/${productCode}/dashboard${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      source_store_id: filters.sourceStoreId,
      months: filters.months || 6
    })}`, { session, signal: filters.signal });
  },

  // Store-wide (not supplier-scoped) stock-status counts for the NMW-Stock
  // filter dropdown - see backend/modules/supplier_stock_analysis/router.py.
  getWarehouseStockCounts(tenantId, storeId, session, filters = {}) {
    return request(`/api/supplier-stock-analysis/warehouse-stock/counts${toQuery({
      tenant_id: tenantId,
      store_id: storeId
    })}`, { session, signal: filters.signal });
  },

  // The store's own product catalogue filtered by stock status, independent
  // of any supplier selection.
  getWarehouseStockProducts(tenantId, storeId, stockFilter, session, filters = {}) {
    return request(`/api/supplier-stock-analysis/warehouse-stock/products${toQuery({
      tenant_id: tenantId,
      store_id: storeId,
      stock_filter: stockFilter,
      search: filters.search || ''
    })}`, { session, signal: filters.signal });
  },
  getStockCore(storeId, productCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/core${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      product: productCode,
      months: filters.months || 3
    })}`, { session });
  },

  // Cross-store product-selection sync (see backend
  // modules/stock_availability/service.py:match_cross_store_selection): for a
  // product selected in one store, resolve its equivalent in every other
  // store via SupplierProductMatch -> normalized name -> structured
  // attributes -> relevance-scored fuzzy candidate.
  syncStockSelection(sourceStoreId, sourceProductCode, sourceProductName, targetStoreIds, session, filters = {}) {
    const settings = loadSettings();
    return request('/api/stock-availability/products/sync-selection', {
      method: 'POST',
      session,
      body: JSON.stringify({
        tenant_id: filters.tenantId || settings.tenantId,
        source_store_id: sourceStoreId,
        source_product_code: sourceProductCode,
        source_product_name: sourceProductName,
        target_store_ids: targetStoreIds || []
      })
    });
  },

  getStockCoreBulk(items, session, filters = {}) {
    const settings = loadSettings();
    return request('/api/stock-availability/products/core/bulk', {
      method: 'POST',
      session,
      body: JSON.stringify({
        tenant_id: filters.tenantId || settings.tenantId,
        months: filters.months || 3,
        items: items || []
      })
    });
  },

  getStockBatches(storeId, productCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/batches${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      product: productCode
    })}`, { session });
  },

  getBatchDetail(storeId, productCode, batchNo, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/batch-detail${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      product: productCode,
      batch: batchNo
    })}`, { session });
  },

  getStockPurchases(storeId, productCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/purchases${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      product: productCode
    })}`, { session });
  },

  getStockSales(storeId, productCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/sales${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      product: productCode
    })}`, { session });
  },

  getStockMovement(storeId, productCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/movement${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      product: productCode,
      months: filters.months || 3
    })}`, { session });
  },


  getBillItems(storeId, billNo, billDate, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/bill${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      bill_no: billNo,
      bill_date: billDate ? String(billDate).slice(0, 10) : ''
    })}`, { session });
  },
  getMatchCandidates(storeId, name, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/product-mapping/candidates${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      target_store_id: storeId,
      name,
      limit: filters.limit || 8
    })}`, { session });
  },

  getSuppliers(session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/suppliers${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      // Honor an explicit storeId even when it's '' (super admin lists at tenant
      // level); only fall back to the device store when unspecified.
      store_id: filters.storeId !== undefined ? filters.storeId : settings.storeId,
      search: filters.search || ''
    })}`, { session });
  },

  getSupplierProducts(supplierCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/supplier-products${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: filters.storeId !== undefined ? filters.storeId : settings.storeId,
      supplier_code: supplierCode,
      search: filters.search || '',
      only_available: filters.onlyAvailable ?? 1
    })}`, {
      session,
      // The underlying query cold-reads from disk on the DB server (limited
      // RAM there means product_mapping/Products pages routinely fall out of
      // the buffer pool between uses) -- a first touch for a given supplier
      // can legitimately take ~35-40s even though it's back down to ~1-2s on
      // a warm cache. That's right at the default 45s wall, so a slightly
      // busy moment tips it into a client-side timeout even though the query
      // would have finished. Not a query-design problem (verified directly
      // against the DB); this just gives the cold case room to land. 180s
      // also covers a backend still running the pre-f02dd04 query (~90s for
      // a 3000-line supplier) until it is restarted.
      timeoutMs: 180000
    });
  },

  getSupplierAnalysisReport(supplierCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/supplier-report${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: filters.storeId || settings.storeId,
      supplier_code: supplierCode,
      only_available: filters.onlyAvailable ?? 0
    })}`, { session });
  },

  getSupplierDashboard(supplierStockId, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/supplier-stock/${supplierStockId}/dashboard${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      months: filters.months || 6
    })}`, { session });
  },

  // Fast stage: match resolution + stock/summary for every store in one
  // batched query - no batches/purchases/sales/movement history.
  getSupplierDashboardStock(supplierStockId, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/supplier-stock/${supplierStockId}/dashboard/stock${toQuery({
      tenant_id: filters.tenantId || settings.tenantId
    })}`, { session, signal: filters.signal });
  },

  // Second stage: batches/purchases/sales/movement history, fetched once the
  // stock stage has resolved a product_code + source_store_id.
  getSupplierDashboardDetails(supplierStockId, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/supplier-stock/${supplierStockId}/dashboard/details${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      source_store_id: filters.sourceStoreId,
      product_code: filters.productCode,
      months: filters.months || 6
    })}`, { session, signal: filters.signal });
  },

  matchSupplierStock(supplierStockId, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/supplier-stock/${supplierStockId}/match${toQuery({
      tenant_id: filters.tenantId || settings.tenantId
    })}`, { session });
  },

  // The store's OrderNMC supplier list (Excel import choices).
  getOrderSuppliers(tenantId, storeId, session) {
    return request(`/api/supplier-stock-analysis/order-suppliers${toQuery({
      tenant_id: tenantId || loadSettings().tenantId,
      store_id: storeId
    })}`, { session });
  },

  // tenantId/storeId/supplierCode (optional) pre-fill the supplier's saved mapping.
  previewSupplierExcel(file, session, { tenantId, storeId, supplierCode } = {}) {
    const form = new FormData();
    form.append('file', file);
    if (storeId && supplierCode) {
      form.append('tenant_id', tenantId || loadSettings().tenantId);
      form.append('store_id', storeId);
      form.append('supplier_code', supplierCode);
    }
    return request('/api/supplier-stock-analysis/excel/preview', {
      method: 'POST',
      session,
      body: form
    });
  },

  importSupplierExcel({ tenantId, storeId, supplierCode, mapping, file, importedBy }, session) {
    const settings = loadSettings();
    const form = new FormData();
    form.append('tenant_id', tenantId || settings.tenantId);
    form.append('store_id', storeId || settings.storeId);
    form.append('supplier_code', supplierCode);
    form.append('mapping_json', JSON.stringify(mapping));
    if (importedBy) form.append('imported_by', importedBy);
    form.append('file', file);
    // Replace + reinsert of a large supplier file can outlast the 45s default.
    return request('/api/supplier-stock-analysis/excel/import', {
      method: 'POST',
      session,
      body: form,
      timeoutMs: 180000
    });
  },

  bulkImportStores(tenantId, supplierCode, session) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/excel/bulk-stores${toQuery({
      tenant_id: tenantId || settings.tenantId,
      supplier_code: supplierCode
    })}`, { session });
  },

  importSupplierExcelBulk({ tenantId, supplierCode, mapping, storeIds, file, importedBy }, session) {
    const settings = loadSettings();
    const form = new FormData();
    form.append('tenant_id', tenantId || settings.tenantId);
    form.append('supplier_code', supplierCode);
    form.append('mapping_json', JSON.stringify(mapping));
    if (storeIds) form.append('store_ids_json', JSON.stringify(storeIds));
    if (importedBy) form.append('imported_by', importedBy);
    form.append('file', file);
    // Replace + reinsert across every store can outlast the 45s default.
    return request('/api/supplier-stock-analysis/excel/import-bulk', {
      method: 'POST',
      session,
      body: form,
      timeoutMs: 300000
    });
  },

  getNonMovingStock(storeId, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/reports/non-moving/highlights${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      dwell_days: filters.dwellDays || 60,
      min_pur_age: filters.minPurAge || 10,
      limit: filters.limit || 50
    })}`, { session });
  },

  getNonMovingTotals(storeId, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/reports/non-moving/totals${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      sales_age: filters.salesAge || 90,
      grn_age: filters.grnAge || 10
    })}`, { session });
  },

  updateSupplierMapping(payload, session) {
    return request('/api/supplier-stock-analysis/mapping', {
      method: 'POST',
      session,
      body: JSON.stringify(payload)
    });
  },

  // Warehouse-zero-stock lines the branches are selling, with each branch's
  // 1-month need. Kept warm server-side; only the very first call after a
  // backend restart computes inline (slow on a cold DB), hence the long timeout.
  getSupplierStoreNeed(supplierCode, session, filters = {}) {
    return request(`/api/supplier-stock-analysis/store-need${toQuery({
      tenant_id: filters.tenantId,
      store_id: filters.storeId,
      supplier_code: supplierCode
    })}`, { session, timeoutMs: 240000 });
  },

  getTodaySupplierAssignments(session, filters = {}) {
    return request(`/api/supplier-stock-analysis/assignments/today${toQuery({
      tenant_id: filters.tenantId,
      store_id: filters.storeId
    })}`, { session });
  },

  saveSupplierAssignments(payload, session) {
    return request('/api/supplier-stock-analysis/assignments', {
      method: 'PUT',
      session,
      body: JSON.stringify(payload)
    });
  },

  // NMW Sales Report (Bill-wise). store_id is passed only when the caller wants
  // to narrow to one store; a super admin omits it to see every store. The
  // server also enforces scoping (store users are locked to their own stores).
  getNmwSalesBills(session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/nmw-sales-report/bills${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: filters.storeId || '',
      status: filters.status || 'all',
      date_from: filters.dateFrom || '',
      date_to: filters.dateTo || '',
      purchase_status: filters.purchaseStatus || 'all'
    })}`, { session });
  },

  getNmwSalesBillItems(billNo, billDate, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/nmw-sales-report/bills/${encodeURIComponent(billNo)}/items${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      bill_date: billDate ? String(billDate).slice(0, 10) : ''
    })}`, { session });
  },

  // Store-side purchase-entry (GRN) status for one NMW bill. The /bills list
  // already carries a per-bill purchase_status from a single batched lookup, so
  // this per-bill call is only for the detail pane (never fired in a loop over
  // the list).
  getNmwPurchaseEntry(billNo, billDate, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/nmw-sales-report/bills/${encodeURIComponent(billNo)}/purchase-entry${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      bill_date: billDate ? String(billDate).slice(0, 10) : ''
    })}`, { session });
  },

  approveNmwBills(tenantId, bills, session, status = 'approved') {
    return request('/api/nmw-sales-report/bills/approve', {
      method: 'POST',
      session,
      body: JSON.stringify({ tenant_id: tenantId, bills, status })
    });
  },

  // ----- Procurement Workspace (Nexora decision engine) -----
  // Same /api/procurement endpoints as the web Purchase Manager: GUID
  // tenant/store/refresh context, suggestions from decision_rules.evaluate.
  procurementRefreshes(tenantId, storeId, session) {
    return request(`/api/procurement/vpl${toQuery({ tenant_id: tenantId, store_id: storeId, page_size: 200 })}`, { session })
      .then((r) => r?.items || []);
  },

  procurementEnsureContext(tenantId, storeId, createdBy, session) {
    return request(`/api/procurement/stores/${encodeURIComponent(storeId)}/ensure-context${toQuery({ tenant_id: tenantId })}`, {
      method: 'POST',
      session,
      timeoutMs: 180000,
      body: JSON.stringify({ created_by: createdBy || null })
    });
  },

  // A refresh's whole VPL in one page (700-2000 rows); the grid filters locally.
  procurementWorkspace(tenantId, refreshId, session) {
    return request(`/api/procurement/refreshes/${encodeURIComponent(refreshId)}/workspace${toQuery({
      tenant_id: tenantId, sort_by: 'product_name', sort_dir: 'asc', page: 1, page_size: 5000
    })}`, { session, timeoutMs: 90000 });
  },

  // Last sale / last GRN date per product of a refresh (LSD / LPD columns).
  // Separate from the grid load: it reads sync.ProductSaleInformation, which is
  // slow on a cold SQL cache.
  procurementLastActivity(tenantId, refreshId, session) {
    return request(`/api/procurement/refreshes/${encodeURIComponent(refreshId)}/last-activity${toQuery({ tenant_id: tenantId })}`, { session, timeoutMs: 120000 })
      .then((r) => r?.items || []);
  },

  // Abnormal / high bill sales of a refresh's products (rulebook
  // PRR-SALE-ABNORMAL / PRR-SALE-WARNING), and the "do not consider in order"
  // mark for one product on one bill (written to both order databases).
  procurementAbnormalSales(tenantId, refreshId, session) {
    return request(`/api/procurement/refreshes/${encodeURIComponent(refreshId)}/abnormal-sales${toQuery({ tenant_id: tenantId })}`, { session, timeoutMs: 120000 });
  },

  procurementSetDontConsider(tenantId, storeId, body, session) {
    return request(`/api/procurement/stores/${encodeURIComponent(storeId)}/sales/dont-consider${toQuery({ tenant_id: tenantId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify(body)
    });
  },

  // Suggestion panel for ANY store product: ranked suppliers (best /
  // frequent / latest / live) and other stores' stock, non-moving first.
  procurementStoreTrends(tenantId, storeId, productCode, session) {
    return request(`/api/procurement/stores/${encodeURIComponent(storeId)}/products/${encodeURIComponent(productCode)}/store-trends${toQuery({ tenant_id: tenantId })}`, { session });
  },

  procurementProductSuggestions(tenantId, storeId, productCode, session) {
    return request(`/api/procurement/stores/${encodeURIComponent(storeId)}/products/${encodeURIComponent(productCode)}/suggestions${toQuery({ tenant_id: tenantId })}`, { session });
  },

  procurementOrderItem(tenantId, orderItemId, session) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}${toQuery({ tenant_id: tenantId })}`, { session });
  },

  procurementSetFinalQty(tenantId, orderItemId, finalQty, reason, by, session) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/final-qty${toQuery({ tenant_id: tenantId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ final_qty: finalQty, override_reason: reason || null, reviewed_by: by || null })
    });
  },

  procurementRestoreSuggested(tenantId, orderItemId, by, session) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/restore-suggested${toQuery({ tenant_id: tenantId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify({ reviewed_by: by || null })
    });
  },

  procurementSkip(tenantId, orderItemId, reason, by, session) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/skip${toQuery({ tenant_id: tenantId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify({ skip_reason: reason, reviewed_by: by || null })
    });
  },

  // Un-skip / un-defer (the backend restore accepts both).
  procurementRestore(tenantId, orderItemId, by, session) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/restore${toQuery({ tenant_id: tenantId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify({ reviewed_by: by || null })
    });
  },

  procurementDecision(tenantId, orderItemId, session) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/decision${toQuery({ tenant_id: tenantId })}`, { session });
  },

  procurementSupplierQueue(tenantId, orderItemId, session, limit = 5) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/supplier-queue${toQuery({ tenant_id: tenantId, limit })}`, { session });
  },

  procurementItemAssignments(tenantId, orderItemId, session) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/assignments${toQuery({ tenant_id: tenantId })}`, { session })
      .then((r) => r?.items || []);
  },

  procurementAssign(tenantId, orderItemId, supplierCode, qty, by, session) {
    return request(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/assignments${toQuery({ tenant_id: tenantId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify({ supplier_code: supplierCode, qty, created_by: by || null })
    });
  },

  procurementRemoveAssignment(tenantId, assignmentId, by, session) {
    return request(`/api/procurement/assignments/${encodeURIComponent(assignmentId)}${toQuery({ tenant_id: tenantId, deleted_by: by })}`, {
      method: 'DELETE',
      session
    });
  },

  // ----- Order Workspace (legacy VB-style ordering console) -----
  // Store-scoped by store_name and authorised server-side; independent of the
  // desktop tenant/store GUID context (mirrors the web legacyOrderService).
  legacyStores(session, activeOnly = true) {
    return request(`/api/legacy-order/stores${toQuery({ active_only: activeOnly })}`, { session });
  },

  // ----- Legacy Order generation (super admin, every tenant) -----
  // Every platform store incl. inactive ones: only used to map an OrderNMC
  // StoreName (= store_code) to its tenant, never for a selector.
  listAllStores(session) {
    return request('/api/stores', { session });
  },

  // ----- Sync Live (super admin): same data as the HO web Sync Live page -----
  syncControlCenter(session) {
    return request('/api/sync/control-center', { session });
  },
  syncLive(session) {
    return request('/api/sync/live', { session });
  },
  syncHistory(session) {
    return request('/api/sync/history', { session });
  },
  createSyncTask(body, session) {
    return request('/api/sync/tasks/create', { method: 'POST', body: JSON.stringify(body), session });
  },

  legacyDefaults(session) {
    return request('/api/legacy-order/defaults', { session });
  },

  legacyStoreEngine(storeName, session) {
    return request(`/api/legacy-order/engine/${encodeURIComponent(storeName)}`, { session });
  },

  // POST /order-process -> {job_id}. A 409 carries either "already running"
  // or one of the two Order Process warnings ("... Confirm Order & Process").
  legacyStartOrderProcess(payload, session) {
    return request('/api/legacy-order/order-process', {
      method: 'POST',
      session,
      timeoutMs: 120000,
      body: JSON.stringify(payload)
    });
  },

  // PM Order Entry: latest order state, earlier-day block, latest job.
  legacyOrderEntry(storeName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/order-entry`, { session });
  },

  // PM: last bill + last GRN + order type -> Order Process for their store.
  legacyPmStartOrder(storeName, payload, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/order-entry`, {
      method: 'POST',
      session,
      timeoutMs: 120000,
      body: JSON.stringify(payload)
    });
  },

  // Supplier GRN lines since the previous active day's first order for
  // products the app never ordered. productType: pharma | non_pharma | all.
  legacyReceivedNotOrdered(storeName, productType, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/received-not-ordered?product_type=${encodeURIComponent(productType)}`, { session });
  },

  // Per-store "Compare today's previous order" (saved in OrderNMC; read back
  // through legacyStoreEngine's compare_today_previous).
  // The store's saved Compare mode: PREVIOUS_PENDING / TODAY / NONE / HO.
  legacySetCompareMode(storeName, mode, session) {
    return request(`/api/legacy-order/engine/${encodeURIComponent(storeName)}/compare-mode`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ mode })
    });
  },

  legacySetCompareToday(storeName, enabled, session) {
    return request(`/api/legacy-order/engine/${encodeURIComponent(storeName)}/compare-today`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ enabled })
    });
  },

  // Evening (second) order schedule: {enabled, run_at, stores|null, next_run,
  // last_run, running, ...}. stores null = every active store.
  legacyEveningSchedule(session) {
    return request('/api/legacy-order/schedule/evening', { session });
  },

  legacySaveEveningSchedule(payload, session) {
    return request('/api/legacy-order/schedule/evening', {
      method: 'PUT',
      session,
      body: JSON.stringify(payload)
    });
  },

  legacyRunEveningNow(session) {
    return request('/api/legacy-order/schedule/evening/run', { method: 'POST', session });
  },

  legacyJobs(session, limit = 50) {
    return request(`/api/legacy-order/jobs${toQuery({ limit })}`, { session });
  },

  legacyJob(jobId, session) {
    return request(`/api/legacy-order/jobs/${encodeURIComponent(jobId)}`, { session, transientRetries: 0 });
  },

  legacyQtyCheckRows(storeName, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}`, { session });
  },

  legacyResetPendingQtyCheck(storeName, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/reset-pending`, {
      method: 'POST',
      session,
      body: JSON.stringify({})
    });
  },

  legacyPendingOrderRows(storeName, session) {
    return request(`/api/legacy-order/pending-order/${encodeURIComponent(storeName)}`, { session });
  },

  // Skip a line with a platform skip mode (current_refresh |
  // until_next_sales | until_next_demand) -- see repository.skip_product.
  legacySkipProduct(storeName, productCode, mode, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/skip`, {
      method: 'POST',
      session,
      body: JSON.stringify({ mode })
    });
  },

  legacyUpdateQtyCheck(storeName, productCode, orderQty, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}`, {
      method: 'PATCH',
      session,
      body: JSON.stringify({ order_qty: orderQty })
    });
  },

  legacyUpdateRemarks(storeName, productCode, remarks, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/${productCode}/remarks`, {
      method: 'PATCH',
      session,
      body: JSON.stringify({ remarks })
    });
  },

  legacyOrders(storeName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}`, { session });
  },

  legacyUpdateOrderQty(storeName, productCode, orderQty, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/${productCode}`, {
      method: 'PATCH',
      session,
      body: JSON.stringify({ order_qty: orderQty })
    });
  },

  legacyOrderWorkflow(storeName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/workflow`, { session });
  },

  legacyOrderHeader(storeName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/header`, { session });
  },

  legacyFinalizeOrder(storeName, note, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/workflow/finalize`, {
      method: 'POST',
      session,
      body: JSON.stringify({ note: note || null })
    });
  },

  legacyReopenOrder(storeName, note, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/workflow/reopen`, {
      method: 'POST',
      session,
      body: JSON.stringify({ note: note || null })
    });
  },

  // Abnormal / high bill sales of the store's open order, and the "do not
  // consider in order" mark (OrderNMC + platform). Same rule as Procurement.
  legacyAbnormalSales(storeName, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/abnormal-sales`, { session, timeoutMs: 120000 });
  },

  legacySetDontConsider(storeName, body, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/sales/dont-consider`, {
      method: 'PATCH',
      session,
      body: JSON.stringify(body)
    });
  },

  legacyOrderHistory(storeName, productCode, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/order-history`, { session });
  },

  // Product intelligence for the selected order row (purchase/GRN, bill/sales,
  // monthly statistics). Same endpoints/semantics as the web ProductDetailPanel;
  // transfers-vs-purchases distinction is handled server-side in the SP.
  legacyPurchaseDetails(storeName, productCode, mode, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/purchase-details${toQuery({ mode })}`, { session });
  },

  // Whole purchase invoice / sales bill for the Order Workspace row-click card.
  legacyPurchaseInvoice(storeName, params, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/purchase-invoice${toQuery(params)}`, { session });
  },

  legacySaleBill(storeName, params, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/sale-bill${toQuery(params)}`, { session });
  },

  legacySalesDetails(storeName, productCode, mode, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/sales-details${toQuery({ mode })}`, { session });
  },

  // months: calendar months back from (and including) the current one;
  // omitted = the legacy 4-month window.
  legacyMonthlyStats(storeName, productCode, mode, session, months) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/monthly-stats${toQuery({ mode, months })}`, { session });
  },

  // Supplier assignment: supplier list, orderable rows per supplier (by purchase
  // history or by live supplier stock), the assigned-order view, and the
  // assign/unassign toggle. Same endpoints as the web Order Workspace.
  legacySuppliers(storeName, search, session) {
    return request(`/api/legacy-order/suppliers/${encodeURIComponent(storeName)}${toQuery({ search: search || '' })}`, { session });
  },

  legacyOrdersBySupplier(storeName, supplierCode, mode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/by-supplier${toQuery({ supplier_code: supplierCode, mode })}`, { session });
  },

  // Every open orderable product for the store, independent of any supplier
  // match -- the By Supplier grid's "Load all products" toggle.
  legacyAllOpenOrders(storeName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/all-open`, { session });
  },

  // {product_code: [every supplier's live stock/offer/Disc% line]} for the
  // store's open order -- the Procurement row's compare-suppliers card.
  legacySupplierStockCompare(storeName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/supplier-stock-compare`, { session });
  },

  legacyAssignedOrders(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/assigned${toQuery({ supplier_code: supplierCode })}`, { session });
  },

  legacyRemoveUnavailable(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/unavailable/remove`, {
      method: 'POST',
      session,
      body: JSON.stringify({ supplier_code: supplierCode })
    });
  },

  legacyUnassignAll(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/assigned/unassign-all`, {
      method: 'POST',
      session,
      body: JSON.stringify({ supplier_code: supplierCode })
    });
  },

  // Bulk Assign · Best Margin: proposals, then assign (recomputed server-side).
  legacyAutoAssignPreview(storeName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/auto-assign`, { session });
  },

  legacyAutoAssign(storeName, productCodes, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/auto-assign`, {
      method: 'POST',
      session,
      body: JSON.stringify({ product_codes: productCodes })
    });
  },

  // Supplier-wise WhatsApp (store-level WhatsApp): saved targets + auto-send.
  legacyWhatsAppContacts(storeName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/whatsapp/contacts`, { session });
  },

  legacySaveWhatsAppContact(storeName, payload, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/whatsapp/contacts`, {
      method: 'POST',
      session,
      body: JSON.stringify(payload)
    });
  },

  legacyWhatsAppStatus(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/whatsapp/status${toQuery({ supplier_code: supplierCode })}`, { session });
  },

  legacyMarkWhatsAppSent(storeName, supplierCode, productCodes, kind, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/whatsapp/sent`, {
      method: 'POST',
      session,
      body: JSON.stringify({ supplier_code: supplierCode, product_codes: productCodes, kind })
    });
  },

  // A supplier's own web-order portal (its URL + login), stored on the supplier
  // row. When a store order selects a supplier and clicks Website, the client
  // reads this and signs in. The password only ever comes back from
  // legacySupplierPortalLogin (for the Stock Client's auto sign-in).
  legacySupplierPortal(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/portal`, { session });
  },

  legacySupplierPortalLogin(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/portal/login`, { session, cache: 'no-store' });
  },

  // payload: { url, username, password, auto_submit, clear }. Blank password
  // keeps the saved one; clear wipes the portal.
  legacySaveSupplierPortal(storeName, supplierCode, payload, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/portal`, {
      method: 'POST', session, body: JSON.stringify(payload)
    });
  },

  // HARVEST (write-only): post the supplier's portal catalog (rows:
  // [{ name, code, stock, mrp, ptr, discount, packing, scheme, free }]); the
  // server writes it to SupplierStock. Live Stock mode then shows it in the grid.
  legacyHarvestSupplierStock(storeName, supplierCode, rows, complete, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/harvest`, {
      method: 'POST', session, body: JSON.stringify({ rows, complete: complete !== false })
    });
  },

  // When this supplier's stock was last harvested, and how many rows (freshness).
  legacySupplierHarvestStatus(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/harvest`, { session });
  },

  // MAP REVIEW (separate): match the harvested stock to the store's products,
  // by tier (matched / suggested / needs_mapping) -- the "Map supplier products" panel.
  legacySupplierMatchReview(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/match-review`, { session });
  },

  // ProductCode -> this supplier's own product code, for already-confirmed
  // matches -- lets Website/Auto-Assign search the supplier's site by code.
  legacySupplierMatchCodes(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/match-codes`, { session });
  },

  // Save a chosen mapping to SupplierProductMatch (blank product_code unmaps).
  legacyConfirmSupplierMatch(storeName, supplierCode, payload, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/match-review/confirm`, {
      method: 'POST', session, body: JSON.stringify(payload)
    });
  },

  legacyAssignSupplier(storeName, productCode, supplierCode, supplierName, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/${productCode}/assign`, {
      method: 'POST',
      session,
      body: JSON.stringify({ supplier_code: supplierCode, supplier_name: supplierName })
    });
  },

  // Bulk-assigns every OrderQty>0 row for this supplier, then returns the
  // legacy-faithful Order Workspace Excel export (or a .zip of "Part N of M"
  // files when splitSize splits it) built server-side by order_export.py --
  // the same port of Form1.ExportSelectedColumnsFromGrid the web Order
  // Workspace already uses. Filename + assigned count come back in headers,
  // so this bypasses the JSON request() helper and reads the raw Response.
  // ----- Label Exporter (letter-wise review + print) -----
  searchLabelProducts(session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/label-exporter/products/search${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: filters.storeId || settings.storeId,
      q: filters.q || '',
      starts_with: filters.startsWith || '',
      unit_description: filters.unitDescription || '',
      unit_description_mode: filters.unitDescriptionMode || 'contains',
      box_number: filters.boxNumber || '',
      stock_filter: filters.stockFilter || 'all',
      only_null_sublocation: filters.onlyNullSublocation ? 1 : 0,
      only_sale_unit_gt_one: filters.onlySaleUnitGtOne ? 1 : 0,
      sublocation_filter: filters.sublocationFilter || '',
      review_status: filters.reviewStatus || '',
      unit_source: filters.unitSource || 'new'
    })}`, { session, signal: filters.signal });
  },

  // Reviewer corrects a product's unit (auto-saved, dbo.label_review only).
  correctLabelUnit(productCode, tenantId, storeId, unitDescription, currentUnit, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/unit${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ unit_description: unitDescription, current_unit: currentUnit || '' })
    });
  },

  // Super-admin manual box override (auto-saved). Bypasses the standard-box/
  // SYP assignment engine for one product; old box is captured server-side.
  correctLabelLocation(productCode, tenantId, storeId, location, currentLocation, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/location${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ location, current_location: currentLocation || '' })
    });
  },

  // Preview a box plan (no commit) so the UI can show the assignment before
  // the operator confirms. `body` = { unit, mode, assignment_type, letter,
  // product_codes, start_number }.
  previewLabelAssignment(tenantId, storeId, body, session) {
    return request(`/api/label-exporter/assignments/preview${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify(body)
    });
  },

  // Transactionally commit the box plan (super-admin only, backend re-plans).
  commitLabelAssignment(tenantId, storeId, body, session) {
    return request(`/api/label-exporter/assignments/commit${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify(body)
    });
  },

  // Reset ONLY the assignment result (assigned box + label state) for the given
  // products — review Y/N and master data are left intact (spec §10).
  clearLabelAssignment(tenantId, storeId, productCodes, session) {
    return request(`/api/label-exporter/assignments/clear${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify({ product_codes: productCodes })
    });
  },

  // Reset the Y/N review AND assignment/label state for the given products
  // (spec §11). Preserves unit corrections, old locations and master data.
  clearLabelReview(tenantId, storeId, productCodes, session) {
    return request(`/api/label-exporter/review/clear${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify({ product_codes: productCodes })
    });
  },

  getLabelQueue(tenantId, storeId, session) {
    return request(`/api/label-exporter/label-queue${toQuery({ tenant_id: tenantId, store_id: storeId })}`, { session });
  },

  markLabelsPrinted(tenantId, storeId, productCodes, session) {
    return request(`/api/label-exporter/label-queue/mark-printed${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify({ product_codes: productCodes })
    });
  },

  clearPrintedLabels(tenantId, storeId, productCodes, session) {
    return request(`/api/label-exporter/label-queue/clear-printed${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'POST',
      session,
      body: JSON.stringify({ product_codes: productCodes })
    });
  },

  updateLabelReview(productCode, tenantId, storeId, body, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/review${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify(body)
    });
  },

  bulkSetLabelInclude(tenantId, storeId, productCodes, includeLabel, session) {
    return request(`/api/label-exporter/products/bulk-review${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ product_codes: productCodes, include_label: includeLabel })
    });
  },

  // Bulk find-and-replace a unit (e.g. set every selected RM product's NEW unit
  // to TAB). Writes dbo.label_review only; master unit captured server-side.
  bulkCorrectLabelUnit(tenantId, storeId, productCodes, unitDescription, session) {
    return request(`/api/label-exporter/products/bulk-unit${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ product_codes: productCodes, unit_description: unitDescription })
    });
  },

  assignLabelSublocation(productCode, tenantId, storeId, sublocation, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/sublocation${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ sublocation })
    });
  },

  async exportLabelQueuePdf(tenantId, storeId, session, letter = '') {
    const settings = loadSettings();
    let response;
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, `/api/label-exporter/label-queue/pdf${toQuery({ tenant_id: tenantId, store_id: storeId, letter: letter || undefined })}`), {
        headers: { ...authHeaders(session) }
      });
    } catch {
      throw new Error('Unable to reach the server. Check that the API is running.');
    }
    if (!response.ok) {
      let detail = response.statusText || 'PDF export failed';
      try { const parsed = await response.json(); detail = detailToMessage(parsed) || detail; } catch { /* no JSON body */ }
      throw new Error(detail);
    }
    return response.blob();
  },

  async exportLabelProductsExcel(tenantId, storeId, letter, session) {
    const settings = loadSettings();
    let response;
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, `/api/label-exporter/products/export.xlsx${toQuery({ tenant_id: tenantId, store_id: storeId, letter })}`), {
        headers: { ...authHeaders(session) }
      });
    } catch {
      throw new Error('Unable to reach the server. Check that the API is running.');
    }
    if (!response.ok) {
      let detail = response.statusText || 'Excel export failed';
      try { const parsed = await response.json(); detail = detailToMessage(parsed) || detail; } catch { /* no JSON body */ }
      throw new Error(detail);
    }
    return response.blob();
  },

  getLabelLetterLock(tenantId, storeId, letter, session) {
    return request(`/api/label-exporter/letter-lock${toQuery({ tenant_id: tenantId, store_id: storeId, letter })}`, { session });
  },

  lockLabelLetter(tenantId, storeId, letter, session) {
    return request(`/api/label-exporter/letter-lock${toQuery({ tenant_id: tenantId, store_id: storeId, letter })}`, { method: 'POST', session });
  },

  // Finalise dialog: unreviewed stock>0 / sale-unit>1 products that must be
  // reviewed by hand + the letter's review counts.
  getLabelLetterFinalise(tenantId, storeId, letter, session) {
    return request(`/api/label-exporter/letter-finalise${toQuery({ tenant_id: tenantId, store_id: storeId, letter })}`, { session });
  },

  // Complete a letter: auto-N every other unreviewed product, then lock.
  finaliseLabelLetter(tenantId, storeId, letter, session) {
    return request(`/api/label-exporter/letter-finalise${toQuery({ tenant_id: tenantId, store_id: storeId, letter })}`, { method: 'POST', session });
  },

  unlockLabelLetter(tenantId, storeId, letter, session) {
    return request(`/api/label-exporter/letter-lock/unlock${toQuery({ tenant_id: tenantId, store_id: storeId, letter })}`, { method: 'POST', session });
  },

  getLabelProductTrend(productCode, tenantId, storeId, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/trend${toQuery({ tenant_id: tenantId, store_id: storeId })}`, { session });
  },

  getLabelProductPurchases(productCode, tenantId, storeId, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/purchases${toQuery({ tenant_id: tenantId, store_id: storeId })}`, { session });
  },

  getLabelProductSales(productCode, tenantId, storeId, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/sales${toQuery({ tenant_id: tenantId, store_id: storeId })}`, { session });
  },

  async legacyExportOrder(storeName, supplierCode, supplierName, mode, splitSize, session, options = {}) {
    const settings = loadSettings();
    let response;
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, `/api/legacy-order/orders/${encodeURIComponent(storeName)}/export`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(session)
        },
        body: JSON.stringify({
          supplier_code: supplierCode,
          supplier_name: supplierName,
          mode,
          split_size: splitSize || 0,
          ...(options.columns ? { columns: options.columns } : {}),
          ...(options.fileFormat ? { file_format: options.fileFormat } : {}),
          ...(options.orderNo ? { order_no: options.orderNo } : {}),
          ...(options.productCodes ? { product_codes: options.productCodes } : {}),
          ...(options.allProducts ? { all_products: true } : {}),
          ...(options.images ? { images: true } : {}),
          ...(options.onlyCodes ? { only_codes: options.onlyCodes } : {}),
          ...(options.imageHeader ? { image_header: true } : {}),
          ...(options.excelHeader ? { excel_header: true } : {}),
          ...(options.orgName ? { org_name: options.orgName } : {}),
          ...(options.billsDays ? { bills_days: options.billsDays } : {}),
          ...(options.nameSuffix ? { name_suffix: options.nameSuffix } : {}),
          ...(options.remarks && Object.keys(options.remarks).length ? { remarks: options.remarks } : {})
        })
      });
    } catch {
      throw new Error('Unable to reach the server. Check that the API is running.');
    }
    if (!response.ok) {
      let detail = response.statusText || 'Export failed';
      try {
        const parsed = await response.json();
        detail = detailToMessage(parsed) || detail;
      } catch { /* no JSON body */ }
      throw new Error(detail);
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = /filename="?([^"]+)"?/.exec(disposition);
    return {
      blob,
      filename: match?.[1] || `${supplierName} ${storeName}.xlsx`,
      exportedCount: Number(response.headers.get('X-Exported-Count') || 0)
    };
  },

  // Export the Pending grid (reviewed, qtycheck=1, not yet assigned to any
  // supplier, status=0) -- same workbook look as legacyExportOrder, but
  // read-only: no assignment step, nothing changes server-side besides
  // building the file. See order_export.export_pending_order.
  async legacyExportPendingOrder(storeName, splitSize, session, options = {}) {
    const settings = loadSettings();
    let response;
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, `/api/legacy-order/orders/${encodeURIComponent(storeName)}/export-pending`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(session)
        },
        body: JSON.stringify({
          split_size: splitSize || 0,
          ...(options.columns ? { columns: options.columns } : {}),
          ...(options.fileFormat ? { file_format: options.fileFormat } : {}),
          ...(options.orderNo ? { order_no: options.orderNo } : {}),
          ...(options.images ? { images: true } : {}),
          ...(options.remarks && Object.keys(options.remarks).length ? { remarks: options.remarks } : {})
        })
      });
    } catch {
      throw new Error('Unable to reach the server. Check that the API is running.');
    }
    if (!response.ok) {
      let detail = response.statusText || 'Export failed';
      try {
        const parsed = await response.json();
        detail = detailToMessage(parsed) || detail;
      } catch { /* no JSON body */ }
      throw new Error(detail);
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = /filename="?([^"]+)"?/.exec(disposition);
    return {
      blob,
      filename: match?.[1] || `Pending ${storeName}.xlsx`,
      exportedCount: Number(response.headers.get('X-Exported-Count') || 0)
    };
  },

  // ----- Schema Sync (Dev -> Production) - super admin only -----
  getSchemaSyncLocalSource(session) {
    return request('/api/schema-sync/local-source-info', { session });
  },

  testSchemaSyncConnection(connection, session) {
    return request('/api/schema-sync/test-connection', {
      method: 'POST',
      session,
      body: JSON.stringify({ connection })
    });
  },

  ensureSchemaSyncDatabase(connection, session) {
    return request('/api/schema-sync/ensure-database', {
      method: 'POST',
      session,
      body: JSON.stringify({ connection })
    });
  },

  compareSchemaSync(source, target, session) {
    return request('/api/schema-sync/compare', {
      method: 'POST',
      session,
      // Legacy DBs like OrderNMC can have far more tables/columns/SPs than
      // NEXORA_PLATFORM - a full metadata snapshot of both Source and Target
      // can run past two minutes. 120s clipped that mid-read (nothing gets
      // created because Apply never fires without a compare result).
      timeoutMs: 600000,
      body: JSON.stringify({ source, target })
    });
  },

  applySchemaSync(target, statements, session) {
    return request('/api/schema-sync/apply', {
      method: 'POST',
      session,
      timeoutMs: 300000,
      body: JSON.stringify({ target, statements })
    });
  },

  // Store outbox: NMW stock files HO queued for THIS store to send from its
  // own WhatsApp (distribution whatsapp_sender = STORE).
  getStoreWhatsAppOutbox(tenantId, storeId, session) {
    return request(`/api/procurement/distribution/store-outbox${toQuery({ tenant_id: tenantId, store_id: storeId })}`, { session });
  },

  claimStoreWhatsAppItem(runItemId, session) {
    return request(`/api/procurement/distribution/store-outbox/${encodeURIComponent(runItemId)}/claim`, { method: 'POST', session });
  },

  async getStoreWhatsAppFile(runItemId, session) {
    const settings = loadSettings();
    const response = await fetch(joinUrl(settings.apiBaseUrl, `/api/procurement/distribution/store-outbox/${encodeURIComponent(runItemId)}/file`), {
      headers: authHeaders(session)
    });
    if (!response.ok) {
      let detail = response.statusText || 'Download failed';
      try { detail = detailToMessage(await response.json()) || detail; } catch { /* no JSON body */ }
      throw new Error(detail);
    }
    return response.blob();
  },

  // HO server's WhatsApp profile (backend/modules/whatsapp) -- used when this
  // PC sends through HO's already-linked WhatsApp instead of its own.
  hoWhatsAppState(session) {
    return request('/api/whatsapp/state', { session });
  },

  hoWhatsAppStatus(profileId, session) {
    return request(`/api/whatsapp/profiles/${encodeURIComponent(profileId)}/status`, { session, timeoutMs: 90000 });
  },

  hoWhatsAppChats(profileId, session) {
    return request(`/api/whatsapp/profiles/${encodeURIComponent(profileId)}/chats`, { session, timeoutMs: 120000 });
  },

  hoWhatsAppSendFiles(payload, session) {
    return request('/api/whatsapp/send/chat-files', {
      method: 'POST', session, timeoutMs: 300000, body: JSON.stringify(payload)
    });
  },

  hoWhatsAppSendText(payload, session) {
    return request('/api/whatsapp/send/chat', {
      method: 'POST', session, timeoutMs: 180000, body: JSON.stringify(payload)
    });
  },

  hoWhatsAppLog(session) {
    return request('/api/whatsapp/send-log?limit=100', { session });
  },

  // Time Report (COSEC attendance, /api/time-report/*).
  timeReportMeta(session) {
    return request('/api/time-report/meta', { session });
  },

  timeReport(report, params, session) {
    return request(`/api/time-report/${encodeURIComponent(report)}${toQuery(params)}`, { session });
  },

  timeReportPath(report, params) {
    return `/api/time-report/${report}${toQuery(params)}`;
  },

  // GET any file-returning path (report Excel / image) as a Blob.
  async getBlob(path, session) {
    const settings = loadSettings();
    let response;
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, path), { headers: authHeaders(session) });
    } catch {
      throw new Error('Unable to reach the server. Check that the API is running.');
    }
    if (!response.ok) {
      let detail = response.statusText || 'Download failed';
      try { detail = detailToMessage(await response.json()) || detail; } catch { /* no JSON body */ }
      throw new Error(detail);
    }
    return response.blob();
  },

  reportStoreWhatsAppResult(runItemId, sent, error, session) {
    return request(`/api/procurement/distribution/store-outbox/${encodeURIComponent(runItemId)}/result`, {
      method: 'POST',
      session,
      body: JSON.stringify({ sent, error: error || null })
    });
  },

  // ----- Rate Analysis (supplier purchase-rate tools) -----
  rateSuppliers(tenantId, days, session) {
    return request(`/api/rate-analysis/suppliers?tenant_id=${encodeURIComponent(tenantId)}&days=${days || 90}`, { session, timeoutMs: 120000 });
  },

  rateQuoteMatch(body, session) {
    return request('/api/rate-analysis/quote/match', { method: 'POST', session, timeoutMs: 120000, body: JSON.stringify(body) });
  },

  // kind: 'quote/compare' | 'fast-movers' | 'rate-difference'. These read
  // months of bills + sales across every store, so they get a long timeout.
  rateReport(kind, body, session) {
    return request(`/api/rate-analysis/${kind}`, { method: 'POST', session, timeoutMs: 300000, body: JSON.stringify(body) });
  },

  async rateReportExcel(kind, body, session) {
    const settings = loadSettings();
    let response;
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, `/api/rate-analysis/${kind}?format=xlsx`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders(session) },
        body: JSON.stringify(body)
      });
    } catch {
      throw new Error('Unable to reach the server. Check that the API is running.');
    }
    if (!response.ok) {
      let detail = response.statusText || 'Export failed';
      try { detail = detailToMessage(await response.json()) || detail; } catch { /* no JSON body */ }
      throw new Error(detail);
    }
    const blob = await response.blob();
    const match = /filename="?([^"]+)"?/.exec(response.headers.get('Content-Disposition') || '');
    return { blob, filename: match?.[1] || 'Rate_Analysis.xlsx' };
  },

  // ----- Non-Moving Stock analysis (read-only) -----
  // section: 'own-store' | 'other-stores' | 'transfers' | 'dashboard' | 'product'.
  // The first call for a tenant builds every store's snapshot (can take a
  // minute or two on a cold server), so these get a long timeout.
  nonMoving(section, params, session) {
    return request(`/api/non-moving-analysis/${section}${toQuery(params)}`, { session, timeoutMs: 300000 });
  },

  async nonMovingExcel(section, params, session, body) {
    const settings = loadSettings();
    const path = body
      ? `/api/non-moving-analysis/${section}`
      : `/api/non-moving-analysis/${section}${toQuery({ ...params, format: 'xlsx' })}`;
    let response;
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, path), body
        ? { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders(session) }, body: JSON.stringify(body) }
        : { headers: authHeaders(session) });
    } catch {
      throw new Error('Unable to reach the server. Check that the API is running.');
    }
    if (!response.ok) {
      let detail = response.statusText || 'Export failed';
      try { detail = detailToMessage(await response.json()) || detail; } catch { /* no JSON body */ }
      throw new Error(detail);
    }
    const blob = await response.blob();
    const match = /filename="?([^"]+)"?/.exec(response.headers.get('Content-Disposition') || '');
    return { blob, filename: match?.[1] || 'Non_Moving_Stock.xlsx' };
  }
};





