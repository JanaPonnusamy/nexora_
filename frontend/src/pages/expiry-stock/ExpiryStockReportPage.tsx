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
import { exportExpiryStockExcel, buildExpiryStockExcelFile } from './exportExpiryStockExcel'
import { WhatsAppSendCard } from '../../components/common/WhatsAppSendCard'
import { ColumnChooser, applyColumnPrefs, type ColumnPrefs } from '../../components/common/ColumnChooser'
import '../reports.css'

const PREFS_KEY = 'expiryStock.cols.'
const emptyPrefs: ColumnPrefs = { order: [], hidden: [] }
const iso = (d: Date) => d.toISOString().slice(0, 10)
const firstIso = (y: number, m: number) => iso(new Date(y, m, 1))
const lastIso = (y: number, m: number) => iso(new Date(y, m + 1, 0))
const monthValue = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
const parseMonth = (v: string): [number, number] => {
  const [y, m] = v.split('-').map(Number)
  return [y, (m || 1) - 1]
}
const monthLabel = (v: string) => {
  if (!v) return ''
  const [y, m] = parseMonth(v)
  return new Date(y, m, 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
}

function loadPrefs(level: string): ColumnPrefs | null {
  try {
    const raw = localStorage.getItem(PREFS_KEY + level)
    if (raw) return { ...emptyPrefs, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return null
}

type Period = 'beforeIncl' | 'current' | 'before' | 'afterIncl' | 'after' | 'month' | 'range'
const PERIODS: { key: Period; label: string }[] = [
  { key: 'beforeIncl', label: 'Up to this month' },
  { key: 'current', label: 'This month' },
  { key: 'before', label: 'Before this month' },
  { key: 'afterIncl', label: 'This month onward' },
  { key: 'after', label: 'After this month' },
  { key: 'month', label: 'Selected month' },
  { key: 'range', label: 'Month range' },
]

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
  const thisMonth = useMemo(() => monthValue(today), [today])
  const [period, setPeriod] = useState<Period>('beforeIncl')
  const [selMonth, setSelMonth] = useState(thisMonth)
  const [fromMonth, setFromMonth] = useState(thisMonth)
  const [toMonth, setToMonth] = useState(thisMonth)
  const [onlyCutting, setOnlyCutting] = useState(false)

  // Derive the expiry-date window (from/to, ISO) from the chosen period.
  const { from, to } = useMemo(() => {
    const y = today.getFullYear()
    const m = today.getMonth()
    switch (period) {
      case 'current': return { from: firstIso(y, m), to: lastIso(y, m) }
      case 'before': return { from: '', to: lastIso(y, m - 1) }
      case 'beforeIncl': return { from: '', to: lastIso(y, m) }
      case 'after': return { from: firstIso(y, m + 1), to: '' }
      case 'afterIncl': return { from: firstIso(y, m), to: '' }
      case 'month': {
        const [sy, sm] = parseMonth(selMonth)
        return { from: firstIso(sy, sm), to: lastIso(sy, sm) }
      }
      case 'range': {
        const [fy, fm] = parseMonth(fromMonth)
        const [ty, tm] = parseMonth(toMonth)
        return { from: firstIso(fy, fm), to: lastIso(ty, tm) }
      }
      default: return { from: '', to: lastIso(y, m) }
    }
  }, [period, selMonth, fromMonth, toMonth, today])

  const [result, setResult] = useState<ExpiryStockResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Per-view column layout (web + Electron via localStorage). Optional columns
  // (Cost/PTR/Tax/Supplier) start hidden until the user enables them.
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
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  useEffect(() => {
    if (!tenantId || !storeId) { setSuppliers([]); return }
    let live = true
    expiryStockService.suppliers(tenantId, storeId)
      .then((r) => { if (live) setSuppliers(r.suppliers) })
      .catch(() => { if (live) setSuppliers([]) })
    return () => { live = false }
  }, [tenantId, storeId])
  useEffect(() => { setSupplierCode('') }, [storeId])

  // Load the report whenever any filter changes (period drives from/to).
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
  const rangeText = useMemo(() => {
    const f = from ? monthLabel(monthValue(new Date(from))) : 'earliest'
    const t = to ? monthLabel(monthValue(new Date(to))) : 'latest'
    return `${f} → ${t}`
  }, [from, to])
  const title = useMemo(() => {
    const parts = [`Expiry Stock — ${storeName}`]
    if (supplierName) parts.push(supplierName)
    if (onlyCutting) parts.push('Cutting only')
    parts.push(`Expiry ${rangeText}`)
    return parts.join('  |  ')
  }, [storeName, supplierName, onlyCutting, rangeText])

  const safeName = (s: string) => s.replace(/[^\w.-]+/g, '_').slice(0, 60)
  const excelOpts = () => ({
    columns: displayColumns,
    rows: result!.rows,
    summary: result!.summary,
    sheetName: 'Expiry Stock',
    fileName: safeName(`ExpiryStock_${storeName}_${to || from || 'all'}`),
    title,
    orientation: (displayColumns.length > 8 ? 'landscape' : 'portrait') as 'landscape' | 'portrait',
  })
  const exportExcel = () => {
    if (!result || result.rows.length === 0) return
    void exportExpiryStockExcel(excelOpts())
  }
  const buildWhatsAppFile = async () => {
    if (!result || result.rows.length === 0) throw new Error('Load a report before sharing it.')
    return buildExpiryStockExcelFile(excelOpts())
  }

  const hasRows = !!result && result.rows.length > 0

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
        <button className="btn btn-success btn-sm rpt-action" disabled={!hasRows} onClick={exportExcel}>
          <i className="bi bi-file-earmark-excel-fill" /> Export Excel (A4)
        </button>
        <WhatsAppSendCard
          disabled={!hasRows}
          title="Share expiry stock (A4 Excel) on WhatsApp"
          defaultCaption={title}
          buildFile={buildWhatsAppFile}
        />
      </FilterBar>

      {/* Period presets (expiry month window) */}
      <div className="expiry-tabs" role="tablist" aria-label="Expiry period">
        {PERIODS.map((p) => (
          <button
            key={p.key}
            className={`expiry-tab expiry-tab-alt${period === p.key ? ' active' : ''}`}
            onClick={() => setPeriod(p.key)}
          >
            {p.label}
          </button>
        ))}
        {period === 'month' && (
          <label className="rpt-field"><span>Month</span>
            <input type="month" className="form-control form-control-sm" value={selMonth} onChange={(e) => setSelMonth(e.target.value)} />
          </label>
        )}
        {period === 'range' && (
          <>
            <label className="rpt-field"><span>From month</span>
              <input type="month" className="form-control form-control-sm" value={fromMonth} onChange={(e) => setFromMonth(e.target.value)} />
            </label>
            <label className="rpt-field"><span>To month</span>
              <input type="month" className="form-control form-control-sm" value={toMonth} onChange={(e) => setToMonth(e.target.value)} />
            </label>
          </>
        )}
        <span className="rpt-rangenote">Expiry {rangeText}{hasRows ? ` · ${result!.rows.length} batches` : ''}</span>
      </div>

      {error ? (
        <ErrorState description={error} onRetry={() => setPeriod((p) => p)} />
      ) : loading ? (
        <EmptyState icon="bi-hourglass-split" title="Loading…" description="Fetching expiry stock." />
      ) : !hasRows ? (
        <EmptyState icon="bi-inbox" title="No stock" description="No in-stock batches for this filter / expiry period." />
      ) : (
        <div className="rpt-tablewrap">
          <table className="rpt-table">
            <thead>
              <tr>{displayColumns.map((c) => <th key={c.key} className={`rpt-${c.align}`}>{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {result!.rows.map((row, i) => (
                <tr key={i} className={row._cutting ? 'expiry-cut-row' : undefined}>
                  {displayColumns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(row[c.key], c)}</td>)}
                </tr>
              ))}
              {result!.summary && (
                <tr className="rpt-total">
                  {displayColumns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(result!.summary![c.key], c)}</td>)}
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
