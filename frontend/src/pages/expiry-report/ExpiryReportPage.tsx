import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { FilterBar } from '../../design-system/components/FilterBar'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { expiryReportService, type ExpiryStatus, type ExpiryGroupBy } from '../../services/expiryReportService'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { ExpiryColumn, ExpiryResult } from '../../types/expiryReport'
import { money, num, date } from '../../components/stock/format'
import { exportExpiryExcel, buildExpiryExcelFile } from './exportExpiryExcel'
import { WhatsAppSendCard } from '../../components/common/WhatsAppSendCard'
import { ColumnChooser, applyColumnPrefs, type ColumnPrefs } from '../../components/common/ColumnChooser'
import '../reports.css'

const PREFS_KEY = 'expiry.cols.'
const emptyPrefs: ColumnPrefs = { order: [], hidden: [] }
const iso = (d: Date) => d.toISOString().slice(0, 10)

function loadPrefs(level: string): ColumnPrefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY + level)
    if (raw) return { ...emptyPrefs, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return emptyPrefs
}

const STATUSES: { key: ExpiryStatus; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'received', label: 'Received' },
  { key: 'pending', label: 'Pending' },
  { key: 'rejected', label: 'Rejected' },
]
const GROUPS: { key: ExpiryGroupBy; label: string }[] = [
  { key: 'summary', label: 'Summary' },
  { key: 'ack', label: 'Ack-wise' },
  { key: 'month', label: 'Month-wise' },
  { key: 'supplier', label: 'Supplier-wise' },
  { key: 'product', label: 'Product-wise' },
]

function cell(value: unknown, col: ExpiryColumn): string {
  if (value === null || value === undefined || value === '') return col.format === 'money' ? '—' : ''
  if (col.format === 'money') return money(Number(value))
  if (col.format === 'int') return num(Number(value))
  if (col.format === 'date') return date(String(value))
  return String(value)
}

