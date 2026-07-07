import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { productMappingService } from '../../services/productMappingService'
import type { ProductSearchResult } from '../../types/productMapping'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { Money } from './shared'

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Bold the query tokens where they appear in ``text`` (safe React nodes, no
 *  dangerouslySetInnerHTML). */
function highlight(text: string, query: string): ReactNode {
  const tokens = query.trim().split(/\s+/).filter(Boolean)
  if (!tokens.length) return text
  const set = new Set(tokens.map((t) => t.toLowerCase()))
  const re = new RegExp(`(${tokens.map(escapeRegExp).join('|')})`, 'ig')
  return text.split(re).map((part, i) =>
    set.has(part.toLowerCase()) ? <mark key={i} className="pmx-hl">{part}</mark> : <span key={i}>{part}</span>,
  )
}

/** Reusable, server-side product lookup for the target store. Used by Manual
 *  Review v2 to pick a "Correct Product" when the engine's suggestion is wrong.
 *  Searches product name (brand / generic / strength / pack all live inside the
 *  name) plus product code, and shows parsed attributes for quick disambiguation. */
export function ProductSearchDialog({
  tenantId,
  targetStoreId,
  targetLabel,
  sourceName,
  onPick,
  onClose,
}: {
  tenantId: string
  targetStoreId: string
  targetLabel: string
  sourceName: string
  onPick: (product: ProductSearchResult) => void
  onClose: () => void
}) {
  const [q, setQ] = useState('')
  const debounced = useDebouncedValue(q)
  const [rows, setRows] = useState<ProductSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    const term = debounced.trim()
    if (!term || !targetStoreId) { setRows([]); return }
    let live = true
    setLoading(true)
    productMappingService
      .searchProducts(tenantId, targetStoreId, term, 30)
      .then((r) => { if (live) { setRows(r); setActive(0) } })
      .catch(() => { if (live) setRows([]) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [tenantId, targetStoreId, debounced])

  const attrs = (p: ProductSearchResult) =>
    [p.brand, p.strength && `${p.strength}${p.unit_of_strength ?? ''}`, p.dosage_form]
      .filter(Boolean).join(' · ') || '—'

  const move = (delta: number) => {
    setActive((cur) => {
      const next = Math.max(0, Math.min(rows.length - 1, cur + delta))
      const el = listRef.current?.querySelectorAll('tbody tr')[next] as HTMLElement | undefined
      el?.scrollIntoView({ block: 'nearest' })
      return next
    })
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); move(1) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
    else if (e.key === 'Enter') { e.preventDefault(); if (rows[active]) onPick(rows[active]) }
    else if (e.key === 'Tab') {
      // Focus trap: keep Tab cycling within the dialog.
      const nodes = panelRef.current?.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
      if (!nodes || nodes.length === 0) return
      const list = Array.from(nodes).filter((n) => !n.hasAttribute('disabled'))
      const first = list[0]
      const last = list[list.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
  }

  const hint = useMemo(() => {
    if (loading) return 'Searching…'
    if (!q.trim()) return 'Type a product name, brand, strength, pack, or code to search.'
    return 'No matching products in this store.'
  }, [loading, q])

  return (
    <div className="pmx-modal" role="dialog" aria-modal="true" aria-label="Find correct product" onKeyDown={onKeyDown}>
      <div className="pmx-modal__backdrop" onClick={onClose} />
      <div className="pmx-modal__panel" ref={panelRef}>
        <header className="pmx-modal__head">
          <div className="min-w-0">
            <h5 className="pmx-modal__title"><i className="bi bi-search me-2" aria-hidden="true" />Find Correct Product</h5>
            <div className="pmx-modal__sub">
              Replacing match for <b>{sourceName}</b> · in {targetLabel || 'target store'}
            </div>
          </div>
          <button type="button" className="pmx-modal__close" aria-label="Close" onClick={onClose}>
            <i className="bi bi-x-lg" aria-hidden="true" />
          </button>
        </header>

        <div className="pmx-modal__search">
          <i className="bi bi-search" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={q}
            placeholder="Search product name, brand, generic, strength, pack, or code…"
            aria-label="Search products"
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        <div className="pmx-modal__results" ref={listRef}>
          {rows.length === 0 ? (
            <div className="pmx-modal__hint">{hint}</div>
          ) : (
            <table className="sx-table">
              <thead>
                <tr>
                  <th>Product</th><th>Brand / Strength / Form</th>
                  <th className="sx-num">Pack</th><th className="sx-num">MRP</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p, i) => (
                  <tr
                    key={p.product_code}
                    className={i === active ? 'sx-row--active' : ''}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => setActive(i)}
                    onDoubleClick={() => onPick(p)}
                  >
                    <td>
                      <div className="sx-rowlabel">
                        <span className="sx-rowlabel__main">{p.product_name ? highlight(p.product_name, debounced) : '—'}</span>
                        <span className="sx-rowlabel__sub">Code {highlight(p.product_code, debounced)}</span>
                      </div>
                    </td>
                    <td><span className="sx-dim" style={{ fontSize: '0.82rem' }}>{attrs(p)}</span></td>
                    <td className="sx-num sx-dim">{p.pack_size ?? '—'}</td>
                    <td className="sx-num"><Money value={p.mrp} /></td>
                    <td className="sx-num">
                      <button type="button" className="sx-btn sx-btn--success sx-btn--sm" onClick={(e) => { e.stopPropagation(); onPick(p) }}>
                        <i className="bi bi-check2" aria-hidden="true" />Use
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <footer className="pmx-modal__foot">
          <span className="sx-dim">↑↓ to navigate · Enter to choose · Esc to close</span>
          <button type="button" className="sx-btn sx-btn--primary sx-btn--sm" disabled={!rows[active]} onClick={() => rows[active] && onPick(rows[active])}>
            Use selected product
          </button>
        </footer>
      </div>
    </div>
  )
}
