// Ported verbatim (method names, URL paths, params, body shapes all
// unchanged) from desktop/supplier-stock-client/src/api/client.js's
// legacy-order / procurement / WhatsApp methods, which
// ProcurementWorkspace.jsx and its sibling panels (supplierCompare.jsx,
// storeTrends.jsx, abnormalSales.jsx, bulkAssign.jsx, harvestReview.jsx,
// siteCheckBar.jsx, storeWhatsApp.jsx, supplierWhatsApp.jsx) call as
// `api.<name>(...)`. Owner instruction: copy the logic unchanged, only
// adapt plumbing. The one mechanical difference every method below has
// from its source: the source's `request(path, { session, ... })` took an
// explicit `session` argument per call; this app's apiGet/apiPost/apiPut/
// apiPatch/apiDelete (src/api/client.js) pull the bearer token from
// sessionStore internally, so every `session` parameter is dropped and
// every call site in the copied components passes one argument fewer.
// Nothing about which endpoint is called, with which params, changes.
//
// Write-action methods (assign/export/finalize/harvest/portal/WhatsApp
// send/etc.) are kept here, fully implemented, exactly like the source —
// per the owner's read-only rule, the UI controls that would trigger them
// are disabled in the copied components, not the functions themselves.
import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from '../api/client.js';
import { resolveApiBaseUrl } from './settingsStore.js';
import { getSession } from './sessionStore.js';

function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

function joinUrl(base, path) {
  return `${String(base || '').replace(/\/+$/, '')}/${String(path || '').replace(/^\/+/, '')}`;
}

// getStoreWhatsAppFile / getBlob in the source do a raw fetch for a binary
// response (not JSON) — same reason here: apiGet's response parsing only
// branches json/text, never blob.
async function fetchBlob(path) {
  const token = getSession()?.token || '';
  let response;
  try {
    response = await fetch(joinUrl(resolveApiBaseUrl(), path), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch {
    throw new Error('Unable to reach the server. Check that the API is running.');
  }
  if (!response.ok) {
    let detail = response.statusText || 'Download failed';
    try {
      const data = await response.json();
      detail = data?.detail || data?.message || detail;
    } catch {
      /* no JSON body */
    }
    throw new Error(detail);
  }
  return response.blob();
}

// Platform store list, same filtering as the source's api.listStores —
// kept here (not read from useAuth()'s own directory) so this port's
// platformStore/tenantId resolution logic matches the source exactly.
export function listStores() {
  return apiGet('/api/stores').then((rows) => (
    Array.isArray(rows) ? rows.filter((s) => s.is_active !== false) : rows
  ));
}

export function legacyStores(activeOnly = true) {
  return apiGet(`/api/legacy-order/stores${qs({ active_only: activeOnly })}`);
}

// ----- Order Workspace / Procurement Workspace (legacy VB-style ordering) -----

export function legacyQtyCheckRows(storeName) {
  return apiGet(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}`);
}

export function legacyResetPendingQtyCheck(storeName) {
  return apiPost(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/reset-pending`, {});
}

export function legacyPendingOrderRows(storeName) {
  return apiGet(`/api/legacy-order/pending-order/${encodeURIComponent(storeName)}`);
}

// Local order cache (Order_Sync_Redesign_Plan.md section 3.3). Not wired
// into any screen yet -- added here so the app CAN read it once a screen
// is pointed at it; existing qty-check/orders calls above are untouched.
// { available: false } when no cache has been built for this store yet
// (LEGACY_ORDER_CACHE_ENABLED unset, or first order not yet processed with
// it on) -- callers should fall back to legacyQtyCheckRows/legacyOrders.
export function legacyOrderCacheView(storeName) {
  return apiGet(`/api/legacy-order/order-cache/${encodeURIComponent(storeName)}/view`);
}

export function legacySkipProduct(storeName, productCode, mode) {
  return apiPost(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/skip`, { mode });
}

export function legacyUpdateQtyCheck(storeName, productCode, orderQty) {
  return apiPatch(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}`, { order_qty: orderQty });
}

export function legacyUpdateRemarks(storeName, productCode, remarks) {
  return apiPatch(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/${productCode}/remarks`, { remarks });
}

export function legacyOrders(storeName) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}`);
}

export function legacyUpdateOrderQty(storeName, productCode, orderQty) {
  return apiPatch(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/${productCode}`, { order_qty: orderQty });
}

export function legacyOrderWorkflow(storeName) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/workflow`);
}

export function legacyOrderHeader(storeName) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/header`);
}

export function legacyFinalizeOrder(storeName, note) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/workflow/finalize`, { note: note || null });
}

