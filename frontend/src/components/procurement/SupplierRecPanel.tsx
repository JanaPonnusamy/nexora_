import { useEffect, useRef } from 'react'
import type { SupplierRow, WorkspaceItem } from '../../types/procurement'
import { date, money, num } from '../stock/format'
import { costMarginPercent, marginPercent, preferredSupplier, SUPPLIER_REC_LIMIT } from './purchaseValue'

// A mouse click on a card (plain <div>, no tabIndex) never claims DOM focus —
// document.activeElement falls back to <body>, which is not a descendant of
// the grid's own keyboard-owning container, so every arrow key afterwards
// silently misses ProductGrid/SupplierStockTable's onKeyDown and falls
// through to the browser's native scroll. Re-parking focus on the grid wrap
// after every mouse interaction here (same pattern SupplierPicker's
// onReturnToGrid already uses) keeps the keyboard workflow alive regardless
// of whether the supplier was picked by mouse or by Right-Arrow/Enter.
function focusGrid() {
  (document.querySelector('.pm-grid-wrap') as HTMLElement | null)?.focus()
}

// Rank the shown suppliers by latest received Item Cost (ascending) and map each
// onto a 5-band colour scale: lowest → green … highest → red. Suppliers with no
// recorded cost get no band. Returns a class per supplier_code.
function costBands(suppliers: SupplierRow[]): Record<string, string> {
  const BANDS = ['pm-cost--l1', 'pm-cost--l2', 'pm-cost--l3', 'pm-cost--l4', 'pm-cost--l5']
  const priced = suppliers.filter((s) => s.last_purchase_rate != null)
  const sorted = [...priced].sort((a, b) => (a.last_purchase_rate ?? 0) - (b.last_purchase_rate ?? 0))
  const n = sorted.length
  const out: Record<string, string> = {}
  sorted.forEach((s, r) => {
    const band = n <= 1 ? 0 : Math.round((r / (n - 1)) * 4)
    out[s.supplier_code] = BANDS[band]
  })
  return out
}

/**
 * Vertical Supplier Recommendation column — sits between the product grid and
 * the detail panel. Shows the selected product's ranked suppliers as
 * abbreviation cards (top → bottom). The keyboard "supplier zone" is driven from
 * the grid (Right enters, Left/Right move, Enter assigns) via the shared
 * selected-supplier state; `active` rings the panel while that zone holds focus.
 * Mouse: click a card to select, Assign to commit.
 */
