import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { intelligenceService } from '../../services/intelligenceService'
import { ApiError } from '../../services/apiClient'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { PiDetail, PiGrid, PiRow } from '../../types/intelligence'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { IntelligenceGrid } from '../../components/procurement/intelligence/IntelligenceGrid'
import { IntelligenceDetail } from '../../components/procurement/intelligence/IntelligenceDetail'
import { IntelligenceCharts } from '../../components/procurement/intelligence/IntelligenceCharts'
import { num } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'
import '../../components/procurement/intelligence/product-intelligence.css'

/**
 * Product Intelligence — the decision engine behind the warehouse's Purchase
 * Manager, not an analytics dashboard. Every row answers ONE question: how much
 * should the WAREHOUSE buy for the entire network?
 *
 * The build consolidates EVERY selected store's VPL (each store has its own
 * ProductCodes, sales, stock and VPL) into canonical supplier products via the
 * Common Product Mapping. The warehouse's own VPL is just one input.
 */

type Coverage = 'all' | 'purchase' | 'transfer' | 'critical' | 'multi' | 'nowh'
type Banner = { kind: 'success' | 'danger'; text: string } | null

const COVERAGE: { value: Coverage; label: string }[] = [
  { value: 'all', label: 'All products' },
  { value: 'purchase', label: 'Purchase needed' },
  { value: 'critical', label: 'Critical (a store is out)' },
  { value: 'transfer', label: 'Transfer opportunities' },
  { value: 'multi', label: 'Multi-store only' },
  { value: 'nowh', label: 'Not stocked by warehouse' },
]

