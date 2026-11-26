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

// Own Store grid columns: grouped for visual separators + the Column
// Settings panel (Procurement's ⚙ show/move/width model -- see
// ProcurementWorkspace.jsx's PW_COLUMNS / colOrder / colWidths). `key` is the
// persisted id (order + visibility + width), `mandatory` columns can't be
// hidden (owner ruling: Supplier, Product, Stock).
export const OWN_COL_GROUPS = [
  { id: 'product', label: 'Supplier & Product' },
  { id: 'inventory', label: 'Batch & Inventory' },
  { id: 'dates', label: 'Date Tracking' },
  { id: 'ageing', label: 'Ageing' },
  { id: 'pricing', label: 'Pricing & Valuation' },
  { id: 'reference', label: 'References' },
];

export const OWN_COLS_DEF = [
  { key: 'supplier', label: 'Supplier', sort: 'supplier_name', w: 200, group: 'product', mandatory: true, sortType: 'text' },
  { key: 'product_code', label: 'Code', sort: 'product_code', w: 70, group: 'product', sortType: 'text' },
  { key: 'product_name', label: 'Product', sort: 'product_name', group: 'product', mandatory: true, sortType: 'text' },
  { key: 'pack', label: 'Pack', sort: 'pack', w: 54, num: true, group: 'inventory', sortType: 'text' },
  { key: 'batch_count', label: 'Batch', sort: 'batch_count', w: 54, num: true, group: 'inventory', sortType: 'num' },
  { key: 'stock', label: 'Stock', sort: 'stock', w: 64, num: true, group: 'inventory', mandatory: true, sortType: 'num' },
  { key: 'expiry_status', label: 'Expiry', sort: 'expiry_status', w: 90, group: 'dates', sortType: 'text' },
  { key: 'last_grn_date', label: 'Last Received', sort: 'last_grn_date', w: 90, group: 'dates', sortType: 'date' },
  { key: 'last_sale_date', label: 'Last Sold', sort: 'last_sale_date', w: 82, group: 'dates', sortType: 'date' },
  { key: 'days_since_sale', label: 'Days', sort: 'days_since_sale', w: 56, num: true, group: 'ageing', sortType: 'days' },
  { key: 'ptr_value', label: 'Purchase', sort: 'ptr_value', w: 88, num: true, group: 'pricing', sortType: 'num' },
  { key: 'cost_value', label: 'Cost Value', sort: 'cost_value', w: 88, num: true, group: 'pricing', sortType: 'num' },
  { key: 'mrp_value', label: 'MRP', sort: 'mrp_value', w: 88, num: true, group: 'pricing', sortType: 'num' },
  { key: 'classification', label: 'Classification', sort: 'classification', w: 128, group: 'reference', sortType: 'classification' },
  { key: 'action', label: 'Action', w: 58, group: 'reference', mandatory: true },
];
export const OWN_COLS_BY_KEY = Object.fromEntries(OWN_COLS_DEF.map((c) => [c.key, c]));
export const OWN_COLS_DEFAULT_ORDER = OWN_COLS_DEF.map((c) => c.key);
export const OWN_COLS_MANDATORY = OWN_COLS_DEF.filter((c) => c.mandatory).map((c) => c.key);

// ----- Column settings persistence (per tenant + store, this PC only;
// mirrors Procurement's own localStorage-per-PC pattern but under its own
// key, so changing Non-Moving Stock columns never touches Procurement's
// saved pwColumnOrder4 / pwColumnWidths / pwLegacyColumns4) -----
export const colSettingsKey = (tenantId, storeId) => `nexora.desktop.nmOwnCols.${tenantId || 'none'}.${storeId || 'none'}`;
const DEFAULT_COL_SETTINGS = { order: OWN_COLS_DEFAULT_ORDER, hidden: [], widths: {} };

