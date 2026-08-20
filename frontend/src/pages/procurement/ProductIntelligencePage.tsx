import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { intelligenceService } from '../../services/intelligenceService'
import { ApiError } from '../../services/apiClient'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type {
  PiDetail, PiGrid, PiHistory, PiOfferRow, PiOffers, PiRow, PiSupplier,
} from '../../types/intelligence'
import { IntelligenceGrid } from '../../components/procurement/intelligence/IntelligenceGrid'
import { SupplierOfferGrid } from '../../components/procurement/intelligence/SupplierOfferGrid'
import { IntelligenceDetail } from '../../components/procurement/intelligence/IntelligenceDetail'
import { IntelligenceCharts } from '../../components/procurement/intelligence/IntelligenceCharts'
import { AssignProductDialog } from '../../components/procurement/intelligence/AssignProductDialog'
import { num } from '../../components/stock/format'
import {
  FilterAction, FilterBar, FilterBarEnd, FilterSearch, FilterSelect, FilterTabs,
} from '../../design-system/components/FilterBar'
import '../../components/procurement/purchase-manager.css'
import '../../components/procurement/intelligence/product-intelligence.css'

/**
 * Product Intelligence — the NMW Purchase Manager's central procurement cockpit.
 * The whole decision is made here, without opening another module:
 *
 *     selected stores -> Refresh every store -> Store VPL x N
 *                     -> merged on the Common Product Mapping (never ProductCode)
 *                     -> canonical product -> what NMW buys FOR THE NETWORK
 *
 * Mode 1 (Network Procurement) starts from the merged store VPLs; Mode 2
 * (Supplier Offer Intelligence) starts from a supplier's live stock file and reads
 * it against the same network intelligence, mapping unmapped lines in place.
 */

type Mode = 'network' | 'offers'
type Filter = 'all' | 'purchase' | 'critical' | 'transfer' | 'unmapped'
type Banner = { kind: 'success' | 'danger'; text: string } | null

const FILTERS: Record<Mode, { value: Filter; label: string }[]> = {
  network: [
    { value: 'all', label: 'All' },
    { value: 'purchase', label: 'To purchase' },
    { value: 'critical', label: 'Critical' },
    { value: 'transfer', label: 'Transfer only' },
  ],
  offers: [
    { value: 'all', label: 'All' },
    { value: 'purchase', label: 'Needed' },
    { value: 'unmapped', label: 'Unmapped' },
  ],
}

const offerKey = (r: PiOfferRow) => `${r.supplier_product_code ?? r.supplier_product_name}`

