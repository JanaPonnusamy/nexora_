// Permanent local product index (IndexedDB) for instant, offline-capable
// search. Stores only the four compact fields per product across every store
// the user can see - product_code, product_name, unit, stock - seeded from
// GET /api/stock-availability/products/index and refreshed in the background.
//
// Why this exists: typeahead reads names straight from here (no per-keystroke
// network -> instant from the first letter, and the 35-45s cold-DB spikes on HO
// are avoided), and when HO is unreachable the UI still shows cached names +
// last-known stock with a "Last sync" time.
//
// Low-RAM: this file lives on disk (IndexedDB). Callers load ONE store's index
// into memory at a time for searching (a few MB) and release it on switch;
// they never hold every store in RAM at once.

const DB_NAME = 'nexora-product-index';
const DB_VERSION = 1;
const STORE = 'products';
const META = 'meta';

const scopeKey = (tenantId, storeId) => `${tenantId}::${storeId}`;
const rowKey = (tenantId, storeId, code) => `${tenantId}::${storeId}::${code}`;

let dbPromise = null;
function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const s = db.createObjectStore(STORE, { keyPath: '_key' });
        s.createIndex('by_scope', '_scope', { unique: false });
      }
      if (!db.objectStoreNames.contains(META)) {
        db.createObjectStore(META, { keyPath: '_scope' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

// ---- pure search helper (unit-testable, no IndexedDB) ---------------------

// Case-insensitive substring match on name (primary) or code (secondary).
// `list` is the in-memory array returned by loadScope(). Name matches rank
// before code-only matches; within each, a prefix hit ranks before a mid-string
// hit so "PARA" surfaces "PARACETAMOL" above "...PARA...". Bounded by `limit`.
export function filterProducts(list, query, limit = 50) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return [];
  const prefix = [];
  const contains = [];
  const codeOnly = [];
  for (let i = 0; i < list.length; i += 1) {
    const p = list[i];
    const idx = (p.name_lc || '').indexOf(q);
    if (idx === 0) prefix.push(p);
    else if (idx > 0) contains.push(p);
    else if (String(p.product_code || '').toLowerCase().includes(q)) codeOnly.push(p);
    if (prefix.length >= limit) break;
  }
  return prefix.concat(contains, codeOnly).slice(0, limit);
}

// ---- seeding / refresh ----------------------------------------------------

// Replace a store's cached index with `products` (upsert present, delete gone),
// then stamp its last-synced time. Never throws - the cache is an optimization.
export async function syncStoreIndex(tenantId, storeId, meta, products) {
  try {
    const db = await openDb();
    const scope = scopeKey(tenantId, storeId);
    const freshKeys = new Set(products.map((p) => rowKey(tenantId, storeId, p.product_code)));
    await new Promise((resolve, reject) => {
      const tx = db.transaction([STORE, META], 'readwrite');
      const store = tx.objectStore(STORE);
      const idx = store.index('by_scope');
      idx.openCursor(IDBKeyRange.only(scope)).onsuccess = (e) => {
        const cur = e.target.result;
        if (cur) {
          if (!freshKeys.has(cur.value._key)) store.delete(cur.value._key);
          cur.continue();
        } else {
          products.forEach((p) => {
            store.put({
              _key: rowKey(tenantId, storeId, p.product_code),
              _scope: scope,
              product_code: p.product_code,
              product_name: p.product_name,
              name_lc: String(p.product_name || '').toLowerCase(),
              unit: p.unit,
              stock: p.stock,
            });
          });
          tx.objectStore(META).put({
            _scope: scope,
            tenant_id: tenantId,
            store_id: storeId,
            store_code: meta?.store_code || null,
            store_name: meta?.store_name || null,
            last_synced: Date.now(),
            product_count: products.length,
          });
        }
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    return true;
  } catch {
    return false;
  }
}

// Incremental upsert: add/update the given products WITHOUT deleting the rest
// of the store's cached index (unlike syncStoreIndex, which replaces it). Used
// to GROW the cache from live search results and refresh the "last sync" stamp
// even when the dedicated full-catalogue /products/index endpoint isn't present
// on the backend (older HO build). Never throws — the cache is an optimization.
export async function upsertProducts(tenantId, storeId, meta, products) {
  if (!products || !products.length) return false;
  try {
    const db = await openDb();
    const scope = scopeKey(tenantId, storeId);
    await new Promise((resolve, reject) => {
      const tx = db.transaction([STORE, META], 'readwrite');
      const store = tx.objectStore(STORE);
      products.forEach((p) => {
        store.put({
          _key: rowKey(tenantId, storeId, p.product_code),
          _scope: scope,
          product_code: p.product_code,
          product_name: p.product_name,
          name_lc: String(p.product_name || '').toLowerCase(),
          unit: p.unit,
          stock: p.stock,
        });
      });
      const metaStore = tx.objectStore(META);
      const getReq = metaStore.get(scope);
      getReq.onsuccess = () => {
        const prev = getReq.result || {};
        metaStore.put({
          _scope: scope,
          tenant_id: tenantId,
          store_id: storeId,
          store_code: meta?.store_code || prev.store_code || null,
          store_name: meta?.store_name || prev.store_name || null,
          last_synced: Date.now(),
          product_count: prev.product_count || products.length,
        });
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    return true;
  } catch {
    return false;
  }
}

// Background stock refresh: patch just the `stock` of already-cached rows for a
// store from {product_code: stock}. Cheaper than a full re-seed.
export async function applyStockUpdates(tenantId, storeId, stockByCode) {
  try {
    const db = await openDb();
    const scope = scopeKey(tenantId, storeId);
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      const idx = tx.objectStore(STORE).index('by_scope');
      idx.openCursor(IDBKeyRange.only(scope)).onsuccess = (e) => {
        const cur = e.target.result;
        if (cur) {
          const next = stockByCode[cur.value.product_code];
          if (next !== undefined && next !== cur.value.stock) {
            cur.update({ ...cur.value, stock: next });
          }
          cur.continue();
        } else {
          resolve();
        }
      };
      tx.onerror = () => reject(tx.error);
    });
    return true;
  } catch {
    return false;
  }
}

// ---- reads ----------------------------------------------------------------

// Load one store's index into memory for searching. Returns [] on any failure
// (offline-safe: an empty cache just means "not seeded yet").
export async function loadScope(tenantId, storeId) {
  try {
    const db = await openDb();
    const scope = scopeKey(tenantId, storeId);
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const idx = tx.objectStore(STORE).index('by_scope');
      const rows = [];
      idx.openCursor(IDBKeyRange.only(scope)).onsuccess = (e) => {
        const cur = e.target.result;
        if (cur) {
          const { _key, _scope, ...row } = cur.value;
          rows.push(row);
          cur.continue();
        } else {
          resolve(rows);
        }
      };
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    return [];
  }
}

export async function getMeta(tenantId, storeId) {
  try {
    const db = await openDb();
    return await new Promise((resolve) => {
      const tx = db.transaction(META, 'readonly');
      const req = tx.objectStore(META).get(scopeKey(tenantId, storeId));
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

// Newest last_synced across all cached scopes for a tenant - drives the header
// "Last sync: <time>" indicator shown when HO is unreachable.
export async function getLastSync(tenantId) {
  try {
    const db = await openDb();
    return await new Promise((resolve) => {
      const tx = db.transaction(META, 'readonly');
      let newest = null;
      tx.objectStore(META).openCursor().onsuccess = (e) => {
        const cur = e.target.result;
        if (cur) {
          if ((!tenantId || cur.value.tenant_id === tenantId)
              && (newest === null || cur.value.last_synced > newest)) {
            newest = cur.value.last_synced;
          }
          cur.continue();
        } else {
          resolve(newest);
        }
      };
      tx.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}
