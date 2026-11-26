import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MODULE_STATUS,
  NAV_GROUPS,
  NAV_SECTIONS,
  breadcrumbsForPath,
  findNavItemByPath,
  isNavItemEnabled,
  searchNavItems,
} from '../src/navigation/navConfig.js';

test('navigation groups cover the Phase 3 product map', () => {
  const labels = NAV_GROUPS.map((g) => g.label);
  assert.deepEqual(labels, [
    'Dashboard',
    'Inventory',
    'Procurement & Suppliers',
    'Sales & Reports',
    'AI Intelligence',
    'System & Administration',
  ]);
});

test('integrated destinations are enabled and none are left as planned placeholders', () => {
  const enabled = NAV_SECTIONS.filter(isNavItemEnabled).map((item) => item.id);
  assert.ok(enabled.includes('dashboard'));
  assert.ok(enabled.includes('stock-enquiry'));
  assert.ok(enabled.includes('supplier-stock'));
  assert.ok(enabled.includes('order-entry'));
  assert.ok(enabled.includes('administration'));
  assert.equal(NAV_SECTIONS.some((item) => item.status === MODULE_STATUS.PLANNED), false);
  assert.ok(NAV_SECTIONS.every((item) => Object.values(MODULE_STATUS).includes(item.status)));
});

test('supplier stock is a real route, not a planned stub', () => {
  const stock = findNavItemByPath('/supplier-stock');
  assert.equal(stock.status, MODULE_STATUS.IN_PROGRESS);
  assert.equal(isNavItemEnabled(stock), true);
});

test('breadcrumbsForPath uses group then leaf', () => {
  const crumbs = breadcrumbsForPath('/stock-enquiry');
  assert.equal(crumbs[0].label, 'Inventory');
  assert.equal(crumbs[1].label, 'Stock Enquiry');
});

test('searchNavItems matches label, group, and description', () => {
  const hits = searchNavItems('rate');
  assert.ok(hits.some((item) => item.id === 'rate-analysis'));
});