export function readColSettings(storage, tenantId, storeId) {
  try {
    const saved = JSON.parse(storage?.getItem(colSettingsKey(tenantId, storeId)) || 'null');
    if (!saved || !Array.isArray(saved.order)) return { ...DEFAULT_COL_SETTINGS };
    const order = saved.order.filter((k) => OWN_COLS_BY_KEY[k]);
    for (const k of OWN_COLS_DEFAULT_ORDER) if (!order.includes(k)) order.push(k);
    const hidden = Array.isArray(saved.hidden) ? saved.hidden.filter((k) => OWN_COLS_BY_KEY[k] && !OWN_COLS_MANDATORY.includes(k)) : [];
    const widths = saved.widths && typeof saved.widths === 'object' && !Array.isArray(saved.widths) ? saved.widths : {};
    return { order, hidden, widths };
  } catch {
    return { ...DEFAULT_COL_SETTINGS };
  }
}

export function writeColSettings(storage, tenantId, storeId, settings) {
  try { storage?.setItem(colSettingsKey(tenantId, storeId), JSON.stringify(settings)); } catch { /* storage unavailable */ }
}

// Ordered, visible column defs for rendering, with a `groupStart` flag on the
// first visible column of each group (for the separator rule) and any saved
// width override applied.
export function resolveOwnCols(settings) {
  const visible = settings.order.filter((k) => !settings.hidden.includes(k)).map((k) => OWN_COLS_BY_KEY[k]).filter(Boolean);
  let lastGroup = null;
  return visible.map((c) => {
    const groupStart = c.group !== lastGroup;
    lastGroup = c.group;
    const w = settings.widths?.[c.key];
    return { ...c, groupStart, w: (w != null && w !== '') ? Number(w) : c.w };
  });
}

// Age filter presets (days since last sale). min_days passes a never-sold
// row through unfiltered (service.py filter_rows / the frontend mirror
// below both treat days=None as "not excluded by a minimum"), so every
// preset here already reads as "N+ days OR never sold" without a separate
// never-sold flag.
export const AGE_PRESETS = [
  { id: '', label: 'Any age', min: '', max: '' },
  { id: '31', label: '30+ days', min: 31, max: '' },
  { id: '61', label: '60+ days', min: 61, max: '' },
  { id: '91', label: '90+ days', min: 91, max: '' },
  { id: '121', label: '120+ days', min: 121, max: '' },
  { id: '181', label: '180+ days', min: 181, max: '' },
  { id: '271', label: '270+ days', min: 271, max: '' },
  { id: '366', label: '365+ days', min: 366, max: '' },
];

// "Show" presets for the Own Store filter toolbar. Each sets the pending
// filter patch applied on Apply/Enter. `NO_SALES` is the backend's existing
// classification for "no sale in any source" (and not within new_days of
// first receipt) -- this IS "Never Sold"; no new backend classification was
// needed. "Non-moving (180+ days / no sales)" is a NEW default distinct from
// the existing non_moving_only flag (which means > 90 days / NM_RISK or
// worse, per service.py's NON_MOVING set) -- it is expressed purely as
// min_days=180 with non_moving_only off, which already includes never-sold
// rows (min_days doesn't exclude a null days_since_sale), so no backend
// change was required for this default either.
export const SHOW_PRESETS = [
  { id: 'nm180', label: 'Non-Moving (180+ days / no sales)', minDays: 181, maxDays: '', classes: [], nonMovingOnly: false },
  { id: 'all', label: 'All Products', minDays: '', maxDays: '', classes: [], nonMovingOnly: false },
  { id: 'never', label: 'Never Sold', minDays: '', maxDays: '', classes: ['NO_SALES'], nonMovingOnly: false },
  { id: 'slow', label: 'Slow Moving', minDays: '', maxDays: '', classes: ['SLOW'], nonMovingOnly: false },
  { id: 'veryslow', label: 'Very Slow', minDays: '', maxDays: '', classes: ['VERY_SLOW'], nonMovingOnly: false },
  { id: 'dead', label: 'Critical Dead Stock', minDays: '', maxDays: '', classes: ['DEAD'], nonMovingOnly: false },
  { id: 'new', label: 'New - No Sale Yet', minDays: '', maxDays: '', classes: ['NEW'], nonMovingOnly: false },
  { id: 'nosaleshist', label: 'No Sales History', minDays: '', maxDays: '', classes: ['NO_SALES'], nonMovingOnly: false },
];
export const SHOW_PRESET_BY_ID = Object.fromEntries(SHOW_PRESETS.map((p) => [p.id, p]));
export const DEFAULT_SHOW_ID = 'nm180';

