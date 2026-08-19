import { Fragment, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { syncService } from '../../services/syncService'
import { stockCheckReportService } from '../../services/stockCheckReportService'
import { exportStockCheckExcel } from './exportStockCheckExcel'
import { SublocationPicker } from './SublocationPicker'
import { groupStockCheckRows, isExpired } from './stockCheckGrouping'
import type { Tenant } from '../../types/tenant'
import type { TenantStore } from '../../types/store'
import type { StockCheckRow } from '../../types/stockCheckReport'
import { FilterBar } from '../../design-system/components/FilterBar'

const POLL_MS = 2000
const SYNC_MAX_MS = 5 * 60 * 1000

function terminal(status?: string | null): 'ok' | 'fail' | null {
  if (!status) return null
  const s = status.toUpperCase()
  if (s === 'COMPLETED' || s === 'SUCCESS') return 'ok'
  if (s === 'FAILED' || s === 'ERROR' || s === 'CANCELLED') return 'fail'
  return null
}

export default function StockCheckReportPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<TenantStore[]>([])
  const [storeId, setStoreId] = useState('')
  const [subFrom, setSubFrom] = useState('')
  const [subTo, setSubTo] = useState('')

  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState<string | null>(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<StockCheckRow[]>([])

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
      .getByTenant(tenantId)
      .then((list) => {
        setStores(list)
        if (list.length) setStoreId((cur) => cur || list[0].store_id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load stores'))
  }, [tenantId])

  const storeCode = stores.find((s) => s.store_id === storeId)?.store_code ?? storeId

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
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await new Promise((r) => setTimeout(r, POLL_MS))
        const sum = await syncService.executionSummary(task_id)
        const total = sum.total_tables ?? 0
        const done = sum.completed_tables ?? 0
        setSyncMessage(total > 0 ? `Syncing… ${done}/${total} tables` : 'Syncing…')
        const t = terminal(sum.status)
        if (t === 'ok') {
          setSyncMessage('Sync complete')
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
      const result = await stockCheckReportService.getRows(tenantId, storeId, subFrom.trim(), subTo.trim())
      setRows(result.rows)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report')
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  async function exportExcel() {
    if (rows.length === 0) return
    await exportStockCheckExcel({ rows, storeCode, sublocationFrom: subFrom.trim(), sublocationTo: subTo.trim() })
  }

  const groups = useMemo(() => groupStockCheckRows(rows), [rows])

  return (
    <div className="d-flex flex-column gap-3">
      <PageHeader
        title="Stock Check Report"
        breadcrumb={['Operations', 'Inventory', 'Stock Check Report']}
        description="Physical-count sheet by sublocation range, ported from the legacy OrderRpt report. Sync the store, preview, then export to Excel."
      />

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
          <span className="small text-muted">Sublocation From</span>
          <SublocationPicker
            tenantId={tenantId}
            storeId={storeId}
            value={subFrom}
            onChange={setSubFrom}
            placeholder="A001"
            ariaLabel="Sublocation From"
          />
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Sublocation To</span>
          <SublocationPicker
            tenantId={tenantId}
            storeId={storeId}
            value={subTo}
            onChange={setSubTo}
            placeholder="A050"
            ariaLabel="Sublocation To"
          />
        </label>

        <button className="btn btn-outline-secondary" disabled={!storeId || syncing} onClick={() => void runSync()}>
          <i className="bi bi-arrow-repeat me-1" />
          {syncing ? 'Syncing…' : 'Sync Now'}
        </button>

        <button
          className="btn btn-primary"
          disabled={!storeId || loading}
          onClick={() => void preview()}
        >
          <i className="bi bi-eye me-1" />
          {loading ? 'Loading…' : 'Preview'}
        </button>

        <button className="btn btn-success" disabled={rows.length === 0} onClick={() => void exportExcel()}>
          <i className="bi bi-file-earmark-excel me-1" />
          Export Excel
        </button>
      </FilterBar>

      {syncMessage && <div className="alert alert-info py-2 small mb-0">{syncMessage}</div>}
      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

      {rows.length > 0 && (
        <div className="table-responsive">
          <table className="table table-sm table-bordered align-middle mb-0">
            <thead>
              <tr style={{ background: 'var(--nx-surface-sunk)', color: 'var(--nx-text)' }}>
                <th style={{ whiteSpace: 'nowrap' }}>code</th>
                <th style={{ whiteSpace: 'nowrap' }}>sublocation</th>
                <th style={{ width: '100%' }}>PRODUCTNAME</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>TotalStock</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>STOCK</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Counted Stock</th>
                <th style={{ whiteSpace: 'nowrap' }}>EXPIRYDATE</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>MRP</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>SUnit</th>
                <th style={{ whiteSpace: 'nowrap' }}>Batch</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Pday</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Sday</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((sub, subIndex) => (
                <Fragment key={`sub-${sub.sublocation}-${subIndex}`}>
                  {subIndex > 0 && (
                    <tr key={`sep-${sub.sublocation}-${subIndex}`} style={{ height: '0.6rem' }}>
                      <td colSpan={12} className="p-0 border-0" />
                    </tr>
                  )}
                  {sub.products.map((product) =>
                    product.rows.map((r, i) => (
                      <tr key={`${product.productCode}-${r.batch_code}-${i}`}>
                        {i === 0 && (
                          <>
                            <td rowSpan={product.rows.length} className="align-top" style={{ whiteSpace: 'nowrap' }}>{product.productCode}</td>
                            <td rowSpan={product.rows.length} className="align-top" style={{ whiteSpace: 'nowrap' }}>{product.sublocation}</td>
                            <td rowSpan={product.rows.length} className={`align-top${product.nonMoving ? ' table-warning' : ''}`}>
                              {r.product_name}
                              {product.nonMoving && <span className="badge text-bg-warning ms-1">NM</span>}
                            </td>
                            <td rowSpan={product.rows.length} className="align-top text-end" style={{ whiteSpace: 'nowrap' }}>{r.total_stock}</td>
                          </>
                        )}
                        <td className="text-end" style={{ whiteSpace: 'nowrap' }}>{r.batch_stock}</td>
                        <td />
                        <td className={isExpired(r.expiry_date) ? 'table-danger fw-semibold' : ''} style={{ whiteSpace: 'nowrap' }}>{r.expiry_date}</td>
                        <td className="text-end" style={{ whiteSpace: 'nowrap' }}>{r.mrp}</td>
                        <td className="text-end" style={{ whiteSpace: 'nowrap' }}>{r.sale_unit}</td>
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
      )}
    </div>
  )
}
