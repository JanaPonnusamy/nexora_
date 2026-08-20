import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { ManualProduct } from '../../types/procurement'
import { procurementService } from '../../services/procurementService'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useListNav } from '../../hooks/useListNav'
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
  // Same index/auto-scroll mechanics as SupplierPicker's search dropdown —
  // shared via useListNav so this keyboard behavior isn't a second copy.
  const nav = useListNav(rows.length)
  const qtyRef = useRef<HTMLInputElement>(null)

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
      .then((r) => {
        if (!live) return
        setRows(r)
        nav.reset() // auto-highlight the first result
      })
      .catch(() => live && setRows([]))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, storeId, debounced])

  const submit = () => {
    // `busy` disables the footer button, but the Qty field's Enter handler
    // below bypasses that disabled state — without this check, keyboard
    // auto-repeat (holding Enter) or a fast double-Enter fires a second
    // onAdd/POST before the first request's busy flag can re-render in.
    if (busy) return
    const n = Number(qty)
    if (!selected || Number.isNaN(n) || n <= 0) return
    onAdd(selected, n)
  }

  // Selecting a result moves straight to the Qty field — the search →
  // navigate → pick → quantify → submit flow needs no mouse at any step.
  const pick = (p: ManualProduct) => {
    setSelected(p)
    qtyRef.current?.focus()
    qtyRef.current?.select()
  }

  const onSearchKey = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      nav.reset() // clear the highlight only — Close/backdrop still dismiss the modal
      return
    }
    if (e.key === 'Tab' && !e.shiftKey && rows.length > 0) {
      // Accept the highlighted result before leaving; the browser still moves
      // focus to the next control (the Qty field, already next in DOM order).
      pick(rows[nav.active])
      return
    }
    if (rows.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); nav.moveNext() }
    else if (e.key === 'ArrowUp') { e.preventDefault(); nav.movePrev() }
    else if (e.key === 'Enter') { e.preventDefault(); pick(rows[nav.active]) }
  }

  const onQtyKey = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); submit() }
  }

  const stepQty = (amount: number) => {
    const current = Number(qty)
    setQty(String(Math.max(1, (Number.isFinite(current) ? current : 1) + amount)))
  }

  return (
    <>
      <div className="pm-drawer__backdrop" onClick={onClose} />
      <div className="pm-modal pm-modal--manual" role="dialog" aria-modal="true" aria-labelledby="pm-manual-title">
        <header className="pm-modal__head">
          <div className="pm-manual__heading">
            <span>Product master</span>
            <h2 id="pm-manual-title">Add a product</h2>
            <p>Find an item and add the required quantity to this refresh.</p>
          </div>
          <button className="pm-manual__close" type="button" aria-label="Close dialog" onClick={onClose}>
            <i className="bi bi-x-lg" aria-hidden="true" />
          </button>
        </header>
        <div className="pm-modal__body">
          <label className="pm-manual__search-label" htmlFor="pm-manual-search">Find a product</label>
          <span className="sx-search pm-manual__search">
            <i className="bi bi-search" aria-hidden="true" />
            <input
              id="pm-manual-search"
              autoFocus
              type="search"
              value={q}
              placeholder="Search by product name or code"
              aria-label="Search product master"
              role="combobox"
              aria-expanded={rows.length > 0}
              aria-controls="pm-manual-results"
              aria-activedescendant={rows.length > 0 ? `pm-manual-opt-${nav.active}` : undefined}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={onSearchKey}
            />
            <kbd>Enter</kbd>
          </span>

          <div className="pm-modal__results">
            {loading ? (
              <div className="pm-manual__state">
                <i className="bi bi-arrow-repeat pm-manual__spinner" aria-hidden="true" />
                <b>Searching product master…</b>
                <span>This will only take a moment.</span>
              </div>
            ) : rows.length === 0 ? (
              <div className="pm-manual__state">
                <i className={`bi ${q.trim() ? 'bi-search' : 'bi-box-seam'}`} aria-hidden="true" />
                <b>{q.trim() ? 'No matching products' : 'Search the product master'}</b>
                <span>{q.trim() ? 'Try another product name or code.' : 'Start typing above to find a product to add.'}</span>
              </div>
            ) : (
              <table className="sx-table">
                <thead>
                  <tr><th>Product</th><th>Unit</th><th className="sx-num">Stock</th><th className="sx-num">MRP</th></tr>
                </thead>
                <tbody id="pm-manual-results" role="listbox">
                  {rows.map((p, i) => (
                    <tr
                      key={p.product_code}
                      id={`pm-manual-opt-${i}`}
                      role="option"
                      aria-selected={i === nav.active}
                      ref={nav.itemRef(i)}
                      className={`sa-rowsel${selected?.product_code === p.product_code ? ' sa-rowsel--on' : ''}${i === nav.active ? ' sa-rowsel--active' : ''}`}
                      onMouseEnter={() => nav.setActive(i)}
                      onClick={() => pick(p)}
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
            <span className={`pm-manual__selected-icon${selected ? ' is-selected' : ''}`}>
              <i className={`bi ${selected ? 'bi-check-lg' : 'bi-box'}`} aria-hidden="true" />
            </span>
            <span>
              <small>{selected ? 'Selected product' : 'No product selected'}</small>
              <b>{selected ? selected.product_name ?? selected.product_code : 'Choose a product from the results'}</b>
              {selected && selected.product_name && <em>{selected.product_code}</em>}
            </span>
          </div>
          <div className="pm-modal__qty">
            <span>Quantity</span>
            <div className="pm-manual__stepper">
              <button type="button" aria-label="Decrease quantity" onClick={() => stepQty(-1)} disabled={Number(qty) <= 1}>−</button>
              <input
                ref={qtyRef}
                className="pm-qty"
                inputMode="numeric"
                aria-label="Quantity"
                value={qty}
                onFocus={(e) => e.currentTarget.select()}
                onChange={(e) => setQty(e.target.value)}
                onKeyDown={onQtyKey}
              />
              <button type="button" aria-label="Increase quantity" onClick={() => stepQty(1)}>+</button>
            </div>
          </div>
          <button className="pm-btn pm-btn--primary" onClick={submit} disabled={!selected || busy}>
            <i className={`bi ${busy ? 'bi-arrow-repeat pm-manual__spinner' : 'bi-plus-lg'}`} aria-hidden="true" />
            {busy ? 'Adding product…' : 'Add product'}
          </button>
        </footer>
      </div>
    </>
  )
}
