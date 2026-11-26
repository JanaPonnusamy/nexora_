import { Fragment, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { syncService } from '../../services/syncService'
import { stockCheckReportService } from '../../services/stockCheckReportService'
import { exportStockCheckExcel } from './exportStockCheckExcel'
import { SublocationPicker } from './SublocationPicker'
import { groupStockCheckRows, isExpired } from './stockCheckGrouping'
import type { Tenant } from '../../types/tenant'
import type { TenantStore } from '../../types/store'
import type { StockCheckFilters, StockCheckRow, StockCheckSupplierOption } from '../../types/stockCheckReport'
import { EMPTY_STOCK_CHECK_FILTERS } from '../../types/stockCheckReport'
import { FilterBar } from '../../design-system/components/FilterBar'
import { KpiBar, StatCard } from '../../design-system/components/StatCard'

const POLL_MS = 2000
const SYNC_MAX_MS = 5 * 60 * 1000

function terminal(status?: string | null): 'ok' | 'fail' | null {
  if (!status) return null
  const s = status.toUpperCase()
  if (s === 'COMPLETED' || s === 'SUCCESS') return 'ok'
  if (s === 'FAILED' || s === 'ERROR' || s === 'CANCELLED') return 'fail'
  return null
}

function countActiveFilters(f: StockCheckFilters): number {
  let n = 0
  if (f.sublocationFrom || f.sublocationTo) n += 1
  if (f.productCodeFrom || f.productCodeTo) n += 1
  if (f.productName) n += 1
  if (f.supplierCode) n += 1
  if (f.unitDescription) n += 1
  if (f.batchCode) n += 1
  if (f.expiryFrom || f.expiryTo) n += 1
  if (f.minStock || f.maxStock) n += 1
  if (f.includeZeroStock) n += 1
  if (f.includeNegativeStock) n += 1
  return n
}

export default function StockCheckReportPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<TenantStore[]>([])
  const [storeId, setStoreId] = useState('')

  const [filters, setFilters] = useState<StockCheckFilters>(EMPTY_STOCK_CHECK_FILTERS)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [suppliers, setSuppliers] = useState<StockCheckSupplierOption[]>([])
  const [units, setUnits] = useState<string[]>([])

  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState<string | null>(null)
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<StockCheckRow[] | null>(null)

  function setFilter<K extends keyof StockCheckFilters>(key: K, value: StockCheckFilters[K]) {
    setFilters((cur) => ({ ...cur, [key]: value }))
  }

  useEffect(() => {
    tenantService
      .list()
      .then((list) => {
        const active = list.filter((t) => t.is_active)
        setTenants(active)
        if (active.length) setTenantId((cur) => cur || active[0].tenant_id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load tenants'))
  }, [])

  useEffect(() => {
    if (!tenantId) return
    setStoreId('')
    storeService
      .getActiveByTenant(tenantId)
      .then((list) => {
        setStores(list)
        if (list.length) setStoreId((cur) => cur || list[0].store_id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load stores'))
  }, [tenantId])

  // Supplier/unit option lists for the current store — reloaded whenever the
  // store changes, independent of the result grid.
  useEffect(() => {
    if (!tenantId || !storeId) {
      setSuppliers([])
      setUnits([])
      return
    }
    let live = true
    stockCheckReportService
      .listSuppliers(tenantId, storeId)
      .then((r) => { if (live) setSuppliers(r.suppliers) })
      .catch(() => { if (live) setSuppliers([]) })
    stockCheckReportService
      .listUnits(tenantId, storeId)
      .then((r) => { if (live) setUnits(r.units) })
      .catch(() => { if (live) setUnits([]) })
    return () => {
      live = false
    }
  }, [tenantId, storeId])

  const storeCode = stores.find((s) => s.store_id === storeId)?.store_code ?? storeId
  const tenantName = tenants.find((t) => t.tenant_id === tenantId)?.tenant_name ?? ''

  async function runSync() {
    if (!tenantId || !storeId) return
    setSyncing(true)
    setSyncMessage('Starting sync…')
    setError(null)
    try {
      const { task_id } = await syncService.createTask({
        tenant_id: tenantId,
        store_id: storeId,
        execution_type: 'FULL',
        sync_mode: 'FULL',
      })
      const start = Date.now()
      while (true) {
        await new Promise((r) => setTimeout(r, POLL_MS))
        const sum = await syncService.executionSummary(task_id)
        const total = sum.total_tables ?? 0
        const done = sum.completed_tables ?? 0
        setSyncMessage(total > 0 ? `Syncing… ${done}/${total} tables` : 'Syncing…')
        const t = terminal(sum.status)
        if (t === 'ok') {
          setSyncMessage('Sync complete')
          setLastSyncedAt(new Date())
          break
        }
        if (t === 'fail') {
          throw new Error('Sync failed')
        }
        if (Date.now() - start > SYNC_MAX_MS) {
          throw new Error('Sync did not finish in time')
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed')
      setSyncMessage(null)
    } finally {
      setSyncing(false)
    }
  }

  async function preview() {
    if (!tenantId || !storeId) return
    setLoading(true)
    setError(null)
    try {
      const result = await stockCheckReportService.getRows(tenantId, storeId, filters)
      setRows(result.rows)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report')
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  async function exportExcel() {
    if (!rows || rows.length === 0) return
    await exportStockCheckExcel({
      rows,
      storeCode,
      sublocationFrom: filters.sublocationFrom.trim(),
      sublocationTo: filters.sublocationTo.trim(),
    })
  }

  function clearAll() {
    setFilters(EMPTY_STOCK_CHECK_FILTERS)
  }

  const groups = useMemo(() => groupStockCheckRows(rows ?? []), [rows])
  const activeFilterCount = countActiveFilters(filters)

  const kpis = useMemo(() => {
    if (!rows) return null
    const products = new Set(rows.map((r) => r.product_code ?? '')).size
    const expected = rows.reduce((sum, r) => sum + (r.total_stock ?? 0), 0)
    const counted = rows.reduce((sum, r) => sum + (r.batch_stock ?? 0), 0)
    return { products, expected, counted, variance: counted - expected }
  }, [rows])

  return (
    <div className="d-flex flex-column gap-3">
      <PageHeader
        title="Stock Check"
        breadcrumb={['Operations', 'Inventory', 'Stock Check']}
        description="Physical Inventory & Stock Reconciliation"
      />

      <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 small text-muted">
        <span>
          <strong>{tenantName || 'Tenant'}</strong> · <strong>{storeCode || 'Store'}</strong>
          {lastSyncedAt && <> · Last sync {lastSyncedAt.toLocaleTimeString()}</>}
        </span>
        <div className="d-flex gap-2">
          <button className="btn btn-outline-secondary btn-sm" disabled={!storeId || syncing} onClick={() => void runSync()}>
            <i className="bi bi-arrow-repeat me-1" />
            {syncing ? 'Syncing…' : 'Sync Now'}
          </button>
          <button className="btn btn-primary btn-sm" disabled={!storeId || loading} onClick={() => void preview()}>
            <i className="bi bi-eye me-1" />
            {loading ? 'Loading…' : 'Preview'}
          </button>
          <button className="btn btn-success btn-sm" disabled={!rows || rows.length === 0} onClick={() => void exportExcel()}>
            <i className="bi bi-file-earmark-excel me-1" />
            Export Excel
          </button>
        </div>
      </div>

      <KpiBar>
        <StatCard
          label="Total Products"
          value={kpis ? kpis.products.toLocaleString() : '—'}
          icon="bi-boxes"
          loading={loading}
        />
        <StatCard
          label="Expected Stock"
          value={kpis ? kpis.expected.toLocaleString() : '—'}
          icon="bi-clipboard-data"
          tone="primary"
          loading={loading}
        />
        <StatCard
          label="Counted Stock"
          value={kpis ? kpis.counted.toLocaleString() : '—'}
          icon="bi-check2-square"
          tone="success"
          loading={loading}
        />
        <StatCard
          label="Stock Variance"
          value={kpis ? kpis.variance.toLocaleString() : '—'}
          icon="bi-arrow-left-right"
          tone={kpis && kpis.variance < 0 ? 'danger' : kpis && kpis.variance > 0 ? 'warning' : 'neutral'}
          loading={loading}
        />
      </KpiBar>

      <FilterBar compact className="align-items-end" ariaLabel="Stock check filters">
        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Tenant</span>
          <select className="form-select" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading...</option>}
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.tenant_name}
              </option>
            ))}
          </select>
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Store</span>
          <select className="form-select" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            {stores.length === 0 && <option value="">Loading...</option>}
            {stores.map((s) => (
              <option key={s.store_id} value={s.store_id}>
                {s.store_code} — {s.store_name}
              </option>
            ))}
          </select>
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Product Name</span>
          <input
            className="form-control"
            style={{ width: '12rem' }}
            value={filters.productName}
            placeholder="Search product…"
            onChange={(e) => setFilter('productName', e.target.value)}
          />
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Supplier</span>
          <select
            className="form-select"
            style={{ width: '12rem' }}
            value={filters.supplierCode}
            onChange={(e) => setFilter('supplierCode', e.target.value)}
          >
            <option value="">All suppliers</option>
            {suppliers.map((s) => (
              <option key={s.supplier_code} value={s.supplier_code}>
                {s.supplier_name ?? s.supplier_code}
              </option>
            ))}
          </select>
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Unit</span>
          <select
            className="form-select"
            style={{ width: '9rem' }}
            value={filters.unitDescription}
            onChange={(e) => setFilter('unitDescription', e.target.value)}
          >
            <option value="">All units</option>
            {units.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Sublocation From</span>
          <SublocationPicker
            tenantId={tenantId}
            storeId={storeId}
            value={filters.sublocationFrom}
            onChange={(v) => setFilter('sublocationFrom', v)}
            placeholder="A001"
            ariaLabel="Sublocation From"
          />
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Sublocation To</span>
          <SublocationPicker
            tenantId={tenantId}
            storeId={storeId}
            value={filters.sublocationTo}
            onChange={(v) => setFilter('sublocationTo', v)}
            placeholder="A050"
            ariaLabel="Sublocation To"
          />
        </label>

        <button
          type="button"
          className="btn btn-outline-secondary"
          onClick={() => setAdvancedOpen((v) => !v)}
        >
          <i className={`bi bi-sliders me-1`} />
          Advanced
          {activeFilterCount > 0 && <span className="badge text-bg-primary ms-1">{activeFilterCount}</span>}
        </button>

        <button type="button" className="btn btn-link text-decoration-none" onClick={clearAll} disabled={activeFilterCount === 0}>
          Clear All
        </button>
      </FilterBar>

      {advancedOpen && (
        <div className="border rounded p-3 d-flex flex-wrap gap-3" style={{ background: 'var(--nx-surface-sunk)' }}>
          <label className="d-flex flex-column gap-1">
            <span className="small text-muted">Product Code From</span>
            <input
              type="number"
              className="form-control"
              style={{ width: '8rem' }}
              value={filters.productCodeFrom}
              onChange={(e) => setFilter('productCodeFrom', e.target.value)}
            />
          </label>
          <label className="d-flex flex-column gap-1">
            <span className="small text-muted">Product Code To</span>
            <input
              type="number"
              className="form-control"
              style={{ width: '8rem' }}
              value={filters.productCodeTo}
              onChange={(e) => setFilter('productCodeTo', e.target.value)}
            />
          </label>
          <label className="d-flex flex-column gap-1">
            <span className="small text-muted">Batch Number</span>
            <input
              className="form-control"
              style={{ width: '9rem' }}
              value={filters.batchCode}
              onChange={(e) => setFilter('batchCode', e.target.value)}
            />
          </label>
          <label className="d-flex flex-column gap-1">
            <span className="small text-muted">Expiry From</span>
            <input
              type="date"
              className="form-control"
              value={filters.expiryFrom}
              onChange={(e) => setFilter('expiryFrom', e.target.value)}
            />
          </label>
          <label className="d-flex flex-column gap-1">
            <span className="small text-muted">Expiry To</span>
            <input
              type="date"
              className="form-control"
              value={filters.expiryTo}
              onChange={(e) => setFilter('expiryTo', e.target.value)}
            />
          </label>
          <label className="d-flex flex-column gap-1">
            <span className="small text-muted">Min Stock</span>
            <input
              type="number"
              className="form-control"
              style={{ width: '7rem' }}
              value={filters.minStock}
              onChange={(e) => setFilter('minStock', e.target.value)}
            />
          </label>
          <label className="d-flex flex-column gap-1">
            <span className="small text-muted">Max Stock</span>
            <input
              type="number"
              className="form-control"
              style={{ width: '7rem' }}
              value={filters.maxStock}
              onChange={(e) => setFilter('maxStock', e.target.value)}
            />
          </label>
          <label className="d-flex flex-column gap-1 justify-content-end">
            <span className="d-flex align-items-center gap-2">
              <input
                type="checkbox"
                checked={filters.includeZeroStock}
                onChange={(e) => setFilter('includeZeroStock', e.target.checked)}
              />
              <span className="small">Include zero stock</span>
            </span>
          </label>
          <label className="d-flex flex-column gap-1 justify-content-end">
            <span className="d-flex align-items-center gap-2">
              <input
                type="checkbox"
                checked={filters.includeNegativeStock}
                onChange={(e) => setFilter('includeNegativeStock', e.target.checked)}
              />
              <span className="small">Include negative stock</span>
            </span>
          </label>
        </div>
      )}

      {syncMessage && <div className="alert alert-info py-2 small mb-0">{syncMessage}</div>}
      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

      {rows && (
        <div className="small text-muted">
          {rows.length.toLocaleString()} row{rows.length === 1 ? '' : 's'} matched
        </div>
      )}

      <div className="table-responsive" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
        <table className="table table-sm table-bordered align-middle mb-0">
          <thead>
            <tr style={{ background: 'var(--nx-surface-sunk)', color: 'var(--nx-text)', position: 'sticky', top: 0, zIndex: 1 }}>
              <th style={{ whiteSpace: 'nowrap' }}>Code</th>
              <th style={{ whiteSpace: 'nowrap' }}>Sublocation</th>
              <th style={{ width: '100%' }}>Product Name</th>
              <th style={{ whiteSpace: 'nowrap' }}>Supplier</th>
              <th style={{ whiteSpace: 'nowrap' }}>Unit</th>
              <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Total Stock</th>
              <th className="text-end" style={{ whiteSpace: 'nowrap' }}>System Stock</th>
              <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Counted Stock</th>
              <th style={{ whiteSpace: 'nowrap' }}>Expiry Date</th>
              <th className="text-end" style={{ whiteSpace: 'nowrap' }}>MRP</th>
              <th style={{ whiteSpace: 'nowrap' }}>Batch</th>
              <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Pday</th>
              <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Sday</th>
            </tr>
          </thead>
          <tbody>
            {rows === null && (
              <tr>
                <td colSpan={13} className="p-0">
                  <EmptyState
                    icon="bi-clipboard-data"
                    title="No preview yet"
                    description="Pick filters and click Preview to load the physical-count sheet."
                  />
                </td>
              </tr>
            )}
            {rows !== null && rows.length === 0 && (
              <tr>
                <td colSpan={13} className="text-center text-muted py-4">
                  {loading ? 'Loading…' : 'No rows match these filters.'}
                </td>
              </tr>
            )}
            {groups.map((sub, subIndex) => (
              <Fragment key={`sub-${sub.sublocation}-${subIndex}`}>
                {subIndex > 0 && (
                  <tr key={`sep-${sub.sublocation}-${subIndex}`} style={{ height: '0.6rem' }}>
                    <td colSpan={13} className="p-0 border-0" />
                  </tr>
                )}
                {sub.products.map((product) =>
                  product.rows.map((r, i) => (
                    <tr key={`${product.productCode}-${r.batch_code}-${i}`}>
                      {i === 0 && (
                        <>
                          <td rowSpan={product.rows.length} className="align-top" style={{ whiteSpace: 'nowrap' }}>{product.productCode}</td>
                          <td rowSpan={product.rows.length} className="align-top" style={{ whiteSpace: 'nowrap' }}>{product.sublocation}</td>
                          <td rowSpan={product.rows.length} className={`align-top${product.nonMoving ? ' table-warning' : ''}`} title={r.product_name ?? ''}>
                            {r.product_name}
                            {product.nonMoving && <span className="badge text-bg-warning ms-1">NM</span>}
                          </td>
                          <td rowSpan={product.rows.length} className="align-top" style={{ whiteSpace: 'nowrap' }} title={r.supplier_name ?? ''}>
                            {r.supplier_name ?? r.supplier_code ?? ''}
                          </td>
                          <td rowSpan={product.rows.length} className="align-top" style={{ whiteSpace: 'nowrap' }}>{r.unit_description}</td>
                          <td rowSpan={product.rows.length} className="align-top text-end" style={{ whiteSpace: 'nowrap' }}>{r.total_stock}</td>
                        </>
                      )}
                      <td className="text-end" style={{ whiteSpace: 'nowrap' }}>{r.batch_stock}</td>
                      <td />
                      <td className={isExpired(r.expiry_date) ? 'table-danger fw-semibold' : ''} style={{ whiteSpace: 'nowrap' }}>{r.expiry_date}</td>
                      <td className="text-end" style={{ whiteSpace: 'nowrap' }}>{r.mrp}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{r.batch_code}</td>
                      {i === 0 && (
                        <>
                          <td rowSpan={product.rows.length} className="align-top text-end" style={{ whiteSpace: 'nowrap' }}>{r.purchase_days ?? ''}</td>
                          <td rowSpan={product.rows.length} className="align-top text-end" style={{ whiteSpace: 'nowrap' }}>{r.sale_days ?? ''}</td>
                        </>
                      )}
                    </tr>
                  )),
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <p className="small text-muted mb-0">
        Physical-count sheet by sublocation range, ported from the legacy OrderRpt report. Sync the store, preview, then export to Excel.
      </p>
    </div>
  )
}
