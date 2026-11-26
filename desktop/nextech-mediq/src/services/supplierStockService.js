// Uses the existing, unmodified backend contract — verified against
// backend/modules/supplier_stock_analysis/router.py, repository.py:
//   GET /suppliers               -> [{supplier_code, supplier_name, product_count, available_count, total_available_stock, last_imported_at}]
//   GET /supplier-products       -> [{supplier_stock_id, store_id, store_name, supplier_code,
//                                      supplier_product_code, supplier_product_name, product_code,
//                                      mapped_product_name, available_stock, ptr, mrp, discount, gst,
//                                      packing, free, minimum_qty, scheme, transaction_date, imported_at,
//                                      has_mapping, mapping_scope_status, own_store_stock, other_store_has_stock}]
//   GET /warehouse-stock/counts  -> {all, zero, positive, zero_other_positive, zero_all_zero}
//   GET /warehouse-stock/products
//   GET /supplier-stock/{id}/match          -> {supplier_stock, exact_match}
//   GET /supplier-stock/{id}/dashboard/stock
//   GET /supplier-stock/{id}/dashboard/details
//   GET  /order-suppliers        -> {suppliers: [{supplier_code, supplier_name, ...}]}
//   POST /excel/preview, /excel/import  (multipart, same as supplier-stock-client)
import { apiGet, apiPost, apiPut, apiRequest } from '../api/client.js';

const PRODUCTS_TIMEOUT_MS = 180000;

function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

// The backend wraps lists ({suppliers}, {items}, {rows}); return the bare array.
function unwrapList(data, key) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.[key])) return data[key];
  for (const k of ['items', 'rows', 'suppliers']) {
    if (Array.isArray(data?.[k])) return data[k];
  }
  return [];
}

export function listSuppliers(tenantId, storeId, search = '') {
  return apiGet(`/api/supplier-stock-analysis/suppliers${qs({ tenant_id: tenantId, store_id: storeId, search })}`)
    .then((data) => unwrapList(data, 'suppliers'));
}

export function listSupplierProducts(tenantId, storeId, supplierCode, { search = '', onlyAvailable = false } = {}) {
  return apiGet(
    `/api/supplier-stock-analysis/supplier-products${qs({
      tenant_id: tenantId,
      store_id: storeId,
      supplier_code: supplierCode,
      search,
      only_available: onlyAvailable ? 1 : 0,
    })}`,
    { timeoutMs: PRODUCTS_TIMEOUT_MS }
  ).then((data) => unwrapList(data, 'items'));
}

// Plain SupplierStock rows for one supplier across the tenant's stores (or one
// store) -> {items, truncated, limit}. No mapping analysis, not capped at 3000.
export function listSupplierStock(tenantId, supplierCode, storeId) {
  return apiGet(
    `/api/supplier-stock-analysis/stock-list${qs({ tenant_id: tenantId, supplier_code: supplierCode, store_id: storeId })}`,
    { timeoutMs: PRODUCTS_TIMEOUT_MS }
  );
}

export function warehouseStockCounts(tenantId, storeId) {
  return apiGet(`/api/supplier-stock-analysis/warehouse-stock/counts${qs({ tenant_id: tenantId, store_id: storeId })}`);
}

export function warehouseStockProducts(tenantId, storeId, stockFilter, search = '') {
  return apiGet(
    `/api/supplier-stock-analysis/warehouse-stock/products${qs({
      tenant_id: tenantId,
      store_id: storeId,
      stock_filter: stockFilter,
      search,
    })}`,
    { timeoutMs: PRODUCTS_TIMEOUT_MS }
  ).then((data) => unwrapList(data, 'rows'));
}

export function listOrderSuppliers(tenantId, storeId) {
  return apiGet(`/api/supplier-stock-analysis/order-suppliers${qs({ tenant_id: tenantId, store_id: storeId })}`);
}

export function previewSupplierExcel(file, { tenantId, storeId, supplierCode } = {}) {
  const form = new FormData();
  form.append('file', file);
  if (storeId && supplierCode) {
    form.append('tenant_id', tenantId);
    form.append('store_id', storeId);
    form.append('supplier_code', supplierCode);
  }
  return apiRequest('/api/supplier-stock-analysis/excel/preview', { method: 'POST', body: form, timeoutMs: 120000 });
}

export function importSupplierExcel({ tenantId, storeId, supplierCode, mapping, file, importedBy }) {
  const form = new FormData();
  form.append('tenant_id', tenantId);
  form.append('store_id', storeId);
  form.append('supplier_code', supplierCode);
  form.append('mapping_json', JSON.stringify(mapping));
  if (importedBy) form.append('imported_by', importedBy);
  form.append('file', file);
  return apiRequest('/api/supplier-stock-analysis/excel/import', { method: 'POST', body: form, timeoutMs: 180000 });
}

export function supplierStockMatch(supplierStockId, tenantId) {
  return apiGet(`/api/supplier-stock-analysis/supplier-stock/${encodeURIComponent(supplierStockId)}/match${qs({ tenant_id: tenantId })}`);
}

export function supplierStockDashboardStock(supplierStockId, tenantId) {
  return apiGet(`/api/supplier-stock-analysis/supplier-stock/${encodeURIComponent(supplierStockId)}/dashboard/stock${qs({ tenant_id: tenantId })}`);
}

export function supplierStockDashboardDetails(supplierStockId, tenantId, { sourceStoreId, productCode, months = 6 } = {}) {
  return apiGet(
    `/api/supplier-stock-analysis/supplier-stock/${encodeURIComponent(supplierStockId)}/dashboard/details${qs({
      tenant_id: tenantId,
      source_store_id: sourceStoreId,
      product_code: productCode,
      months,
    })}`
  );
}

// Supplier mail import (backend/modules/supplier_mail_import/router.py):
// tenant mailbox + per-supplier switch; the backend polls the mailbox and
// imports each switched-on supplier's newest Excel with its saved mapping.
export function getMailConfig(tenantId) {
  return apiGet(`/api/supplier-mail-import/config${qs({ tenant_id: tenantId })}`);
}

export function saveMailConfig(tenantId, config) {
  return apiPut(`/api/supplier-mail-import/config${qs({ tenant_id: tenantId })}`, config);
}

export function testMailConfig(tenantId, config) {
  return apiPost(`/api/supplier-mail-import/config/test${qs({ tenant_id: tenantId })}`, config, { timeoutMs: 90000 });
}

export function listMailSuppliers(tenantId, storeId) {
  return apiGet(`/api/supplier-mail-import/suppliers${qs({ tenant_id: tenantId, store_id: storeId })}`)
    .then((data) => unwrapList(data, 'suppliers'));
}

export function saveMailSupplier(payload) {
  return apiPut('/api/supplier-mail-import/suppliers', payload);
}

export function runMailImport(tenantId) {
  return apiPost(`/api/supplier-mail-import/run${qs({ tenant_id: tenantId })}`, {}, { timeoutMs: 600000 });
}

export function pullMailSupplier(tenantId, storeId, supplierCode) {
  return apiPost(
    `/api/supplier-mail-import/pull${qs({ tenant_id: tenantId, store_id: storeId, supplier_code: supplierCode })}`,
    {},
    { timeoutMs: 600000 }
  );
}

export function mailImportLog(tenantId, storeId, limit = 50) {
  return apiGet(`/api/supplier-mail-import/log${qs({ tenant_id: tenantId, store_id: storeId, limit })}`)
    .then((data) => unwrapList(data, 'rows'));
}
