// Uses the existing, unmodified backend contract — verified against
// backend/modules/label_exporter/router.py and schemas.py. This wraps every
// route the old supplier-stock-client Label Exporter screen uses, so
// LabelExportPage.jsx only ever calls into this file.
//
// Blob-returning endpoints (PDF / Excel export) bypass apiRequest, which only
// ever parses JSON or text — see fetchBlob()/downloadBlob() below.
import { apiGet, apiPost, apiPut } from '../api/client.js';
import { getSession } from './sessionStore.js';
import { resolveApiBaseUrl } from './settingsStore.js';

function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') return;
    search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

// ---------- Search ----------

export function searchLabelProducts(tenantId, storeId, filters = {}) {
  return apiGet(`/api/label-exporter/products/search${qs({
    tenant_id: tenantId,
    store_id: storeId,
    q: filters.q,
    starts_with: filters.startsWith,
    unit_description: filters.unitDescription,
    unit_description_mode: filters.unitDescriptionMode,
    box_number: filters.boxNumber,
    stock_filter: filters.stockFilter,
    only_null_sublocation: filters.onlyNullSublocation ? 1 : 0,
    only_sale_unit_gt_one: filters.onlySaleUnitGtOne ? 1 : 0,
    sublocation_filter: filters.sublocationFilter,
    review_status: filters.reviewStatus,
    unit_source: filters.unitSource,
  })}`);
}

// ---------- Review (Y/N + remarks) ----------

export function updateLabelReview(tenantId, storeId, productCode, body) {
  return apiPut(`/api/label-exporter/products/${encodeURIComponent(productCode)}/review${qs({ tenant_id: tenantId, store_id: storeId })}`, body);
}

export function bulkSetLabelInclude(tenantId, storeId, productCodes, includeLabel) {
  return apiPut(`/api/label-exporter/products/bulk-review${qs({ tenant_id: tenantId, store_id: storeId })}`, {
    product_codes: productCodes,
    include_label: includeLabel,
  });
}

// ---------- Unit / location correction ----------

export function correctLabelUnit(tenantId, storeId, productCode, unitDescription, currentUnit) {
  return apiPut(`/api/label-exporter/products/${encodeURIComponent(productCode)}/unit${qs({ tenant_id: tenantId, store_id: storeId })}`, {
    unit_description: unitDescription,
    current_unit: currentUnit || '',
  });
}

export function bulkCorrectLabelUnit(tenantId, storeId, productCodes, unitDescription) {
  return apiPut(`/api/label-exporter/products/bulk-unit${qs({ tenant_id: tenantId, store_id: storeId })}`, {
    product_codes: productCodes,
    unit_description: unitDescription,
  });
}

export function correctLabelLocation(tenantId, storeId, productCode, location, currentLocation) {
  return apiPut(`/api/label-exporter/products/${encodeURIComponent(productCode)}/location${qs({ tenant_id: tenantId, store_id: storeId })}`, {
    location,
    current_location: currentLocation || '',
  });
}

// ---------- Product intelligence (trend / purchases / sales) ----------

export function getLabelProductTrend(tenantId, storeId, productCode) {
  return apiGet(`/api/label-exporter/products/${encodeURIComponent(productCode)}/trend${qs({ tenant_id: tenantId, store_id: storeId })}`);
}

export function getLabelProductPurchases(tenantId, storeId, productCode) {
  return apiGet(`/api/label-exporter/products/${encodeURIComponent(productCode)}/purchases${qs({ tenant_id: tenantId, store_id: storeId })}`);
}

export function getLabelProductSales(tenantId, storeId, productCode) {
  return apiGet(`/api/label-exporter/products/${encodeURIComponent(productCode)}/sales${qs({ tenant_id: tenantId, store_id: storeId })}`);
}

// ---------- Box assignment (preview / commit / clear) ----------

export function previewLabelAssignment(tenantId, storeId, body) {
  return apiPost(`/api/label-exporter/assignments/preview${qs({ tenant_id: tenantId, store_id: storeId })}`, body);
}

export function commitLabelAssignment(tenantId, storeId, body) {
  return apiPost(`/api/label-exporter/assignments/commit${qs({ tenant_id: tenantId, store_id: storeId })}`, body);
}

export function clearLabelAssignment(tenantId, storeId, productCodes) {
  return apiPost(`/api/label-exporter/assignments/clear${qs({ tenant_id: tenantId, store_id: storeId })}`, { product_codes: productCodes });
}

export function clearLabelReview(tenantId, storeId, productCodes) {
  return apiPost(`/api/label-exporter/review/clear${qs({ tenant_id: tenantId, store_id: storeId })}`, { product_codes: productCodes });
}

// ---------- Label queue ----------

export function getLabelQueue(tenantId, storeId) {
  return apiGet(`/api/label-exporter/label-queue${qs({ tenant_id: tenantId, store_id: storeId })}`);
}

export function markLabelsPrinted(tenantId, storeId, productCodes) {
  return apiPost(`/api/label-exporter/label-queue/mark-printed${qs({ tenant_id: tenantId, store_id: storeId })}`, { product_codes: productCodes });
}

export function clearPrintedLabels(tenantId, storeId, productCodes) {
  return apiPost(`/api/label-exporter/label-queue/clear-printed${qs({ tenant_id: tenantId, store_id: storeId })}`, { product_codes: productCodes });
}

// ---------- Per-letter lock / finalise ----------

export function getLabelLetterLock(tenantId, storeId, letter) {
  return apiGet(`/api/label-exporter/letter-lock${qs({ tenant_id: tenantId, store_id: storeId, letter })}`);
}

export function lockLabelLetter(tenantId, storeId, letter) {
  return apiPost(`/api/label-exporter/letter-lock${qs({ tenant_id: tenantId, store_id: storeId, letter })}`);
}

export function unlockLabelLetter(tenantId, storeId, letter) {
  return apiPost(`/api/label-exporter/letter-lock/unlock${qs({ tenant_id: tenantId, store_id: storeId, letter })}`);
}

export function getLabelLetterFinalise(tenantId, storeId, letter) {
  return apiGet(`/api/label-exporter/letter-finalise${qs({ tenant_id: tenantId, store_id: storeId, letter })}`);
}

export function finaliseLabelLetter(tenantId, storeId, letter) {
  return apiPost(`/api/label-exporter/letter-finalise${qs({ tenant_id: tenantId, store_id: storeId, letter })}`);
}

// ---------- Blob downloads (PDF / Excel) ----------
//
// api/client.js's apiRequest() always parses the response as JSON or text, so
// it cannot be reused for these two binary endpoints. This fetches directly,
// attaches the same bearer token apiRequest would, and returns a Blob.
async function fetchBlob(path) {
  const token = getSession()?.token || '';
  const url = `${String(resolveApiBaseUrl() || '').replace(/\/+$/, '')}/${String(path).replace(/^\/+/, '')}`;
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const data = await response.json();
      message = data?.detail || data?.message || message;
    } catch {
      // body wasn't JSON — keep the generic message
    }
    throw new Error(message);
  }
  return response.blob();
}

export function exportLabelQueuePdf(tenantId, storeId, letter = '') {
  return fetchBlob(`/api/label-exporter/label-queue/pdf${qs({ tenant_id: tenantId, store_id: storeId, letter })}`);
}

export function exportLabelProductsExcel(tenantId, storeId, letter) {
  return fetchBlob(`/api/label-exporter/products/export.xlsx${qs({ tenant_id: tenantId, store_id: storeId, letter })}`);
}

export function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