export function legacyReopenOrder(storeName, note) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/workflow/reopen`, { note: note || null });
}

export function legacyAbnormalSales(storeName) {
  return apiGet(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/abnormal-sales`, { timeoutMs: 120000 });
}

export function legacySetDontConsider(storeName, body) {
  return apiPatch(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/sales/dont-consider`, body);
}

export function legacyOrderHistory(storeName, productCode) {
  return apiGet(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/order-history`);
}

export function legacyPurchaseDetails(storeName, productCode, mode) {
  return apiGet(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/purchase-details${qs({ mode })}`);
}

export function legacyPurchaseInvoice(storeName, params) {
  return apiGet(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/purchase-invoice${qs(params)}`);
}

export function legacySaleBill(storeName, params) {
  return apiGet(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/sale-bill${qs(params)}`);
}

export function legacySalesDetails(storeName, productCode, mode) {
  return apiGet(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/sales-details${qs({ mode })}`);
}

export function legacyMonthlyStats(storeName, productCode, mode, months) {
  return apiGet(`/api/legacy-order/qty-check/${encodeURIComponent(storeName)}/${productCode}/monthly-stats${qs({ mode, months })}`);
}

export function legacySuppliers(storeName, search) {
  return apiGet(`/api/legacy-order/suppliers/${encodeURIComponent(storeName)}${qs({ search: search || '' })}`);
}

export function legacyOrdersBySupplier(storeName, supplierCode, mode) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/by-supplier${qs({ supplier_code: supplierCode, mode })}`);
}

export function legacyAllOpenOrders(storeName) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/all-open`);
}

export function legacySupplierStockCompare(storeName) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/supplier-stock-compare`);
}

export function legacyAssignedOrders(storeName, supplierCode) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/assigned${qs({ supplier_code: supplierCode })}`);
}

export function legacyRemoveUnavailable(storeName, supplierCode) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/unavailable/remove`, { supplier_code: supplierCode });
}

export function legacyUnassignAll(storeName, supplierCode) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/assigned/unassign-all`, { supplier_code: supplierCode });
}

export function legacyAutoAssignPreview(storeName) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/auto-assign`);
}

export function legacyAutoAssign(storeName, productCodes) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/auto-assign`, { product_codes: productCodes });
}

export function legacyWhatsAppContacts(storeName) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/whatsapp/contacts`);
}

export function legacySaveWhatsAppContact(storeName, payload) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/whatsapp/contacts`, payload);
}

export function legacyWhatsAppStatus(storeName, supplierCode) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/whatsapp/status${qs({ supplier_code: supplierCode })}`);
}

export function legacyMarkWhatsAppSent(storeName, supplierCode, productCodes, kind) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/whatsapp/sent`, {
    supplier_code: supplierCode,
    product_codes: productCodes,
    kind,
  });
}

export function legacySupplierPortal(storeName, supplierCode) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/portal`);
}

export function legacySupplierPortalLogin(storeName, supplierCode) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/portal/login`);
}

export function legacySaveSupplierPortal(storeName, supplierCode, payload) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/portal`, payload);
}

export function legacyHarvestSupplierStock(storeName, supplierCode, rows, complete) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/harvest`, {
    rows,
    complete: complete !== false,
  });
}

export function legacySupplierHarvestStatus(storeName, supplierCode) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/harvest`);
}

export function legacySupplierMatchReview(storeName, supplierCode) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/match-review`);
}

export function legacySupplierMatchCodes(storeName, supplierCode) {
  return apiGet(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/match-codes`);
}

export function legacyConfirmSupplierMatch(storeName, supplierCode, payload) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/suppliers/${encodeURIComponent(supplierCode)}/match-review/confirm`, payload);
}

