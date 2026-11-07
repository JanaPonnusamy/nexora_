// Pure helpers for the Non-Moving Stock screen (kept JSX-free so node --test
// can load them).

export const SECTIONS = [
  { id: 'own', label: 'Own Store Analysis' },
  { id: 'other', label: 'Other Stores Analysis' },
  { id: 'transfer', label: 'Transfer Opportunities' },
  { id: 'value', label: 'Stock Value & Expiry Risk' },
];

// Classification keys from the backend, in severity order. `tone` picks the
// .nms-cls--<tone> colour.
export const CLASSES = [
  { key: 'ACTIVE', label: 'Active', tone: 'active' },
  { key: 'SLOW', label: 'Slow Moving', tone: 'slow' },
  { key: 'VERY_SLOW', label: 'Very Slow', tone: 'veryslow' },
  { key: 'NM_RISK', label: 'Non-Moving Risk', tone: 'risk' },
  { key: 'NON_MOVING', label: 'Non-Moving', tone: 'nonmoving' },
  { key: 'DEAD', label: 'Critical Dead Stock', tone: 'dead' },
  { key: 'NEW', label: 'New - No Sale Yet', tone: 'new' },
  { key: 'NO_SALES', label: 'No Sales History', tone: 'nosales' },
];
export const CLASS_BY_KEY = Object.fromEntries(CLASSES.map((c) => [c.key, c]));
export const NON_MOVING_KEYS = ['NM_RISK', 'NON_MOVING', 'DEAD', 'NO_SALES'];

export const FLAG_TEXT = {
  STOCK_MISMATCH: 'Store stock and batch stock disagree',
  SALE_DATE_CONFLICT: 'Bill lines and the POS monthly rollup disagree on the last sale date (bill lines used)',
  LAST_SALE_FROM_ROLLUP: 'Last sale is older than the synced bill history - taken from the POS monthly rollup',
  LAST_SALE_FROM_BATCH: 'Last sale taken from the batch record (no bill or rollup date)',
  RECENT_GRN: 'Received in the last 10 days',
  INVALID_SALES: 'Has cancelled / invalid sale lines in 180 days (excluded)',
  INACTIVE: 'Product is inactive in the POS',
  NO_TXN_HISTORY: 'No sale, purchase or receipt on record',
};

export const toNum = (v) => {
  const n = Number(v);
  return v === null || v === undefined || v === '' || !Number.isFinite(n) ? null : n;
};

export function fmtQty(v) {
  const n = toNum(v);
  return n === null ? '—' : n.toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

export function fmtMoney(v) {
  const n = toNum(v);
  return n === null ? '—' : n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Indian short form for KPI tiles: 1,32,079 -> 1.32 L; 2,40,00,000 -> 2.40 Cr.
export function fmtCompact(v) {
  const n = toNum(v);
  if (n === null) return '—';
  const a = Math.abs(n);
  if (a >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)} K`;
  return n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

// 'YYYY-MM-DD...' -> 'DD-MM-YYYY'.
export function fmtDate(v) {
  if (!v) return '—';
  const [y, m, d] = String(v).slice(0, 10).split('-');
  return d ? `${d}-${m}-${y}` : String(v);
}

export function fmtDays(v) {
  const n = toNum(v);
  return n === null ? 'never' : n.toLocaleString('en-IN');
}

// Own Store filter state -> /own-store query params (empty values dropped by toQuery).
export function ownParams(tenantId, storeId, f, sort, page, pageSize) {
  return {
    tenant_id: tenantId,
    store_id: storeId,
    search: f.search?.trim() || undefined,
    classes: f.classes?.length ? f.classes.join(',') : undefined,
    ptype: f.ptype || undefined,
    supplier: f.supplier || undefined,
    min_days: f.minDays === '' || f.minDays == null ? undefined : f.minDays,
    max_days: f.maxDays === '' || f.maxDays == null ? undefined : f.maxDays,
    expiry: f.expiry || undefined,
    include_zero: f.includeZero ? 'true' : undefined,
    non_moving_only: f.nonMovingOnly ? 'true' : undefined,
    sort: sort.key,
    direction: sort.dir,
    page,
    page_size: pageSize,
  };
}

// Age filter presets (days since last sale).
export const AGE_PRESETS = [
  { id: '', label: 'Any age', min: '', max: '' },
  { id: '31', label: '> 30 days', min: 31, max: '' },
  { id: '61', label: '> 60 days', min: 61, max: '' },
  { id: '91', label: '> 90 days', min: 91, max: '' },
  { id: '181', label: '> 180 days', min: 181, max: '' },
  { id: '366', label: '> 365 days', min: 366, max: '' },
];

// ----- Manual review list (per tenant, this PC only) -----
export const reviewKey = (tenantId) => `nexora.desktop.nmReview.${tenantId || 'none'}`;
const itemKey = (it) => `${String(it.store_id).toUpperCase()}|${it.product_code}`;

export function readReview(storage, tenantId) {
  try {
    const list = JSON.parse(storage?.getItem(reviewKey(tenantId)) || '[]');
    return Array.isArray(list) ? list.filter((it) => it && it.store_id && it.product_code != null) : [];
  } catch {
    return [];
  }
}

export function writeReview(storage, tenantId, list) {
  try { storage?.setItem(reviewKey(tenantId), JSON.stringify(list)); } catch { /* storage unavailable */ }
}

export function inReview(list, storeId, code) {
  const k = itemKey({ store_id: storeId, product_code: code });
  return list.some((it) => itemKey(it) === k);
}

// Add when absent, remove when present.
export function toggleReview(list, item) {
  const k = itemKey(item);
  return list.some((it) => itemKey(it) === k)
    ? list.filter((it) => itemKey(it) !== k)
    : [...list, { store_id: item.store_id, store_code: item.store_code, product_code: String(item.product_code), product_name: item.product_name, added: new Date().toISOString().slice(0, 10) }];
}

// Bar height (%) on a shared scale; a non-zero value never drops below 3%.
export function barPct(v, max) {
  const n = toNum(v) || 0;
  if (n <= 0 || !max) return 0;
  return Math.max(3, (n / max) * 100);
}
