// Pure Procurement Workspace helpers. Kept out of the JSX module so node:test
// can import them without a React transform.

export function pwKey(code) {
  return String(code ?? '').replace(/\.0$/, '');
}

// 0 stays valid (don't-order). Positive entries are whole packs, five digits.
export function pwWholeQty(raw) {
  const n = Math.trunc(Number(raw));
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.min(n, 99999);
}

// Saved column order -> every movable key exactly once. Unknown keys drop.
// A key missing from an older save is inserted after the nearest preceding
// default neighbour, so new columns do not jump to the front.
export function pwColumnOrder(saved, movableKeys) {
  const keys = Array.isArray(movableKeys) ? movableKeys : [];
  const order = (Array.isArray(saved) ? saved : []).filter((k, i, arr) => keys.includes(k) && arr.indexOf(k) === i);
  keys.forEach((k, i) => {
    if (order.includes(k)) return;
    const prev = keys.slice(0, i).reverse().find((p) => order.includes(p));
    order.splice(prev ? order.indexOf(prev) + 1 : 0, 0, k);
  });
  return order;
}

// ST_* is warehouse stock bridged into the supplier list. It can be shown
// on a recommendation card and must not be assigned as an order supplier.
export function pwIsWarehouseCard(card) {
  if (!card || typeof card !== 'object') return false;
  if (card.is_warehouse) return true;
  if (Array.isArray(card.tags) && card.tags.includes('warehouse')) return true;
  return String(card.supplier_code ?? '').toUpperCase().startsWith('ST_');
}

// Latest-GRN facts render only when they belong to the selected product.
// A previous row's payload stays in state until the next fetch returns.
export function pwGrnForSelection(latest, productKey) {
  if (!latest || productKey == null || latest.code == null) return null;
  return pwKey(latest.code) === pwKey(productKey) ? latest : null;
}

// A saved width wins. An empty or non-numeric save keeps the column default.
export function pwColumnWidth(defaultWidth, saved) {
  const n = Number(saved);
  return Number.isFinite(n) && n > 0 ? Math.max(24, n) : defaultWidth;
}

export function pwQtyKeyAction({ key, view, hasSupplier, status, clear, ctrl, index, last }) {
  const next = Math.min(index + 1, last);
  const prev = Math.max(index - 1, 0);
  if (key === '+' || key === '-') return { type: 'nudge', delta: key === '+' ? 1 : -1 };
  if (key === 'ArrowDown') return { type: 'commit', nextIndex: next };
  if (key === 'ArrowUp') return { type: 'commit', nextIndex: prev };
  if (key === 'Enter') {
    if (view === 'supplier' && hasSupplier && status !== 1) return { type: 'assign' };
    return { type: 'commit', nextIndex: null };
  }
  if (key === 'Escape' || (key === 'Backspace' && clear)) return { type: 'commit', zero: true, nextIndex: next };
  if (key === 'Delete' && view === 'supplier') return { type: 'remove' };
  if (key === 'ArrowRight') return { type: 'suggest' };
  if ((key === 'i' || key === 'I') && !ctrl) return { type: 'decisions' };
  return null;
}

export function pwAssignRefusal({ card, finalized, busy, status, qty, legacySupplier, store }) {
  if (!card || finalized || busy || status == null || status === 1) return { ok: false };
  const name = card.supplier_name || card.supplier_code;
  if (pwIsWarehouseCard(card)) return { ok: false, error: `${name} is warehouse stock and cannot be assigned as a supplier.` };
  if (!legacySupplier) return { ok: false, error: `${name} is not in ${store}'s order supplier list — it can't be assigned here.` };
  if (!(Number(qty) > 0)) return { ok: false, error: 'Set an order qty above 0 first.' };
  return { ok: true };
}

export function pwExportGuard({ needsSupplier, supplier }) {
  if (needsSupplier && !supplier) return 'Pick a supplier first.';
  return '';
}