export function SupplierRecPanel({
  item,
  suppliers,
  loading = false,
  selectedCode,
  assignedCode,
  assignedName,
  liveCodes,
  active,
  onSelect,
  onCommit,
  onRemoveAssignment,
}: {
  item: WorkspaceItem | null
  suppliers: SupplierRow[]
  loading?: boolean
  selectedCode?: string | null
  assignedCode?: string | null
  /** Display name of the supplier holding the current assignment (if any) —
   *  drives the "Already assigned to X" tooltip on every other card. */
  assignedName?: string | null
  liveCodes?: Set<string> | null
  active?: boolean
  onSelect?: (supplierCode: string) => void
  onCommit?: (item: WorkspaceItem, supplierCode: string) => void
  /** Unassign the current supplier from this product (reverts to review/draft).
   *  Rendered only on the assigned card, not every card. */
  onRemoveAssignment?: () => void
}) {
  const recommendedQty = item ? item.remaining_qty ?? item.final_qty ?? 0 : 0
  const canAssign = Boolean(item) && item!.item_status !== 'skipped' && recommendedQty > 0
  const shown = suppliers.slice(0, SUPPLIER_REC_LIMIT)
  // Auto-scroll (§9): keep the focused/selected card visible during Up/Down
  // keyboard navigation — same pattern as SupplierPicker's result list.
  const cardRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  useEffect(() => {
    if (!selectedCode) return
    cardRefs.current.get(selectedCode)?.scrollIntoView({ block: 'nearest' })
  }, [selectedCode])

  return (
    <div className={`pm-srp${active ? ' pm-srp--active' : ''}`}>
      <div className="pm-srp__title"><i className="bi bi-people" /> Supplier Recommendation</div>
      {!loading && item && suppliers.length > 0 && (
        <div className="pm-srp__ranking-note">Ranked by recent purchase, frequency &amp; price</div>
      )}
      {loading ? (
        <div className="pm-srp__hint">Loading supplier recommendations...</div>
      ) : !item ? (
        <div className="pm-srp__hint">Select a product.</div>
      ) : suppliers.length === 0 ? (
        <div className="pm-srp__hint">No purchase history for this product.</div>
      ) : (
        <div className="pm-srp__list">
          {(() => {
            const bands = costBands(shown)
            // Suppliers arrive already ranked (rankSuppliersForRecommendation —
            // recency + frequency + PTR blend, not price alone). The top card
            // is BEST; badge follows the array position, not a separate
            // "cheapest" lookup, so BEST always matches what Up/Down keyboard
            // navigation lands on first.
            const bestCode = shown[0]?.supplier_code
            // Preferred = latest purchased (own purchase history) — a
            // secondary badge, shown even when it's not also the top-ranked
            // card, so "most recently bought from" stays visible.
            const preferredCode = preferredSupplier(shown)
            return shown.map((s) => {
            const code = s.supplier_code
            const selected = selectedCode === code
            const assigned = assignedCode === code
            const best = code === bestCode
            const preferred = code === preferredCode && code !== bestCode
            const live = Boolean(liveCodes?.has(code))
            // Per-supplier MRP from this supplier's last purchase transaction
            // (sync.PurchaseTrans.mrp) wins over the product-level VPL figure,
            // which is often not captured at refresh time.
            const mrp = s.last_mrp ?? item?.mrp ?? null
            // Margin % = (PTR - Cost) / Cost * 100 — markup on cost, the SAME
            // formula NEXORA's own Margin Report already treats as the
            // authoritative "Margin %" (reports/repository.py's margin();
            // see costMarginPercent's docstring). The raw
            // sync.PurchaseTrans.Margin column (last_margin_percent) does not
            // reconcile against the visible Cost/PTR figures (verified against
            // real data — e.g. Cost 103.00/PTR 108.42 stored Margin=40.36%
            // when the true Cost/PTR margin is ~5.26%), so it is only used as
            // a last resort when Cost itself isn't available. Falls back to
            // the MRP-vs-PTR calculation only when neither purchase-history
            // figure is present.
            const legacyMargin = s.last_item_cost == null ? (s.last_margin_percent ?? null) : null
            const margin =
              costMarginPercent(s.last_purchase_rate, s.last_item_cost) ??
              legacyMargin ??
              marginPercent(mrp, s.last_purchase_rate)
            // A different supplier already owns this product — the button
            // stays reachable (routes into the confirm-reassign flow) but is
            // disabled from a plain click/Enter fast-path.
            const ownedElsewhere = Boolean(assignedCode) && !assigned
            return (
              <div
                key={code}
                ref={(el) => { if (el) cardRefs.current.set(code, el); else cardRefs.current.delete(code) }}
                className={`pm-srpcard${selected ? ' pm-srpcard--sel' : ''}${assigned ? ' pm-srpcard--assigned' : ''}${best ? ' pm-srpcard--cheapest' : ''}${ownedElsewhere ? ' pm-srpcard--disabled' : ''}`}
                onClick={() => { onSelect?.(code); focusGrid() }}
                onDoubleClick={() => { if (item) onCommit?.(item, code); focusGrid() }}
                title={s.supplier_name ?? code}
              >
                <div className="pm-srpcard__top">
                  <div className="pm-srpcard__badges">
                    {best && <span className="pm-srpcard__best" title="Top recommendation — recent purchase, frequency and price combined">BEST</span>}
                    {preferred && <span className="pm-srpcard__preferred" title="Latest purchasing supplier (purchase history)">PREFERRED</span>}
                    {live && <span className="pm-srpcard__live">LIVE</span>}
                  </div>
                  {/* No product-level batch/lot number exists in the supplier
                      recommendation data (SupplierRow carries no batch field) —
                      nothing is shown here rather than fabricated. */}
                </div>
                {/* Full name, never truncated (§2/§16) — wraps onto as many
                    lines as it needs; the card grows, the panel never
                    widens (bounded by PmWorkspaceSplit's px min/max). */}
                <div className="pm-srpcard__name">{s.supplier_name ?? code}</div>
                {/* Cost -> PTR -> Margin % -> MRP, always in this order and always
                    all four visible without expanding the card (spec) — each
                    value comes straight from the supplier recommendation feed
                    (or the product's own MRP); a missing source value renders
                    as "—", never a fabricated 0 or estimate. */}
                <div className="pm-srpcard__stats">
                  <span className="pm-srpcard__stat">
                    <b>{money(s.last_item_cost)}</b>
                    <label>Cost</label>
                  </span>
                  <span className="pm-srpcard__stat">
                    <b className={bands[code] ?? ''}>{money(s.last_purchase_rate)}</b>
                    <label>PTR</label>
                  </span>
                  <span className="pm-srpcard__stat">
                    <b className={margin != null ? 'pm-srpcard__margin' : undefined}>{margin != null ? `${margin.toFixed(2)}%` : '—'}</b>
                    <label>Margin</label>
                  </span>
                  <span className="pm-srpcard__stat">
                    <b>{mrp != null ? money(mrp) : '—'}</b>
                    <label>MRP</label>
                  </span>
                </div>
                <div className="pm-srpcard__facts">
                  <span>Last Purchase: {s.last_grn_date ? date(s.last_grn_date) : 'No history'}</span>
                  <span>Freq {num(s.purchase_frequency ?? 0)}</span>
                </div>
                <div className="pm-srpcard__actions">
                  {assigned && onRemoveAssignment && (
                    <button
                      className="pm-linkbtn pm-linkbtn--sm pm-linkbtn--danger pm-srpcard__remove"
                      onClick={(e) => { e.stopPropagation(); onRemoveAssignment(); focusGrid() }}
                    >
                      Remove
                    </button>
                  )}
                  <button
                    className="pm-btn pm-btn--success pm-btn--sm pm-srpcard__assign"
                    disabled={!canAssign || ownedElsewhere}
                    onClick={(e) => { e.stopPropagation(); if (item) onCommit?.(item, code); focusGrid() }}
                    title={
                      assigned ? 'Already assigned to this supplier'
                        : ownedElsewhere ? `Already assigned to ${assignedName ?? assignedCode} — use Change Supplier in the Assign stage to reassign`
                          : canAssign ? 'Assign the remaining quantity to this supplier' : 'Nothing left to assign'
                    }
                  >
                    {assigned ? 'Assigned' : `Assign ${recommendedQty > 0 ? num(recommendedQty) : ''}`}
                  </button>
                </div>
              </div>
            )
          }) })()}
        </div>
      )}
    </div>
  )
}
