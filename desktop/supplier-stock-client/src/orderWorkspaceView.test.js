import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  owLineFromRow,
  owLineNote,
  owNormalizeLayout,
  owWorkspaceSummary,
} from './orderWorkspaceView.js';

test('older saved layouts keep Normal row font and gain any panel they lack', () => {
  const layout = owNormalizeLayout({
    rowSize: 'compact',
    sidePosition: 'left',
    panels: [
      { key: 'trend', dock: 'side', hidden: false },
      { key: 'purchase', dock: 'bottom', hidden: true },
    ],
  });
  assert.equal(layout.rowWeight, 'normal');
  assert.equal(layout.rowSize, 'compact');
  assert.equal(layout.sidePosition, 'left');
  assert.equal(layout.panels.find((p) => p.key === 'purchase').dock, 'bottom');
  assert.equal(layout.panels.find((p) => p.key === 'purchase').hidden, true);
  assert.ok(layout.panels.some((p) => p.key === 'sales' && p.dock === 'side'));
  assert.ok(layout.panels.some((p) => p.key === 'history' && p.dock === 'bottom' && !p.hidden));
});

test('unrecognised layout values fall back without dropping a valid save', () => {
  const layout = owNormalizeLayout({
    rowSize: 'huge',
    rowWeight: 'black',
    sidePosition: 'center',
    sideWidth: 'full',
    bottomHeight: 'tiny',
    sideHidden: 1,
    panels: [{ key: 'not-a-panel', dock: 'side' }, { key: 'sales', dock: 'bottom', hidden: false }],
  });
  assert.equal(layout.rowSize, 'normal');
  assert.equal(layout.rowWeight, 'normal');
  assert.equal(layout.sidePosition, 'right');
  assert.equal(layout.sideWidth, 'normal');
  assert.equal(layout.bottomHeight, 'normal');
  assert.equal(layout.sideHidden, true);
  assert.equal(layout.panels.some((p) => p.key === 'not-a-panel'), false);
  assert.equal(layout.panels.filter((p) => p.key === 'sales').length, 1);
});

test('a qty line keeps zero as do-not-order and does not invent an original qty', () => {
  const line = owLineFromRow('qty', {
    productcode: 12,
    productname: '  AMOX   500  ',
    unitdescription: 'TAB',
    saleunit: 10,
    totalstock: 0,
    orderqty: 4,
    mrp: 12.5,
    IsOffer: 1,
    wantedtype: 'Regular',
  }, { edit: 0, reviewed: false });
  assert.equal(line.name, 'AMOX 500');
  assert.equal(line.unit, 'TAB');
  assert.equal(line.finalQty, 0);
  assert.equal(line.originalQty, null);
  assert.equal(line.qtyCheck, 'pending');
  assert.equal(line.offer, true);
  assert.equal(line.stock, 0);
  assert.match(owLineNote(line, 'qty'), /not ordered/);
});

test('supplier line reads PascalCase fields and assignment status', () => {
  const line = owLineFromRow('supplier', {
    ProductCode: '9',
    ProductName: 'CET',
    UnitDescription: 'CAP',
    SaleUnit: 15,
    TotalStock: 3,
    OrderQty: 2,
    OrgOrderQty: 5,
    Qtycheck: 0,
    IsOffer: false,
    S_Stock: 40,
    WantedType: 'Short',
  }, { edit: 2, qtyChecked: false, assignedStatus: 1, supplierName: 'Medico', stockMode: true });
  assert.equal(line.originalQty, 5);
  assert.equal(line.finalQty, 2);
  assert.equal(line.assignment, 'assigned');
  assert.equal(line.qtyCheck, 'pending');
  assert.equal(line.supplierStock, 40);
  assert.equal(line.supplierName, 'Medico');
  assert.match(owLineNote(line, 'supplier'), /differs from the original/);
});

test('summary while loading does not report zero totals', () => {
  const summary = owWorkspaceSummary({ loading: true, rows: [], workflow: { assigned_lines: 4 } });
  assert.equal(summary.loading, true);
  assert.equal(summary.products, null);
  assert.equal(summary.finalQty, null);
  assert.equal(summary.assignedLines, null);
});

test('summary sums only rows that actually have an original quantity', () => {
  const rows = [
    { orderqty: 2, orgorderqty: 4, IsOffer: true, productcode: 1 },
    { orderqty: 0, IsOffer: false, productcode: 2 },
    { orderqty: 3, orgorderqty: 3, IsOffer: false, productcode: 3 },
  ];
  const summary = owWorkspaceSummary({
    rows,
    qtyOf: (row) => row.orderqty,
    originalOf: (row) => row.orgorderqty,
    offerOf: (row) => row.IsOffer,
    qtyCheckedOf: (row) => (row.productcode === 1 ? 'checked' : 'pending'),
    workflow: { qty_pending: 8, assigned_lines: 1, unassigned_lines: 6, status: 'IN_PROGRESS' },
  });
  assert.equal(summary.products, 3);
  assert.equal(summary.finalQty, 5);
  assert.equal(summary.originalQty, 7);
  assert.equal(summary.offers, 1);
  assert.equal(summary.zeroQty, 1);
  assert.equal(summary.qtyCheckChecked, 1);
  assert.equal(summary.qtyCheckKnown, 3);
  assert.equal(summary.pendingLines, 8);
  assert.equal(summary.assignedLines, 1);
  assert.equal(summary.openLines, 6);
  assert.equal(summary.status, 'IN_PROGRESS');
});

test('summary hides original qty when the loader did not send it', () => {
  const summary = owWorkspaceSummary({
    rows: [{ OrderQty: 6 }],
    qtyOf: (row) => row.OrderQty,
    originalOf: () => undefined,
    offerOf: () => false,
    qtyCheckedOf: () => null,
  });
  assert.equal(summary.finalQty, 6);
  assert.equal(summary.originalQty, null);
  assert.equal(summary.qtyCheckKnown, null);
});

test('qty check shows a tick by default; only an explicit Text setting keeps text', () => {
  assert.equal(owNormalizeLayout(null).qtyCheckStyle, 'tick');
  assert.equal(owNormalizeLayout({ qtyCheckStyle: 'bogus' }).qtyCheckStyle, 'tick');
  assert.equal(owNormalizeLayout({ qtyCheckStyle: 'text' }).qtyCheckStyle, 'text');
});
