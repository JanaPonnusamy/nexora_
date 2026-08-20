import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../components/common/PageHeader'
import { EmptyState } from '../components/common/EmptyState'
import { ErrorState } from '../components/common/ErrorState'
import { WhatsAppSendCard } from '../components/common/WhatsAppSendCard'
import { tenantService } from '../services/tenantService'
import { storeService } from '../services/storeService'
import { reportsService } from '../services/reportsService'
import type { Tenant } from '../types/tenant'
import type { Store } from '../types/store'
import type { ReportColumn, ReportDef, ReportResult, SupplierOption } from '../types/reports'
import { money, num, date } from '../components/stock/format'
import { FilterBar } from '../design-system/components/FilterBar'
import './reports.css'

const iso = (d: Date) => d.toISOString().slice(0, 10)

function cell(value: unknown, col: ReportColumn): string {
  if (value === null || value === undefined || value === '') return col.format === 'money' ? '—' : ''
  if (col.format === 'money') return money(Number(value))
  if (col.format === 'int') return num(Number(value))
  if (col.format === 'date') return date(String(value))
  return String(value)
}

function toCsv(result: ReportResult): string {
  const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
  const header = result.columns.map((c) => esc(c.label)).join(',')
  const line = (row: Record<string, unknown>) =>
    result.columns.map((c) => esc(cell(row[c.key], c))).join(',')
  const body = result.rows.map(line)
  if (result.summary) body.push(line(result.summary))
  return [header, ...body].join('\n')
}