export function pwFinalizePlan({ store, reopen, note }) {
  if (!store) return { action: 'skip' };
  if (note === null || note === undefined) return { action: 'cancel' };
  return { action: reopen ? 'reopen' : 'finalize', note };
}

// Detail panels (owner request 2026-10-25, "like our Order Workspace"): each
// can be shown/hidden, docked in the Middle column (beside the grid), the
// Side column or the Bottom strip under the grid, and reordered. All Stores
// defaults under Supplier Recommendation (that column had empty space), so
// it is fully visible; Previous Decisions defaults to the bottom like the
// Order Workspace's.
export const PW_PANEL_DEFS = [
  { key: 'suggest', label: 'Supplier Recommendation' },
  { key: 'stores', label: 'All Stores (3 months)' },
  { key: 'facts', label: 'Product Summary' },
  { key: 'trend', label: 'Monthly Trend' },
  { key: 'purchase', label: 'Purchase / GRN' },
  { key: 'sales', label: 'Bill / Sales' },
  { key: 'decisions', label: 'Previous Decisions' },
];
export const PW_DOCKS = [['middle', 'Middle'], ['side', 'Side'], ['bottom', 'Bottom']];
export const PW_PANELS_DEFAULT = [
  { key: 'suggest', dock: 'middle', hidden: false },
  { key: 'stores', dock: 'middle', hidden: false },
  { key: 'facts', dock: 'side', hidden: false },
  { key: 'trend', dock: 'side', hidden: false },
  { key: 'purchase', dock: 'side', hidden: false },
  { key: 'sales', dock: 'side', hidden: false },
  { key: 'decisions', dock: 'bottom', hidden: false },
];

// Saved panels -> a complete list: unknown keys and duplicates dropped, a bad
// dock falls back to the panel's default, panels missing from an older save
// are appended with their defaults.
export function pwNormalizePanels(saved) {
  const defaults = new Map(PW_PANELS_DEFAULT.map((p) => [p.key, p]));
  const docks = new Set(PW_DOCKS.map(([k]) => k));
  const out = [];
  (Array.isArray(saved) ? saved : []).forEach((p) => {
    if (!p || !defaults.has(p.key) || out.some((o) => o.key === p.key)) return;
    out.push({ key: p.key, dock: docks.has(p.dock) ? p.dock : defaults.get(p.key).dock, hidden: Boolean(p.hidden) });
  });
  PW_PANELS_DEFAULT.forEach((d) => { if (!out.some((p) => p.key === d.key)) out.push({ ...d }); });
  return out;
}

// ---- supplier stock compare (row card) ----
// Effective discount of a live-stock line: the flat Disc% stacked with the
// free-qty offer ("10+2" = pay for 10 of 12). Ranks suppliers on one number.
export function pwEffectiveDiscount(line) {
  const disc = Math.min(Math.max(Number(line?.discount) || 0, 0), 100);
  const sch = Number(line?.sch) || 0;
  const free = Number(line?.free) || 0;
  const paid = sch > 0 && free > 0 ? sch / (sch + free) : 1;
  return Math.round((1 - (1 - disc / 100) * paid) * 10000) / 100;
}

// The picked supplier's own live-stock line for one product (S.Stock /
// S.Offer grid columns). A unified supplier joins several member codes: the
// best-stocked member line speaks for it. null = not listed = no stock.
export function pwSupplierLine(lines, currentCodes = []) {
  const codes = new Set((currentCodes || []).map((c) => String(c).trim()));
  if (!codes.size || !Array.isArray(lines)) return null;
  return lines.filter((l) => codes.has(String(l?.supplier_code).trim()))
    .reduce((best, l) => (!best || Number(l.stock) > Number(best.stock) ? l : best), null);
}

// Supplier offer as "sch+free" (e.g. 10+1); '' when there is no offer.
export function pwOfferText(sch, free) {
  const s = Number(sch) || 0;
  const f = Number(free) || 0;
  return s > 0 && f > 0 ? `${s}+${f}` : '';
}

