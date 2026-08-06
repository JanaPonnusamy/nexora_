import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { stockIntegrityService } from '../../services/stockIntegrityService'
import type { Tenant } from '../../types/tenant'
import type { TenantStore } from '../../types/store'
import type { StockIntegrityRow } from '../../types/stockIntegrity'

export default function StockIntegrityReportPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<TenantStore[]>([])
  const [storeId, setStoreId] = useState('')

  const [loading, setLoading] = useState(false)
  const [repairing, setRepairing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<StockIntegrityRow[]>([])
  const [ran, setRan] = useState(false)
  const [repairMessage, setRepairMessage] = useState<string | null>(null)

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

  async function runComparison() {
    if (!tenantId) return
    setLoading(true)
    setError(null)
    try {
      const result = await stockIntegrityService.getReport(tenantId, storeId)
      setRows(result.rows)
      setRan(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load comparison')
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  async function repairAll() {
    if (!tenantId || !storeId) return
    setRepairing(true)
    setError(null)
    setRepairMessage(null)
    try {
      const result = await stockIntegrityService.repair(tenantId, storeId)
      setRepairMessage(
        `Repaired ${result.repaired} batch row${result.repaired === 1 ? '' : 's'}. ` +
          `${result.remaining_mismatches} mismatch${result.remaining_mismatches === 1 ? '' : 'es'} remaining.`,
      )
      await runComparison()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Repair failed')
    } finally {
      setRepairing(false)
    }
  }

  return (
    <div className="d-flex flex-column gap-3">
      <PageHeader
        title="Stock Integrity Check"
        breadcrumb={['Operations', 'Inventory', 'Stock Integrity Check']}
        description="Compares SUM(Batches.Stock) against Products.TotalStock per store/product, and can repair stale sync.Batches rows from the live store database."
      />

      <div className="alert alert-info py-2 small mb-0">
        <i className="bi bi-info-circle me-1" />
        Root cause found: <strong>sync.Batches.Stock</strong> was not flagged for change-detection
        in the sync pipeline, so stock-only changes (e.g. a batch depleting to 0) were never
        re-synced — that flag is now fixed going forward. <strong>Repair</strong> corrects the
        existing backlog by reading the live store database (read-only there) and updating only
        the stale <strong>sync.Batches.Stock</strong> values in Nexora, with every change logged to
        the audit table.
      </div>

      <div className="ds-toolbar d-flex flex-wrap gap-3 align-items-end">
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
          <span className="small text-muted">Store (blank = all stores)</span>
          <select className="form-select" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            <option value="">All stores</option>
            {stores.map((s) => (
              <option key={s.store_id} value={s.store_id}>
                {s.store_code} — {s.store_name}
              </option>
            ))}
          </select>
        </label>

        <button className="btn btn-primary" disabled={!tenantId || loading} onClick={() => void runComparison()}>
          <i className="bi bi-search me-1" />
          {loading ? 'Comparing…' : 'Run Comparison'}
        </button>

        <button
          className="btn btn-warning"
          disabled={!tenantId || !storeId || repairing}
          title={!storeId ? 'Select a specific store to repair (not "All stores")' : undefined}
          onClick={() => void repairAll()}
        >
          <i className="bi bi-tools me-1" />
          {repairing ? 'Repairing…' : 'Repair All'}
        </button>
      </div>

      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}
      {repairMessage && <div className="alert alert-success py-2 small mb-0">{repairMessage}</div>}

      {ran && (
        <div className={`alert py-2 small mb-0 ${rows.length === 0 ? 'alert-success' : 'alert-secondary'}`}>
          {rows.length === 0 ? (
            <>
              <i className="bi bi-check-circle me-1" />0 mismatches
            </>
          ) : (
            `${rows.length} mismatch${rows.length === 1 ? '' : 'es'} found`
          )}
        </div>
      )}

      {rows.length > 0 && (
        <div className="table-responsive">
          <table className="table table-sm table-bordered align-middle mb-0">
            <thead>
              <tr className="table-light">
                <th style={{ whiteSpace: 'nowrap' }}>Store</th>
                <th style={{ whiteSpace: 'nowrap' }}>Product Code</th>
                <th style={{ width: '100%' }}>Product Name</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Store Batch Total</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Nexora Total Stock</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Difference</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.store_id}-${r.product_code}-${i}`}>
                  <td style={{ whiteSpace: 'nowrap' }}>{r.store_code} — {r.store_name}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{r.product_code}</td>
                  <td>{r.product_name}</td>
                  <td className="text-end">{r.store_batch_total}</td>
                  <td className="text-end">{r.nexora_total_stock}</td>
                  <td className={`text-end fw-semibold ${r.difference !== 0 ? 'text-danger' : ''}`}>{r.difference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
