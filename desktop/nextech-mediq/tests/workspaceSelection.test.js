import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  reconcileWorkspace,
  selectStore,
  selectTenant,
  workspaceFromLogin,
} from '../src/services/workspaceSelection.js';

const stores = [
  { store_id: 's1', tenant_id: 't1', store_name: 'One', is_active: true },
  { store_id: 's2', tenant_id: 't2', store_name: 'Two', is_active: true },
  { store_id: 's3', tenant_id: 't2', store_name: 'Closed', is_active: false },
];

test('workspaceFromLogin uses the user tenant and primary store when settings are empty', () => {
  const next = workspaceFromLogin(
    { tenantId: '', storeId: '', storeName: '' },
    { tenant_id: 't1', roles: [{ store_id: 's1', store_name: 'One' }] }
  );
  assert.deepEqual(next, { tenantId: 't1', storeId: 's1', storeName: 'One' });
});

test('workspaceFromLogin keeps a previously saved tenant and store', () => {
  const next = workspaceFromLogin(
    { tenantId: 'saved', storeId: 'ss', storeName: 'Saved' },
    { tenant_id: 't1', roles: [{ store_id: 's1', store_name: 'One' }] }
  );
  assert.equal(next.tenantId, 'saved');
  assert.equal(next.storeId, 'ss');
});

test('selectTenant drops a store from another tenant and picks the first active store', () => {
  const next = selectTenant({ tenantId: 't1', storeId: 's1', storeName: 'One' }, 't2', stores);
  assert.equal(next.tenantId, 't2');
  assert.equal(next.storeId, 's2');
  assert.equal(next.storeName, 'Two');
});

test('selectTenant keeps the current store when it belongs to the new tenant', () => {
  const next = selectTenant({ tenantId: 't2', storeId: 's2', storeName: 'Two' }, 't2', stores);
  assert.equal(next.storeId, 's2');
});

test('selectStore follows the store onto its tenant', () => {
  const next = selectStore({ tenantId: 't1', storeId: 's1', storeName: 'One' }, stores[1]);
  assert.equal(next.tenantId, 't2');
  assert.equal(next.storeId, 's2');
  assert.equal(next.storeName, 'Two');
});

test('reconcileWorkspace replaces a tenant the directory did not return', () => {
  const user = { tenant_id: 't1' };
  const tenants = [
    { tenant_id: 't1', tenant_name: 'Alpha', is_active: true },
    { tenant_id: 't2', tenant_name: 'Beta', is_active: true },
  ];
  const next = reconcileWorkspace({ tenantId: 'not-allowed', storeId: 's2' }, user, tenants, stores);
  assert.equal(next.tenantId, 't1');
  assert.equal(next.storeId, 's1');
});
