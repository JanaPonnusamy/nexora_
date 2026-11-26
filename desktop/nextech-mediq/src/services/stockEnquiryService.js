// Uses the existing, unmodified backend contract — verified against
// backend/modules/stock_availability/router.py, schemas.py, service.py:
//   GET /products/search?tenant_id&q&only_stock        -> SearchResult
//   GET /batches/search?tenant_id&batch&mrp&product    -> SearchResult (same shape)
//   GET /products/core?tenant_id&store_id&product&months -> {batches, purchases, sales, movement}
//   GET /products/details?tenant_id&store_id&product   -> raw SP row (usp_ProductDetails, no fixed schema)
// tenant_id is the workspace selection: the login user's tenant, or a tenant
// returned by GET /api/tenants. The renderer does not invent ids. The
// backend's assert_tenant_access still governs whether that tenant_id is honoured.
//
// Endpoints beyond /search, /batches/search and /core return raw SQL
// Server stored-procedure result rows with no Pydantic model (confirmed by
// reading service.py/repository.py — they are pass-through plumbing, not a
// typed contract). UI code consuming them must render defensively (read
// whatever keys are present) rather than assume an exact field name/casing.
import { apiGet, apiPost } from '../api/client.js';

export function searchProducts(tenantId, query, { onlyStock = false } = {}) {
  const params = new URLSearchParams({ tenant_id: tenantId, q: query, only_stock: onlyStock ? '1' : '0' });
  return apiGet(`/api/stock-availability/products/search?${params.toString()}`);
}

export function searchBatches(tenantId, { batch = '', mrp = '', product = '' } = {}) {
  const params = new URLSearchParams({ tenant_id: tenantId, batch, mrp, product });
  return apiGet(`/api/stock-availability/batches/search?${params.toString()}`);
}

export function productDetails(tenantId, storeId, productCode) {
  const params = new URLSearchParams({ tenant_id: tenantId, store_id: storeId, product: productCode });
  return apiGet(`/api/stock-availability/products/details?${params.toString()}`);
}

// Combines batches + purchases + sales + movement in one round trip — the
// backend's own perf-optimized endpoint for exactly this "product detail
// panel" use case, per service.py's docstring. Prefer this over calling
// /products/batches, /products/purchases, /products/sales, /products/movement
// separately.
export function productCore(tenantId, storeId, productCode, { months = 3 } = {}) {
  const params = new URLSearchParams({ tenant_id: tenantId, store_id: storeId, product: productCode, months: String(months) });
  return apiGet(`/api/stock-availability/products/core?${params.toString()}`);
}

// One request for every store's core data instead of one request per store —
// N concurrent per-store /products/core calls contend on the same heavy
// query, leaving most stores stuck on "Loading..." (the all-stores Quick
// Stock view only had 1-2 of 6 columns ever resolve). Backend parallelizes
// internally with a bounded thread pool (see service.product_core_bulk).
export function productCoreBulk(tenantId, items, { months = 3 } = {}) {
  return apiPost('/api/stock-availability/products/core/bulk', { tenant_id: tenantId, months, items });
}

export function billItems(tenantId, storeId, billNo, billDate) {
  const params = new URLSearchParams({ tenant_id: tenantId, store_id: storeId, bill_no: billNo });
  if (billDate) params.set('bill_date', billDate);
  return apiGet(`/api/stock-availability/products/bill?${params.toString()}`);
}

// GRN (Purchase Bill) drawer — mirrors billItems for the purchase side.
export function purchaseBill(tenantId, storeId, grnNo, grnDate) {
  const params = new URLSearchParams({ tenant_id: tenantId, store_id: storeId, grn_no: String(grnNo) });
  if (grnDate) params.set('grn_date', grnDate);
  return apiGet(`/api/stock-availability/bills/purchase?${params.toString()}`);
}

// Resolves the equivalent product in each target store via the real Product
// Mapping matcher — a store whose product name differs by even whitespace
// from the searched store still resolves instead of silently staying blank.
export function crossStoreMatch(tenantId, sourceStoreId, sourceProductCode, sourceProductName, targetStoreIds) {
  return apiPost('/api/stock-availability/products/sync-selection', {
    tenant_id: tenantId,
    source_store_id: sourceStoreId,
    source_product_code: sourceProductCode,
    source_product_name: sourceProductName,
    target_store_ids: targetStoreIds,
  });
}