export default function ExpiryReportPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('') // '' = all stores

  const today = useMemo(() => new Date(), [])
  const yesterday = useMemo(() => iso(new Date(today.getTime() - 864e5)), [today])
  const [from, setFrom] = useState(iso(new Date(today.getTime() - 365 * 864e5)))
  const [to, setTo] = useState(yesterday)
  const [status, setStatus] = useState<ExpiryStatus>('all')
  const [groupBy, setGroupBy] = useState<ExpiryGroupBy>('summary')

  const [result, setResult] = useState<ExpiryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Per-view column layout, persisted in localStorage (web + Electron).
  const [prefs, setPrefs] = useState<ColumnPrefs>(emptyPrefs)
  const level = result?.level ?? ''
  useEffect(() => { if (level) setPrefs(loadPrefs(level)) }, [level])
  const savePrefs = useCallback((next: ColumnPrefs) => {
    setPrefs(next)
    if (level) { try { localStorage.setItem(PREFS_KEY + level, JSON.stringify(next)) } catch { /* quota */ } }
  }, [level])
  const resetPrefs = useCallback(() => {
    if (level) { try { localStorage.removeItem(PREFS_KEY + level) } catch { /* ignore */ } }
    setPrefs(emptyPrefs)
  }, [level])
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
    // Reset store to "all" when tenant changes if the current store is foreign.
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : ''))
  }, [tenantStores])

  // Default the "from" date to the oldest pending date for the scope.
  useEffect(() => {
    if (!tenantId) return
    let live = true
    expiryReportService.dateBounds(tenantId, storeId || undefined)
      .then((b) => { if (live && b.oldest_pending) setFrom(b.oldest_pending) })
      .catch(() => { /* keep current from */ })
    return () => { live = false }
  }, [tenantId, storeId])

  // Load the grouped data whenever a filter changes.
  useEffect(() => {
    if (!tenantId || !from || !to) return
    let live = true
    setLoading(true)
    setError(null)
    expiryReportService.data(tenantId, storeId || undefined, from, to, status, groupBy)
      .then((r) => { if (live) setResult(r) })
      .catch((err) => { if (live) { setResult(null); setError(err instanceof Error ? err.message : 'Failed to load') } })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [tenantId, storeId, from, to, status, groupBy])

  const storeName = useMemo(
    () => (storeId ? tenantStores.find((s) => s.store_id === storeId)?.store_name ?? 'Store' : 'All stores'),
    [storeId, tenantStores],
  )
  const levelTitle = useMemo(() => {
    const st = STATUSES.find((s) => s.key === status)?.label ?? ''
    const gb = GROUPS.find((g) => g.key === groupBy)?.label ?? ''
    return `Expiry — ${st} — ${gb} — ${storeName}`
  }, [status, groupBy, storeName])

  const safeName = (s: string) => s.replace(/[^\w.-]+/g, '_').slice(0, 50)
  const excelOpts = () => ({
    columns: displayColumns,
    rows: result!.rows,
    summary: result!.summary,
    sheetName: `${status}-${groupBy}`,
    fileName: safeName(`${levelTitle}_${from}_${to}`),
    title: `${levelTitle}  (${from} to ${to})`,
  })
  const exportExcel = () => {
    if (!result || result.rows.length === 0) return
    void exportExpiryExcel(excelOpts())
  }
  const buildWhatsAppFile = async () => {
    if (!result || result.rows.length === 0) throw new Error('Run a report before sending it to WhatsApp.')
    return buildExpiryExcelFile(excelOpts())
  }

  return (
    <div className="container-fluid px-0 rpt">
      <PageHeader title="Expiry Report" breadcrumb={['Expiry Report']} />

      <FilterBar compact className="rpt-bar" ariaLabel="Expiry report filters">
        <select className="form-select form-select-sm" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          {tenants.length === 0 && <option value="">Loading…</option>}
          {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
          <option value="">All stores</option>
          {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
        </select>
        <label className="rpt-field"><span>From</span><input type="date" className="form-control form-control-sm" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="rpt-field"><span>To</span><input type="date" className="form-control form-control-sm" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        {result && result.columns.length > 0 && (
          <ColumnChooser
            columns={result.columns.map((c) => ({ key: c.key, label: c.label }))}
            prefs={prefs}
            onChange={savePrefs}
            onReset={resetPrefs}
          />
        )}
        <button className="btn btn-outline-secondary btn-sm" disabled={!result || result.rows.length === 0} onClick={exportExcel}>
          <i className="bi bi-file-earmark-excel" /> Export Excel
        </button>
        <WhatsAppSendCard
          disabled={!result || result.rows.length === 0}
          title="Send expiry report (Excel) to WhatsApp"
          defaultCaption={`${levelTitle} | ${from} to ${to}`}
          buildFile={buildWhatsAppFile}
        />
      </FilterBar>

      {/* Status filter */}
      <div className="expiry-tabs" role="tablist" aria-label="Status">
        {STATUSES.map((s) => (
          <button key={s.key} className={`expiry-tab${status === s.key ? ' active' : ''}`} onClick={() => setStatus(s.key)}>{s.label}</button>
        ))}
      </div>
      {/* Group-by selector */}
      <div className="expiry-tabs" role="tablist" aria-label="Group by">
        {GROUPS.map((g) => (
          <button key={g.key} className={`expiry-tab expiry-tab-alt${groupBy === g.key ? ' active' : ''}`} onClick={() => setGroupBy(g.key)}>{g.label}</button>
        ))}
      </div>

      {error ? (
        <ErrorState description={error} onRetry={() => setTo((t) => t)} />
      ) : loading && !result ? (
        <EmptyState icon="bi-hourglass-split" title="Loading…" description="Fetching expiry data." />
      ) : !result || result.rows.length === 0 ? (
        <EmptyState icon="bi-inbox" title="No data" description="No expiry records for this status / date range." />
      ) : (
        <div className="rpt-tablewrap">
          <table className="rpt-table">
            <thead>
              <tr>{displayColumns.map((c) => <th key={c.key} className={`rpt-${c.align}`}>{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
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
