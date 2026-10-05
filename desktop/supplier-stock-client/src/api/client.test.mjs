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
