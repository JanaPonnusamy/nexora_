import assert from 'node:assert/strict';
import { test } from 'node:test';
import { barPct, fmtCompact, fmtDate, fmtDays, inReview, ownParams, readReview, toggleReview, writeReview } from './nonMovingView.js';

test('fmtCompact uses Indian lakh / crore', () => {
  assert.equal(fmtCompact(132079.59), '1.32 L');
  assert.equal(fmtCompact(24000000), '2.40 Cr');
  assert.equal(fmtCompact(4500), '4.5 K');
  assert.equal(fmtCompact(null), '—');
});

test('dates and days', () => {
  assert.equal(fmtDate('2026-08-24T00:00:00'), '24-08-2026');
  assert.equal(fmtDate(null), '—');
  assert.equal(fmtDays(null), 'never');
  assert.equal(fmtDays(1200), '1,200');
});

test('ownParams drops empty filters and joins classes', () => {
  const p = ownParams('T', 'S', { search: ' para ', classes: ['DEAD', 'NO_SALES'], minDays: '', nonMovingOnly: true }, { key: 'cost_value', dir: 'desc' }, 2, 200);
  assert.equal(p.search, 'para');
  assert.equal(p.classes, 'DEAD,NO_SALES');
  assert.equal(p.min_days, undefined);
  assert.equal(p.non_moving_only, 'true');
  assert.equal(p.include_zero, undefined);
  assert.equal(p.page, 2);
});

test('review list toggles per store + product and survives storage', () => {
  const mem = new Map();
  const storage = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  let list = toggleReview([], { store_id: 'abc', product_code: 7, product_name: 'X' });
  assert.ok(inReview(list, 'ABC', '7'));
  writeReview(storage, 'T', list);
  assert.equal(readReview(storage, 'T').length, 1);
  list = toggleReview(list, { store_id: 'ABC', product_code: '7' });
  assert.equal(list.length, 0);
  assert.deepEqual(readReview({ getItem: () => '{bad' }, 'T'), []);
});

test('barPct keeps small non-zero bars visible', () => {
  assert.equal(barPct(0, 100), 0);
  assert.equal(barPct(1, 1000), 3);
  assert.equal(barPct(50, 100), 50);
});
