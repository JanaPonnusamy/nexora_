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

beforeEach(() => {
  installLocalStorageStub();
  originalFetch = globalThis.fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function jsonResponse(status, body, headers = { 'content-type': 'application/json' }) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (key) => headers[key.toLowerCase()] || null },
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

test('apiGet returns parsed JSON on success', async () => {
  globalThis.fetch = async () => jsonResponse(200, { ok: true });
  const { apiGet } = await import('../src/api/client.js?t=' + Date.now());
  const result = await apiGet('/api/ping');
  assert.deepEqual(result, { ok: true });
});

test('apiRequest surfaces a string detail message on 4xx', async () => {
  globalThis.fetch = async () => jsonResponse(401, { detail: 'Invalid Username Or Password' });
  const { apiGet, ApiError } = await import('../src/api/client.js?t=' + Date.now());
  await assert.rejects(
    () => apiGet('/api/auth/login'),
    (err) => err instanceof ApiError && err.message === 'Invalid Username Or Password' && err.status === 401
  );
});

test('apiRequest flattens a FastAPI validation-error list detail', async () => {
  globalThis.fetch = async () =>
    jsonResponse(422, { detail: [{ loc: ['body', 'username'], msg: 'field required' }] });
  const { apiGet, ApiError } = await import('../src/api/client.js?t=' + Date.now());
  await assert.rejects(
    () => apiGet('/api/auth/login'),
    (err) => err instanceof ApiError && err.message.includes('username') && err.message.includes('field required')
  );
});

test('apiRequest retries a transient GET failure then succeeds', async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) return jsonResponse(503, { detail: 'Service Unavailable' });
    return jsonResponse(200, { ok: true });
  };
  const { apiGet } = await import('../src/api/client.js?t=' + Date.now());
  const result = await apiGet('/api/ping', { transientRetries: 1 });
  assert.deepEqual(result, { ok: true });
  assert.equal(calls, 2);
});

test('skipAuth 401 does not clear a remembered session', async () => {
  const { setSession, getSession, resetSessionState } = await import('../src/services/sessionStore.js');
  resetSessionState();
  const { apiGet } = await import('../src/api/client.js');
  setSession({ token: 'kept-token', user: { username: 'ada' } });
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.headers.Authorization, undefined);
    return jsonResponse(401, { detail: 'Invalid passcode' });
  };
  await assert.rejects(() => apiGet('/api/quick-stock/verify', { skipAuth: true }));
  assert.equal(getSession()?.token, 'kept-token');
});

test('apiPost never retries, even on a transient status', async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return jsonResponse(503, { detail: 'Service Unavailable' });
  };
  const { apiPost, ApiError } = await import('../src/api/client.js?t=' + Date.now());
  await assert.rejects(() => apiPost('/api/orders', { qty: 1 }), ApiError);
  assert.equal(calls, 1);
});
