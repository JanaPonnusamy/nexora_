import { useRef } from 'react'
import type { SupplierStockRow } from '../../types/procurement'
import { num, date } from '../stock/format'
import { EmptyState } from '../common/EmptyState'

/** Stable row key: supplier product code, falling back to the mapped code. */
export const stockRowKey = (r: SupplierStockRow) => r.supplier_product_code ?? r.product_code ?? ''

/** Supplier Live Stock. Shows the supplier's live stock file (supplier_stock)
 *  already resolved to store ProductCodes via SupplierProductMatch and
 *  intersected with the current VPL. Selection + order qty are owned by the page
 *  so the persistent Product Details panel stays in sync with the focused row. */
export function SupplierStockTable({
  rows,
  loading,
  error,
  onOrder,
  busy,
  storeStockByCode,
  statusByCode,
  selectedKey,
  onSelect,
  draft,
  onDraftChange,
}: {
  rows: SupplierStockRow[]
  loading: boolean
  error: string | null
  onOrder: (row: SupplierStockRow, qty: number) => void
  busy: boolean
  /** Current store stock keyed by mapped store ProductCode (from the workspace
   *  items already loaded for this refresh — no extra fetch). */
  storeStockByCode: Map<string, number>
  /** Assigned / Skipped state keyed by mapped ProductCode (nothing shown for
   *  rows still in the Review workflow). */
  statusByCode: Map<string, 'assigned' | 'skipped'>
  selectedKey: string | null
  onSelect: (row: SupplierStockRow) => void
  draft: Record<string, string>
  onDraftChange: (key: string, value: string) => void
}) {
  // Order-qty inputs, keyed by row, so Enter can advance focus to the next row.
  const inputs = useRef<Record<string, HTMLInputElement | null>>({})

  if (loading) return <div className="pm-queue__hint">Loading supplier live stock…</div>
  if (error) {
    return <EmptyState icon="bi-cloud-slash" title="Supplier stock unavailable" description={error} />
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        icon="bi-inboxes"
        title="No matched stock"
        description="Import supplier stock and map SupplierProductMatch, then reopen this supplier to see products available in the current VPL."
      />
    )
  }

  const add = (r: SupplierStockRow) => {
    const n = Number(draft[stockRowKey(r)])
    if (!Number.isNaN(n) && n > 0) onOrder(r, n)
  }

  return (
    <table className="pm-grid pm-grid--stock">
      <thead>
        <tr>
          <th>Supplier Product</th>
          <th>Mapped Product</th>
          <th className="sx-num">Supplier Stock</th>
          <th className="sx-num">Store Stock</th>
          <th className="sx-num">Sugg.</th>
          <th className="sx-num">Disc%</th>
          <th className="sx-num">Free</th>
          <th>Scheme</th>
          <th className="sx-num">Last Sync</th>
          <th>Status</th>
          <th className="sx-num pm-grid__final">Order Qty</th>
          <th className="pm-grid__act" />
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const key = stockRowKey(r)
          const storeStock = r.product_code != null ? storeStockByCode.get(r.product_code) : undefined
          const status = r.product_code != null ? statusByCode.get(r.product_code) : undefined
          return (
            <tr
              key={key}
              className={key === selectedKey ? 'pm-row--sel' : undefined}
              onClick={() => onSelect(r)}
            >
              <td>
                <div className="pm-prod__name">{r.supplier_product_name ?? '—'}</div>
                <div className="pm-prod__meta">{r.supplier_product_code}</div>
              </td>
              <td>
                <div className="pm-prod__name">{r.product_name ?? '—'}</div>
                <div className="pm-prod__meta">{r.product_code ?? '—'}</div>
              </td>
              <td className="sx-num pm-sx__supp">{num(r.available_stock ?? 0)}</td>
              <td className="sx-num pm-sx__store">{storeStock != null ? num(storeStock) : '—'}</td>
              <td className="sx-num sx-dim">{num(r.suggested_qty ?? 0)}</td>
              <td className="sx-num">{r.discount != null ? `${num(r.discount)}%` : '—'}</td>
              <td className="sx-num">{num(r.free ?? 0)}</td>
              <td className="sx-dim">{r.scheme ?? '—'}</td>
              <td className="sx-num sx-dim">{date(r.transaction_date)}</td>
              <td>
                {status && (
                  <span className={`pm-sxchip pm-sxchip--${status}`}>
                    {status === 'assigned' ? 'Assigned' : 'Skipped'}
                  </span>
                )}
              </td>
              <td className="sx-num pm-grid__final">
                <input
                  ref={(el) => { inputs.current[key] = el }}
                  className="pm-qty pm-qty--sm"
                  inputMode="numeric"
                  value={draft[key] ?? ''}
                  onFocus={(e) => { onSelect(r); e.currentTarget.select() }}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => onDraftChange(key, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== 'Enter') return
                    e.preventDefault()
                    add(r)
                    const next = rows[i + 1]
                    if (next) inputs.current[stockRowKey(next)]?.focus()
                  }}
                />
              </td>
              <td className="pm-grid__act">
                <button
                  className="pm-btn pm-btn--add"
                  disabled={busy}
                  onClick={(e) => { e.stopPropagation(); add(r) }}
                  title="Add to order"
                >
                  <i className="bi bi-plus-lg" /> Add
                </button>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
