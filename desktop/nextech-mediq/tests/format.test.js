import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatQty, formatCurrency, formatDate, isLowStock, isOutOfStock } from '../src/utilities/format.js';

test('formatQty renders a locale-grouped number', () => {
  assert.equal(formatQty(1234), '1,234');
  assert.equal(formatQty(0), '0');
});

test('formatQty falls back to an em dash for missing or non-numeric input', () => {
  assert.equal(formatQty(null), '—');
  assert.equal(formatQty(undefined), '—');
  assert.equal(formatQty(''), '—');
  assert.equal(formatQty('n/a'), '—');
  assert.equal(formatQty(NaN), '—');
});

test('formatCurrency renders a rupee-prefixed, fixed-decimal amount', () => {
  assert.equal(formatCurrency(45), '₹45.00');
  assert.equal(formatCurrency(1234.5), '₹1,234.50');
});

test('formatCurrency falls back to an em dash for missing or non-numeric input, not a real zero', () => {
  // Number(null) and Number('') both coerce to 0 — formatCurrency must reject
  // them explicitly so a missing field never renders as a real ₹0.00.
  assert.equal(formatCurrency(null), '—');
  assert.equal(formatCurrency(undefined), '—');
  assert.equal(formatCurrency(''), '—');
  assert.equal(formatCurrency('bad'), '—');
});

test('formatCurrency renders an actual zero amount as ₹0.00', () => {
  assert.equal(formatCurrency(0), '₹0.00');
});

test('formatDate renders a short localized date for a valid value', () => {
  const out = formatDate('2026-01-15T00:00:00Z');
  assert.match(out, /2026/);
  assert.match(out, /Jan/);
});

test('formatDate falls back to an em dash for empty/missing values', () => {
  assert.equal(formatDate(null), '—');
  assert.equal(formatDate(undefined), '—');
  assert.equal(formatDate(''), '—');
});

test('formatDate returns the raw string when it cannot be parsed as a date', () => {
  assert.equal(formatDate('not-a-date'), 'not-a-date');
});

test('isLowStock flags positive stock at or below the threshold', () => {
  assert.equal(isLowStock(5), true);
  assert.equal(isLowStock(10), true);
  assert.equal(isLowStock(11), false);
  assert.equal(isLowStock(0), false);
  assert.equal(isLowStock(-3), false);
});

test('isOutOfStock flags zero, negative, and non-numeric stock', () => {
  assert.equal(isOutOfStock(0), true);
  assert.equal(isOutOfStock(-1), true);
  assert.equal(isOutOfStock(null), true);
  assert.equal(isOutOfStock('bad'), true);
  assert.equal(isOutOfStock(1), false);
});