export function legacyAssignSupplier(storeName, productCode, supplierCode, supplierName) {
  return apiPost(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/${productCode}/assign`, {
    supplier_code: supplierCode,
    supplier_name: supplierName,
  });
}

// Export endpoints return the generated workbook itself (binary
// Content-Disposition attachment + X-Exported-Count header), not JSON — so
// unlike every other method in this file they cannot go through apiPost
// (src/api/client.js only ever branches on `application/json` vs `.text()`;
// routed through it, the binary body was read as text and the `{ blob, ... }`
// shape callers destructure never existed, so `blob` was `undefined` — the
// actual cause of the `readAsDataURL(): parameter 1 is not of type 'Blob'`
// export crash traced from OwExportKit.js's blobToBase64 back through
// ProcurementWorkspace.jsx's runExport/runPendingExport to here). Ported from
// supplier-stock-client/src/api/client.js's own legacyExportOrder /
// legacyExportPendingOrder, which fetch + `response.blob()` directly for
// exactly this reason — restoring that pattern instead of apiPost.
async function legacyExportFetch(path, body) {
  const token = getSession()?.token || '';
  let response;
  try {
    response = await fetch(`${String(resolveApiBaseUrl() || '').replace(/\/+$/, '')}/${String(path).replace(/^\/+/, '')}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error('Unable to reach the server. Check that the API is running.');
  }
  if (!response.ok) {
    let detail = response.statusText || 'Export failed';
    try {
      const parsed = await response.json();
      const d = parsed?.detail ?? parsed?.message ?? parsed?.error;
      detail = (typeof d === 'string' && d) || detail;
    } catch { /* no JSON body */ }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = /filename="?([^"]+)"?/.exec(disposition);
  return {
    blob,
    filename: match?.[1] || null,
    exportedCount: Number(response.headers.get('X-Exported-Count') || 0),
  };
}

export async function legacyExportOrder(storeName, supplierCode, supplierName, mode, splitSize, options = {}) {
  const body = {
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
    ...(options.remarks && Object.keys(options.remarks).length ? { remarks: options.remarks } : {}),
  };
  const result = await legacyExportFetch(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/export`, body);
  return { ...result, filename: result.filename || `${supplierName || storeName} export.xlsx` };
}

export async function legacyExportPendingOrder(storeName, splitSize, options = {}) {
  const body = {
    split_size: splitSize || 0,
    ...(options.columns ? { columns: options.columns } : {}),
    ...(options.fileFormat ? { file_format: options.fileFormat } : {}),
    ...(options.orderNo ? { order_no: options.orderNo } : {}),
    ...(options.images ? { images: true } : {}),
    ...(options.remarks && Object.keys(options.remarks).length ? { remarks: options.remarks } : {}),
  };
  // Backend registers POST /orders/{store}/export-pending (see
  // backend/modules/legacy_order/router.py) — the prior /pending-order/export
  // path 404'd on every call; this was broken independently of the Blob bug.
  const result = await legacyExportFetch(`/api/legacy-order/orders/${encodeURIComponent(storeName)}/export-pending`, body);
  return { ...result, filename: result.filename || `${storeName} pending export.xlsx` };
}

// ----- Procurement (the newer platform-native engine) -----

export function procurementStoreTrends(tenantId, storeId, productCode) {
  return apiGet(`/api/procurement/stores/${encodeURIComponent(storeId)}/products/${encodeURIComponent(productCode)}/store-trends${qs({ tenant_id: tenantId })}`);
}

export function procurementProductSuggestions(tenantId, storeId, productCode) {
  return apiGet(`/api/procurement/stores/${encodeURIComponent(storeId)}/products/${encodeURIComponent(productCode)}/suggestions${qs({ tenant_id: tenantId })}`);
}

export function procurementOrderItem(tenantId, orderItemId) {
  return apiGet(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}${qs({ tenant_id: tenantId })}`);
}

export function procurementSetFinalQty(tenantId, orderItemId, finalQty, reason, by) {
  return apiPut(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/final-qty${qs({ tenant_id: tenantId })}`, {
    final_qty: finalQty,
    override_reason: reason || null,
    reviewed_by: by || null,
  });
}

export function procurementRestoreSuggested(tenantId, orderItemId, by) {
  return apiPost(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/restore-suggested${qs({ tenant_id: tenantId })}`, {
    reviewed_by: by || null,
  });
}

export function procurementSkip(tenantId, orderItemId, reason, by) {
  return apiPost(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/skip${qs({ tenant_id: tenantId })}`, {
    skip_reason: reason,
    reviewed_by: by || null,
  });
}

export function procurementRestore(tenantId, orderItemId, by) {
  return apiPost(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/restore${qs({ tenant_id: tenantId })}`, {
    reviewed_by: by || null,
  });
}