// True when two filter states are equivalent for query purposes (used to
// show the "unapplied changes" indicator and to skip a no-op Apply).
export function filtersEqual(a, b) {
  if (a === b) return true;
  if (!a || !b) return false;
  const ca = [...(a.classes || [])].sort();
  const cb = [...(b.classes || [])].sort();
  return a.search === b.search && ca.length === cb.length && ca.every((v, i) => v === cb[i])
    && a.ptype === b.ptype && a.supplier === b.supplier && String(a.minDays) === String(b.minDays)
    && String(a.maxDays) === String(b.maxDays) && a.age === b.age && a.expiry === b.expiry
    && !!a.includeZero === !!b.includeZero && !!a.nonMovingOnly === !!b.nonMovingOnly;
}

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

// ----- AG Grid client-side sort comparators (Own Store) -----
// Mirrors the backend's service.py _sort_key / _page: NULL/blank always
// sorts last on screen, in EITHER direction. AG Grid does not auto-negate a
// custom comparator's result for a descending sort -- it passes `isDescending`
// as the comparator's 5th argument and uses the return value as-is (see
// ag-grid-community's SortComparatorFn type) -- so each comparator below
// flips its own real-value comparison on `desc` but keeps nulls pinned to
// the end of the array regardless, matching the backend exactly (verified
// against both directions in nonMovingView.test.js).
const NULLISH = (v) => v === null || v === undefined || v === '';

function withNullsLast(cmp) {
  return (a, b, nodeA, nodeB, isDescending) => {
    if (NULLISH(a) && NULLISH(b)) return 0;
    if (NULLISH(a)) return 1;
    if (NULLISH(b)) return -1;
    const result = cmp(a, b);
    return isDescending ? -result : result;
  };
}

export const numericComparator = withNullsLast((a, b) => toNum(a) - toNum(b));
export const dateComparator = withNullsLast((a, b) => new Date(a).getTime() - new Date(b).getTime());
export const textComparator = withNullsLast((a, b) => String(a).toLowerCase().localeCompare(String(b).toLowerCase()));

// days_since_sale: "never sold" (null) is the oldest possible value, i.e. it
// sorts as the largest number of days -- same rule as service.py's
// _sort_key -- rather than being pinned to the end regardless of direction.
export function daysSinceSaleComparator(a, b, nodeA, nodeB, isDescending) {
  if (NULLISH(a) && NULLISH(b)) return 0;
  const an = NULLISH(a) ? Number.POSITIVE_INFINITY : toNum(a);
  const bn = NULLISH(b) ? Number.POSITIVE_INFINITY : toNum(b);
  const result = an - bn;
  return isDescending ? -result : result;
}

const CLASS_ORDER = Object.fromEntries(CLASSES.map((c, i) => [c.key, i]));
export const classificationComparator = withNullsLast((a, b) => (CLASS_ORDER[a] ?? 99) - (CLASS_ORDER[b] ?? 99));

export const COMPARATORS = {
  text: textComparator,
  num: numericComparator,
  date: dateComparator,
  days: daysSinceSaleComparator,
  classification: classificationComparator,
};

// Count of active (non-default) filters, for the status bar's "Active Filter
// Count" -- search text, a non-default Show selection, Age preset, and every
// other filter that narrows the result counts as one active filter each.
// Show counts as active whenever it differs from DEFAULT_SHOW_ID -- this
// covers both a different preset AND "Custom" (show: ''), which happens
// whenever minDays/maxDays/classes were set directly (e.g. via a
// classification chip) rather than through a SHOW_PRESETS option.
export function activeFilterCount(f) {
  let n = 0;
  if (f.search?.trim()) n += 1;
  if ((f.show || '') !== DEFAULT_SHOW_ID) n += 1;
  if (f.ptype) n += 1;
  if (f.supplier) n += 1;
  if (f.age) n += 1;
  if (f.expiry) n += 1;
  if (f.includeZero) n += 1;
  return n;
}
