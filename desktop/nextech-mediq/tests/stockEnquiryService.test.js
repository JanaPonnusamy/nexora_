import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

function installLocalStorageStub() {
  const store = new Map();
  globalThis.window = globalThis.window || {};
  globalThis.window.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
}

let originalFetch;
let capturedUrl;

beforeEach(() => {
  installLocalStorageStub();
  originalFetch = globalThis.fetch;
  capturedUrl = null;
  globalThis.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({ stores: [], summary: {} }),
    };
  };
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('searchProducts calls /products/search with tenant_id, q, only_stock', async () => {
  const { searchProducts } = await import('../src/services/stockEnquiryService.js?t=' + Date.now());
  await searchProducts('tenant-1', 'dolo', { onlyStock: true });
  assert.match(capturedUrl, /\/api\/stock-availability\/products\/search\?/);
  assert.match(capturedUrl, /tenant_id=tenant-1/);
  assert.match(capturedUrl, /q=dolo/);
  assert.match(capturedUrl, /only_stock=1/);
});

test('searchBatches calls /batches/search with batch, mrp, product params', async () => {
  const { searchBatches } = await import('../src/services/stockEnquiryService.js?t=' + Date.now());
  await searchBatches('tenant-1', { batch: 'B100', mrp: '99', product: 'dolo' });
  assert.match(capturedUrl, /\/api\/stock-availability\/batches\/search\?/);
  assert.match(capturedUrl, /batch=B100/);
  assert.match(capturedUrl, /mrp=99/);
  assert.match(capturedUrl, /product=dolo/);
});

test('productCore calls /products/core with store_id, product, months', async () => {
  const { productCore } = await import('../src/services/stockEnquiryService.js?t=' + Date.now());
  await productCore('tenant-1', 'store-9', 'DOLO650', { months: 6 });
  assert.match(capturedUrl, /\/api\/stock-availability\/products\/core\?/);
  assert.match(capturedUrl, /store_id=store-9/);
  assert.match(capturedUrl, /product=DOLO650/);
  assert.match(capturedUrl, /months=6/);
});
