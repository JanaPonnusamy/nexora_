import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

// Minimal localStorage polyfill for Node's test environment (no DOM/window
// available by default under `node --test`).
function installLocalStorageStub() {
  const store = new Map();
  globalThis.window = globalThis.window || {};
  globalThis.window.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
}

beforeEach(() => {
  installLocalStorageStub();
});

test('getSession returns null when nothing stored', async () => {
  const { getSession } = await import('../src/services/sessionStore.js?t=' + Date.now());
  assert.equal(getSession(), null);
});

test('setSession then getSession round-trips token and user, stamping loginDate', async () => {
  const mod = await import('../src/services/sessionStore.js?t=' + Date.now());
  mod.setSession({ token: 'abc123', user: { tenant_id: 't1' } });
  const session = mod.getSession();
  assert.equal(session.token, 'abc123');
  assert.equal(session.user.tenant_id, 't1');
  assert.equal(session.loginDate, new Date().toDateString());
  assert.equal(globalThis.window.localStorage.getItem('nextechMediq.session'), null);
});

test('clearSession removes the stored session', async () => {
  const mod = await import('../src/services/sessionStore.js?t=' + Date.now());
  mod.setSession({ token: 'abc123' });
  mod.clearSession();
  assert.equal(mod.getSession(), null);
});

test('getSession keeps a session from a stale loginDate (no daily re-login prompt)', async () => {
  // Owner decision 2026-11-24 ("one time login life time"): the calendar-day
  // cutoff was removed -- a remembered session now survives across days and
  // is only ever ended by the JWT's own exp claim or an explicit logout.
  const mod = await import('../src/services/sessionStore.js?t=' + Date.now());
  globalThis.window.localStorage.setItem(
    'nextechMediq.session',
    JSON.stringify({ token: 'abc123', loginDate: 'Mon Jan 01 2000' })
  );
  const session = mod.getSession();
  assert.equal(session.token, 'abc123');
});

test('isAuthenticated reflects whether a valid token is present', async () => {
  const mod = await import('../src/services/sessionStore.js?t=' + Date.now());
  assert.equal(mod.isAuthenticated(), false);
  mod.setSession({ token: 'abc123' });
  assert.equal(mod.isAuthenticated(), true);
});

function fakeJwt(expSeconds) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'none', typ: 'JWT' })}.${encode({ exp: expSeconds })}.sig`;
}

test('getSession restores a token whose exp is still in the future', async () => {
  const mod = await import('../src/services/sessionStore.js?t=' + Date.now());
  const token = fakeJwt(Math.floor(Date.now() / 1000) + 3600);
  mod.setSession({ token, user: { username: 'ada' } });
  const session = mod.getSession();
  assert.equal(session.user.username, 'ada');
  assert.equal(typeof session.expiresAt, 'number');
  assert.ok(session.expiresAt > Date.now());
});

test('getSession drops an expired token and does not keep it for restoration', async () => {
  const mod = await import('../src/services/sessionStore.js?t=' + Date.now());
  const token = fakeJwt(Math.floor(Date.now() / 1000) - 60);
  globalThis.window.localStorage.setItem(
    'nextechMediq.session',
    JSON.stringify({ token, user: { username: 'ada' }, loginDate: new Date().toDateString() })
  );
  assert.equal(mod.getSession(), null);
  assert.equal(mod.consumeSessionEndReason(), 'Token expired');
  assert.equal(globalThis.window.localStorage.getItem('nextechMediq.session'), null);
});
