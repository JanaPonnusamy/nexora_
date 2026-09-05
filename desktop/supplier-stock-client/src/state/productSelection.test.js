// Regression tests for the two-color product-selection state model
// (GREEN = user source click, BLUE = auto-synchronized equivalent).
// Run with: node --test src/state/productSelection.test.js

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  applySyncResult,
  buildSynchronizedMap,
  emptySelectionState,
  selectionFor,
  selectionStateForClick
} from './productSelection.js';

const NMW = 'NMW-id';
const NMA = 'NMA-id';
const NMG = 'NMG-id';
const NMS = 'NMS-id';
const NMV = 'NMV-id';

// Real BRIV-family sync-selection API responses (shape matches
// backend stock_availability/service.py:match_cross_store_selection),
// captured while debugging the reported cross-store sync bug.
const BRIV_25MG_RESULTS = [
  { store_id: NMA, match_type: 'STRONG_ATTRIBUTE_MATCH', score: 96.0, product: { product_code: '5883025', product_name: 'BRIV 25MG', mrp: 95.64 } },
  { store_id: NMG, match_type: 'EXACT_NORMALIZED_NAME', score: 99.0, product: { product_code: '5886702', product_name: 'BRIV 25MG  TAB', mrp: 95.64 } },
  { store_id: NMS, match_type: 'STRONG_ATTRIBUTE_MATCH', score: 96.0, product: { product_code: '5884023', product_name: 'BRIV 25MG', mrp: 95.64 } },
  { store_id: NMV, match_type: 'EXACT_NORMALIZED_NAME', score: 98.0, product: { product_code: '44320', product_name: 'BRIV 25 MG TAB', mrp: 92.75 } }
];

const BRIV_50MG_RESULTS = [
  { store_id: NMW, match_type: 'EXACT_NORMALIZED_NAME', score: 99.0, product: { product_code: '5884054', product_name: 'BRIV 50MG  TAB', mrp: 295.24 } },
  { store_id: NMG, match_type: 'EXACT_NORMALIZED_NAME', score: 99.0, product: { product_code: '5884054', product_name: 'BRIV 50MG  TAB', mrp: 295.24 } },
  { store_id: NMS, match_type: 'EXACT_NORMALIZED_NAME', score: 98.0, product: { product_code: '5852078', product_name: 'BRIV 50MG TAB', mrp: 295.24 } },
  { store_id: NMV, match_type: 'EXACT_NORMALIZED_NAME', score: 98.0, product: { product_code: '43126', product_name: 'BRIV 50MG TAB', mrp: 295.24 } }
];

test('TEST 1: NMW -> BRIV 25MG TAB - source is GREEN, every other store is BLUE with the real target codes', () => {
  let state = emptySelectionState();
  state = selectionStateForClick(NMW, '5886702');
  state = applySyncResult(state, NMW, '5886702', buildSynchronizedMap(BRIV_25MG_RESULTS));

  assert.equal(state.sourceStoreId, NMW);
  assert.equal(state.sourceProductCode, '5886702');

  const nmw = selectionFor(state, NMW);
  assert.equal(nmw.sourceProductCode, '5886702');
  assert.equal(nmw.syncProductCode, null, 'source store must never also be BLUE');

  const expectations = { [NMA]: '5883025', [NMG]: '5886702', [NMS]: '5884023', [NMV]: '44320' };
  for (const [storeId, expectedCode] of Object.entries(expectations)) {
    const sel = selectionFor(state, storeId);
    assert.equal(sel.sourceProductCode, null, `${storeId} must not be GREEN`);
    assert.equal(sel.syncProductCode, expectedCode, `${storeId} BLUE target code`);
  }
});

test('TEST 2: clicking NMA -> BRIV 50MG TAB completely replaces the state - NMW becomes BLUE, no stale 25MG anywhere', () => {
  let state = selectionStateForClick(NMW, '5886702');
  state = applySyncResult(state, NMW, '5886702', buildSynchronizedMap(BRIV_25MG_RESULTS));

  // second click: a different store, a different product
  state = selectionStateForClick(NMA, '5884054');
  state = applySyncResult(state, NMA, '5884054', buildSynchronizedMap(BRIV_50MG_RESULTS));

  assert.equal(state.sourceStoreId, NMA);
  assert.equal(state.sourceProductCode, '5884054');

  const nma = selectionFor(state, NMA);
  assert.equal(nma.sourceProductCode, '5884054');
  assert.equal(nma.syncProductCode, null);

  const nmw = selectionFor(state, NMW);
  assert.equal(nmw.sourceProductCode, null, 'NMW must no longer be GREEN');
  assert.equal(nmw.syncProductCode, '5884054', 'NMW must now show the 50MG equivalent');

  // No store may retain the previous 25MG target codes anywhere.
  const previous25mgCodes = new Set(['5883025', '5886702', '5884023', '44320']);
  for (const storeId of [NMW, NMA, NMG, NMS, NMV]) {
    const sel = selectionFor(state, storeId);
    assert.ok(!previous25mgCodes.has(sel.syncProductCode), `${storeId} must not keep a stale 25MG blue code`);
  }
});

