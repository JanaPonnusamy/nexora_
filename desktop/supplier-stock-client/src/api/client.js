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
  const response = await fetch(joinUrl(settings.apiBaseUrl, path), {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...authHeaders(session),
      ...(options.headers || {})
    }
  });

  const text = await response.text();
  const data = text ? safeJson(text) : null;

  if (!response.ok) {
    const message = data?.message || data?.error || `Request failed with ${response.status}`;
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

  getStockBatches(storeId, productCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/stock-availability/products/batches${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      product: productCode
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
  getSuppliers(session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/suppliers${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: filters.storeId || settings.storeId,
      search: filters.search || ''
    })}`, { session });
  },

  getSupplierProducts(supplierCode, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/supplier-products${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: filters.storeId || settings.storeId,
      supplier_code: supplierCode,
      search: filters.search || '',
      only_available: filters.onlyAvailable ?? 1
    })}`, { session });
  },

  getSupplierDashboard(supplierStockId, session, filters = {}) {
    const settings = loadSettings();
    return request(`/api/supplier-stock-analysis/supplier-stock/${supplierStockId}/dashboard${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      months: filters.months || 6
    })}`, { session });
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
    return request(`/api/reports/non-moving${toQuery({
      tenant_id: filters.tenantId || settings.tenantId,
      store_id: storeId,
      dwell_days: filters.dwellDays || 60
    })}`, { session });
  },

  updateSupplierMapping(payload, session) {
    return request('/api/supplier-stock-analysis/mapping', {
      method: 'POST',
      session,
      body: JSON.stringify(payload)
    });
  }
};





