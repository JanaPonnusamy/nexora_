import type { SupplierRow, WorkspaceItem } from '../../types/procurement'
import type { DrawerTab } from './DetailColumn'
import { money, num } from '../stock/format'
import { supplierAbbrev } from './supplierAbbrev'

// Whole days since a date (for "90 Days" style relative Last Purchase labels).
function daysSince(d?: string | null): number | null {
  if (!d) return null
  const t = Date.parse(d)
  if (Number.isNaN(t)) return null
  return Math.max(0, Math.round((Date.now() - t) / 86_400_000))
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
  selectedCode,
  assignedCode,
  liveCodes,
  active,
  onSelect,
  onCommit,
  onOpenInfo,
}: {
  item: WorkspaceItem | null
  suppliers: SupplierRow[]
  selectedCode?: string | null
  assignedCode?: string | null
  liveCodes?: Set<string> | null
  active?: boolean
  onSelect?: (supplierCode: string) => void
  onCommit?: (item: WorkspaceItem, supplierCode: string) => void
  onOpenInfo?: (item: WorkspaceItem, tab?: DrawerTab) => void
}) {
  const recommendedQty = item ? item.remaining_qty ?? item.final_qty ?? 0 : 0
  const canAssign = Boolean(item) && item!.item_status !== 'skipped' && recommendedQty > 0
  const shown = suppliers.slice(0, 8)

  return (
    <div className={`pm-srp${active ? ' pm-srp--active' : ''}`}>
      <div className="pm-srp__title"><i className="bi bi-people" /> Supplier Recommendation</div>
      {!item ? (
        <div className="pm-srp__hint">Select a product.</div>
      ) : suppliers.length === 0 ? (
        <div className="pm-srp__hint">No purchase history for this product.</div>
      ) : (
        <div className="pm-srp__list">
          {(() => {
            const bands = costBands(shown)
            // Suppliers arrive cheapest-first (sortSuppliersByCost). The first
            // priced supplier is the cheapest → gets the green "best price" accent.
            const cheapestCode = shown.find((s) => s.last_purchase_rate != null)?.supplier_code
            return shown.map((s) => {
            const code = s.supplier_code
            const selected = selectedCode === code
            const assigned = assignedCode === code
            const cheapest = code === cheapestCode
            const live = Boolean(liveCodes?.has(code))
            const days = daysSince(s.last_grn_date)
            return (
              <div
                key={code}
                className={`pm-srpcard${selected ? ' pm-srpcard--sel' : ''}${assigned ? ' pm-srpcard--assigned' : ''}${cheapest ? ' pm-srpcard--cheapest' : ''}`}
                onClick={() => onSelect?.(code)}
                onDoubleClick={() => item && onCommit?.(item, code)}
                title={s.supplier_name ?? code}
              >
                <div className="pm-srpcard__top">
                  <span className="pm-srpcard__abbr">{supplierAbbrev(s.supplier_name, code)}</span>
                  {cheapest && <span className="pm-srpcard__best" title="Lowest cost (PTR)">BEST</span>}
                  <span className={`pm-srpcard__ptr ${bands[code] ?? ''}`}>{money(s.last_purchase_rate)}</span>
                  {live && <span className="pm-srpcard__live">LIVE</span>}
                </div>
                <div className="pm-srpcard__facts">
                  <span>Freq {num(s.purchase_frequency ?? 0)}</span>
                  <span>{days != null ? `${num(days)} Days` : 'No history'}</span>
                </div>
                <button
                  className="pm-btn pm-btn--success pm-btn--sm pm-srpcard__assign"
                  disabled={!canAssign}
                  onClick={(e) => { e.stopPropagation(); item && onCommit?.(item, code) }}
                  title={canAssign ? 'Assign the remaining quantity to this supplier' : 'Nothing left to assign'}
                >
                  {assigned ? 'Assigned' : `Assign ${recommendedQty > 0 ? num(recommendedQty) : ''}`}
                </button>
              </div>
            )
          }) })()}
        </div>
      )}

      {/* Decision Summary — compact, sits directly below the supplier list */}
      {item && (
        <div className="pm-srp__decision">
          <div className="pm-srp__dtitle"><i className="bi bi-lightbulb" /> Decision Summary</div>
          <div className="pm-srp__drow">
            <span className="pm-srp__dcell"><b>{num(item.final_qty ?? 0)}</b><span>Final</span></span>
            <span className="pm-srp__dcell"><b>{num(item.suggested_qty ?? 0)}</b><span>Suggested</span></span>
            <span className="pm-srp__dcell"><b>{item.days_cover != null ? `${item.days_cover.toFixed(0)}d` : '—'}</b><span>Cover</span></span>
          </div>
          {onOpenInfo && (
            <button className="pm-btn pm-btn--ghost pm-btn--sm pm-srp__why" onClick={() => onOpenInfo(item, 'decision')}>
              <i className="bi bi-question-circle" /> Why?
            </button>
          )}
        </div>
      )}
    </div>
  )
}
