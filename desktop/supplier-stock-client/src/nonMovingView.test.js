import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  activeFilterCount, barPct, dateComparator, daysSinceSaleComparator, DEFAULT_SHOW_ID, filtersEqual, fmtCompact,
  fmtDate, fmtDays, inReview, numericComparator, OWN_COLS_DEFAULT_ORDER, OWN_COLS_MANDATORY, ownParams,
  readColSettings, readReview, resolveOwnCols, SHOW_PRESET_BY_ID, textComparator, toggleReview, writeColSettings,
  writeReview,
} from './nonMovingView.js';

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

test('column settings persist order + hidden + widths, falling back to defaults', () => {
  const mem = new Map();
  const storage = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  assert.deepEqual(readColSettings(storage, 'T', 'S1'), { order: OWN_COLS_DEFAULT_ORDER, hidden: [], widths: {} });
  writeColSettings(storage, 'T', 'S1', { order: ['stock', 'product_name'], hidden: ['pack'], widths: { supplier: 220 } });
  const s = readColSettings(storage, 'T', 'S1');
  assert.equal(s.order[0], 'stock');
  assert.ok(s.order.includes('classification'));
  assert.ok(s.hidden.includes('pack'));
  assert.equal(s.widths.supplier, 220);
  // a different store never sees store S1's saved settings
  assert.deepEqual(readColSettings(storage, 'T', 'S2'), { order: OWN_COLS_DEFAULT_ORDER, hidden: [], widths: {} });
  assert.deepEqual(readColSettings({ getItem: () => '{bad' }, 'T', 'S1'), { order: OWN_COLS_DEFAULT_ORDER, hidden: [], widths: {} });
});

test('mandatory columns can never be hidden', () => {
  const s = readColSettings({ getItem: () => JSON.stringify({ order: OWN_COLS_DEFAULT_ORDER, hidden: OWN_COLS_MANDATORY }) }, 'T', 'S1');
  assert.deepEqual(s.hidden, []);
});

test('resolveOwnCols marks the first visible column of each group and applies width overrides', () => {
  const cols = resolveOwnCols({ order: OWN_COLS_DEFAULT_ORDER, hidden: ['product_code'], widths: { supplier: 240 } });
  assert.ok(!cols.some((c) => c.key === 'product_code'));
  assert.equal(cols.find((c) => c.key === 'supplier').w, 240);
  const starts = cols.filter((c) => c.groupStart).map((c) => c.group);
  assert.deepEqual(starts, [...new Set(starts)]);
});

// ----- AG Grid client-side sort comparators (Own Store, no pagination) -----
// AG Grid passes `isDescending` as the 5th arg and uses the result as-is (no
// auto-negation of a custom comparator), so these are exercised the same way
// AG Grid calls them, for both directions, mirroring service.py's
// null-always-last rule (see nonMovingView.js withNullsLast).
const sortWith = (vals, cmp, isDescending) => [...vals].sort((a, b) => cmp(a, b, null, null, isDescending));

test('numericComparator: 100 sorts after 20 numerically, not lexicographically, nulls last both directions', () => {
  assert.ok(numericComparator(20, 100, null, null, false) < 0);
  assert.ok(numericComparator(100, 20, null, null, false) > 0);
  const vals = [null, 5, 1, null, 100, 20];
  assert.deepEqual(sortWith(vals, numericComparator, false), [1, 5, 20, 100, null, null]);
  assert.deepEqual(sortWith(vals, numericComparator, true), [100, 20, 5, 1, null, null]);
});

test('daysSinceSaleComparator treats "never sold" (null) as the oldest in both directions', () => {
  assert.ok(daysSinceSaleComparator(null, 500, null, null, false) > 0);   // never-sold is older (ascending: last)
  assert.ok(daysSinceSaleComparator(500, null, null, null, false) < 0);
  assert.equal(daysSinceSaleComparator(null, null, null, null, false), 0);
  const vals = [10, null, 200, 5];
  assert.deepEqual(sortWith(vals, daysSinceSaleComparator, false), [5, 10, 200, null]);
  assert.deepEqual(sortWith(vals, daysSinceSaleComparator, true), [null, 200, 10, 5]); // never-sold still "oldest" -> first on desc
});

test('dateComparator sorts chronologically with nulls last both directions', () => {
  const vals = ['2026-03-01', null, '2024-01-15', '2025-06-20'];
  assert.deepEqual(sortWith(vals, dateComparator, false), ['2024-01-15', '2025-06-20', '2026-03-01', null]);
  assert.deepEqual(sortWith(vals, dateComparator, true), ['2026-03-01', '2025-06-20', '2024-01-15', null]);
});

test('textComparator is alphabetical and case-insensitive, nulls last both directions', () => {
  const vals = ['Zinc', 'amoxicillin', null, 'Paracetamol'];
  assert.deepEqual(sortWith(vals, textComparator, false), ['amoxicillin', 'Paracetamol', 'Zinc', null]);
  assert.deepEqual(sortWith(vals, textComparator, true), ['Zinc', 'Paracetamol', 'amoxicillin', null]);
});

test('activeFilterCount counts search/show/type/supplier/age/expiry/zero-stock as one each', () => {
  assert.equal(activeFilterCount({ show: DEFAULT_SHOW_ID }), 0);
  assert.equal(activeFilterCount({ search: 'dolo', show: DEFAULT_SHOW_ID }), 1);
  assert.equal(activeFilterCount({ show: 'all' }), 1);
  assert.equal(activeFilterCount({ show: '' }), 1); // Custom (e.g. a bare classification chip)
  assert.equal(activeFilterCount({ search: ' ', show: 'dead', supplier: 'S1', includeZero: true }), 3);
});

test('SHOW_PRESETS: the default id resolves to a preset and Never Sold / No Sales History both map to NO_SALES', () => {
  assert.ok(SHOW_PRESET_BY_ID[DEFAULT_SHOW_ID]);
  assert.equal(SHOW_PRESET_BY_ID.never.classes[0], 'NO_SALES');
  assert.equal(SHOW_PRESET_BY_ID.nosaleshist.classes[0], 'NO_SALES');
  // The default report is 180+ days (strictly > 180, i.e. minDays 181, same
  // "N+1" convention as the existing > 90 days preset) OR never sold --
  // minDays alone already covers "or never sold" since a null
  // days_since_sale is never excluded by a minimum (see filtersEqual /
  // service.py filter_rows).
  assert.equal(SHOW_PRESET_BY_ID[DEFAULT_SHOW_ID].minDays, 181);
});

test('filtersEqual ignores key order and array order in classes, and catches every tracked field', () => {
  const a = { search: 'x', classes: ['DEAD', 'NEW'], ptype: 'pharma', supplier: 'S1', minDays: 181, maxDays: '', age: '181', expiry: 'risk', includeZero: false, nonMovingOnly: false };
  const b = { ...a, classes: ['NEW', 'DEAD'] };
  assert.ok(filtersEqual(a, b));
  assert.ok(!filtersEqual(a, { ...a, search: 'y' }));
  assert.ok(!filtersEqual(a, { ...a, minDays: 91 }));
  assert.ok(!filtersEqual(a, { ...a, classes: ['DEAD'] }));
  assert.equal(filtersEqual(null, a), false);
  assert.equal(filtersEqual(a, null), false);
  assert.equal(filtersEqual(a, a), true); // same reference short-circuits
});
