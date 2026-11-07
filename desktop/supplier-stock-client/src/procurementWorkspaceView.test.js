import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  pwAssignRefusal,
  pwColumnOrder,
  pwColumnWidth,
  pwCompareSuppliers,
  pwEffectiveDiscount,
  pwExportGuard,
  pwFinalizePlan,
  pwGrnForSelection,
  pwIsWarehouseCard,
  pwKey,
  pwOfferRemark,
  pwOfferText,
  pwQtyKeyAction,
  pwSupplierLine,
  pwWholeQty,
} from './procurementWorkspaceView.js';

const MOVABLE = ['state', 'qty', 'stock', 'pack', 'disc'];

test('quantity keeps zero, truncates fractions, and caps at five digits', () => {
  assert.equal(pwWholeQty(0), 0);
  assert.equal(pwWholeQty('0'), 0);
  assert.equal(pwWholeQty(''), 0);
  assert.equal(pwWholeQty(null), 0);
  assert.equal(pwWholeQty(-4), 0);
  assert.equal(pwWholeQty(12.9), 12);
  assert.equal(pwWholeQty(100000), 99999);
  assert.equal(pwWholeQty('99999'), 99999);
});

test('older column saves keep their order and gain new keys in the default slot', () => {
  assert.deepEqual(pwColumnOrder(['qty', 'stock', 'nope', 'qty'], MOVABLE), ['state', 'qty', 'stock', 'pack', 'disc']);
  assert.deepEqual(pwColumnOrder(['disc', 'state'], MOVABLE), ['disc', 'state', 'qty', 'stock', 'pack']);
  assert.deepEqual(pwColumnOrder(null, MOVABLE), MOVABLE);
});

test('warehouse ST_* cards are not assignable suppliers', () => {
  assert.equal(pwIsWarehouseCard({ supplier_code: 'ST_2', supplier_name: 'Warehouse transfer (ST_2)' }), true);
  assert.equal(pwIsWarehouseCard({ supplier_code: 'st_9' }), true);
  assert.equal(pwIsWarehouseCard({ supplier_code: '107', is_warehouse: true }), true);
  assert.equal(pwIsWarehouseCard({ supplier_code: '107', tags: ['best', 'warehouse'] }), true);
  assert.equal(pwIsWarehouseCard({ supplier_code: '107', tags: ['best', 'latest'], supplier_name: 'PENTACARE' }), false);
  assert.equal(pwIsWarehouseCard(null), false);
});

test('a saved Wanted width wins over the wider default', () => {
  assert.equal(pwColumnWidth(116, 88), 88);
  assert.equal(pwColumnWidth(116, ''), 116);
  assert.equal(pwColumnWidth(116, 0), 116);
  assert.equal(pwColumnWidth(116, 10), 24);
});

test('quantity keys save, assign, or leave a text edit alone', () => {
  const base = { view: 'qty', hasSupplier: false, status: 0, clear: false, ctrl: false, index: 2, last: 9 };
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'ArrowDown' }), { type: 'commit', nextIndex: 3 });
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'ArrowUp' }), { type: 'commit', nextIndex: 1 });
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'Enter' }), { type: 'commit', nextIndex: null });
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'Escape' }), { type: 'commit', zero: true, nextIndex: 3 });
  assert.equal(pwQtyKeyAction({ ...base, key: 'Backspace' }), null);
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'Backspace', clear: true }), { type: 'commit', zero: true, nextIndex: 3 });
  assert.deepEqual(pwQtyKeyAction({ ...base, key: '+', view: 'supplier', hasSupplier: true }), { type: 'nudge', delta: 1 });
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'Enter', view: 'supplier', hasSupplier: true, status: 0 }), { type: 'assign' });
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'Enter', view: 'supplier', hasSupplier: true, status: 1 }), { type: 'commit', nextIndex: null });
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'Delete', view: 'supplier' }), { type: 'remove' });
  assert.equal(pwQtyKeyAction({ ...base, key: 'Delete' }), null);
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'ArrowRight' }), { type: 'suggest' });
  assert.deepEqual(pwQtyKeyAction({ ...base, key: 'i' }), { type: 'decisions' });
  assert.equal(pwQtyKeyAction({ ...base, key: 'i', ctrl: true }), null);
});

