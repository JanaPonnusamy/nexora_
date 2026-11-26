import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

function installWindow() {
  const store = new Map();
  const events = [];
  globalThis.window = {
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, String(value)),
      removeItem: (key) => store.delete(key),
    },
    dispatchEvent: (event) => {
      events.push(event);
      return true;
    },
  };
  return events;
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (key) => (key.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

function fakeJwt(expSeconds) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'none', typ: 'JWT' })}.${encode({ exp: expSeconds })}.sig`;
}

let originalFetch;
let events;

beforeEach(async () => {
  events = installWindow();
  originalFetch = globalThis.fetch;
  const { resetSessionState } = await import('../src/services/sessionStore.js');
  resetSessionState();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('valid login stores a session and does not return the token to the caller', async () => {
  const token = fakeJwt(Math.floor(Date.now() / 1000) + 3600);
  globalThis.fetch = async () => jsonResponse(200, {
    token,
    token_type: 'bearer',
    user: { username: 'ada', tenant_id: 't1', roles: [{ role_name: 'STORE_USER', store_id: 's1', store_name: 'Main' }] },
  });
  const { login } = await import('../src/services/authService.js');
  const { getSession } = await import('../src/services/sessionStore.js');
  const user = await login('ada', 'not-a-real-password');
  assert.equal(user.username, 'ada');
  assert.equal(Object.hasOwn(user, 'token'), false);
  const session = getSession();
  assert.equal(session.user.tenant_id, 't1');
  assert.equal(typeof session.token, 'string');
  assert.equal(events.length, 0);
});

test('invalid login leaves no session', async () => {
  globalThis.fetch = async () => jsonResponse(401, { detail: 'Invalid Username Or Password' });
  const { login } = await import('../src/services/authService.js');
  const { getSession } = await import('../src/services/sessionStore.js');
  await assert.rejects(
    () => login('ada', 'wrong'),
    (err) => err.status === 401 && err.message === 'Invalid Username Or Password'
  );
  assert.equal(getSession(), null);
  assert.equal(events.length, 0);
});

test('logout clears the local session when the server rejects the token', async () => {
  const token = fakeJwt(Math.floor(Date.now() / 1000) + 3600);
  const { setSession, getSession } = await import('../src/services/sessionStore.js');
  const { logout } = await import('../src/services/authService.js');
  setSession({ token, user: { username: 'ada' } });
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return jsonResponse(401, { detail: 'Token expired' });
  };
  await logout();
  assert.equal(calls, 1);
  assert.equal(getSession(), null);
  assert.equal(events.length, 0);
});

test('a 401 on an authenticated request ends the session without echoing the token', async () => {
  const token = fakeJwt(Math.floor(Date.now() / 1000) + 3600);
  const { setSession, getSession } = await import('../src/services/sessionStore.js');
  const { apiGet, ApiError } = await import('../src/api/client.js');
  setSession({ token, user: { username: 'ada' } });
  globalThis.fetch = async () => jsonResponse(401, { detail: `Token expired ${token}` });
  await assert.rejects(
    () => apiGet('/api/tenants'),
    (err) => err instanceof ApiError && err.status === 401 && err.message === 'Request failed' && !err.message.includes(token)
  );
  assert.equal(getSession(), null);
  assert.equal(events.length, 1);
  assert.equal(events[0].detail.message, 'Request failed');
  assert.equal(String(events[0].detail.message).includes(token), false);
});

test('directory calls drop inactive tenants and stores', async () => {
  const token = fakeJwt(Math.floor(Date.now() / 1000) + 3600);
  const { setSession } = await import('../src/services/sessionStore.js');
  const { listTenants, listStores } = await import('../src/services/directoryService.js');
  setSession({ token, user: { username: 'ada' } });
  globalThis.fetch = async (url) => {
    if (String(url).includes('/api/tenants')) {
      return jsonResponse(200, [
        { tenant_id: 't1', tenant_name: 'Alpha', is_active: true },
        { tenant_id: 't2', tenant_name: 'Closed', is_active: false },
      ]);
    }
    return jsonResponse(200, [
      { store_id: 's1', tenant_id: 't1', store_name: 'Main', is_active: true },
      { store_id: 's9', tenant_id: 't1', store_name: 'Old', is_active: false },
    ]);
  };
  const tenants = await listTenants();
  const stores = await listStores();
  assert.deepEqual(tenants.map((tenant) => tenant.tenant_id), ['t1']);
  assert.deepEqual(stores.map((store) => store.store_id), ['s1']);
});
