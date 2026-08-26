import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { FilterBar } from '../../design-system/components/FilterBar'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { expiryReportService, type ExpiryStatus, type ExpiryGroupBy, type ExpirySupplier } from '../../services/expiryReportService'
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
  const [suppliers, setSuppliers] = useState<ExpirySupplier[]>([])
  const [supplierCode, setSupplierCode] = useState('') // '' = all suppliers

  const today = useMemo(() => new Date(), [])
  const yesterday = useMemo(() => iso(new Date(today.getTime() - 864e5)), [today])
  const [from, setFrom] = useState(iso(new Date(today.getTime() - 365 * 864e5)))
  const [to, setTo] = useState(yesterday)
  const [status, setStatus] = useState<ExpiryStatus>('all')
  const [groupBy, setGroupBy] = useState<ExpiryGroupBy>('summary')

  const [result, setResult] = useState<ExpiryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Core filters (tenant/store/supplier/from/to) only take effect when the user
  // clicks Load — no fetch fires while they are still choosing. Status/Group-By
  // remain instant pivots that reuse whatever core was last loaded.
  interface Core { tenantId: string; storeId: string; supplierCode: string; from: string; to: string }
  const [applied, setApplied] = useState<Core | null>(null)
  const [boundsReady, setBoundsReady] = useState(false)
  const didInit = useRef(false)
  const load = useCallback(() => {
    if (!tenantId || !from || !to) return
    setApplied({ tenantId, storeId, supplierCode, from, to })
  }, [tenantId, storeId, supplierCode, from, to])
  const dirty = !applied
    || applied.tenantId !== tenantId || applied.storeId !== storeId
    || applied.supplierCode !== supplierCode || applied.from !== from || applied.to !== to

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

  // Supplier list for the current tenant/store scope.
  useEffect(() => {
    if (!tenantId) { setSuppliers([]); return }
    let live = true
    expiryReportService.suppliers(tenantId, storeId || undefined)
      .then((r) => { if (live) setSuppliers(r.suppliers) })
      .catch(() => { if (live) setSuppliers([]) })
    return () => { live = false }
  }, [tenantId, storeId])
  // Drop the supplier filter if it isn't valid for the new scope.
  useEffect(() => {
    setSupplierCode((cur) => (cur && suppliers.some((s) => s.SupplierCode === cur) ? cur : ''))
  }, [suppliers])

  // Default the "from" date to the oldest pending date for the scope.
  useEffect(() => {
    if (!tenantId) return
    let live = true
    expiryReportService.dateBounds(tenantId, storeId || undefined, supplierCode || undefined)
      .then((b) => { if (live && b.oldest_pending) setFrom(b.oldest_pending) })
      .catch(() => { /* keep current from */ })
      .finally(() => { if (live) setBoundsReady(true) })
    return () => { live = false }
  }, [tenantId, storeId, supplierCode])

  // Auto-run the report ONCE on first open (after the oldest-pending default is
  // in), so the page isn't empty. Every later core-filter change waits for Load.
  useEffect(() => {
    if (didInit.current || !boundsReady) return
    if (tenantId && from && to) {
      didInit.current = true
      setApplied({ tenantId, storeId, supplierCode, from, to })
    }
  }, [boundsReady, tenantId, storeId, supplierCode, from, to])

  // Fetch on the APPLIED core (set by Load) + the live Status / Group-By pivots.
  useEffect(() => {
    if (!applied) return
    let live = true
    setLoading(true)
    setError(null)
    expiryReportService.data(applied.tenantId, applied.storeId || undefined, applied.from,
                             applied.to, status, groupBy, applied.supplierCode || undefined)
      .then((r) => { if (live) setResult(r) })
      .catch((err) => { if (live) { setResult(null); setError(err instanceof Error ? err.message : 'Failed to load') } })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [applied, status, groupBy])

  // Titles / exports describe the LOADED data (applied core), not pending edits.
  const shownStoreId = applied?.storeId ?? storeId
  const shownSupplierCode = applied?.supplierCode ?? supplierCode
  const shownFrom = applied?.from ?? from
  const shownTo = applied?.to ?? to
  const storeName = useMemo(
    () => (shownStoreId ? tenantStores.find((s) => s.store_id === shownStoreId)?.store_name ?? 'Store' : 'All stores'),
    [shownStoreId, tenantStores],
  )
  const supplierName = useMemo(
    () => (shownSupplierCode ? suppliers.find((s) => s.SupplierCode === shownSupplierCode)?.SupplierName ?? '' : ''),
    [shownSupplierCode, suppliers],
  )
  const levelTitle = useMemo(() => {
    const st = STATUSES.find((s) => s.key === status)?.label ?? ''
    const gb = GROUPS.find((g) => g.key === groupBy)?.label ?? ''
    const base = `Expiry — ${st} — ${gb} — ${storeName}`
    return supplierName ? `${base} — ${supplierName}` : base
  }, [status, groupBy, storeName, supplierName])

  const safeName = (s: string) => s.replace(/[^\w.-]+/g, '_').slice(0, 50)
  const excelOpts = () => ({
    columns: displayColumns,
    rows: result!.rows,
    summary: result!.summary,
    sheetName: `${status}-${groupBy}`,
    fileName: safeName(`${levelTitle}_${shownFrom}_${shownTo}`),
    title: `${levelTitle}  (${shownFrom} to ${shownTo})`,
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

      {/* Prominent supplier search — above all other filters. */}
      <div className="rpt-supplierbar">
        <label className="rpt-supplier-label" htmlFor="expiry-supplier">
          <i className="bi bi-search" /> Supplier
        </label>
        <select
          id="expiry-supplier"
          className="form-select form-select-sm rpt-supplier-select"
          aria-label="Supplier"
          value={supplierCode}
          onChange={(e) => setSupplierCode(e.target.value)}
        >
          <option value="">All suppliers</option>
          {suppliers.map((s) => <option key={s.SupplierCode} value={s.SupplierCode}>{s.SupplierName}</option>)}
        </select>
        {supplierCode && (
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setSupplierCode('')}>
            <i className="bi bi-x-lg" /> Clear
          </button>
        )}
        <span className="rpt-supplier-count">{suppliers.length} suppliers</span>
      </div>

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
        <button
          className={`btn btn-sm rpt-load ${dirty ? 'btn-primary' : 'btn-outline-primary'}`}
          disabled={!tenantId || !from || !to || loading}
          onClick={load}
          title="Load the report for the selected store / dates / supplier"
        >
          <i className="bi bi-arrow-clockwise" /> {loading ? 'Loading…' : dirty ? 'Load' : 'Reload'}
        </button>
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
          defaultCaption={`${levelTitle} | ${shownFrom} to ${shownTo}`}
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

      {dirty && applied && (
        <div className="rpt-dirty" role="status">
          <i className="bi bi-exclamation-circle" /> Filters changed — click <strong>Load</strong> to update the report.
        </div>
      )}

      {error ? (
        <ErrorState description={error} onRetry={load} />
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