export function procurementDecision(tenantId, orderItemId) {
  return apiGet(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/decision${qs({ tenant_id: tenantId })}`);
}

export function procurementSupplierQueue(tenantId, orderItemId, limit = 5) {
  return apiGet(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/supplier-queue${qs({ tenant_id: tenantId, limit })}`);
}

export function procurementItemAssignments(tenantId, orderItemId) {
  return apiGet(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/assignments${qs({ tenant_id: tenantId })}`).then((r) => r?.items || []);
}

export function procurementAssign(tenantId, orderItemId, supplierCode, qty, by) {
  return apiPost(`/api/procurement/order-items/${encodeURIComponent(orderItemId)}/assignments${qs({ tenant_id: tenantId })}`, {
    supplier_code: supplierCode,
    qty,
    created_by: by || null,
  });
}

export function procurementRemoveAssignment(tenantId, assignmentId, by) {
  return apiDelete(`/api/procurement/assignments/${encodeURIComponent(assignmentId)}${qs({ tenant_id: tenantId, deleted_by: by })}`);
}

export function procurementExportDefaults(tenantId) {
  return apiGet(`/api/procurement/export-defaults${qs({ tenant_id: tenantId })}`);
}

export function procurementSaveExportDefaults(tenantId, body) {
  return apiPut(`/api/procurement/export-defaults${qs({ tenant_id: tenantId })}`, body);
}

// ----- Store-level / HO WhatsApp -----

export function getStoreWhatsAppOutbox(tenantId, storeId) {
  return apiGet(`/api/procurement/distribution/store-outbox${qs({ tenant_id: tenantId, store_id: storeId })}`);
}

export function claimStoreWhatsAppItem(runItemId) {
  return apiPost(`/api/procurement/distribution/store-outbox/${encodeURIComponent(runItemId)}/claim`, {});
}

export function getStoreWhatsAppFile(runItemId) {
  return fetchBlob(`/api/procurement/distribution/store-outbox/${encodeURIComponent(runItemId)}/file`);
}

export function reportStoreWhatsAppResult(runItemId, sent, error) {
  return apiPost(`/api/procurement/distribution/store-outbox/${encodeURIComponent(runItemId)}/result`, { sent, error: error || null });
}

export function hoWhatsAppState() {
  return apiGet('/api/whatsapp/state');
}

export function hoWhatsAppStatus(profileId) {
  return apiGet(`/api/whatsapp/profiles/${encodeURIComponent(profileId)}/status`, { timeoutMs: 90000 });
}

export function hoWhatsAppChats(profileId) {
  return apiGet(`/api/whatsapp/profiles/${encodeURIComponent(profileId)}/chats`, { timeoutMs: 120000 });
}

export function hoWhatsAppSendFiles(payload) {
  return apiPost('/api/whatsapp/send/chat-files', payload, { timeoutMs: 300000 });
}

export function hoWhatsAppSendText(payload) {
  return apiPost('/api/whatsapp/send/chat', payload, { timeoutMs: 180000 });
}

export function hoWhatsAppLog() {
  return apiGet('/api/whatsapp/send-log?limit=100');
}

export function getBlob(path) {
  return fetchBlob(path);
}

// ----- Non-Moving Stock Analysis (Store DB + HO SQL, read-only) -----

export function nonMoving(section, params, { signal } = {}) {
  return apiGet(`/api/non-moving-analysis/${section}${qs(params)}`, { timeoutMs: 300000, signal });
}

export async function nonMovingExcel(section, params, body) {
  const token = getSession()?.token || '';
  const q = qs(body ? params : { ...params, format: 'xlsx' });
  const response = await fetch(joinUrl(resolveApiBaseUrl(), `/api/non-moving-analysis/${section}${q}`), {
    method: body ? 'POST' : 'GET',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    let detail = response.statusText || 'Export failed';
    try {
      const data = await response.json();
      detail = data?.detail || detail;
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  const cd = response.headers.get('content-disposition') || '';
  const m = /filename="?([^";]+)"?/i.exec(cd);
  const name = m ? m[1] : `non_moving_${String(section).replace(/\//g, '_')}.xlsx`;
  return { blob: await response.blob(), filename: name, fileName: name };
}

