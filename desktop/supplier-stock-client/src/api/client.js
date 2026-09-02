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

async function request(path, options = {}) {
  const settings = loadSettings();
  const session = options.session;
  const timeoutMs = options.timeoutMs ?? 45000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  // React Query passes its own per-query AbortSignal so switching products
  // cancels the previous product's in-flight request (req 5) - forward its
  // abort into our internal controller without losing the timeout behavior.
  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    else options.signal.addEventListener('abort', () => controller.abort(), { once: true });
  }
  let response;
  try {
    response = await fetch(joinUrl(settings.apiBaseUrl, path), {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...authHeaders(session),
        ...(options.headers || {})
      }
    });
  } catch (err) {
    if (err.name === 'AbortError') throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    throw err;
  } finally {
    clearTimeout(timer);
  }

  const text = await response.text();
  const data = text ? safeJson(text) : null;

  if (!response.ok) {
    const message = data?.detail || data?.message || data?.error || `Request failed with ${response.status}`;
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

  listTenants(session) {
    return request('/api/tenants', { session });
  },

  listStores(session) {
    return request('/api/stores', { session });
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

  getProductDashboard(productCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/products/${productCode}/dashboard${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      months: filters.months || 6
    })}`, { session });
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
    })}`, { session });
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

  previewSupplierExcel(file, session) {
    const form = new FormData();
    form.append('file', file);
    return request('/api/supplier-stock-analysis/excel/preview', {
      method: 'POST',
      session,
      body: form
    });
  },

  importSupplierExcel({ storeId, supplierCode, mapping, file, importedBy }, session) {
    const settings = loadSettings();
    const form = new FormData();
    form.append('tenant_id', settings.tenantId);
    form.append('store_id', storeId || settings.storeId);
    form.append('supplier_code', supplierCode);
    form.append('mapping_json', JSON.stringify(mapping));
    if (importedBy) form.append('imported_by', importedBy);
    form.append('file', file);
    return request('/api/supplier-stock-analysis/excel/import', {
      method: 'POST',
      session,
      body: form
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
      date_to: filters.dateTo || ''
    })}`, { session });
  },

  getNmwSalesBillItems(billNo, billDate, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/nmw-sales-report/bills/${encodeURIComponent(billNo)}/items${toQuery({
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

  // ----- Order Workspace (legacy VB-style ordering console) -----
  // Store-scoped by store_name and authorised server-side; independent of the
  // desktop tenant/store GUID context (mirrors the web legacyOrderService).
  legacyStores(session, activeOnly = true) {
    return request(`/api/legacy-order/stores${toQuery({ active_only: activeOnly })}`, { session });
  },

  legacyQtyCheckRows(storeName, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}`, { session });
  },

  legacyUpdateQtyCheck(storeName, productCode, orderQty, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}`, {
      method: 'PATCH',
      session,
      body: JSON.stringify({ order_qty: orderQty })
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

  legacyOrderHistory(storeName, productCode, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/order-history`, { session });
  },

  // Product intelligence for the selected order row (purchase/GRN, bill/sales,
  // monthly statistics). Same endpoints/semantics as the web ProductDetailPanel;
  // transfers-vs-purchases distinction is handled server-side in the SP.
  legacyPurchaseDetails(storeName, productCode, mode, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/purchase-details${toQuery({ mode })}`, { session });
  },

  legacySalesDetails(storeName, productCode, mode, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/sales-details${toQuery({ mode })}`, { session });
  },

  legacyMonthlyStats(storeName, productCode, mode, session) {
    return request(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/monthly-stats${toQuery({ mode })}`, { session });
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

  legacyAssignedOrders(storeName, supplierCode, session) {
    return request(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/assigned${toQuery({ supplier_code: supplierCode })}`, { session });
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
      only_sale_unit_gt_one: filters.onlySaleUnitGtOne ? 1 : 0
    })}`, { session });
  },

  updateLabelReview(productCode, tenantId, storeId, body, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/review${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify(body)
    });
  },

  assignLabelSublocation(productCode, tenantId, storeId, sublocation, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/sublocation${toQuery({ tenant_id: tenantId, store_id: storeId })}`, {
      method: 'PUT',
      session,
      body: JSON.stringify({ sublocation })
    });
  },

  getLabelProductTrend(productCode, tenantId, storeId, session) {
    return request(`/api/label-exporter/products/${encodeURIComponent(productCode)}/trend${toQuery({ tenant_id: tenantId, store_id: storeId })}`, { session });
  },

  async legacyExportOrder(storeName, supplierCode, supplierName, mode, splitSize, session) {
    const settings = loadSettings();
    let response;
    try {
      response = await fetch(joinUrl(settings.apiBaseUrl, `/api/legacy-order/orders/${encodeURIComponent(storeName)}/export`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(session)
        },
        body: JSON.stringify({ supplier_code: supplierCode, supplier_name: supplierName, mode, split_size: splitSize || 0 })
      });
    } catch {
      throw new Error('Unable to reach the server. Check that the API is running.');
    }
    if (!response.ok) {
      let detail = response.statusText || 'Export failed';
      try { const parsed = await response.json(); detail = parsed?.detail || parsed?.message || detail; } catch { /* no JSON body */ }
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
  }
};





