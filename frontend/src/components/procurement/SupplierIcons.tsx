import type { SupplierRow } from '../../types/procurement'
import { money, num, date } from '../stock/format'
import { supplierAbbrev } from './supplierAbbrev'

/**
 * Compact supplier recommendation cell for the Product Grid — up to five ranked
 * supplier *abbreviation chips* (NMA, BP, …) in rank order. Single click
 * *selects* the supplier (highlights the chip, the caller updates the Cost
 * column); double click *commits* the assignment. Hover shows the supplier
 * facts. No popup, no new business rules — the ranking comes straight from
 * purchase history.
 */
export function SupplierIcons({
  suppliers,
  recommendedQty,
  selectedCode,
  assignedCode,
  liveCodes,
  disabled = false,
  onSelect,
  onCommit,
}: {
  suppliers: SupplierRow[]
  recommendedQty: number
  selectedCode?: string | null
  assignedCode?: string | null
  liveCodes?: Set<string> | null
  disabled?: boolean
  onSelect: (supplierCode: string) => void
  onCommit: (supplierCode: string) => void
}) {
  if (!suppliers || suppliers.length === 0) {
    return <span className="pm-supicons__empty" title="No purchase history">—</span>
  }

  return (
    <div className="pm-supicons" onClick={(e) => e.stopPropagation()}>
      {suppliers.slice(0, 5).map((s) => {
        const code = s.supplier_code
        const selected = selectedCode === code
        const assigned = assignedCode === code
        const live = Boolean(liveCodes?.has(code))
        const cls =
          'pm-supicon' +
          (assigned ? ' pm-supicon--assigned' : selected ? ' pm-supicon--selected' : '') +
          (live ? ' pm-supicon--live' : '')
        return (
          <button
            key={code}
            type="button"
            className={cls}
            disabled={disabled}
            aria-label={`Supplier ${s.supplier_name ?? code}`}
            aria-pressed={selected || assigned}
            onClick={() => !disabled && onSelect(code)}
            onDoubleClick={() => !disabled && onCommit(code)}
          >
            <span className="pm-supicon__abbr">{supplierAbbrev(s.supplier_name, code)}</span>
            {assigned && <i className="bi bi-check-lg pm-supicon__badge" aria-hidden="true" />}
            {live && !assigned && <span className="pm-supicon__dot" aria-hidden="true" />}
            <span className="pm-supicon__tip" role="tooltip">
              <span className="pm-supicon__tipname">
                {s.supplier_name ?? code}
                {live && <span className="pm-supicon__tiplive">LIVE</span>}
              </span>
              <span className="pm-supicon__tiprow"><b>PTR</b>{money(s.last_purchase_rate)}</span>
              <span className="pm-supicon__tiprow"><b>Last Buy</b>{date(s.last_grn_date)}</span>
              <span className="pm-supicon__tiprow"><b>Frequency</b>{num(s.purchase_frequency ?? 0)}</span>
              <span className="pm-supicon__tiprow"><b>Rec. Qty</b>{num(recommendedQty)}</span>
              <span className="pm-supicon__tiphint">
                {assigned ? 'Assigned' : 'Click = select · Double-click = assign'}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
