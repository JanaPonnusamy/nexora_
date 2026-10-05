// Pure, DB-free, unit-tested logic for the Stock Availability two-color
// product-selection model: GREEN = the product the user explicitly clicked
// (the "source"); BLUE = an equivalent auto-selected in another store
// because it matches that source (a "synchronized" match).
//
// Kept separate from App.jsx (and from storeDetails, which is about what
// CORE DATA is loaded for the detail panels, not what color a row renders)
// so the state-transition rules can be exercised directly, without a React
// render, wherever a click or a sync-selection API response needs to be
// turned into the next selectionState.

export function emptySelectionState() {
  return { sourceStoreId: null, sourceProductCode: null, synchronized: {} };
}

// A user click (mouse or arrow-key - both go through the same handler)
// ALWAYS becomes the new GREEN source and wipes every previous BLUE match
// immediately, before any network round trip - so a click never leaves a
// stale blue row from the previous source product on screen, even for the
// instant before the sync response arrives.
export function selectionStateForClick(storeId, productCode) {
  return { sourceStoreId: storeId, sourceProductCode: productCode ?? null, synchronized: {} };
}

// Builds the BLUE map fresh from ONE sync-selection API response only - never
// merges into a previous synchronized map. A store with no match in this
// response simply has no key here, which is what makes a stale blue row from
// an earlier click impossible: it is never carried forward.
export function buildSynchronizedMap(results) {
  const synchronized = {};
  for (const r of results || []) {
    if (r && r.product && r.match_type !== 'NO_MATCH') {
      synchronized[r.store_id] = { productCode: r.product.product_code, matchType: r.match_type, score: r.score };
    }
  }
  return synchronized;
}

// Applies a sync-selection response to the current selectionState, but only
// if the state still corresponds to the exact click that triggered the
// request (same source store AND product). This is the guard that makes a
// stale/superseded response a no-op even in a race an outer request-ticket
// didn't already catch: a newer click always wins.
export function applySyncResult(currentState, sourceStoreId, sourceProductCode, synchronized) {
  if (currentState.sourceStoreId !== sourceStoreId || currentState.sourceProductCode !== sourceProductCode) {
    return currentState;
  }
  return { ...currentState, synchronized };
}

// Per-store selection descriptor for rendering: a store is EITHER the GREEN
// source (sourceProductCode set, syncProductCode always null) OR may have a
// BLUE synchronized match (syncProductCode set) - never both. This is what
// structurally guarantees the source store can never also render a blue row.
export function selectionFor(selectionState, storeId) {
  if (selectionState.sourceStoreId === storeId) {
    return { sourceProductCode: selectionState.sourceProductCode, syncProductCode: null };
  }
  return { sourceProductCode: null, syncProductCode: selectionState.synchronized[storeId]?.productCode ?? null };
}
