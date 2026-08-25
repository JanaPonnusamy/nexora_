import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { FilterBar } from '../../design-system/components/FilterBar'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { expiryStockService } from '../../services/expiryStockService'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { ExpiryStockColumn, ExpiryStockResult, ExpiryStockSupplier } from '../../types/expiryStock'
import { money, num, date } from '../../components/stock/format'
import { exportExpiryStockExcel } from './exportExpiryStockExcel'
import { ColumnChooser, applyColumnPrefs, type ColumnPrefs } from '../../components/common/ColumnChooser'
import '../reports.css'

const PREFS_KEY = 'expiryStock.cols.'
const emptyPrefs: ColumnPrefs = { order: [], hidden: [] }
const iso = (d: Date) => d.toISOString().slice(0, 10)
const endOfMonth = (d: Date) => iso(new Date(d.getFullYear(), d.getMonth() + 1, 0))

function loadPrefs(level: string): ColumnPrefs | null {
  try {
    const raw = localStorage.getItem(PREFS_KEY + level)
    if (raw) return { ...emptyPrefs, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return null
}

/** qty: thousands + up to 2 decimals (batch/total stock can be fractional). */
function qty(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '0'
  return value.toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

function cell(value: unknown, col: ExpiryStockColumn) {
  if (col.format === 'mark') {
    return value ? <span className="expiry-cut-badge">Cutting</span> : ''
  }
  if (value === null || value === undefined || value === '') return col.format === 'money' ? '—' : ''
  if (col.format === 'money') return money(Number(value))
  if (col.format === 'int') return num(Number(value))
  if (col.format === 'qty') return qty(Number(value))
  if (col.format === 'date') return date(String(value))
  return String(value)
}

export default function ExpiryStockReportPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')

  const [suppliers, setSuppliers] = useState<ExpiryStockSupplier[]>([])
  const [supplierCode, setSupplierCode] = useState('')

  const today = useMemo(() => new Date(), [])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState(endOfMonth(today))
  const [onlyCutting, setOnlyCutting] = useState(false)

  const [result, setResult] = useState<ExpiryStockResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Per-view column layout (web + Electron via localStorage). When the user has
  // no saved layout, the optional columns (Cost/PTR/Tax/Supplier) start hidden.
  const [prefs, setPrefs] = useState<ColumnPrefs>(emptyPrefs)
  const level = result?.level ?? ''
  useEffect(() => {
    if (!result) return
    const saved = loadPrefs(result.level)
    if (saved) { setPrefs(saved); return }
    const hidden = result.columns.filter((c) => c.optional).map((c) => c.key)
    setPrefs({ order: [], hidden })
  }, [result])
  const savePrefs = useCallback((next: ColumnPrefs) => {
    setPrefs(next)
    if (level) { try { localStorage.setItem(PREFS_KEY + level, JSON.stringify(next)) } catch { /* quota */ } }
  }, [level])
  const resetPrefs = useCallback(() => {
    if (level) { try { localStorage.removeItem(PREFS_KEY + level) } catch { /* ignore */ } }
    const hidden = result ? result.columns.filter((c) => c.optional).map((c) => c.key) : []
    setPrefs({ order: [], hidden })
  }, [level, result])
  const displayColumns = useMemo(
    () => (result ? applyColumnPrefs(result.columns, prefs) : []),
    [result, prefs],
  )

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
    // Pick the first store of the tenant if the current one is foreign/empty.
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  // Supplier list for the chosen store.
  useEffect(() => {
    if (!tenantId || !storeId) { setSuppliers([]); return }
    let live = true
    expiryStockService.suppliers(tenantId, storeId)
      .then((r) => { if (live) setSuppliers(r.suppliers) })
      .catch(() => { if (live) setSuppliers([]) })
    return () => { live = false }
  }, [tenantId, storeId])
  useEffect(() => { setSupplierCode('') }, [storeId])

  // Load the report whenever a filter changes.
  useEffect(() => {
    if (!tenantId || !storeId) { setResult(null); return }
    let live = true
    setLoading(true)
    setError(null)
    expiryStockService.report(tenantId, storeId, {
      supplierCode: supplierCode || undefined,
      from: from || undefined,
      to: to || undefined,
      onlyCutting,
    })
      .then((r) => { if (live) setResult(r) })
      .catch((err) => { if (live) { setResult(null); setError(err instanceof Error ? err.message : 'Failed to load') } })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [tenantId, storeId, supplierCode, from, to, onlyCutting])

  const storeName = useMemo(
    () => tenantStores.find((s) => s.store_id === storeId)?.store_name ?? 'Store',
    [storeId, tenantStores],
  )
  const supplierName = useMemo(
    () => (supplierCode ? suppliers.find((s) => s.SupplierCode === supplierCode)?.SupplierName ?? '' : ''),
    [supplierCode, suppliers],
  )
  const title = useMemo(() => {
    const parts = [`Expiry Stock — ${storeName}`]
    if (supplierName) parts.push(supplierName)
    if (onlyCutting) parts.push('Cutting only')
    const range = to ? `${from || 'earliest'} → ${to}` : 'all'
    parts.push(`Expiry ${range}`)
    return parts.join('  |  ')
  }, [storeName, supplierName, onlyCutting, from, to])

  const safeName = (s: string) => s.replace(/[^\w.-]+/g, '_').slice(0, 60)
  const exportExcel = () => {
    if (!result || result.rows.length === 0) return
    void exportExpiryStockExcel({
      columns: displayColumns,
      rows: result.rows,
      summary: result.summary,
      sheetName: 'Expiry Stock',
      fileName: safeName(`ExpiryStock_${storeName}_${to || 'all'}`),
      title,
      orientation: displayColumns.length > 8 ? 'landscape' : 'portrait',
    })
  }

  return (
    <div className="container-fluid px-0 rpt">
      <PageHeader title="Expiry Stock" breadcrumb={['Expiry Report', 'Expiry Stock']} />

      <FilterBar compact className="rpt-bar" ariaLabel="Expiry stock filters">
        <select className="form-select form-select-sm" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          {tenants.length === 0 && <option value="">Loading…</option>}
          {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
          {tenantStores.length === 0 && <option value="">No stores</option>}
          {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Supplier" value={supplierCode} onChange={(e) => setSupplierCode(e.target.value)}>
          <option value="">All suppliers</option>
          {suppliers.map((s) => <option key={s.SupplierCode} value={s.SupplierCode}>{s.SupplierName}</option>)}
        </select>
        <label className="rpt-field"><span>Expiry from</span><input type="date" className="form-control form-control-sm" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="rpt-field"><span>Expiry to</span><input type="date" className="form-control form-control-sm" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <label className="rpt-check" title="Show only batches whose remaining stock is below one sale unit (loose / part packs)">
          <input type="checkbox" checked={onlyCutting} onChange={(e) => setOnlyCutting(e.target.checked)} /> <span>Cutting only</span>
        </label>
        {result && result.columns.length > 0 && (
          <ColumnChooser
            columns={result.columns.map((c) => ({ key: c.key, label: c.label }))}
            prefs={prefs}
            onChange={savePrefs}
            onReset={resetPrefs}
          />
        )}
        <button className="btn btn-outline-secondary btn-sm" disabled={!result || result.rows.length === 0} onClick={exportExcel}>
          <i className="bi bi-file-earmark-excel" /> Export Excel (A4)
        </button>
      </FilterBar>

      {error ? (
        <ErrorState description={error} onRetry={() => setTo((t) => t)} />
      ) : loading && !result ? (
        <EmptyState icon="bi-hourglass-split" title="Loading…" description="Fetching expiry stock." />
      ) : !result || result.rows.length === 0 ? (
        <EmptyState icon="bi-inbox" title="No stock" description="No in-stock batches for this filter / expiry range." />
      ) : (
        <div className="rpt-tablewrap">
          <table className="rpt-table">
            <thead>
              <tr>{displayColumns.map((c) => <th key={c.key} className={`rpt-${c.align}`}>{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i} className={row._cutting ? 'expiry-cut-row' : undefined}>
                  {displayColumns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(row[c.key], c)}</td>)}
                </tr>
              ))}
              {result.summary && (
                <tr className="rpt-total">
                  {displayColumns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(result.summary![c.key], c)}</td>)}
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
