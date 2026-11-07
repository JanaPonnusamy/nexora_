const assert = require('node:assert/strict');
const test = require('node:test');
const { enrollmentPlan } = require('./enrollmentGuard.cjs');

test('enrollment does not call HO without a session or when the key is unchanged', () => {
  assert.deepEqual(enrollmentPlan({ apiBaseUrl: '', token: 't' }), { action: 'skip', ok: false, reason: 'not signed in' });
  assert.deepEqual(enrollmentPlan({ apiBaseUrl: 'http://ho', token: '' }), { action: 'skip', ok: false, reason: 'not signed in' });
  assert.deepEqual(
    enrollmentPlan({ apiBaseUrl: 'http://ho', token: 't', storedMarker: 'same', nextMarker: 'same' }),
    { action: 'skip', ok: true, skipped: true },
  );
  assert.deepEqual(
    enrollmentPlan({ apiBaseUrl: 'http://ho', token: 't', storedMarker: 'old', nextMarker: 'new' }),
    { action: 'register' },
  );
  assert.equal(enrollmentPlan({ apiBaseUrl: 'http://ho', token: 't', storedMarker: '', nextMarker: 'new' }).action, 'register');
});
