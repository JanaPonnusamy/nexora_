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
