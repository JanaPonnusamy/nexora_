import type { SupplierRow, WorkspaceItem } from '../../types/procurement'

/** Rank suppliers cheapest-first (owner-directed): ascending Last Purchase Rate
 *  (PTR), suppliers with no recorded rate last, ties broken by purchase
 *  frequency (desc). The cheapest supplier is always the top card. */
export function sortSuppliersByCost(suppliers: SupplierRow[]): SupplierRow[] {
  return [...suppliers].sort((a, b) => {
    const ra = a.last_purchase_rate
    const rb = b.last_purchase_rate
    if (ra == null && rb == null) return (b.purchase_frequency ?? 0) - (a.purchase_frequency ?? 0)
    if (ra == null) return 1
    if (rb == null) return -1
    if (ra !== rb) return ra - rb
    return (b.purchase_frequency ?? 0) - (a.purchase_frequency ?? 0)
  })
}

/** The supplier with the most recent purchase (max last_grn_date) — "Preferred
 *  Supplier" per the buyer's own purchase history. Ties keep the first one
 *  encountered (list order, already cheapest-first). Display order is NOT
 *  changed by this — callers badge/pre-select the returned code, they don't
 *  reorder the list (owner-approved: cheapest stays first). */
export function preferredSupplier(suppliers: SupplierRow[] | undefined): string | null {
  if (!suppliers || suppliers.length === 0) return null
  let best: SupplierRow | null = null
  let bestTime = -Infinity
  for (const s of suppliers) {
    const t = s.last_grn_date ? Date.parse(s.last_grn_date) : NaN
    if (!Number.isNaN(t) && t > bestTime) {
      bestTime = t
      best = s
    }
  }
  return best?.supplier_code ?? null
}

/** Optional per-product signals for Auto Assign scoring that are not carried in
 *  the batched recommendation feed (kept optional so the caller adds no extra
 *  per-product query). */
export interface AutoAssignSignals {
  /** Supplier explicitly mapped to this product (Exact Product Mapping). */
  mappedSupplier?: string | null
  /** Supplier codes with live stock available for this product. */
  liveStockCodes?: Set<string> | null
}

// Relative weights (highest wins). Exact mapping dominates; live stock breaks ties.
const AA_WEIGHTS = { mapping: 100, lastPurchase: 40, frequency: 30, ptr: 20, liveStock: 10 }

/**
 * Auto Assign supplier selection — WEIGHTED SCORING (exactly ONE supplier is
 * ever chosen per product). Each candidate is scored across, in weight order:
 *
 *   1. Exact Product Mapping  (100) — supplier explicitly mapped to the product
 *   2. Last Purchase          ( 40) — most recent GRN date (newest = full)
 *   3. Purchase Frequency     ( 30) — normalised against the top candidate
 *   4. Lowest PTR             ( 20) — cheapest last rate = full
 *   5. Live Stock             ( 10) — stock currently available
 *
 * The highest total score wins. Mapping/live-stock signals are optional (not in
 * the batched feed) and simply contribute 0 when absent — so the ranking then
 * resolves to Last Purchase → Frequency → PTR without any extra query. Returns
 * the chosen supplier_code, or null when the product has no supplier history.
 */
export function autoAssignSupplier(
  recs: SupplierRow[] | undefined,
  signals?: AutoAssignSignals,
): string | null {
  if (!recs || recs.length === 0) return null

  const maxFreq = Math.max(1, ...recs.map((r) => r.purchase_frequency ?? 0))
  const times = recs.map((r) => (r.last_grn_date ? Date.parse(r.last_grn_date) : NaN)).filter((t) => !Number.isNaN(t))
  const newest = times.length ? Math.max(...times) : NaN
  const oldest = times.length ? Math.min(...times) : NaN
  const rates = recs.map((r) => r.last_purchase_rate).filter((x): x is number => x != null)
  const minRate = rates.length ? Math.min(...rates) : NaN
  const maxRate = rates.length ? Math.max(...rates) : NaN

  let best: string | null = null
  let bestScore = -1
  for (const r of recs) {
    let s = 0
    if (signals?.mappedSupplier && r.supplier_code === signals.mappedSupplier) s += AA_WEIGHTS.mapping
    if (r.last_grn_date && !Number.isNaN(newest)) {
      const t = Date.parse(r.last_grn_date)
      const span = newest - oldest
      s += AA_WEIGHTS.lastPurchase * (span > 0 ? (t - oldest) / span : 1)
    }
    s += AA_WEIGHTS.frequency * ((r.purchase_frequency ?? 0) / maxFreq)
    if (r.last_purchase_rate != null && !Number.isNaN(minRate)) {
      const span = maxRate - minRate
      s += AA_WEIGHTS.ptr * (span > 0 ? (maxRate - r.last_purchase_rate) / span : 1)
    }
    if (signals?.liveStockCodes?.has(r.supplier_code)) s += AA_WEIGHTS.liveStock
    if (s > bestScore) {
      bestScore = s
      best = r.supplier_code
    }
  }
  return best
}

/** Purchase value for a working line: Final Qty × Last Purchase Rate (PTR),
 *  falling back to the VPL ptr_cost when a last rate is not recorded. */
export function purchaseValue(item: WorkspaceItem): number {
  const rate = item.last_purchase_rate ?? item.ptr_cost ?? 0
  return (item.final_qty ?? 0) * (rate ?? 0)
}

/** Cost (PTR) for a working line driven by the *current supplier*, not an
 *  average. Priority: the locally selected supplier → the already-assigned
 *  supplier → the top-ranked recommendation → the item's own last rate/ptr.
 *  Changing the selected supplier changes this cost (and the totals). */
export function effectiveCost(
  item: WorkspaceItem,
  recs: SupplierRow[] | undefined,
  selectedCode: string | null | undefined,
): number {
  const code = selectedCode ?? item.supplier_code ?? null
  const list = recs ?? []
  const chosen = code ? list.find((s) => s.supplier_code === code) : undefined
  const rate =
    chosen?.last_purchase_rate ??
    list[0]?.last_purchase_rate ??
    item.last_purchase_rate ??
    item.ptr_cost ??
    0
  return rate ?? 0
}