export default function ProductIntelligencePage() {
  const [params] = useSearchParams()
  const actingUser = useActingUser()

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState(params.get('tenant') ?? '')
  const [stores, setStores] = useState<Store[]>([])
  /** The purchasing warehouse — the store the purchase quantity is calculated FOR. */
  const [warehouseId, setWarehouseId] = useState(params.get('warehouse') ?? '')

  const [grid, setGrid] = useState<PiGrid | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [needsBuild, setNeedsBuild] = useState(false)
  const [building, setBuilding] = useState(false)
  const [banner, setBanner] = useState<Banner>(null)

  const [search, setSearch] = useState('')
  const [coverage, setCoverage] = useState<Coverage>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const [detail, setDetail] = useState<PiDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const searchRef = useRef<HTMLInputElement>(null)

  const say = useCallback((kind: 'success' | 'danger', text: string) => {
    setBanner({ kind, text })
    window.setTimeout(() => setBanner(null), 5000)
  }, [])
  const fail = useCallback(
    (e: unknown) => say('danger', e instanceof Error ? e.message : 'Request failed'),
    [say],
  )

  useEffect(() => {
    tenantService.list()
      .then((rows) => {
        const active = rows.filter((t) => t.is_active)
        setTenants(active)
        if (active.length) setTenantId((c) => c || active[0].tenant_id)
      })
      .catch(fail)
    storeService.list().then(setStores).catch(() => setStores([]))
  }, [fail])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )
  useEffect(() => {
    setWarehouseId((cur) =>
      tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? ''),
    )
  }, [tenantStores])

  const loadGrid = useCallback(() => {
    if (!tenantId || !warehouseId) { setGrid(null); return }
    setLoading(true)
    setError(null)
    setNeedsBuild(false)
    intelligenceService.grid(tenantId, warehouseId)
      .then((g) => { setGrid(g); setSelectedId((c) => c ?? (g.rows[0]?.cache_id ?? null)) })
      .catch((e) => {
        setGrid(null)
        if (e instanceof ApiError && e.status === 404) setNeedsBuild(true)
        else setError(e instanceof Error ? e.message : 'Failed to load')
      })
      .finally(() => setLoading(false))
  }, [tenantId, warehouseId])

  useEffect(() => { loadGrid() }, [loadGrid])

  /** Consolidate every store's latest VPL into the network grid. */
  const rebuild = async () => {
    if (!tenantId || !warehouseId) return say('danger', 'Select a warehouse first')
    setBuilding(true)
    try {
      const res = await intelligenceService.build(tenantId, warehouseId, undefined, actingUser || null)
      say(
        'success',
        `Built ${num(res.product_count)} canonical products from ${res.store_count} store VPLs · ` +
        `network need ${num(res.total_need_qty)} · warehouse buys ${num(res.total_purchase_qty)}`,
      )
      setSelectedId(null)
      loadGrid()
    } catch (e) {
      fail(e)
    } finally {
      setBuilding(false)
    }
  }

  // Per-product detail. The charts panel loads its own per-store data.
  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    let live = true
    setDetailLoading(true)
    setDetail(null)
    intelligenceService.detail(selectedId)
      .then((d) => live && setDetail(d))
      .catch(() => live && setDetail(null))
      .finally(() => live && setDetailLoading(false))
    return () => { live = false }
  }, [selectedId])

  // Ctrl/⌘+F focuses search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault(); searchRef.current?.focus(); searchRef.current?.select()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const visibleRows = useMemo(() => {
    if (!grid) return [] as PiRow[]
    const needle = search.trim().toLowerCase()
    return grid.rows.filter((r) => {
      if (needle) {
        const hay = `${r.product_code ?? ''} ${r.product_name ?? ''} ${r.supplier_product_name ?? ''}`.toLowerCase()
        if (!hay.includes(needle)) return false
      }
      if (coverage === 'purchase' && r.consolidated_purchase_qty <= 0) return false
      if (coverage === 'critical' && r.priority !== 'CRITICAL') return false
      if (coverage === 'transfer' && !(r.consolidated_purchase_qty === 0 && r.transfer_qty > 0)) return false
      if (coverage === 'multi' && r.mapped_store_count <= 1) return false
      if (coverage === 'nowh' && r.warehouse_product_code) return false
      return true
    })
  }, [grid, search, coverage])

  useEffect(() => {
    if (visibleRows.length === 0) return
    if (!visibleRows.some((r) => r.cache_id === selectedId)) setSelectedId(visibleRows[0].cache_id)
  }, [visibleRows, selectedId])

  const exportCsv = () => {
    if (!grid || visibleRows.length === 0) return say('danger', 'Nothing to export')
    const cols = grid.stores
    const header = [
      'Product', 'Supplier Code', 'Supplier Product Code', 'Warehouse Code', 'Mapped Stores',
      'Global Suggested', 'Warehouse Purchase', 'Transfer', 'Global Stock',
      'Total Sales', 'Total Purchase', 'Priority', 'Confidence',
    ]
    cols.forEach((s) => { header.push(`${s.store_code ?? s.store_id} Suggested`, `${s.store_code ?? s.store_id} Stock`) })
    const esc = (v: unknown) => {
      const str = v == null ? '' : String(v)
      return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str
    }
    const lines = [header.map(esc).join(',')]
    for (const r of visibleRows) {
      const row: (string | number)[] = [
        r.product_name ?? '', r.supplier_code ?? '', r.supplier_product_code ?? '',
        r.warehouse_product_code ?? '', r.mapped_store_count,
        r.consolidated_suggest_qty, r.consolidated_purchase_qty, r.transfer_qty, r.consolidated_stock_qty,
        r.total_sales_qty ?? 0, r.total_purchase_qty ?? 0, r.priority ?? '', r.confidence ?? '',
      ]
      for (const s of cols) {
        const cell = r.stores[s.store_id]
        row.push(cell ? cell.suggested_qty ?? 0 : '', cell ? cell.stock_qty ?? 0 : '')
      }
      lines.push(row.map(esc).join(','))
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `network-intelligence-${(grid.build.build_id ?? '').slice(0, 8)}.csv`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
  }

  const canWork = Boolean(tenantId && warehouseId)
  const summary = grid?.summary
  const warehouseName = tenantStores.find((s) => s.store_id === warehouseId)?.store_name ?? 'the warehouse'

  return (
    <div className="pm">
      <header className="pm-top">
        <div className="pm-top__ctx">
          <span className="pm-top__brand"><i className="bi bi-cpu" /> Product Intelligence</span>
          <select className="sx-select" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
          <select
            className="sx-select"
            aria-label="Purchasing warehouse"
            title="The store the network purchase quantity is calculated FOR"
            value={warehouseId}
            onChange={(e) => setWarehouseId(e.target.value)}
          >
            <option value="">Select warehouse…</option>
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>Buying for: {s.store_name}</option>)}
          </select>
        </div>
        <div className="pi-buildbar">
          {grid && (
            <span className="pm-top__views" style={{ padding: '4px 10px', fontSize: 12 }}>
              {grid.stores.length} store VPLs · {grid.build.generated_on ? new Date(grid.build.generated_on).toLocaleString('en-IN') : '—'}
            </span>
          )}
          <button className="pm-btn pm-btn--import" disabled={!canWork || building} onClick={rebuild}>
            <i className="bi bi-cpu" /> {building ? 'Consolidating…' : grid ? 'Rebuild' : 'Build Intelligence'}
          </button>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      {!canWork ? (
        <EmptyState icon="bi-cpu" title="Select a tenant and warehouse" description="Product Intelligence merges every store's VPL and calculates what the warehouse must buy for the whole network." />
      ) : needsBuild ? (
        <EmptyState
          icon="bi-cpu"
          title="No network build yet"
          description={`Build the intelligence to merge every store's latest VPL and calculate what ${warehouseName} must purchase for the network.`}
        />
      ) : error ? (
        <ErrorState description={error} onRetry={loadGrid} />
      ) : (
        <>
          <div className="pm-toolbar">
            <span className="sx-search">
              <i className="bi bi-search" aria-hidden="true" />
              <input ref={searchRef} type="search" value={search} placeholder="Search product…" aria-label="Search product" onChange={(e) => setSearch(e.target.value)} />
            </span>
            <select className="sx-select" aria-label="Coverage filter" value={coverage} onChange={(e) => setCoverage(e.target.value as Coverage)}>
              {COVERAGE.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <span className="pi-legend">
              <span><i style={{ background: '#4338ca' }} />Suggested</span>
              <span><i style={{ background: '#64748b' }} />Current Stock</span>
              <span><i style={{ background: '#fef3c7', border: '1px solid #fde68a' }} />Transfer</span>
            </span>
            <div className="pm-toolbar__right">
              <button className="pm-btn pm-btn--ghost" onClick={exportCsv}><i className="bi bi-download" /> Export</button>
              <button className="pm-btn pm-btn--ghost" onClick={loadGrid} title="Reload"><i className="bi bi-arrow-repeat" /></button>
            </div>
          </div>

          <div className="pi-layout">
            <div className="pi-gridwrap">
              {loading ? (
                <div className="pi-chart__empty" style={{ height: '100%' }}>Loading grid…</div>
              ) : visibleRows.length === 0 ? (
                <EmptyState icon="bi-inbox" title="No products" description="No products match the current filters." />
              ) : (
                <IntelligenceGrid
                  rows={visibleRows}
                  stores={grid!.stores}
                  selectedId={selectedId}
                  onSelect={(r) => setSelectedId(r.cache_id)}
                />
              )}
            </div>
            <div className="pi-detailwrap">
              <IntelligenceDetail detail={detail} loading={detailLoading} />
            </div>
            <div className="pi-chartswrap">
              <IntelligenceCharts
                cacheId={selectedId}
                productName={detail?.product.product_name ?? null}
                months={4}
              />
            </div>
          </div>

          {summary && (
            <div className="pm-totals">
              <span className="pm-stat"><span className="pm-stat__k">Canonical Products</span><b className="pm-stat__v">{num(summary.total_products)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Filtered</span><b className="pm-stat__v">{num(visibleRows.length)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Store VPLs</span><b className="pm-stat__v">{num(summary.store_count)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Network Need</span><b className="pm-stat__v">{num(summary.need_quantity)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Warehouse Purchase</span><b className="pm-stat__v pm-stat__v--warn">{num(summary.purchase_quantity)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Transfer Qty</span><b className="pm-stat__v">{num(summary.transfer_quantity)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Network Stock</span><b className="pm-stat__v">{num(summary.stock_quantity)}</b></span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