test('assignment is refused for warehouse stock, zero qty, and a busy or finalized row', () => {
  const card = { supplier_code: '107', supplier_name: 'ANNAI' };
  assert.equal(pwAssignRefusal({ card, finalized: false, busy: false, status: 0, qty: 4, legacySupplier: { supplier_code: '107' }, store: 'NMW' }).ok, true);
  assert.match(pwAssignRefusal({ card: { supplier_code: 'ST_2', supplier_name: 'Warehouse' }, status: 0, qty: 4, legacySupplier: { supplier_code: 'ST_2' }, store: 'NMW' }).error, /warehouse stock/);
  assert.match(pwAssignRefusal({ card, status: 0, qty: 0, legacySupplier: { supplier_code: '107' }, store: 'NMW' }).error, /above 0/);
  assert.match(pwAssignRefusal({ card, status: 0, qty: 4, legacySupplier: null, store: 'NMW' }).error, /order supplier list/);
  assert.equal(pwAssignRefusal({ card, finalized: true, status: 0, qty: 4, legacySupplier: card, store: 'NMW' }).ok, false);
  assert.equal(pwAssignRefusal({ card, busy: true, status: 0, qty: 4, legacySupplier: card, store: 'NMW' }).error, undefined);
  assert.equal(pwAssignRefusal({ card, status: 1, qty: 4, legacySupplier: card, store: 'NMW' }).ok, false);
});

test('export and finalize plans stop before any request', () => {
  assert.equal(pwExportGuard({ needsSupplier: true, supplier: null }), 'Pick a supplier first.');
  assert.equal(pwExportGuard({ needsSupplier: true, supplier: { supplier_code: '1' } }), '');
  assert.equal(pwExportGuard({ needsSupplier: false, supplier: null }), '');
  assert.deepEqual(pwFinalizePlan({ store: '', reopen: false, note: 'x' }), { action: 'skip' });
  assert.deepEqual(pwFinalizePlan({ store: 'NMW', reopen: false, note: null }), { action: 'cancel' });
  assert.deepEqual(pwFinalizePlan({ store: 'NMW', reopen: true, note: 'recount' }), { action: 'reopen', note: 'recount' });
  assert.deepEqual(pwFinalizePlan({ store: 'NMW', reopen: false, note: '' }), { action: 'finalize', note: '' });
});

test('latest GRN facts follow the selected product and keep a real zero', () => {
  const grn = { code: '9810.0', receivedQty: 0, freeQty: 0, cost: null, discount: 0 };
  assert.equal(pwGrnForSelection(grn, '9810'), grn);
  assert.equal(pwGrnForSelection(grn, 9810), grn);
  assert.equal(pwGrnForSelection(grn, '9811'), null);
  assert.equal(pwGrnForSelection(null, '9810'), null);
  assert.equal(pwGrnForSelection({ receivedQty: 4 }, '9810'), null);
  assert.equal(pwKey('100.0'), '100');
  assert.equal(pwKey(100), '100');
});

test('pwNormalizePanels keeps saved order/docks, drops junk, appends new panels', async () => {
  const { pwNormalizePanels, PW_PANELS_DEFAULT } = await import('./procurementWorkspaceView.js');
  assert.deepEqual(pwNormalizePanels(null), PW_PANELS_DEFAULT);
  const out = pwNormalizePanels([
    { key: 'trend', dock: 'bottom', hidden: true },
    { key: 'trend', dock: 'side' },
    { key: 'nope', dock: 'side' },
    { key: 'stores', dock: 'sideways' },
  ]);
  assert.deepEqual(out.slice(0, 2), [
    { key: 'trend', dock: 'bottom', hidden: true },
    { key: 'stores', dock: 'middle', hidden: false },
  ]);
  assert.equal(out.length, PW_PANELS_DEFAULT.length);
  assert.deepEqual(out.map((p) => p.key).sort(), PW_PANELS_DEFAULT.map((p) => p.key).sort());
});

test('effective discount stacks Disc% with the free-qty offer', () => {
  assert.equal(pwEffectiveDiscount({ discount: 10 }), 10);
  assert.equal(pwEffectiveDiscount({ discount: 0, sch: 10, free: 2 }), 16.67);
  assert.equal(pwEffectiveDiscount({ discount: 10, sch: 10, free: 2 }), 25);
  assert.equal(pwEffectiveDiscount({ discount: '', sch: 10, free: 0 }), 0);
});

test('compare: better supplier with stock says switch', () => {
  const lines = [
    { supplier_code: '589', stock: 100, discount: 0 },
    { supplier_code: '1391', stock: 320, discount: 10 },
  ];
  const { verdict, current } = pwCompareSuppliers(lines, ['589'], 20);
  assert.equal(current.supplier_code, '589');
  assert.equal(verdict.kind, 'switch');
  assert.equal(verdict.best.supplier_code, '1391');
  assert.equal(verdict.gain, 10);
  assert.equal(verdict.short, false);
});

