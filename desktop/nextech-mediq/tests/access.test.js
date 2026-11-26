import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isNavItemEnabled } from '../src/navigation/navConfig.js';
import { resolvePathForUser, visibleNavItems } from '../src/navigation/access.js';

function ids(user) {
  return visibleNavItems(user).map((item) => item.id);
}

test('a signed-out user sees no navigation', () => {
  assert.deepEqual(visibleNavItems(null), []);
  assert.equal(resolvePathForUser(null, '/stock-enquiry'), '/dashboard');
});

test('stock viewer navigation is stock only', () => {
  const user = { roles: [{ role_name: 'STOCK_VIEWER' }], modules: [] };
  assert.deepEqual(ids(user), ['stock-enquiry']);
  assert.equal(resolvePathForUser(user, '/settings'), '/stock-enquiry');
  assert.equal(resolvePathForUser(user, '/stock-enquiry'), null);
});

test('label review navigation is label export and settings', () => {
  const user = { roles: [{ role_name: 'LABEL_REVIEW' }] };
  assert.deepEqual(ids(user), ['label-export', 'settings']);
  assert.equal(resolvePathForUser(user, '/dashboard'), '/inventory/label-export');
});

test('purchase manager with an explicit module list does not see stock or admin screens', () => {
  const user = {
    roles: [{ role_name: 'PURCHASE_MANAGER' }],
    modules: [{ module: 'PROCUREMENT', can_view: true }],
  };
  const visible = ids(user);
  assert.ok(visible.includes('dashboard'));
  assert.ok(visible.includes('settings'));
  assert.ok(visible.includes('procurement-workspace'));
  assert.ok(visible.includes('order-entry'));
  assert.equal(visible.includes('stock-enquiry'), false);
  assert.equal(visible.includes('supplier-stock'), false);
  assert.equal(visible.includes('administration'), false);
});

test('a module grant with can_view false does not unlock stock enquiry', () => {
  const user = {
    roles: [{ role_name: 'STORE_USER' }],
    modules: [
      { module: 'stock_availability', can_view: false },
      { module: 'REPORTS', can_view: true },
    ],
  };
  assert.equal(ids(user).includes('stock-enquiry'), false);
  assert.equal(ids(user).includes('sales-reports'), true);
});

test('salesman navigation hides purchase tools and sales reports', () => {
  const user = { roles: [{ role_name: 'SALESMAN' }], modules: [] };
  const visible = ids(user);
  assert.ok(visible.includes('stock-enquiry'));
  assert.ok(visible.includes('settings'));
  assert.equal(visible.includes('procurement-workspace'), false);
  assert.equal(visible.includes('sales-reports'), false);
  assert.equal(visible.includes('expiry-report'), false);
  assert.equal(visible.includes('administration'), false);
});

test('SMS purchase manager keeps the supplier-stock whitelist and not administration', () => {
  const user = { roles: [{ role_name: 'SMS_PURCHASE_MANAGER' }] };
  const visible = ids(user);
  assert.ok(visible.includes('stock-enquiry'));
  assert.ok(visible.includes('supplier-stock'));
  assert.ok(visible.includes('procurement-workspace'));
  assert.ok(visible.includes('settings'));
  assert.equal(visible.includes('dashboard'), false);
  assert.equal(visible.includes('administration'), false);
  assert.equal(visible.includes('legacy-order'), false);
});

test('platform user sees administration as an enabled screen', () => {
  const user = { is_platform_user: true, roles: [], modules: [] };
  const admin = visibleNavItems(user).find((item) => item.id === 'administration');
  assert.ok(admin);
  assert.equal(isNavItemEnabled(admin), true);
  assert.ok(ids(user).includes('stock-enquiry'));
  assert.equal(ids(user).includes('legacy-order'), true);
  assert.equal(ids(user).includes('sync-live'), true);
  assert.equal(ids(user).includes('device-control'), true);
});

test('sync screens are super-admin only', () => {
  const regular = { roles: [{ role_name: 'PURCHASE_MANAGER' }], modules: [{ module: 'PROCUREMENT', can_view: true }] };
  assert.equal(ids(regular).includes('sync-live'), false);
  assert.equal(ids(regular).includes('sync-history'), false);
  assert.equal(ids(regular).includes('store-health'), false);
  assert.equal(ids(regular).includes('device-control'), false);
});
