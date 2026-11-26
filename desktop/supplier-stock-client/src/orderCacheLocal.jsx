// Store-side order cache: this PC's downloaded copy of HO's per-store order
// cache (backend legacy_order/order_cache, schema v3) answers By Supplier
// (History / Live Stock / All products) and the supplier compare card
// locally, instead of HO re-running the PurchaseTrans-heavy grid reads.
// Live order-line states (status, qty, qty check, remarks) are still read
// from HO on every load -- one cheap OrderManagement query -- and laid over
// the copy, so an assign or qty edit made anywhere shows at once. Anything
// the copy can't answer (no cache yet, older file format, a product added
// after the build, HO error) falls back to the existing live SQL call.
//
// Shared verbatim by supplier-stock-client and nextech-mediq; each app
// creates its instance with its own HO fetchers (orderCacheSync.js).
import { useEffect, useState } from 'react';

const SOURCE_KEY = 'nexora.orderCache.source';
const RESYNC_MS = 60 * 1000;
const HISTORY_TYPES = new Set(['Pharma', 'Non Pharma']);

const storeKey = (store) => String(store || '').trim().toUpperCase();
const bridge = () => (typeof window !== 'undefined' ? window.nexoraDesktop?.orderCache : null);

// Float 9664.0 and int 9664 are one product code (backend canonical_product_code).
export function cacheCode(value) {
  const n = Number(value);
  if (value !== null && value !== '' && Number.isFinite(n) && Number.isInteger(n)) return String(n);
  return String(value ?? '').trim();
}

const splitCodes = (code) => String(code || '').split(',').map((c) => c.trim()).filter(Boolean);
const isOpen = (row) => Number(row.Status) === 0 && Number(row.OrderQty) > 0;
const text = (v) => String(v ?? '').toUpperCase();
const byName = (a, b) => (text(a.ProductName) < text(b.ProductName) ? -1 : text(a.ProductName) > text(b.ProductName) ? 1 : 0);
const byTypeThenName = (a, b) => (text(a.ProductTypeName) < text(b.ProductTypeName) ? -1
  : text(a.ProductTypeName) > text(b.ProductTypeName) ? 1 : byName(a, b));

export function cacheUsable(cache) {
  return Number(cache?.meta?.schema_version) >= 3
    && Array.isArray(cache.workspace_rows) && cache.workspace_rows.length > 0;
}

// Cached rows with live state laid over them. null when HO's order has a
// product the copy doesn't (a newer order than the copy) -- caller goes live.
export function overlayLineStates(cache, stateRows) {
  const states = new Map();
  for (const [code, status, qty, qtyCheck, remarks] of stateRows || []) {
    const list = states.get(code) || [];
    list.push({ status, qty, qtyCheck, remarks });
    states.set(code, list);
  }
  const cached = new Map(cache.workspace_rows.map((row) => [cacheCode(row.ProductCode), row]));
  for (const code of states.keys()) if (!cached.has(code)) return null;
  const rank = (s) => [Number(s.status) === 0 && Number(s.qty) > 0 ? 0 : 1, -Number(s.qty || 0)];
  const better = (a, b) => { const ra = rank(a); const rb = rank(b); return ra[0] !== rb[0] ? ra[0] < rb[0] : ra[1] <= rb[1]; };
  const out = [];
  for (const [code, row] of cached) {
    const list = states.get(code);
    if (!list) continue; // line no longer in HO's order
    const live = list.reduce((best, s) => (better(best, s) ? best : s));
    out.push({ ...row, Status: live.status, OrderQty: live.qty, Qtycheck: live.qtyCheck, Remarks: live.remarks });
  }
  return out;
}

// repository.orders_by_supplier, mode 'history' | 'stock'.
export function bySupplierRows(cache, rows, supplierCode, mode) {
  const codes = splitCodes(supplierCode);
  if (mode === 'stock') {
    const warehouse = cache.meta?.ho_code != null && String(cache.meta.ho_code) === String(supplierCode);
    const out = [];
    for (const row of rows) {
      if (!isOpen(row)) continue;
      const lines = (cache.supplier_stock?.[cacheCode(row.ProductCode)] || [])
        .filter((l) => codes.includes(l.supplier_code) && Number(l.stock) > 0);
      if (!lines.length) continue;
      const best = lines.reduce((a, b) => (Number(b.stock) > Number(a.stock) ? b : a));
      out.push({
        ...row,
        S_Stock: best.stock, Discount: best.discount_raw, MinQty: best.min_qty, Sch: best.sch, Free: best.free,
        SupplierProductName: best.supplier_product_name, SupplierProductCode: best.supplier_product_code,
        Rack: best.rack || '', is_warehouse_stock: warehouse,
      });
    }
    return out.sort(byName);
  }
  return rows
    .filter((row) => isOpen(row) && HISTORY_TYPES.has(row.ProductTypeName)
      && (cache.product_suppliers?.[cacheCode(row.ProductCode)] || []).some((c) => codes.includes(c)))
    .sort(byTypeThenName);
}

// repository.all_open_orderables.
export function allOpenRows(rows) {
  return rows.filter((row) => isOpen(row) && HISTORY_TYPES.has(row.ProductTypeName)).sort(byTypeThenName);
}

