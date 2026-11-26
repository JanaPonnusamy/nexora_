import { test } from 'node:test';
import assert from 'node:assert/strict';
import { IPC_CHANNELS } from '../electron/ipc/channels.cjs';
import { secureWebPreferences, isNavigationAllowed } from '../electron/security/windowDefaults.cjs';

test('IPC_CHANNELS is a frozen, finite allowlist', () => {
  assert.ok(Object.isFrozen(IPC_CHANNELS));
  assert.ok(Object.keys(IPC_CHANNELS).length > 0);
});

test('secureWebPreferences enforces the security floor', () => {
  const prefs = secureWebPreferences('/fake/preload.cjs');
  assert.equal(prefs.contextIsolation, true);
  assert.equal(prefs.nodeIntegration, false);
  assert.equal(prefs.sandbox, true);
  assert.equal(prefs.webSecurity, true);
  assert.equal(prefs.preload, '/fake/preload.cjs');
});

test('isNavigationAllowed rejects arbitrary external URLs by default', () => {
  assert.equal(isNavigationAllowed('https://example.com/anything'), false);
  assert.equal(isNavigationAllowed('http://evil.test/'), false);
});

test('isNavigationAllowed accepts file:// URLs', () => {
  assert.equal(isNavigationAllowed('file:///C:/some/path/index.html'), true);
});
