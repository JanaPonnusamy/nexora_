import { useContext, useEffect, useRef, useState } from 'react'
import { AuthContext } from '../../contexts/AuthContext'
import { isSuperAdmin } from '../label-export/labelExportAccess'
import { NEXTECH_MEDIQ_HOST } from './mediqHost'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { PinGate } from './PinGate'
import { BatchDrawer } from './QuickStockAllStoresDetail'
import type { BatchDrawerState, QuickStockColumnTarget } from './QuickStockAllStoresDetail'
import { QuickStockAllStoresDetail } from './QuickStockAllStoresDetail'
import { pinStorage } from './pinStorage'
import { QuickStockLinks } from './QuickStockLinks'
import { useScrollSync } from './useScrollSync'
import './quick-stock.css'
import { quickStockService } from './quickStockService'
import type { QuickStockProduct, QuickStockSearchResult, QuickStockStoreShell, QuickStockTenant } from './types'

const EMPTY: QuickStockSearchResult = { stores: [] }

function isNmwStore(storeCode: string | null | undefined) {
  return String(storeCode || '').trim().toUpperCase() === 'NMW'
}

export default function QuickStockPage() {
  const auth = useContext(AuthContext)
  const mediqSession = auth?.host === NEXTECH_MEDIQ_HOST && auth.isAuthenticated
  // NMW (warehouse) purchase/sales detail is super-admin-only; every user
  // still sees NMW's stock + MRP in the Store Grid, same as the supplier
  // stock client already shows a non-admin.
  const superAdmin = isSuperAdmin(auth?.user ?? null)
  quickStockService.useSessionBearer(mediqSession)
  const [unlocked, setUnlocked] = useState(mediqSession)
  const [tenants, setTenants] = useState<QuickStockTenant[]>([])
  const [tenantId, setTenantId] = useState('')
  // Store shells (code/name only) — fetched once per tenant so every
  // branch's fixed frame is on screen immediately, before any search runs.
  const [stores, setStores] = useState<QuickStockStoreShell[]>([])
  const [query, setQuery] = useState('')
  const [onlyStock, setOnlyStock] = useState(false)
  const [result, setResult] = useState<QuickStockSearchResult>(EMPTY)
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  // The product that drives the all-stores detail section below. Each
  // store's own target (its own product_code for this product) comes
  // straight from that store's own current search results — no network
  // round-trip needed, since `searchProducts` already searched every store.
  const [activeProductName, setActiveProductName] = useState<string | null>(null)
  const [activeTargets, setActiveTargets] = useState<QuickStockColumnTarget[]>([])
  // Replaces the old "hide purchase" checkbox: the third band shows either
  // Sales or Purchase, never both at once, sharing one row of grid space.
  const [detailMode, setDetailMode] = useState<'sales' | 'purchase'>('sales')
  const [showLinks, setShowLinks] = useState(false)
  const [batchDrawer, setBatchDrawer] = useState<BatchDrawerState | null>(null)
  const debQuery = useDebouncedValue(query, 250)
  const ticketRef = useRef(0)
  const batchTicketRef = useRef(0)
  const selectTicketRef = useRef(0)
  const autoSelectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Keeps the Store Grid band's per-store cells scrolled together — without
  // this, scrolling one store's product list desyncs its rows from every
  // other store's, breaking the "same row = same point across stores" read.
  const gridScrollRef = useScrollSync()

  // A PIN already stored from a previous visit on this device unlocks
  // silently — the page only shows the gate again once the server rejects it.
  // MediQ never reads or stores a PIN; the signed-in session is the credential.
  useEffect(() => {
    if (mediqSession) {
      pinStorage.clear()
      setUnlocked(true)
      return
    }
    if (pinStorage.get()) setUnlocked(true)
  }, [mediqSession])

  useEffect(() => {
    if (!unlocked) return
    quickStockService
      .listTenants()
      .then((rows) => {
        setTenants(rows)
        if (rows.length) setTenantId((cur) => cur || rows[0].tenant_id)
      })
      .catch(() => {
        if (!mediqSession) setUnlocked(false)
      })
  }, [unlocked, mediqSession])

  useEffect(() => {
    if (!unlocked || !tenantId) return
    quickStockService.listStores(tenantId).then(setStores).catch(() => setStores([]))
  }, [unlocked, tenantId])

  useEffect(() => {
    setActiveProductName(null)
    setActiveTargets([])
  }, [debQuery, tenantId])

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
        // Auto-open the first matched product's detail shortly after results
        // land, so the counter operator sees chart/sales data without having
        // to click anything for the common "one obvious match" search. A
        // short pause (not instant) avoids flashing a selection while the
        // operator is still mid-typing between debounced searches.
        const firstHit = data.stores.flatMap((s) => s.products.map((p) => ({ storeId: s.store_id, product: p }))).find((row) => row.product.product_code)
        if (autoSelectTimerRef.current) clearTimeout(autoSelectTimerRef.current)
        if (firstHit) {
          autoSelectTimerRef.current = setTimeout(() => {
            if (ticket !== ticketRef.current) return
            selectProduct(firstHit.storeId, firstHit.product)
          }, 450)
        }
      })
      .catch(() => {
        if (ticket !== ticketRef.current) return
        setResult(EMPTY)
        setStatus('error')
      })
    return () => {
      if (autoSelectTimerRef.current) clearTimeout(autoSelectTimerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unlocked, tenantId, debQuery, onlyStock])

  if (!mediqSession && !unlocked) {
    return <PinGate onUnlocked={() => setUnlocked(true)} />
  }

  const totalProducts = result.stores.reduce((sum, s) => sum + s.products.length, 0)
  const productsByStore = new Map<string, QuickStockProduct[]>(result.stores.map((s) => [s.store_id, s.products]))
  // Render every known branch frame always; only the rows inside change —
  // the grid of cards itself never appears/disappears based on search state.
  const frames: { store_id: string; label: string; name: string | null; products: QuickStockProduct[] }[] = stores.map((s) => ({
    store_id: s.store_id,
    label: s.store_code ?? s.store_name ?? 'Store',
    name: s.store_name ?? null,
    products: productsByStore.get(s.store_id) ?? [],
  }))
  const nmwStoreIds = new Set(frames.filter((f) => isNmwStore(f.label)).map((f) => f.store_id))

  // Grid column for each store (1-based; column 1 is the left label strip).
  const columnOf = (storeId: string) => {
    const idx = frames.findIndex((f) => f.store_id === storeId)
    return idx >= 0 ? idx + 2 : 1
  }
  const labelColumn = 1
  // Grid row for each band (1 = header, 2 = STORE GRID, 3 = chart, 4 = detail).
  const ROW_HEADER = 1
  const ROW_STORE_GRID = 2
  const rowOf = { chart: 3, detail: 4 }

  // Finds, for one specific store's current search results, the row whose
  // product_name matches the clicked product — that row's own product_code
  // is already correct for that store, with no cross-store resolution step.
  function ownMatchInStore(storeId: string, productName: string): QuickStockProduct | undefined {
    return productsByStore.get(storeId)?.find((p) => p.product_name === productName)
  }

  function selectProduct(sourceStoreId: string, product: QuickStockProduct) {
    if (!product.product_code || !product.product_name) return
    // Cancel any pending auto-select-first-hit timer -- without this, a
    // manual click on a different product could be overwritten ~450ms later
    // by the stale auto-select firing for the FIRST search hit (NMW's first
    // row), making it look like only NMW's first product could ever be
    // selected.
    if (autoSelectTimerRef.current) {
      clearTimeout(autoSelectTimerRef.current)
      autoSelectTimerRef.current = null
    }
    const selectTicket = ++selectTicketRef.current
    setActiveProductName(product.product_name)
    // Same method as the vertical Stock Availability page's onSelectProduct:
    // every store that has its own matching row for this exact product name
    // (from the SAME search response already sitting in `result`) resolves
    // and renders IMMEDIATELY, using that store's own product_code -- no
    // network round-trip, no waiting on the slower cross-store match below.
    const exact: QuickStockColumnTarget[] = frames
      .map((f) => {
        const own = ownMatchInStore(f.store_id, product.product_name!)
        return own?.product_code
          ? {
              storeId: f.store_id,
              storeLabel: f.label,
              storeName: f.name,
              productCode: own.product_code,
              productName: own.product_name,
              saleUnit: own.sale_unit,
            }
          : null
      })
      .filter((t): t is QuickStockColumnTarget => t !== null)
    setActiveTargets(exact)

    // Stores with no exact-name hit may still stock the same product under a
    // slightly different name (whitespace/brand-suffix drift) -- resolve
    // those via the real Product Mapping matcher, same as the vertical
    // page's syncSelection. Each resolved store is MERGED into the targets
    // as its own result arrives (not held back for the others), so e.g.
    // NMS/NMV appear as soon as the matcher finishes, without blocking the
    // stores that already matched exactly.
    const matchedIds = new Set(exact.map((t) => t.storeId))
    const unresolvedIds = frames.map((f) => f.store_id).filter((id) => id !== sourceStoreId && !matchedIds.has(id))
    if (!unresolvedIds.length) return
    quickStockService
      .crossStoreMatch(tenantId, sourceStoreId, product.product_code, product.product_name, unresolvedIds)
      .then(({ results }) => {
        if (selectTicket !== selectTicketRef.current) return
        const extra: QuickStockColumnTarget[] = results
          .filter((r) => r.product?.product_code)
          .map((r) => {
            const frame = frames.find((f) => f.store_id === r.store_id)
            return {
              storeId: r.store_id,
              storeLabel: frame?.label ?? r.store_id,
              storeName: frame?.name ?? null,
              productCode: r.product!.product_code,
              productName: r.product!.product_name,
            }
          })
        if (extra.length) setActiveTargets((cur) => [...cur, ...extra])
      })
      .catch(() => { /* leave unresolved stores as "Not stocked here" */ })
  }

  // Double-click on a STORE GRID row opens that SPECIFIC store's batch &
  // expiry data for that product — a dedicated on-demand fetch (not the
  // shared productCore call used by chart/detail, since the double-clicked
  // store might not be an active target yet, e.g. before any single-click).
  function openBatchForStore(storeId: string, storeLabel: string, product: QuickStockProduct) {
    if (!product.product_code || !product.product_name) return
    const ticket = ++batchTicketRef.current
    quickStockService
      .productCore(tenantId, storeId, product.product_code, 4)
      .then((core) => {
        if (ticket !== batchTicketRef.current) return
        setBatchDrawer({ storeLabel, productName: product.product_name, rows: core.batches ?? [] })
      })
      .catch(() => { /* leave the modal unopened on failure */ })
  }

  return (
    <div className="qs">
      <div className="qs-head">
        <span className="qs-head__title"><i className="bi bi-search" aria-hidden="true" />NexTech Quick Stock</span>
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
        <button type="button" className="qs-toggle-purchase" onClick={() => setShowLinks((v) => !v)}>
          <i className="bi bi-link-45deg" aria-hidden="true" /> Links
        </button>
      </div>

      {showLinks && (
        <div style={{ padding: '0.7rem 0.9rem 0' }}>
          <QuickStockLinks />
        </div>
      )}

      <div className="qs-body">
        {status === 'error' && <div className="qs-empty">Search failed. Try again.</div>}

        {activeProductName && (
          <div className="qs-active-product">
            <span>
              Showing: <strong>{activeProductName}</strong>
            </span>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <div className="qs-seg" role="group" aria-label="Sales or Purchase">
                <button
                  type="button"
                  className={`qs-seg__btn${detailMode === 'sales' ? ' qs-seg__btn--active' : ''}`}
                  onClick={() => setDetailMode('sales')}
                >
                  Sales
                </button>
                <button
                  type="button"
                  className={`qs-seg__btn${detailMode === 'purchase' ? ' qs-seg__btn--active' : ''}`}
                  onClick={() => setDetailMode('purchase')}
                >
                  Purchase
                </button>
              </div>
              <button
                type="button"
                className="qs-close-btn"
                onClick={() => { setActiveProductName(null); setActiveTargets([]) }}
              >
                ✕ Clear
              </button>
            </div>
          </div>
        )}

        {/* One shared row-band grid: store headers across the top, then
            STORE GRID / CHART / (Sales-or-Purchase) as horizontal bands
            spanning all stores, each with a left-edge label strip — every
            band's frame is always on screen, even with zero stores resolved
            yet. Batch is a double-click modal, not a band (see BatchDrawer). */}
        <div
          className="qs-scm"
          style={{
            gridTemplateColumns: `var(--qs-scm-label-w) repeat(${frames.length}, minmax(0, 1fr))`,
            gridTemplateRows: 'auto minmax(140px, 1.1fr) minmax(170px, 1.3fr) minmax(160px, 1.2fr)',
          }}
        >
          <div className="qs-corner" style={{ gridRow: ROW_HEADER, gridColumn: labelColumn }} />
          {frames.map((f, i) => (
            <div className="qs-colhead" key={f.store_id} style={{ gridRow: ROW_HEADER, gridColumn: i + 2 }}>
              <span className="qs-colhead__code">{f.label}</span>
              {f.name && f.name !== f.label && <span className="qs-colhead__name" title={f.name}>{f.name}</span>}
            </div>
          ))}

          <div className="qs-rowlabel qs-rowlabel--grid" style={{ gridRow: ROW_STORE_GRID, gridColumn: labelColumn }}>
            <span>Store Grid</span>
          </div>
          {frames.map((branch, i) => (
            <div
              className="qs-cell qs-cell--grid"
              key={branch.store_id}
              ref={gridScrollRef(branch.store_id)}
              style={{ gridRow: ROW_STORE_GRID, gridColumn: i + 2 }}
            >
              <div className="qs-branch__row qs-branch__row--head">
                <span>Product</span>
                <span>Unit</span>
                <span className="qs-num">Stock</span>
              </div>
              {branch.products.length === 0 ? (
                <div className="qs-branch__placeholder">
                  {status === 'loading' ? 'Searching…' : query.trim() ? 'No matching product' : 'Type to search'}
                </div>
              ) : (
                branch.products.map((p, pi) => {
                  const isActive = activeTargets.some((t) => t.storeId === branch.store_id && t.productCode === p.product_code)
                  return (
                    <button
                      key={`${p.product_code}-${pi}`}
                      type="button"
                      title="Click to show detail · Double-click for batch & expiry"
                      className={`qs-branch__row${isActive ? ' qs-branch__row--active' : ''}`}
                      onClick={() => selectProduct(branch.store_id, p)}
                      onDoubleClick={() => openBatchForStore(branch.store_id, branch.label, p)}
                    >
                      <span className="qs-clip">
                        <span className={`qs-dot ${(p.stock ?? 0) > 0 ? 'qs-dot--in' : 'qs-dot--out'}`} aria-hidden="true" />
                        <span className="qs-clip__text" title={p.product_name ?? undefined}>{p.product_name ?? '—'}</span>
                      </span>
                      <span className="qs-dim qs-clip__text" title={p.sale_unit ?? undefined}>{p.sale_unit ?? '—'}</span>
                      <span className="qs-num qs-clip__text" title={(p.stock ?? 0).toLocaleString('en-IN')}>{(p.stock ?? 0).toLocaleString('en-IN')}</span>
                    </button>
                  )
                })
              )}
            </div>
          ))}

          {/* CHART / (Sales-or-Purchase) bands: always-present frames; cells
              show real data once a product is selected, using each store's
              OWN product_code from the current search results — otherwise a
              calm "pick a product" placeholder — never absent, never
              unbordered. */}
          {activeProductName && activeTargets.length > 0 ? (
            <QuickStockAllStoresDetail
              tenantId={tenantId}
              targets={activeTargets}
              restrictedStoreIds={superAdmin ? undefined : nmwStoreIds}
              detailMode={detailMode}
              rowOf={rowOf}
              columnOf={columnOf}
              labelColumn={labelColumn}
            />
          ) : (
            <>
              {(['chart', 'detail'] as const).map((key) => (
                <div
                  key={key}
                  className={`qs-rowlabel qs-rowlabel--${key === 'detail' ? detailMode : 'chart'}`}
                  style={{ gridRow: rowOf[key], gridColumn: labelColumn }}
                >
                  <span>{key === 'chart' ? 'Chart' : detailMode === 'sales' ? 'Sales' : 'Purchase'}</span>
                </div>
              ))}
              {frames.map((f, i) =>
                (['chart', 'detail'] as const).map((key) => (
                  <div
                    key={`${f.store_id}-${key}`}
                    className={`qs-cell qs-cell--${key === 'detail' ? detailMode : 'chart'}`}
                    style={{ gridRow: rowOf[key], gridColumn: i + 2 }}
                  >
                    <div className="qs-panel__empty">Select a product above.</div>
                  </div>
                )),
              )}
            </>
          )}
        </div>
      </div>

      {batchDrawer && <BatchDrawer state={batchDrawer} onClose={() => setBatchDrawer(null)} />}
    </div>
  )
}