test('TEST 4 / NO_MATCH: a store with no reliable equivalent gets no new BLUE, and an old BLUE from a previous source is cleared', () => {
  let state = selectionStateForClick(NMW, '5886702');
  state = applySyncResult(state, NMW, '5886702', buildSynchronizedMap(BRIV_25MG_RESULTS));
  assert.equal(selectionFor(state, NMS).syncProductCode, '5884023');

  // New click: NMG -> BRIV 100MG TAB, where NMS has no 100MG equivalent (matches the
  // real backend regression fixture in test_stock_availability_cross_store_sync.py).
  const results100mg = [
    { store_id: NMW, match_type: 'EXACT_SUPPLIER_MATCH', score: 100.0, product: { product_code: '5884053', product_name: 'BRIV 100MG  TAB', mrp: 576.18 } },
    { store_id: NMA, match_type: 'STRONG_ATTRIBUTE_MATCH', score: 96.0, product: { product_code: '5883102', product_name: 'BRIV 100MG', mrp: 614.6 } },
    { store_id: NMS, match_type: 'NO_MATCH', score: 69.78, product: null },
    { store_id: NMV, match_type: 'NO_MATCH', score: 80.96, product: null }
  ];
  state = selectionStateForClick(NMG, '5884053');
  state = applySyncResult(state, NMG, '5884053', buildSynchronizedMap(results100mg));

  const nms = selectionFor(state, NMS);
  assert.equal(nms.sourceProductCode, null);
  assert.equal(nms.syncProductCode, null, 'NMS must have no new blue AND no stale 25MG blue left over');

  const nmv = selectionFor(state, NMV);
  assert.equal(nmv.syncProductCode, null, 'NMV NO_MATCH must never fabricate a blue row');
});

test('TEST 5: clicking a BLUE synchronized row makes it the new GREEN source', () => {
  let state = selectionStateForClick(NMW, '5886702');
  state = applySyncResult(state, NMW, '5886702', buildSynchronizedMap(BRIV_25MG_RESULTS));
  assert.equal(selectionFor(state, NMA).syncProductCode, '5883025', 'NMA starts out BLUE');

  // The user manually clicks NMA's (blue) row, but picks a DIFFERENT product there.
  state = selectionStateForClick(NMA, '5884054');
  const nmaAfterClick = selectionFor(state, NMA);
  assert.equal(nmaAfterClick.sourceProductCode, '5884054', 'NMA is immediately GREEN, even before the sync response');
  assert.equal(nmaAfterClick.syncProductCode, null);

  // And NMW - the ORIGINAL source - must not still be green or blue once the new
  // source's sync response comes back (even for a store that lands in NO_MATCH).
  state = applySyncResult(state, NMA, '5884054', buildSynchronizedMap([
    { store_id: NMW, match_type: 'EXACT_NORMALIZED_NAME', score: 99.0, product: { product_code: '5884054', product_name: 'BRIV 50MG  TAB', mrp: 295.24 } }
  ]));
  const nmw = selectionFor(state, NMW);
  assert.equal(nmw.sourceProductCode, null, 'the old source must not remain green');
  assert.equal(nmw.syncProductCode, '5884054');
});

test('TEST 7 / async race: a stale response for an earlier click must never overwrite a newer click', () => {
  // Click A: NMW 25MG. Click B (rapid): NMA 50MG.
  let state = selectionStateForClick(NMW, '5886702');
  state = selectionStateForClick(NMA, '5884054'); // user's second, LATEST click

  // Response A (for the OLD NMW/25MG click) arrives late.
  const staleApplied = applySyncResult(state, NMW, '5886702', buildSynchronizedMap(BRIV_25MG_RESULTS));
  assert.deepEqual(staleApplied, state, 'a stale response for a superseded click must be a total no-op');

  // Response B (for the current NMA/50MG click) arrives and DOES apply.
  const fresh = applySyncResult(state, NMA, '5884054', buildSynchronizedMap(BRIV_50MG_RESULTS));
  assert.equal(fresh.sourceStoreId, NMA);
  assert.equal(selectionFor(fresh, NMW).syncProductCode, '5884054');
});

test('the source store is never present as a key in its own synchronized map (defensive, matches backend exclusion)', () => {
  const withSourceIncluded = buildSynchronizedMap([
    { store_id: NMW, match_type: 'EXACT_NORMALIZED_NAME', score: 99.0, product: { product_code: 'x', product_name: 'x', mrp: 1 } },
    { store_id: NMA, match_type: 'EXACT_NORMALIZED_NAME', score: 99.0, product: { product_code: 'y', product_name: 'y', mrp: 1 } }
  ]);
  // Even if a caller accidentally included the source store in the API response,
  // selectionFor() for the SOURCE store always takes the source branch and never
  // reads the synchronized map for its own store, so it can never render BLUE.
  const state = { sourceStoreId: NMW, sourceProductCode: '5886702', synchronized: withSourceIncluded };
  const nmw = selectionFor(state, NMW);
  assert.equal(nmw.sourceProductCode, '5886702');
  assert.equal(nmw.syncProductCode, null);
});
