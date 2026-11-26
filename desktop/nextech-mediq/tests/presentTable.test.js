import { test } from 'node:test';
import assert from 'node:assert/strict';
import { extractRows, presentTable } from '../src/modules/workspace/presentTable.js';

test('extractRows flattens branch product cards', () => {
  const rows = extractRows({
    stores: [
      { store_name: 'Main', products: [{ product_name: 'Para', stock: 2 }] },
    ],
  });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].store, 'Main');
  assert.equal(rows[0].product_name, 'Para');
});

test('presentTable hides secret-looking keys and uses declared columns', () => {
  const table = presentTable({
    columns: [{ key: 'name', label: 'Name' }, { key: 'token', label: 'Token' }],
    rows: [{ name: 'Ada', token: 'secret-value', password: 'nope' }],
  });
  assert.deepEqual(table.columns.map((column) => column.key), ['name']);
  assert.equal(table.rows[0].name, 'Ada');
  assert.equal(Object.hasOwn(table.rows[0], 'token'), false);
});

test('a scalar payload becomes one row', () => {
  const rows = extractRows({ status: 'ONLINE', sessions: 1 });
  assert.equal(rows[0].status, 'ONLINE');
  assert.equal(rows[0].sessions, 1);
});
