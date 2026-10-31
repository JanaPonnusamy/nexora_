import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fmtCell, parseQuoteLine } from './rateAnalysisView.js';

test('parseQuoteLine reads an Excel paste row (tab separated, S.No dropped)', () => {
  assert.deepEqual(parseQuoteLine('1\tSPASMONIL\t33.00\t11.50'), { text: 'SPASMONIL', mrp: 33, ptr: 11.5 });
  assert.deepEqual(parseQuoteLine("ALMOX 500 15'S\t117.85\t40.00"), { text: "ALMOX 500 15'S", mrp: 117.85, ptr: 40 });
});

test('parseQuoteLine keeps a blank PTR cell blank instead of shifting MRP into PTR', () => {
  assert.deepEqual(parseQuoteLine('7\tPANTOSEC 40 15\'S\t244.25\t'), { text: "PANTOSEC 40 15'S", mrp: 244.25, ptr: null });
});

test('parseQuoteLine reads typed lines with numbers inside the product name', () => {
  assert.deepEqual(parseQuoteLine('19, Alkof Jun 100ml 121.00 24.00'), { text: 'Alkof Jun 100ml', mrp: 121, ptr: 24 });
  assert.deepEqual(parseQuoteLine('Ery 250 (omega), 75, 28.30'), { text: 'Ery 250 (omega)', mrp: 75, ptr: 28.3 });
  assert.deepEqual(parseQuoteLine('Okacet 5.05'), { text: 'Okacet', mrp: null, ptr: 5.05 });
  assert.equal(parseQuoteLine('   '), null);
});

test('fmtCell formats money, ints and ISO dates', () => {
  assert.equal(fmtCell(1234.5, 'money'), '1,234.50');
  assert.equal(fmtCell(123456.4, 'int'), '1,23,456');
  assert.equal(fmtCell('2026-10-31', 'date'), '31-10-2026');
  assert.equal(fmtCell(null, 'money'), '');
});
