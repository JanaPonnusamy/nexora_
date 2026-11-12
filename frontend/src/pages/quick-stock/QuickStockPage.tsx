import { useEffect, useRef, useState } from 'react'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { PinGate } from './PinGate'
import { QuickStockDetail } from './QuickStockDetail'
import type { QuickStockActiveProduct } from './QuickStockDetail'
import { pinStorage } from './pinStorage'
import './quick-stock.css'
import { quickStockService } from './quickStockService'
import type { QuickStockSearchResult, QuickStockTenant } from './types'

const EMPTY: QuickStockSearchResult = { stores: [] }

export default function QuickStockPage() {
  const [unlocked, setUnlocked] = useState(false)
  const [tenants, setTenants] = useState<QuickStockTenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [query, setQuery] = useState('')
  const [onlyStock, setOnlyStock] = useState(false)
  const [result, setResult] = useState<QuickStockSearchResult>(EMPTY)
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [active, setActive] = useState<QuickStockActiveProduct | null>(null)
  const debQuery = useDebouncedValue(query, 250)
  const ticketRef = useRef(0)

  // A PIN already stored from a previous visit on this device unlocks
  // silently — the page only shows the gate again once the server rejects it.
  useEffect(() => {
    if (pinStorage.get()) setUnlocked(true)
  }, [])

  useEffect(() => {
    if (!unlocked) return
    quickStockService
      .listTenants()
      .then((rows) => {
        setTenants(rows)
        if (rows.length) setTenantId((cur) => cur || rows[0].tenant_id)
      })
      .catch(() => setUnlocked(false))
  }, [unlocked])

  useEffect(() => {
    if (!unlocked || !tenantId) return
    if (!debQuery.trim()) {
      setResult(EMPTY)
      setStatus('idle')
      return
    }
    const ticket = ++ticketRef.current
    setStatus('loading')
    quickStockService
      .searchProducts(tenantId, debQuery.trim(), onlyStock)
      .then((data) => {
        if (ticket !== ticketRef.current) return
        setResult(data)
        setStatus('idle')
      })
      .catch(() => {
        if (ticket !== ticketRef.current) return
        setResult(EMPTY)
        setStatus('error')
      })
  }, [unlocked, tenantId, debQuery, onlyStock])

  if (!unlocked) {
    return <PinGate onUnlocked={() => setUnlocked(true)} />
  }

  const totalProducts = result.stores.reduce((sum, s) => sum + s.products.length, 0)

  return (
    <div className="qs">
      <div className="qs-head">
        <span className="qs-head__title"><i className="bi bi-search" aria-hidden="true" />Quick Stock</span>
        <div className="qs-search">
          <i className="bi bi-search" aria-hidden="true" />
          <input
            autoFocus
            value={query}
            placeholder="Search product name…"
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <label className="qs-check">
          <input type="checkbox" checked={onlyStock} onChange={(e) => setOnlyStock(e.target.checked)} /> In-stock only
        </label>
        {tenants.length > 1 && (
          <label className="qs-tenant">
            <select value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
              {tenants.map((t) => (
                <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>
              ))}
            </select>
          </label>
        )}
        <span className="qs-status">
          {status === 'loading' ? 'Searching…' : query.trim() ? `${totalProducts} matches` : ''}
        </span>
      </div>

      <div className="qs-body">
        {status === 'error' && <div className="qs-empty">Search failed. Try again.</div>}

        {status !== 'error' && !query.trim() && (
          <div className="qs-empty">Start typing a product name to see stock across all branches.</div>
        )}

        {status !== 'error' && query.trim() && result.stores.length === 0 && status !== 'loading' && (
          <div className="qs-empty">No matches.</div>
        )}

        {result.stores.length > 0 && (
          <div className="qs-branches">
            {result.stores.map((branch) => {
              const label = branch.store_code ?? branch.store_name ?? 'Store'
              return (
                <div className="qs-branch" key={branch.store_id}>
                  <div className="qs-branch__head">{label}</div>
                  <div className="qs-branch__row qs-branch__row--head">
                    <span>Product</span>
                    <span>Unit</span>
                    <span className="qs-num">Stock</span>
                  </div>
                  {branch.products.map((p, i) => {
                    const isActive = active?.storeId === branch.store_id && active?.productCode === p.product_code
                    return (
                      <button
                        key={`${p.product_code}-${i}`}
                        type="button"
                        className={`qs-branch__row${isActive ? ' qs-branch__row--active' : ''}`}
                        onClick={() =>
                          p.product_code &&
                          setActive({
                            tenantId,
                            storeId: branch.store_id,
                            storeLabel: label,
                            productCode: p.product_code,
                            productName: p.product_name,
                          })
                        }
                      >
                        <span>
                          <span className={`qs-dot ${(p.stock ?? 0) > 0 ? 'qs-dot--in' : 'qs-dot--out'}`} aria-hidden="true" />
                          {p.product_name ?? '—'}
                        </span>
                        <span className="qs-dim">{p.sale_unit ?? '—'}</span>
                        <span className="qs-num">{(p.stock ?? 0).toLocaleString('en-IN')}</span>
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>
        )}

        {active && <QuickStockDetail active={active} onClose={() => setActive(null)} />}
      </div>
    </div>
  )
}