// Offer remark for a final qty (owner 2026-11-04): a qty on a whole
// multiple of an offer's buy qty (9+1 -> 9, 18, 27...) gets the offer
// ("9+1") as its export remark. offers = candidates in priority order (picked
// supplier, in-stock suppliers, purchase history); reduce = a history bill's
// totals (18+2 is two 9+1s), so it is cut to its smallest pattern.
const pwGcd = (a, b) => (b ? pwGcd(b, a % b) : a);
export function pwOfferRemark(qty, offers) {
  const q = Math.trunc(Number(qty) || 0);
  if (q <= 0) return '';
  for (const o of Array.isArray(offers) ? offers : []) {
    let sch = Math.trunc(Number(o?.sch) || 0);
    let free = Math.trunc(Number(o?.free) || 0);
    if (sch <= 0 || free <= 0) continue;
    if (o.reduce) { const g = pwGcd(sch, free); sch /= g; free /= g; }
    if (q % sch === 0) return `${sch}+${free}`;
  }
  return '';
}

// Below this many points of effective discount, two suppliers count as the
// same deal -- not worth moving an order for.
const PW_COMPARE_MARGIN = 0.5;

// One product's supplier lines -> ranked list + verdict for the card.
// currentCodes = the picked supplier's real codes (a unified supplier joins
// several); empty when no supplier is picked (All products).
// verdict.kind:
//   switch  -- another supplier is a better deal AND has stock
//   stay    -- a better deal exists but has no stock: place with current
//   best    -- current is the best deal in stock
//   only    -- nobody else lists the product (suppliers upload in-stock
//              lines only, so "not listed" = no stock): place with current
//   nostock -- current has no live stock; best = the best supplier in stock
//   pick    -- no current supplier; best = the best supplier in stock
//   none    -- nobody has stock
export function pwCompareSuppliers(lines, currentCodes = [], orderQty = 0) {
  const codes = new Set((currentCodes || []).map((c) => String(c).trim()));
  const ranked = (Array.isArray(lines) ? lines : []).map((l) => ({
    ...l,
    eff: pwEffectiveDiscount(l),
    inStock: Number(l.stock) > 0,
    current: codes.has(String(l.supplier_code).trim()),
  })).sort((a, b) => (b.inStock - a.inStock) || (b.eff - a.eff) || (Number(b.stock) - Number(a.stock)));
  // A unified supplier can carry several member lines: the in-stock,
  // best-deal one speaks for it.
  const current = ranked.find((l) => l.current) || null;
  const others = ranked.filter((l) => !l.current);
  const bestInStock = others.find((l) => l.inStock) || null;
  const qty = Number(orderQty) || 0;
  const short = (l) => Boolean(l && qty > 0 && Number(l.stock) < qty);
  let verdict;
  if (!codes.size) {
    verdict = bestInStock ? { kind: 'pick', best: bestInStock } : { kind: 'none', best: null };
  } else if (current?.inStock && !others.some((l) => l.inStock)) {
    const betterOut = others.filter((l) => l.eff > current.eff + PW_COMPARE_MARGIN);
    verdict = betterOut.length ? { kind: 'stay', best: current, blocked: betterOut } : { kind: 'only', best: current };
  } else if (!current || !current.inStock) {
    verdict = bestInStock ? { kind: 'nostock', best: bestInStock } : { kind: 'none', best: null };
  } else if (bestInStock && bestInStock.eff > current.eff + PW_COMPARE_MARGIN) {
    verdict = { kind: 'switch', best: bestInStock, gain: Math.round((bestInStock.eff - current.eff) * 100) / 100 };
  } else {
    const betterOut = others.filter((l) => !l.inStock && l.eff > current.eff + PW_COMPARE_MARGIN);
    verdict = betterOut.length ? { kind: 'stay', best: current, blocked: betterOut } : { kind: 'best', best: current };
  }
  verdict.short = short(verdict.best);
  return { ranked, current, others, verdict };
}