test('compare: better supplier out of stock says stay with current', () => {
  const lines = [
    { supplier_code: '589', stock: 100, discount: 0 },
    { supplier_code: '1391', stock: 0, discount: 12 },
  ];
  const { verdict } = pwCompareSuppliers(lines, ['589'], 20);
  assert.equal(verdict.kind, 'stay');
  assert.equal(verdict.best.supplier_code, '589');
  assert.deepEqual(verdict.blocked.map((l) => l.supplier_code), ['1391']);
});

test('compare: unified supplier codes, no stock, no supplier, short stock', () => {
  const lines = [
    { supplier_code: '107', stock: 0, discount: 5 },
    { supplier_code: '108', stock: 10, discount: 5 },
    { supplier_code: '99', stock: 4, discount: 5.2 },
  ];
  assert.equal(pwCompareSuppliers(lines, ['107', '108', '109'], 5).verdict.kind, 'best');
  assert.equal(pwCompareSuppliers([{ supplier_code: '1', stock: 0 }, { supplier_code: '2', stock: 6 }], ['1'], 8).verdict.kind, 'nostock');
  const pick = pwCompareSuppliers(lines, [], 8).verdict;
  assert.equal(pick.kind, 'pick');
  assert.equal(pick.best.supplier_code, '99');
  assert.equal(pick.short, true);
  assert.equal(pwCompareSuppliers([{ supplier_code: '1', stock: 0 }], [], 1).verdict.kind, 'none');
  assert.equal(pwCompareSuppliers([{ supplier_code: '1', stock: 3 }, { supplier_code: '2', stock: 9, discount: 9 }], ['1'], 8).verdict.short, false);
  assert.equal(pwCompareSuppliers([{ supplier_code: '1', stock: 3, discount: 9 }], ['1'], 8).verdict.short, true);
});

test('compare: nobody else in stock says place with current', () => {
  const { verdict } = pwCompareSuppliers([{ supplier_code: '589', stock: 40, discount: 0 }], ['589'], 5);
  assert.equal(verdict.kind, 'only');
  assert.equal(verdict.best.supplier_code, '589');
  assert.equal(pwCompareSuppliers([{ supplier_code: '589', stock: 40 }, { supplier_code: '9', stock: 0 }], ['589'], 5).verdict.kind, 'only');
});

test('supplier line: best-stocked member line of the picked supplier', () => {
  const lines = [
    { supplier_code: '107', stock: 5, sch: 10, free: 1 },
    { supplier_code: '108', stock: 40, sch: 0, free: 0 },
    { supplier_code: '9', stock: 900 },
  ];
  assert.equal(pwSupplierLine(lines, ['107', '108']).supplier_code, '108');
  assert.equal(pwSupplierLine(lines, [' 107 ']).stock, 5);
  assert.equal(pwSupplierLine(lines, ['55']), null);
  assert.equal(pwSupplierLine(lines, []), null);
  assert.equal(pwSupplierLine(undefined, ['107']), null);
});

test('offer text needs both sch and free', () => {
  assert.equal(pwOfferText(10, 1), '10+1');
  assert.equal(pwOfferText('10', '2'), '10+2');
  assert.equal(pwOfferText(10, 0), '');
  assert.equal(pwOfferText(null, 1), '');
});

test('offer remark: qty on a multiple of the buy qty gets the offer', () => {
  const sup = [{ sch: 9, free: 1 }];
  assert.equal(pwOfferRemark(9, sup), '9+1');
  assert.equal(pwOfferRemark(18, sup), '9+1');
  assert.equal(pwOfferRemark(27, sup), '9+1');
  assert.equal(pwOfferRemark(10, sup), '');
  assert.equal(pwOfferRemark(0, sup), '');
  assert.equal(pwOfferRemark(9, [{ sch: 9, free: 0 }]), '');
});

test('offer remark: supplier offer first, history fallback reduced', () => {
  assert.equal(pwOfferRemark(20, [{ sch: 9, free: 1 }, { sch: 10, free: 1 }]), '10+1');
  assert.equal(pwOfferRemark(18, [{ sch: 9, free: 1 }, { sch: 6, free: 1 }]), '9+1');
  // A history bill of 18 base + 2 free is the 9+1 pattern.
  assert.equal(pwOfferRemark(27, [{ sch: 18, free: 2, reduce: true }]), '9+1');
  // A live supplier offer is taken as-is: 10+2 is not 5+1.
  assert.equal(pwOfferRemark(15, [{ sch: 10, free: 2 }]), '');
  assert.equal(pwOfferRemark(9, undefined), '');
});
