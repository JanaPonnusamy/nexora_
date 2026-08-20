import type { WorkspaceItem } from '../../types/procurement'
import { money, num } from '../stock/format'
import { effectiveCost } from './purchaseValue'
import type { SupplierRow } from '../../types/procurement'

export interface AutoAssignCandidateGroup {
  supplier_code: string
  order_item_ids: string[]
}

/**
 * Preview-before-commit for Auto Assign Suppliers (Cost or Rank mode) — shows
 * exactly which products would go to which supplier, at what per-line cost
 * and group total, before anything is actually assigned. Nothing here calls
 * the assignment API; the caller commits on Confirm using the same groups.
 */
export function AutoAssignPreviewModal({
  groups,
  droppedBelowMin,
  itemById,
  recommendations,
  nameOf,
  mode,
  busy,
  onConfirm,
  onClose,
}: {
  /** supplier_code -> claimed order_item_ids, already filtered to groups
   *  meeting their min_products threshold. */
  groups: AutoAssignCandidateGroup[]
  /** Suppliers whose claim was released for being below their minimum —
   *  shown as a note, not a group (nothing will be assigned to them). */
  droppedBelowMin: { supplier_code: string; count: number }[]
  itemById: Map<string, WorkspaceItem>
  recommendations: Record<string, SupplierRow[]>
  nameOf: (code: string) => string
  mode: 'cost' | 'rank'
  busy: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  const totalProducts = groups.reduce((a, g) => a + g.order_item_ids.length, 0)
  const totalValue = groups.reduce(
    (a, g) =>
      a +
      g.order_item_ids.reduce((b, id) => {
        const it = itemById.get(id)
        if (!it) return b
        return b + (it.final_qty ?? 0) * effectiveCost(it, recommendations[id], g.supplier_code)
      }, 0),
    0,
  )

  return (
    <div className="pm-drawer" role="presentation">
      <div className="pm-drawer__backdrop" onClick={onClose} />
      <div className="pm-modal pm-modal--wide" role="dialog" aria-label="Auto Assign preview">
        <header className="pm-modal__head">
          <h5 className="mb-0">
            <i className="bi bi-magic me-2" />
            Auto Assign Preview — {mode === 'rank' ? 'Rank' : 'Cost'} mode
          </h5>
          <button className="btn-close" aria-label="Close" onClick={onClose} />
        </header>
        <div className="pm-modal__body">
          <div className="pm-opt__tiles mb-2">
            <span className="pm-opt__tile"><b>{num(groups.length)}</b><span>Suppliers</span></span>
            <span className="pm-opt__tile"><b>{num(totalProducts)}</b><span>Products</span></span>
            <span className="pm-opt__tile"><b>{money(totalValue)}</b><span>Est. Value</span></span>
          </div>
          {groups.length === 0 ? (
            <div className="pm-sq__hint">Nothing eligible to auto-assign.</div>
          ) : (
            <div className="pm-modal__results">
              {groups.map((g) => {
                const rows = g.order_item_ids.map((id) => itemById.get(id)).filter((x): x is WorkspaceItem => Boolean(x))
                const value = rows.reduce((a, it) => a + (it.final_qty ?? 0) * effectiveCost(it, recommendations[it.order_item_id], g.supplier_code), 0)
                return (
                  <div key={g.supplier_code} className="pm-aap__group">
                    <div className="pm-aap__grouphead">
                      <span className="pm-prod__name">{nameOf(g.supplier_code)}</span>
                      <span className="pm-aap__groupstats">{num(rows.length)} products · {money(value)}</span>
                    </div>
                    <div className="pm-aap__products">
                      {rows.map((it) => (
                        <span key={it.order_item_id} className="pm-aap__chip">
                          {it.product_name ?? it.product_code} × {num(it.final_qty ?? 0)}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
          {droppedBelowMin.length > 0 && (
            <div className="pm-sqexp__errors mt-2">
              <i className="bi bi-exclamation-triangle" />
              {droppedBelowMin.map((d) => (
                <span key={d.supplier_code}>
                  {nameOf(d.supplier_code)}: {num(d.count)} product{d.count === 1 ? '' : 's'} available but below its minimum — left unassigned.
                </span>
              ))}
            </div>
          )}
        </div>
        <footer className="pm-modal__foot">
          <div className="pm-modal__sel">Nothing is assigned yet — review, then Confirm.</div>
          <button className="pm-btn pm-btn--ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="pm-btn pm-btn--primary" onClick={onConfirm} disabled={busy || groups.length === 0}>
            <i className="bi bi-check2-square" /> {busy ? 'Assigning…' : `Confirm & Assign ${num(totalProducts)}`}
          </button>
        </footer>
      </div>
    </div>
  )
}
