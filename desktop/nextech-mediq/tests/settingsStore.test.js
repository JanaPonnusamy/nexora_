import { test, beforeEach } from 'node:test';
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

beforeEach(() => {
  installLocalStorageStub();
});

test('loadSettings returns defaults when nothing stored', async () => {
  const mod = await import('../src/services/settingsStore.js?t=' + Date.now());
  const settings = mod.loadSettings();
  assert.equal(settings.apiBaseUrl, mod.DEFAULT_API_BASE_URL);
  assert.equal(settings.lanUrl, mod.DEFAULT_LAN_URL);
  assert.equal(settings.publicUrl, mod.DEFAULT_PUBLIC_URL);
});

test('saveSettings then loadSettings round-trips a custom LAN/public URL', async () => {
  const mod = await import('../src/services/settingsStore.js?t=' + Date.now());
  mod.saveSettings({ lanUrl: 'http://192.168.1.50:8000', tenantId: 't-kept' });
  mod.saveSettings({ publicUrl: 'http://example.test:9000' });
  const settings = mod.loadSettings();
  assert.equal(settings.lanUrl, 'http://192.168.1.50:8000');
  assert.equal(settings.publicUrl, 'http://example.test:9000');
  assert.equal(settings.tenantId, 't-kept');
});

test('resolveApiBaseUrl uses the saved LAN URL when only one candidate is configured', async () => {
  // Owner decision 2026-11-24 (reverses the earlier "never read a saved
  // host" design): a runtime-saved connection URL IS now consulted.
  const mod = await import('../src/services/settingsStore.js?t=' + Date.now());
  mod.saveSettings({ lanUrl: 'http://192.168.1.50:8000', publicUrl: 'http://192.168.1.50:8000' });
  assert.equal(mod.resolveApiBaseUrl(), 'http://192.168.1.50:8000');
});

test('resolveApiBaseUrl refuses to point at the separate .32 HO environment', async () => {
  const mod = await import('../src/services/settingsStore.js?t=' + Date.now());
  mod.saveSettings({ lanUrl: 'http://192.168.10.32:8000', publicUrl: 'http://192.168.10.32:8000' });
  assert.equal(mod.resolveApiBaseUrl(), mod.DEFAULT_LAN_URL);
});

test('resolveApiBaseUrl falls back to the LAN candidate first when two are configured and unreachable', async () => {
  const mod = await import('../src/services/settingsStore.js?t=' + Date.now());
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('unreachable'); };
  try {
    mod.saveSettings({ lanUrl: 'http://10.0.0.1:8000', publicUrl: 'http://10.0.0.2:8000' });
    assert.equal(mod.resolveApiBaseUrl(), 'http://10.0.0.1:8000');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('settings storage key is namespaced separately from existing clients', async () => {
  const mod = await import('../src/services/settingsStore.js?t=' + Date.now());
  mod.saveSettings({ apiBaseUrl: 'http://example.test' });
  assert.equal(globalThis.window.localStorage.getItem('nexora.desktop.settings'), null);
});
