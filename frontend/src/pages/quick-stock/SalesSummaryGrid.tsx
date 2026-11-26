import './salesSummary.css'

export interface SalesSummaryRow {
  key: string
  date: string
  qty: string
  customer: string
}

/** One sales summary for Quick Stock and Stock Enquiry. Three columns only;
 *  bill number and MRP stay on the row data and open in the detail card. */
export function SalesSummaryGrid({
  ariaLabel,
  rows,
  selectedKey,
  onSelect,
}: {
  ariaLabel: string
  rows: SalesSummaryRow[]
  selectedKey: string | null
  onSelect: (key: string, anchor: HTMLElement) => void
}) {
  return (
    <div className="qs-sales" role="table" aria-label={ariaLabel}>
      <div className="qs-sales__row qs-sales__row--head" role="row">
        <span className="qs-sales__date" role="columnheader">Date</span>
        <span className="qs-sales__qty" role="columnheader">Qty</span>
        <span className="qs-sales__customer" role="columnheader">Customer</span>
      </div>
      {rows.map((row) => {
        const customer = row.customer.trim()
        const selected = selectedKey === row.key
        return (
          <button
            key={row.key}
            type="button"
            role="row"
            className={`qs-sales__row${selected ? ' qs-sales__row--selected' : ''}`}
            aria-pressed={selected}
            onClick={(event) => {
              event.stopPropagation()
              onSelect(row.key, event.currentTarget)
            }}
          >
            <span className="qs-sales__date">{row.date}</span>
            <span className="qs-sales__qty">{row.qty}</span>
            <span className="qs-sales__customer" title={customer || undefined}>{customer || '—'}</span>
          </button>
        )
      })}
    </div>
  )
}
