import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.localStorage = {
  getItem(key) {
    if (key === 'nexora.desktop.settings') {
      return JSON.stringify({ apiBaseUrl: 'http://unit.test' });
    }
    return null;
  },
  setItem() {},
  removeItem() {}
};
globalThis.window = { dispatchEvent() {} };

const { api } = await import('./client.js');

test('GET retries transient gateway failures and returns the recovered response', async () => {
  const statuses = [503, 502, 200];
  let calls = 0;
  globalThis.fetch = async () => {
    const status = statuses[calls++];
    return new Response(JSON.stringify(status === 200 ? [{ id: 1 }] : { detail: 'warming' }), {
      status,
      headers: { 'Content-Type': 'application/json' }
    });
  };

  const result = await api.listTenants({ token: 'test-token' });

  assert.deepEqual(result, [{ id: 1 }]);
  assert.equal(calls, 3);
});

test('POST does not automatically retry a potentially mutating operation', async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response(JSON.stringify({ detail: 'warming' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  };

  await assert.rejects(() => api.login({ username: 'u', password: 'p' }), /warming/);
  assert.equal(calls, 1);
});

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers }
  });
}

test('quantity save, assign, remove-unavailable, finalize, and reopen are not retried', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), method: options.method || 'GET', body: options.body, auth: options.headers?.Authorization });
    return jsonResponse(503, { detail: 'busy' });
  };
  const session = { token: 'session-token' };
  await assert.rejects(() => api.legacyUpdateQtyCheck('NMW', 10, 4, session), /busy/);
  await assert.rejects(() => api.legacyAssignSupplier('NMW', 10, '107', 'ANNAI', session), /busy/);
  await assert.rejects(() => api.legacyRemoveUnavailable('NMW', '107', session), /busy/);
  await assert.rejects(() => api.legacyFinalizeOrder('NMW', '', session), /busy/);
  await assert.rejects(() => api.legacyReopenOrder('NMW', 'recount', session), /busy/);
  await assert.rejects(() => api.reportStoreWhatsAppResult('item-1', false, 'no chat', session), /busy/);
  assert.equal(calls.length, 6);
  assert.equal(calls[0].method, 'PATCH');
  assert.match(calls[0].url, /\/api\/legacy-order\/qty-check\/NMW\/10$/);
  assert.deepEqual(JSON.parse(calls[0].body), { order_qty: 4 });
  assert.equal(calls[0].auth, 'Bearer session-token');
  assert.equal(calls[1].method, 'POST');
  assert.match(calls[1].url, /\/assign$/);
  assert.deepEqual(JSON.parse(calls[1].body), { supplier_code: '107', supplier_name: 'ANNAI' });
  assert.match(calls[2].url, /\/unavailable\/remove$/);
  assert.deepEqual(JSON.parse(calls[2].body), { supplier_code: '107' });
  assert.match(calls[3].url, /\/workflow\/finalize$/);
  assert.deepEqual(JSON.parse(calls[3].body), { note: null });
  assert.match(calls[4].url, /\/workflow\/reopen$/);
  assert.deepEqual(JSON.parse(calls[4].body), { note: 'recount' });
  assert.equal(calls[5].method, 'POST');
  assert.match(calls[5].url, /store-outbox\/item-1\/result$/);
  assert.deepEqual(JSON.parse(calls[5].body), { sent: false, error: 'no chat' });
});

test('order export reports permission and network failures and does not write a file', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), method: options.method, body: JSON.parse(options.body) });
    return jsonResponse(403, { detail: 'Not allowed' });
  };
  await assert.rejects(
    () => api.legacyExportOrder('NMW', '107', 'ANNAI', 'history', 0, { token: 't' }, { orderNo: '12', productCodes: ['9'] }),
    /Not allowed/,
  );
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'POST');
  assert.match(calls[0].url, /\/orders\/NMW\/export$/);
  assert.equal(calls[0].body.supplier_code, '107');
  assert.deepEqual(calls[0].body.product_codes, ['9']);

  globalThis.fetch = async () => { throw new Error('offline'); };
  await assert.rejects(() => api.legacyExportPendingOrder('NMW', 0, { token: 't' }), /Unable to reach the server/);

  globalThis.fetch = async () => new Response(new Uint8Array([1]), {
    status: 200,
    headers: { 'Content-Disposition': 'attachment; filename="pending.xlsx"', 'X-Exported-Count': '3' }
  });
  const exported = await api.legacyExportPendingOrder('NMW', 2, { token: 't' }, { fileFormat: 'xlsx', orderNo: '12' });
  assert.equal(exported.filename, 'pending.xlsx');
  assert.equal(exported.exportedCount, 3);
  assert.equal(typeof exported.blob.arrayBuffer, 'function');
});
