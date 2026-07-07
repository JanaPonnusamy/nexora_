import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import { intelligenceService } from '../../services/intelligenceService'
import { stockService } from '../../services/stockService'
import { ApiError } from '../../services/apiClient'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Refresh } from '../../types/procurement'
import type { PiDetail, PiGrid, PiRow } from '../../types/intelligence'
import type { MovementRow, PurchaseRow } from '../../types/stock'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { IntelligenceGrid } from '../../components/procurement/intelligence/IntelligenceGrid'
import { IntelligenceDetail } from '../../components/procurement/intelligence/IntelligenceDetail'
import { IntelligenceCharts } from '../../components/procurement/intelligence/IntelligenceCharts'
import { num } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'
import '../../components/procurement/intelligence/product-intelligence.css'

type Coverage = 'all' | 'purchase' | 'transfer' | 'multi'
type Banner = { kind: 'success' | 'danger'; text: string } | null

const COVERAGE: { value: Coverage; label: string }[] = [
  { value: 'all', label: 'All products' },
  { value: 'purchase', label: 'Purchase needed' },
  { value: 'transfer', label: 'Transfer opportunities' },
  { value: 'multi', label: 'Multi-store only' },
]

export default function ProductIntelligencePage() {
  const [params] = useSearchParams()
  const actingUser = useActingUser()

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState(params.get('tenant') ?? '')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [refreshes, setRefreshes] = useState<Refresh[]>([])
  const [refreshId, setRefreshId] = useState(params.get('refresh') ?? '')

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
  const [movement, setMovement] = useState<MovementRow[] | null>(null)
  const [purchases, setPurchases] = useState<PurchaseRow[] | null>(null)

  const searchRef = useRef<HTMLInputElement>(null)

  const say = useCallback((kind: 'success' | 'danger', text: string) => {
    setBanner({ kind, text })
    window.setTimeout(() => setBanner(null), 4000)
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
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  useEffect(() => {
    if (!tenantId || !storeId) { setRefreshes([]); setRefreshId(''); return }
    procurementService.refreshes(tenantId, storeId)
      .then((rows) => {
        const ready = rows.filter((r) => r.snapshot_status === 'Ready')
        setRefreshes(ready)
        setRefreshId((c) => (c && ready.some((r) => r.refresh_id === c) ? c : (ready[0]?.refresh_id ?? '')))
      })
      .catch(fail)
  }, [tenantId, storeId, fail])

  const loadGrid = useCallback(() => {
    if (!tenantId || !refreshId) { setGrid(null); return }
    setLoading(true)
    setError(null)
    setNeedsBuild(false)
    intelligenceService.grid(tenantId, refreshId)
      .then((g) => { setGrid(g); setSelectedId((c) => c ?? (g.rows[0]?.cache_id ?? null)) })
      .catch((e) => {
        setGrid(null)
        if (e instanceof ApiError && e.status === 404) setNeedsBuild(true)
        else setError(e instanceof Error ? e.message : 'Failed to load')
      })
      .finally(() => setLoading(false))
  }, [tenantId, refreshId])

  useEffect(() => { loadGrid() }, [loadGrid])

  const rebuild = async () => {
    if (!tenantId || !refreshId) return say('danger', 'Select a refresh first')
    setBuilding(true)
    try {
      const res = await intelligenceService.build(tenantId, refreshId, actingUser || null)
      say('success', `Built ${num(res.product_count)} products across ${res.store_count} stores`)
      setSelectedId(null)
      loadGrid()
    } catch (e) {
      fail(e)
    } finally {
      setBuilding(false)
    }
  }

  // Load per-product detail + trend sources when the selection changes.
  useEffect(() => {
    if (!selectedId) { setDetail(null); setMovement(null); setPurchases(null); return }
    let live = true
    setDetailLoading(true)
    setDetail(null); setMovement(null); setPurchases(null)
    intelligenceService.detail(selectedId)
      .then((d) => {
        if (!live) return
        setDetail(d)
        const anchor = grid?.build.anchor_store_id
        const code = d.product.product_code
        if (anchor && code) {
          stockService.monthlyMovement(tenantId, anchor, code, 6).then((m) => live && setMovement(m)).catch(() => live && setMovement([]))
          stockService.purchaseHistory(tenantId, anchor, code).then((p) => live && setPurchases(p)).catch(() => live && setPurchases([]))
        } else {
          setMovement([]); setPurchases([])
        }
      })
      .catch(() => live && setDetail(null))
      .finally(() => live && setDetailLoading(false))
    return () => { live = false }
  }, [selectedId, grid, tenantId])

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
      if (needle && !`${r.product_code ?? ''} ${r.product_name ?? ''}`.toLowerCase().includes(needle)) return false
      if (coverage === 'purchase' && r.consolidated_purchase_qty <= 0) return false
      if (coverage === 'transfer' && !(r.consolidated_purchase_qty === 0 && r.transfer_qty > 0)) return false
      if (coverage === 'multi' && r.mapped_store_count <= 1) return false
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
    const header = ['Product Code', 'Product Name', 'Consolidated Suggested', 'Consolidated Purchase', 'Total Stock', 'Transfer']
    cols.forEach((s) => { header.push(`${s.store_code ?? s.store_id} Suggested`, `${s.store_code ?? s.store_id} Stock`) })
    const esc = (v: unknown) => {
      const str = v == null ? '' : String(v)
      return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str
    }
    const lines = [header.map(esc).join(',')]
    for (const r of visibleRows) {
      const row: (string | number)[] = [
        r.product_code ?? '', r.product_name ?? '',
        r.consolidated_suggest_qty, r.consolidated_purchase_qty, r.consolidated_stock_qty, r.transfer_qty,
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
    a.download = `product-intelligence-${refreshId.slice(0, 8)}.csv`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
  }

  const canWork = Boolean(tenantId && refreshId)
  const summary = grid?.summary

  return (
    <div className="pm">
      <header className="pm-top">
        <div className="pm-top__ctx">
          <span className="pm-top__brand"><i className="bi bi-cpu" /> Product Intelligence</span>
          <select className="sx-select" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
          <select className="sx-select" aria-label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            <option value="">Select store…</option>
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </select>
          <select className="sx-select" aria-label="Refresh" value={refreshId} onChange={(e) => setRefreshId(e.target.value)}>
            <option value="">Select refresh…</option>
            {refreshes.map((r) => <option key={r.refresh_id} value={r.refresh_id}>{r.snapshot_name} · {r.snapshot_status}</option>)}
          </select>
        </div>
        <div className="pi-buildbar">
          {grid && <span className="pm-top__views" style={{ padding: '4px 10px', fontSize: 12 }}>Snapshot: {grid.build.generated_on ? new Date(grid.build.generated_on).toLocaleString('en-IN') : '—'}</span>}
          <button className="pm-btn pm-btn--import" disabled={!canWork || building} onClick={rebuild}>
            <i className="bi bi-cpu" /> {building ? 'Building…' : grid ? 'Rebuild' : 'Build Intelligence'}
          </button>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      {!canWork ? (
        <EmptyState icon="bi-cpu" title="Select a tenant, store and refresh" description="Product Intelligence consolidates a generated Refresh's VPL across every active store." />
      ) : needsBuild ? (
        <EmptyState
          icon="bi-cpu"
          title="No intelligence cache yet"
          description="Build the Product Intelligence cache from the selected Refresh + VPL to see the consolidated cross-store grid."
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
              <IntelligenceCharts detail={detail} movement={movement} purchases={purchases} loading={detailLoading} />
            </div>
          </div>

          {summary && (
            <div className="pm-totals">
              <span className="pm-stat"><span className="pm-stat__k">Total Products</span><b className="pm-stat__v">{num(summary.total_products)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Filtered</span><b className="pm-stat__v">{num(visibleRows.length)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Suggested Qty</span><b className="pm-stat__v">{num(summary.suggest_quantity)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Purchase Qty</span><b className="pm-stat__v pm-stat__v--warn">{num(summary.purchase_quantity)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Transfer Qty</span><b className="pm-stat__v">{num(summary.transfer_quantity)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Stock Qty</span><b className="pm-stat__v">{num(summary.stock_quantity)}</b></span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
