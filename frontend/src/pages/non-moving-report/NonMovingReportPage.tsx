import { useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { FilterBar } from '../../design-system/components/FilterBar'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import {
  nonMovingReportService,
  type NonMovingBasis,
  type NonMovingSupplier,
} from '../../services/nonMovingReportService'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { ExpiryColumn, ExpiryResult } from '../../types/expiryReport'
import { money, num, date } from '../../components/stock/format'
import { exportExpiryExcel } from '../expiry-report/exportExpiryExcel'
import '../reports.css'

const BASES: { key: NonMovingBasis; label: string }[] = [
  { key: 'sold', label: 'By Last Sold' },
  { key: 'received', label: 'By Last Received' },
]

function cell(value: unknown, col: ExpiryColumn): string {
  if (value === null || value === undefined || value === '') return col.format === 'money' ? '—' : ''
  if (col.format === 'money') return money(Number(value))
  if (col.format === 'int') return num(Number(value))
  if (col.format === 'date') return date(String(value))
  return String(value)
}

export default function NonMovingReportPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('') // '' = all stores

  const [basis, setBasis] = useState<NonMovingBasis>('sold')
  const [minDays, setMinDays] = useState(90)
  const [maxDays, setMaxDays] = useState<string>('') // '' = no upper bound
  const [includeNil, setIncludeNil] = useState(false)
  const [supplierMode, setSupplierMode] = useState(0)
  const [supplierCode, setSupplierCode] = useState('')
  const [suppliers, setSuppliers] = useState<NonMovingSupplier[]>([])

  const [result, setResult] = useState<ExpiryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    tenantService.list().then((rows) => {
      const active = rows.filter((t) => t.is_active)
      setTenants(active)
      if (active.length) setTenantId((cur) => cur || active[0].tenant_id)
    }).catch(() => setTenants([]))
    storeService.list().then(setStores).catch(() => setStores([]))
  }, [])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )
  useEffect(() => {
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : ''))
  }, [tenantStores])

  // Supplier dropdown for the current scope.
  useEffect(() => {
    if (!tenantId) return
    let live = true
    nonMovingReportService.suppliers(tenantId, storeId || undefined, supplierMode)
      .then((r) => { if (live) setSuppliers(r.rows) })
      .catch(() => { if (live) setSuppliers([]) })
    return () => { live = false }
  }, [tenantId, storeId, supplierMode])
  // Drop a supplier selection that no longer exists in scope.
  useEffect(() => {
    setSupplierCode((cur) => (cur && suppliers.some((s) => s.SupplierCode === cur) ? cur : ''))
  }, [suppliers])

  const storeName = useMemo(
    () => (storeId ? tenantStores.find((s) => s.store_id === storeId)?.store_name ?? 'Store' : 'All stores'),
    [storeId, tenantStores],
  )

  const runReport = () => {
    if (!tenantId) return
    setLoading(true)
    setError(null)
    nonMovingReportService
      .data(
        tenantId,
        storeId || undefined,
        basis,
        Number(minDays) || 0,
        maxDays === '' ? undefined : Number(maxDays),
        includeNil,
        supplierCode || undefined,
        supplierMode,
      )
      .then(setResult)
      .catch((err) => { setResult(null); setError(err instanceof Error ? err.message : 'Failed to load') })
      .finally(() => setLoading(false))
  }

  // Auto-run on filter changes (debounced-ish via effect).
  useEffect(() => {
    if (!tenantId) return
    let live = true
    setLoading(true)
    setError(null)
    nonMovingReportService
      .data(
        tenantId,
        storeId || undefined,
        basis,
        Number(minDays) || 0,
        maxDays === '' ? undefined : Number(maxDays),
        includeNil,
        supplierCode || undefined,
        supplierMode,
      )
      .then((r) => { if (live) setResult(r) })
      .catch((err) => { if (live) { setResult(null); setError(err instanceof Error ? err.message : 'Failed to load') } })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, storeId, basis, minDays, maxDays, includeNil, supplierMode, supplierCode])

  const levelTitle = useMemo(() => {
    const b = BASES.find((x) => x.key === basis)?.label ?? ''
    const range = maxDays === '' ? `≥ ${minDays} days` : `${minDays}–${maxDays} days`
    return `Non-Moving — ${b} — ${range} — ${storeName}`
  }, [basis, minDays, maxDays, storeName])

  const safeName = (s: string) => s.replace(/[^\w.-]+/g, '_').slice(0, 60)
  const exportExcel = () => {
    if (!result || result.rows.length === 0) return
    void exportExpiryExcel({
      columns: result.columns,
      rows: result.rows,
      summary: result.summary,
      sheetName: `non-moving-${basis}`,
      fileName: safeName(levelTitle),
      title: levelTitle,
    })
  }

  return (
    <div className="container-fluid px-0 rpt">
      <PageHeader title="Non-Moving Report" breadcrumb={['Non-Moving Report']} />

      <FilterBar compact className="rpt-bar" ariaLabel="Non-moving report filters">
        <select className="form-select form-select-sm" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          {tenants.length === 0 && <option value="">Loading…</option>}
          {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
          <option value="">All stores</option>
          {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
        </select>
        <label className="rpt-field"><span>Min days</span>
          <input type="number" min={0} className="form-control form-control-sm" style={{ width: 90 }}
            value={minDays} onChange={(e) => setMinDays(Number(e.target.value))} />
        </label>
        <label className="rpt-field"><span>Max days</span>
          <input type="number" min={0} className="form-control form-control-sm" style={{ width: 90 }}
            placeholder="∞" value={maxDays} onChange={(e) => setMaxDays(e.target.value)} />
        </label>
        <select className="form-select form-select-sm" aria-label="Supplier" value={supplierCode} onChange={(e) => setSupplierCode(e.target.value)}>
          <option value="">All suppliers</option>
          {suppliers.map((s) => <option key={s.SupplierCode} value={s.SupplierCode}>{s.SupplierName}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Supplier basis" value={supplierMode} onChange={(e) => setSupplierMode(Number(e.target.value))}>
          <option value={0}>Product supplier</option>
          <option value={1}>Batch supplier</option>
        </select>
        <label className="rpt-field" style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <input type="checkbox" checked={includeNil} onChange={(e) => setIncludeNil(e.target.checked)} />
          <span>Include nil stock</span>
        </label>
        <button className="btn btn-outline-secondary btn-sm" disabled={!result || result.rows.length === 0} onClick={exportExcel}>
          <i className="bi bi-file-earmark-excel" /> Export Excel
        </button>
      </FilterBar>

      {/* Basis selector */}
      <div className="expiry-tabs" role="tablist" aria-label="Basis">
        {BASES.map((b) => (
          <button key={b.key} className={`expiry-tab${basis === b.key ? ' active' : ''}`} onClick={() => setBasis(b.key)}>{b.label}</button>
        ))}
      </div>

      {error ? (
        <ErrorState description={error} onRetry={runReport} />
      ) : loading && !result ? (
        <EmptyState icon="bi-hourglass-split" title="Loading…" description="Fetching non-moving stock." />
      ) : !result || result.rows.length === 0 ? (
        <EmptyState icon="bi-inbox" title="No non-moving stock" description="No batches match this dwell-day range for the selected scope." />
      ) : (
        <div className="rpt-tablewrap">
          <table className="rpt-table">
            <thead>
              <tr>{result.columns.map((c) => <th key={c.key} className={`rpt-${c.align}`}>{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  {result.columns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(row[c.key], c)}</td>)}
                </tr>
              ))}
              {result.summary && (
                <tr className="rpt-total">
                  {result.columns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(result.summary![c.key], c)}</td>)}
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
