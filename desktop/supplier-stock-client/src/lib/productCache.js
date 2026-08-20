// Persistent per-supplier product cache (IndexedDB) so switching suppliers
// can render instantly from disk instead of waiting on a network round trip
// every time. The server always returns the full current list for a
// supplier (no incremental API) - the "differential" part happens here on
// the client: we diff the fresh list against what's cached, upsert
// new/changed rows, and delete rows that disappeared from the fresh list
// (product delisted by the supplier).
const DB_NAME = 'nexora-supplier-stock';
const DB_VERSION = 1;
const STORE = 'supplier_products';

// Rows don't have a stable id across re-imports (replace_supplier_stock
// reissues a new supplier_stock_id every import), so the durable identity
// for caching/diffing is (tenant_id, supplier_code, supplier_product_code).
const keyOf = (tenantId, supplierCode, row) => `${tenantId}::${supplierCode}::${row.supplier_product_code}`;

let dbPromise = null;
function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: '_key' });
        store.createIndex('by_supplier', '_supplierKey', { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

export async function getCachedProducts(tenantId, supplierCode) {
  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const idx = tx.objectStore(STORE).index('by_supplier');
      const range = IDBKeyRange.only(`${tenantId}::${supplierCode}`);
      const rows = [];
      idx.openCursor(range).onsuccess = (event) => {
        const cursor = event.target.result;
        if (cursor) {
          const { _key, _supplierKey, ...row } = cursor.value;
          rows.push(row);
          cursor.continue();
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

// Replaces the cached set for a supplier with `freshRows`: upserts every
// row present in the fresh list, deletes any cached row absent from it.
export async function syncCachedProducts(tenantId, supplierCode, freshRows) {
  try {
    const db = await openDb();
    const supplierKey = `${tenantId}::${supplierCode}`;
    const freshKeys = new Set(freshRows.map((row) => keyOf(tenantId, supplierCode, row)));
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      const store = tx.objectStore(STORE);
      const idx = store.index('by_supplier');
      idx.openCursor(IDBKeyRange.only(supplierKey)).onsuccess = (event) => {
        const cursor = event.target.result;
        if (cursor) {
          if (!freshKeys.has(cursor.value._key)) store.delete(cursor.value._key);
          cursor.continue();
        } else {
          freshRows.forEach((row) => {
            store.put({ ...row, _key: keyOf(tenantId, supplierCode, row), _supplierKey: supplierKey });
          });
        }
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    // Cache is a perf optimization only - failures here must never block
    // the UI from showing the freshly fetched list.
  }
}
