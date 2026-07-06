import { useEffect, useState } from 'react'
import type { ManualProduct } from '../../types/procurement'
import { procurementService } from '../../services/procurementService'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { money, num } from '../stock/format'

/** Add Manual Product — searches the real Product Master (sync.Products, NOT the
 *  VPL). Added products then behave exactly like VPL working items. */
export function ManualProductModal({
  tenantId,
  storeId,
  onAdd,
  onClose,
  busy,
}: {
  tenantId: string
  storeId: string
  onAdd: (product: ManualProduct, qty: number) => void
  onClose: () => void
  busy: boolean
}) {
  const [q, setQ] = useState('')
  const debounced = useDebouncedValue(q)
  const [rows, setRows] = useState<ManualProduct[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<ManualProduct | null>(null)
  const [qty, setQty] = useState('1')

  useEffect(() => {
    const term = debounced.trim()
    if (!term || !storeId) {
      setRows([])
      return
    }
    let live = true
    setLoading(true)
    procurementService
      .searchProducts(tenantId, storeId, term)
      .then((r) => live && setRows(r))
      .catch(() => live && setRows([]))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [tenantId, storeId, debounced])

  const submit = () => {
    const n = Number(qty)
    if (!selected || Number.isNaN(n) || n <= 0) return
    onAdd(selected, n)
  }

  return (
    <>
      <div className="pm-drawer__backdrop" onClick={onClose} />
      <div className="pm-modal" role="dialog" aria-label="Add manual product">
        <header className="pm-modal__head">
          <h5 className="mb-0"><i className="bi bi-plus-square me-2" />Add Manual Product</h5>
          <button className="btn-close" aria-label="Close" onClick={onClose} />
        </header>
        <div className="pm-modal__body">
          <span className="sx-search mb-2 d-flex">
            <i className="bi bi-search" aria-hidden="true" />
            <input
              autoFocus
              type="search"
              value={q}
              placeholder="Search product name or code…"
              aria-label="Search product master"
              onChange={(e) => setQ(e.target.value)}
            />
          </span>

          <div className="pm-modal__results">
            {loading ? (
              <div className="pm-queue__hint">Searching…</div>
            ) : rows.length === 0 ? (
              <div className="pm-queue__hint">{q.trim() ? 'No products found.' : 'Type to search the product master.'}</div>
            ) : (
              <table className="sx-table">
                <thead>
                  <tr><th>Product</th><th>Unit</th><th className="sx-num">Stock</th><th className="sx-num">MRP</th></tr>
                </thead>
                <tbody>
                  {rows.map((p) => (
                    <tr
                      key={p.product_code}
                      className={`sa-rowsel${selected?.product_code === p.product_code ? ' sa-rowsel--on' : ''}`}
                      onClick={() => setSelected(p)}
                    >
                      <td>
                        <div>{p.product_name ?? '—'}</div>
                        <div className="pm-prod__meta">{p.product_code}</div>
                      </td>
                      <td className="sx-dim">{p.unit ?? '—'}</td>
                      <td className="sx-num">{num(p.current_stock ?? 0)}</td>
                      <td className="sx-num">{money(p.mrp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
        <footer className="pm-modal__foot">
          <div className="pm-modal__sel">
            {selected ? <>Selected: <b>{selected.product_name ?? selected.product_code}</b></> : 'Select a product'}
          </div>
          <label className="pm-modal__qty">
            Qty
            <input
              className="pm-qty"
              inputMode="numeric"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
            />
          </label>
          <button className="pm-btn pm-btn--primary" onClick={submit} disabled={!selected || busy}>
            <i className="bi bi-plus-lg" /> {busy ? 'Adding…' : 'Add to Working Set'}
          </button>
        </footer>
      </div>
    </>
  )
}