export default function ProductIntelligencePage() {
  const [params] = useSearchParams()
  const actingUser = useActingUser()

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState(params.get('tenant') ?? '')
  const [stores, setStores] = useState<Store[]>([])
  /** The purchasing warehouse — the store the network purchase quantity is FOR. */
  const [warehouseId, setWarehouseId] = useState(params.get('warehouse') ?? '')
  /** The stores whose VPL feeds the network decision. */
  const [selectedStores, setSelectedStores] = useState<string[]>([])
  const [storePicker, setStorePicker] = useState(false)

  const [mode, setMode] = useState<Mode>('network')
  const [grid, setGrid] = useState<PiGrid | null>(null)
  const [offers, setOffers] = useState<PiOffers | null>(null)
  const [suppliers, setSuppliers] = useState<PiSupplier[]>([])
  const [supplierCode, setSupplierCode] = useState('')

  const [busy, setBusy] = useState(false)
  const [banner, setBanner] = useState<Banner>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')

  /** The focused row: a cache_id in Mode 1, a supplier line key in Mode 2. */
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PiDetail | null>(null)
  /** The ONE store whose history + charts context is loaded. */
  const [storeId, setStoreId] = useState<string | null>(null)
  const [history, setHistory] = useState<PiHistory | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [assigning, setAssigning] = useState<PiOfferRow | null>(null)

  const searchRef = useRef<HTMLInputElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  const say = useCallback((kind: 'success' | 'danger', text: string) => {
    setBanner({ kind, text })
    window.setTimeout(() => setBanner(null), 6000)
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
      tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? ''))
    setSelectedStores(tenantStores.map((s) => s.store_id))
  }, [tenantStores])

  /* ---- Mode 1: the network grid (served from the build cache) -------------- */
  const loadGrid = useCallback(() => {
    if (!tenantId || !warehouseId) { setGrid(null); return }
    intelligenceService.grid(tenantId, warehouseId)
      .then((g) => setGrid(g))
      .catch((e) => {
        setGrid(null)
        if (!(e instanceof ApiError && e.status === 404)) fail(e)
      })
  }, [tenantId, warehouseId, fail])

  useEffect(() => { loadGrid() }, [loadGrid])

  /* ---- Mode 2: the supplier's offer, read against the network -------------- */
  useEffect(() => {
    if (!tenantId || !warehouseId) return
    intelligenceService.suppliers(tenantId, warehouseId)
      .then((r) => {
        setSuppliers(r.suppliers)
        setSupplierCode((c) => (r.suppliers.some((s) => s.supplier_code === c)
          ? c : (r.suppliers[0]?.supplier_code ?? '')))
      })
      .catch(() => setSuppliers([]))
  }, [tenantId, warehouseId])

  const loadOffers = useCallback(() => {
    if (mode !== 'offers' || !tenantId || !warehouseId || !supplierCode) { setOffers(null); return }
    intelligenceService.offers(tenantId, warehouseId, supplierCode)
      .then(setOffers)
      .catch((e) => {
        setOffers(null)
        if (!(e instanceof ApiError && e.status === 404)) fail(e)
      })
  }, [mode, tenantId, warehouseId, supplierCode, fail])

  useEffect(() => { loadOffers() }, [loadOffers])

  /** Refresh EVERY selected store, rebuild every store VPL, consolidate. */
  const refreshAndBuild = async () => {
    if (!tenantId || !warehouseId) return
    setBusy(true)
    try {
      const res = await intelligenceService.refreshBuild(
        tenantId, warehouseId, selectedStores, actingUser || null)
      const failed = res.failed?.length ?? 0
      say('success',
        `${num(res.product_count)} products from ${res.store_count} store VPLs · ` +
        `network need ${num(res.total_need_qty)} · purchase ${num(res.total_purchase_qty)}` +
        (failed ? ` · ${failed} store refresh failed` : ''))
      setSelectedId(null)
      loadGrid()
      loadOffers()
    } catch (e) {
      fail(e)
    } finally {
      setBusy(false)
    }
  }

  /* ---- Rows ---------------------------------------------------------------- */
  const networkRows = useMemo(() => {
    if (!grid) return [] as PiRow[]
    const needle = search.trim().toLowerCase()
    return grid.rows.filter((r) => {
      if (needle && !`${r.product_name ?? ''} ${r.product_code ?? ''} ${r.supplier_product_name ?? ''}`
        .toLowerCase().includes(needle)) return false
      if (filter === 'purchase' && r.consolidated_purchase_qty <= 0) return false
      if (filter === 'critical' && r.priority !== 'CRITICAL') return false
      if (filter === 'transfer' && !(r.consolidated_purchase_qty === 0 && r.transfer_qty > 0)) return false
      return true
    })
  }, [grid, search, filter])

  const offerRows = useMemo(() => {
    if (!offers) return [] as PiOfferRow[]
    const needle = search.trim().toLowerCase()
    return offers.rows.filter((r) => {
      if (needle && !`${r.supplier_product_name ?? ''} ${r.product_name ?? ''} ${r.supplier_product_code ?? ''}`
        .toLowerCase().includes(needle)) return false
      if (filter === 'purchase' && r.consolidated_purchase_qty <= 0) return false
      if (filter === 'unmapped' && r.mapped) return false
      return true
    })
  }, [offers, search, filter])

  const rowIds = useMemo(
    () => (mode === 'network' ? networkRows.map((r) => r.cache_id) : offerRows.map(offerKey)),
    [mode, networkRows, offerRows],
  )
  const storeColumns = (mode === 'network' ? grid?.stores : offers?.stores) ?? []

  useEffect(() => {
    if (rowIds.length && !rowIds.includes(selectedId ?? '')) setSelectedId(rowIds[0])
    if (!rowIds.length) setSelectedId(null)
  }, [rowIds, selectedId])

  /** The cache_id behind the focused row — a Mode 2 line has one only once mapped. */
  const cacheId = useMemo(() => {
    if (mode === 'network') return selectedId
    return offerRows.find((r) => offerKey(r) === selectedId)?.cache_id ?? null
  }, [mode, selectedId, offerRows])

  // The right panel: instant on selection, straight from the cache.
  useEffect(() => {
    if (!cacheId) { setDetail(null); return }
    let live = true
    intelligenceService.detail(cacheId)
      .then((d) => { if (!live) return; setDetail(d) })
      .catch(() => live && setDetail(null))
    return () => { live = false }
  }, [cacheId])

  // The selected store defaults to the warehouse and survives row changes.
  useEffect(() => { setStoreId((c) => c ?? warehouseId ?? null) }, [warehouseId])

  // History for the SELECTED product + SELECTED store only. Nothing else.
  useEffect(() => {
    if (!cacheId || !storeId) { setHistory(null); return }
    let live = true
    setHistoryLoading(true)
    intelligenceService.history(cacheId, storeId)
      .then((h) => live && setHistory(h))
      .catch(() => live && setHistory(null))
      .finally(() => live && setHistoryLoading(false))
    return () => { live = false }
  }, [cacheId, storeId])

  // Keyboard: ↑/↓ move the selection, Ctrl/⌘+F focuses search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault(); searchRef.current?.focus(); searchRef.current?.select(); return
      }
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'SELECT' || target.tagName === 'TEXTAREA') return
      if (!rowIds.length) return
      e.preventDefault()
      const i = rowIds.indexOf(selectedId ?? '')
      const next = e.key === 'ArrowDown'
        ? Math.min(rowIds.length - 1, i + 1)
        : Math.max(0, i - 1)
      setSelectedId(rowIds[next])
      gridRef.current
        ?.querySelector(`tr[data-cache="${CSS.escape(rowIds[next])}"]`)
        ?.scrollIntoView({ block: 'nearest' })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [rowIds, selectedId])

  const summary = mode === 'network' ? grid?.summary : null
  const warehouseName = tenantStores.find((s) => s.store_id === warehouseId)?.store_name ?? 'Warehouse'
  const storeLabel = selectedStores.length === tenantStores.length
    ? `All ${tenantStores.length} stores`
    : `${selectedStores.length} store${selectedStores.length === 1 ? '' : 's'}`

  return (
    <div className="pm pi">
      <header className="pm-top">
        <div className="pm-top__ctx">
          <span className="pm-top__brand"><i className="bi bi-cpu" /> Product Intelligence</span>
          <FilterSelect ariaLabel="Tenant" value={tenantId} onChange={setTenantId}>
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </FilterSelect>
          <FilterSelect
            ariaLabel="Purchasing warehouse"
            title="The store the network purchase quantity is calculated FOR"
            value={warehouseId}
            onChange={setWarehouseId}
          >
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>Buying for {s.store_name}</option>)}
          </FilterSelect>

          <div className="pi-storepick">
            <button type="button" className="ds-filter-select pi-storepick__btn" onClick={() => setStorePicker((v) => !v)}>
              <i className="bi bi-diagram-3" /> {storeLabel} <i className="bi bi-chevron-down" />
            </button>
            {storePicker && (
              <div className="pi-storepick__menu">
                {tenantStores.map((s) => (
                  <label key={s.store_id}>
                    <input
                      type="checkbox"
                      checked={selectedStores.includes(s.store_id)}
                      disabled={s.store_id === warehouseId}
                      onChange={(e) => setSelectedStores((cur) => e.target.checked
                        ? [...cur, s.store_id]
                        : cur.filter((id) => id !== s.store_id))}
                    />
                    {s.store_code} · {s.store_name}
                  </label>
                ))}
              </div>
            )}
          </div>

          <FilterTabs
            value={mode}
            ariaLabel="Intelligence mode"
            options={[{ value: 'network', label: 'Network' }, { value: 'offers', label: 'Supplier Offer' }]}
            onChange={(next) => { setMode(next); setFilter('all') }}
          />
        </div>

        <div className="pi-buildbar">
          {grid && (
            <span className="pi-stamp">
              {grid.stores.length} VPLs · {grid.build.generated_on
                ? new Date(grid.build.generated_on).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
                : '—'}
            </span>
          )}
          <FilterAction
            label={busy ? 'Refreshing…' : 'Refresh & Build'}
            icon="bi-arrow-repeat"
            disabled={busy || !warehouseId}
            onClick={refreshAndBuild}
          />
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      <FilterBar compact stacked ariaLabel="Product intelligence filters">
        <FilterSearch
          inputRef={searchRef}
          value={search}
          placeholder="Search product…"
          ariaLabel="Search product"
          onChange={setSearch}
        />
        <FilterTabs
          value={filter}
          ariaLabel="Product filters"
          options={FILTERS[mode]}
          onChange={setFilter}
        />
        {mode === 'offers' && (
          <FilterSelect
            ariaLabel="Supplier"
            value={supplierCode}
            onChange={setSupplierCode}
          >
            {suppliers.map((s) => (
              <option key={s.supplier_code} value={s.supplier_code}>
                {s.supplier_name ?? s.supplier_code} ({s.line_count})
              </option>
            ))}
          </FilterSelect>
        )}
        <FilterBarEnd>
          {mode === 'offers' && offers && (
            <span className="pi-stamp">
              {offers.summary.unmapped_lines} unmapped of {offers.summary.offered_lines}
            </span>
          )}
          <FilterAction
            label="Reload"
            icon="bi-arrow-clockwise"
            variant="secondary"
            onClick={mode === 'network' ? loadGrid : loadOffers}
          />
        </FilterBarEnd>
      </FilterBar>

      <div className="pi-layout">
        <div className="pi-gridwrap" ref={gridRef}>
          {mode === 'network' ? (
            <IntelligenceGrid
              rows={networkRows}
              stores={storeColumns}
              selectedId={selectedId}
              onSelect={(r) => setSelectedId(r.cache_id)}
            />
          ) : (
            <SupplierOfferGrid
              rows={offerRows}
              stores={storeColumns}
              selectedKey={selectedId}
              onSelect={(r) => setSelectedId(offerKey(r))}
              onAssign={setAssigning}
            />
          )}
        </div>

        <div className="pi-detailwrap">
          <IntelligenceDetail
            detail={detail}
            selectedStoreId={storeId}
            onSelectStore={setStoreId}
            history={history}
            historyLoading={historyLoading}
          />
        </div>

        <div className="pi-chartswrap">
          <IntelligenceCharts
            cacheId={cacheId}
            selectedStoreId={storeId}
            onSelectStore={setStoreId}
            months={4}
          />
        </div>
      </div>

      <div className="pm-totals">
        <span className="pm-stat"><span className="pm-stat__k">Rows</span><b className="pm-stat__v">{num(rowIds.length)}</b></span>
        {summary && (
          <>
            <span className="pm-stat"><span className="pm-stat__k">Products</span><b className="pm-stat__v">{num(summary.total_products)}</b></span>
            <span className="pm-stat"><span className="pm-stat__k">Store VPLs</span><b className="pm-stat__v">{num(summary.store_count)}</b></span>
            <span className="pm-stat"><span className="pm-stat__k">Network Need</span><b className="pm-stat__v">{num(summary.need_quantity)}</b></span>
            <span className="pm-stat"><span className="pm-stat__k">{warehouseName} Purchase</span><b className="pm-stat__v pm-stat__v--warn">{num(summary.purchase_quantity)}</b></span>
            <span className="pm-stat"><span className="pm-stat__k">Transfer</span><b className="pm-stat__v">{num(summary.transfer_quantity)}</b></span>
            <span className="pm-stat"><span className="pm-stat__k">Network Stock</span><b className="pm-stat__v">{num(summary.stock_quantity)}</b></span>
          </>
        )}
        {mode === 'offers' && offers && (
          <span className="pm-stat">
            <span className="pm-stat__k">Purchase from supplier</span>
            <b className="pm-stat__v pm-stat__v--warn">{num(offers.summary.purchase_quantity)}</b>
          </span>
        )}
      </div>

      {assigning && (
        <AssignProductDialog
          tenantId={tenantId}
          warehouseStoreId={warehouseId}
          warehouseName={warehouseName}
          row={assigning}
          actor={actingUser || null}
          onClose={() => setAssigning(null)}
          onSaved={(msg) => {
            setAssigning(null)
            say('success', `${msg} · rebuild to fold it into the network numbers`)
            loadOffers()
          }}
        />
      )}
    </div>
  )
}