// repository.supplier_stock_compare: open or assigned lines with qty.
export function compareMap(cache, rows) {
  const out = {};
  for (const row of rows) {
    if (!(Number(row.OrderQty) > 0 && [0, 1].includes(Number(row.Status)))) continue;
    const code = cacheCode(row.ProductCode);
    const lines = cache.supplier_stock?.[code];
    // eslint-disable-next-line no-unused-vars
    if (lines?.length) out[code] = lines.map(({ discount_raw, supplier_product_code, ...line }) => line);
  }
  return out;
}

export function createOrderCache({ fetchView, fetchStates }) {
  const mem = new Map();
  const checkedAt = new Map();
  const inflight = new Map();
  const status = new Map();
  const listeners = new Set();
  const emit = () => listeners.forEach((fn) => { try { fn(); } catch { /* listener gone */ } });

  function getSource() {
    try { return window.localStorage.getItem(SOURCE_KEY) === 'sql' ? 'sql' : 'cache'; } catch { return 'cache'; }
  }
  function setSource(value) {
    try { window.localStorage.setItem(SOURCE_KEY, value === 'sql' ? 'sql' : 'cache'); } catch { /* per-session only */ }
    emit();
  }
  function setStatus(store, value) { status.set(storeKey(store), value); emit(); }

  // The PC's copy for this store, re-checked against HO at most once a
  // minute (force: always). HO answers "unchanged" with meta only when the
  // stamp (order build + supplier-stock refresh) matches.
  async function sync(store, force = false) {
    const key = storeKey(store);
    if (!key) return null;
    if (!mem.has(key) && bridge()) {
      const disk = await bridge().read(key).catch(() => null);
      if (disk) mem.set(key, disk);
    }
    if (!force && Date.now() - (checkedAt.get(key) || 0) < RESYNC_MS) return mem.get(key) || null;
    if (inflight.has(key)) return inflight.get(key);
    const run = (async () => {
      const local = mem.get(key);
      try {
        const remote = await fetchView(key, local?.stamp);
        checkedAt.set(key, Date.now());
        if (!remote?.available) { mem.delete(key); return null; }
        if (remote.unchanged && local) return local;
        const data = { ...remote, received_at: new Date().toISOString() };
        mem.set(key, data);
        if (bridge()) {
          try {
            const file = await bridge().write(key, data);
            console.info(`[order-cache] ${key}: cache ${data.stamp} saved to ${file}`);
          } catch { /* the in-memory copy still serves this session */ }
        }
        emit();
        return data;
      } catch {
        return local || null; // HO unreachable: keep the last copy
      } finally {
        inflight.delete(key);
      }
    })();
    inflight.set(key, run);
    return run;
  }

  async function serve(store, live, build) {
    if (!store || getSource() === 'sql') {
      setStatus(store, { source: 'sql', reason: 'Live SQL selected' });
      return live();
    }
    try {
      const cache = await sync(store);
      if (!cacheUsable(cache)) {
        setStatus(store, { source: 'sql', reason: cache ? 'Cache is an older format; the next order rebuilds it' : 'No cache for this store yet' });
        return live();
      }
      const states = await fetchStates(store);
      const rows = overlayLineStates(cache, states?.rows);
      if (!rows) {
        sync(store, true);
        setStatus(store, { source: 'sql', reason: 'A newer order is on HO; downloading its cache' });
        return live();
      }
      const result = build(cache, rows);
      setStatus(store, { source: 'cache', builtAt: cache.meta?.built_at, stockAt: cache.meta?.supplier_stock_at });
      return result;
    } catch (err) {
      setStatus(store, { source: 'sql', reason: `Cache read failed (${err?.message || err})` });
      return live();
    }
  }

  return {
    getSource,
    setSource,
    sync,
    statusFor: (store) => status.get(storeKey(store)) || null,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    bySupplier: (store, supplierCode, mode, live) => serve(store, live, (cache, rows) => bySupplierRows(cache, rows, supplierCode, mode)),
    allOpen: (store, live) => serve(store, live, (_cache, rows) => allOpenRows(rows)),
    compare: (store, live) => serve(store, live, (cache, rows) => compareMap(cache, rows)),
  };
}

const hhmm = (iso) => {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';
};

// Header chip: where By Supplier's data is coming from, and a click to switch
// between the local cache and live SQL.
export function OrderCacheChip({ cache, store, onChange }) {
  const [, setTick] = useState(0);
  useEffect(() => cache.subscribe(() => setTick((n) => n + 1)), [cache]);
  const on = cache.getSource() !== 'sql';
  const s = cache.statusFor(store);
  const serving = on && s?.source === 'cache';
  const label = !on ? 'Live SQL' : serving ? `⚡ Cache ${hhmm(s.builtAt)}` : 'Cache → SQL';
  const title = !on
    ? 'By Supplier / Live Stock / compare read live from HO SQL. Click to use this PC\'s order cache.'
    : serving
      ? `Served from this PC's order cache. Order built ${hhmm(s.builtAt)}, supplier stock ${hhmm(s.stockAt)}; status and qty are live from HO. Click to switch to live SQL.`
      : `Cache on, but this load used live SQL: ${s?.reason || 'not loaded yet'}. Click to switch to live SQL only.`;
  const tone = !on ? 'var(--text-muted, #8a94a6)' : serving ? 'var(--success, #22c55e)' : 'var(--warning, #f59e0b)';
  return (
    <button
      type="button"
      title={title}
      onClick={() => { cache.setSource(on ? 'sql' : 'cache'); onChange?.(); }}
      style={{
        border: `1px solid ${tone}`, color: tone, background: 'transparent', borderRadius: 999,
        padding: '2px 10px', fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
      }}
    >
      {label}
    </button>
  );
}