export default function ReportsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [defs, setDefs] = useState<ReportDef[]>([])
  const [reportKey, setReportKey] = useState('')

  const today = useMemo(() => new Date(), [])
  const [from, setFrom] = useState(iso(new Date(today.getTime() - 30 * 864e5)))
  const [to, setTo] = useState(iso(today))
  const [dwellDays, setDwellDays] = useState('30')
  const [division, setDivision] = useState('2025')

  const [supplierQuery, setSupplierQuery] = useState('')
  const [supplierOptions, setSupplierOptions] = useState<SupplierOption[]>([])
  const [supplierCode, setSupplierCode] = useState('')

  const [result, setResult] = useState<ReportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    tenantService.list().then((rows) => {
      const active = rows.filter((t) => t.is_active)
      setTenants(active)
      if (active.length) setTenantId((current) => current || active[0].tenant_id)
    }).catch(() => setTenants([]))
    storeService.list().then(setStores).catch(() => setStores([]))
    reportsService.catalog().then((rows) => {
      setDefs(rows)
      if (rows.length) setReportKey((current) => current || rows[0].key)
    }).catch(() => setDefs([]))
  }, [])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )

  useEffect(() => {
    setStoreId((current) => (tenantStores.some((s) => s.store_id === current) ? current : tenantStores[0]?.store_id ?? ''))
  }, [tenantStores])

  const def = useMemo(() => defs.find((d) => d.key === reportKey) ?? null, [defs, reportKey])

  useEffect(() => {
    if (!def?.needs_supplier || !tenantId || !storeId) {
      setSupplierOptions([])
      return
    }
    let live = true
    const timer = window.setTimeout(() => {
      reportsService.suppliers(tenantId, storeId, supplierQuery, 50)
        .then((rows) => live && setSupplierOptions(rows))
        .catch(() => live && setSupplierOptions([]))
    }, 250)
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [def, tenantId, storeId, supplierQuery])

  const run = useCallback(() => {
    if (!def || !tenantId || !storeId) return
    setLoading(true)
    setError(null)
    reportsService.run(def.key, tenantId, storeId, {
      from: def.needs_date_range ? from : undefined,
      to: def.needs_date_range ? to : undefined,
      dwell_days: def.needs_dwell_days ? Number(dwellDays) : undefined,
      supplier_code: def.needs_supplier ? supplierCode || undefined : undefined,
      division_code: def.needs_division ? division || undefined : undefined,
    })
      .then(setResult)
      .catch((err) => {
        setResult(null)
        setError(err instanceof Error ? err.message : 'Failed to run report')
      })
      .finally(() => setLoading(false))
  }, [def, tenantId, storeId, from, to, dwellDays, supplierCode, division])

  const exportCsv = () => {
    if (!result) return
    const blob = new Blob([toCsv(result)], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const storeCode = tenantStores.find((s) => s.store_id === storeId)?.store_code ?? 'store'
    a.href = url
    a.download = `${storeCode}_${result.report}_${iso(today)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const buildCsvFile = async () => {
    if (!result) {
      throw new Error('Run a report before sending it to WhatsApp.')
    }
    const storeCode = tenantStores.find((s) => s.store_id === storeId)?.store_code ?? 'store'
    const fileName = `${storeCode}_${result.report}_${iso(today)}.csv`
    return new File([toCsv(result)], fileName, { type: 'text/csv;charset=utf-8;' })
  }

  const canRun = Boolean(def && tenantId && storeId)

  return (
    <div className="container-fluid px-0 rpt">
      <PageHeader title="Reports" breadcrumb={['Reports']} />

      <FilterBar compact className="rpt-bar" ariaLabel="Report filters">
        <select className="form-select form-select-sm" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          {tenants.length === 0 && <option value="">Loading…</option>}
          {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
          {tenantStores.length === 0 && <option value="">No stores</option>}
          {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Report" value={reportKey} onChange={(e) => { setReportKey(e.target.value); setResult(null) }}>
          {defs.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
        </select>

        {def?.needs_date_range && (
          <>
            <label className="rpt-field"><span>From</span><input type="date" className="form-control form-control-sm" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
            <label className="rpt-field"><span>To</span><input type="date" className="form-control form-control-sm" value={to} onChange={(e) => setTo(e.target.value)} /></label>
          </>
        )}
        {def?.needs_dwell_days && (
          <label className="rpt-field"><span>Dwell days</span><input type="number" min={0} className="form-control form-control-sm rpt-num" value={dwellDays} onChange={(e) => setDwellDays(e.target.value)} /></label>
        )}
        {def?.needs_supplier && (
          <>
            <input className="form-control form-control-sm" placeholder="Search supplier…" value={supplierQuery} onChange={(e) => setSupplierQuery(e.target.value)} />
            <select className="form-select form-select-sm" aria-label="Supplier" value={supplierCode} onChange={(e) => setSupplierCode(e.target.value)}>
              <option value="">All suppliers</option>
              {supplierOptions.map((s) => <option key={s.supplier_code} value={s.supplier_code}>{s.supplier_name ?? s.supplier_code}</option>)}
            </select>
          </>
        )}
        {def?.needs_division && (
          <label className="rpt-field"><span>Division</span><input className="form-control form-control-sm rpt-num" value={division} onChange={(e) => setDivision(e.target.value)} /></label>
        )}

        <button className="btn btn-primary btn-sm" disabled={!canRun || loading} onClick={run}>
          <i className="bi bi-play-fill" /> {loading ? 'Running…' : 'Run'}
        </button>
        <button className="btn btn-outline-secondary btn-sm" disabled={!result || result.rows.length === 0} onClick={exportCsv}>
          <i className="bi bi-download" /> Export CSV
        </button>
        <WhatsAppSendCard
          disabled={!result || result.rows.length === 0}
          title="Send report to WhatsApp"
          defaultCaption={`Nexora ${def?.label ?? 'Report'} | ${from}${to ? ` to ${to}` : ''}`}
          buildFile={buildCsvFile}
        />
      </FilterBar>

      {error ? (
        <ErrorState description={error} onRetry={run} />
      ) : !result ? (
        <EmptyState icon="bi-bar-chart" title="Run a report" description="Choose a store, a report and its options, then press Run." />
      ) : result.rows.length === 0 ? (
        <EmptyState icon="bi-inbox" title="No data" description="This report returned no rows for the selected options." />
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
