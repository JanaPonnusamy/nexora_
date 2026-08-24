import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { FilterBar } from '../../design-system/components/FilterBar'
import { tenantService } from '../../services/tenantService'
import { expiryReportService } from '../../services/expiryReportService'
import type { Tenant } from '../../types/tenant'
import type { ExpiryColumn, ExpiryResult } from '../../types/expiryReport'
import { money, num, date } from '../../components/stock/format'
import { exportExpiryExcel } from './exportExpiryExcel'
import '../reports.css'

type View = 'stores' | 'suppliers' | 'supplier' | 'products'
type SupplierTab = 'acks' | 'pending'

interface StoreCtx { id: string; name: string }
interface SupplierCtx { code: string; name: string }

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

  const [view, setView] = useState<View>('stores')
  const [supplierTab, setSupplierTab] = useState<SupplierTab>('acks')
  const [store, setStore] = useState<StoreCtx | null>(null)
  const [supplier, setSupplier] = useState<SupplierCtx | null>(null)
  const [ack, setAck] = useState<string | null>(null)

  const [result, setResult] = useState<ExpiryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    tenantService.list()
      .then((rows) => {
        const active = rows.filter((t) => t.is_active)
        setTenants(active)
        if (active.length) setTenantId((cur) => cur || active[0].tenant_id)
      })
      .catch(() => setTenants([]))
  }, [])

  const tenantName = useMemo(
    () => tenants.find((t) => t.tenant_id === tenantId)?.tenant_name ?? '',
    [tenants, tenantId],
  )

  // Load the data for the current view.
  const load = useCallback(() => {
    if (!tenantId) return
    setLoading(true)
    setError(null)
    let p: Promise<ExpiryResult>
    if (view === 'stores') p = expiryReportService.storeSummary(tenantId)
    else if (view === 'suppliers' && store) p = expiryReportService.supplierSummary(tenantId, store.id)
    else if (view === 'supplier' && store && supplier) {
      p = supplierTab === 'acks'
        ? expiryReportService.supplierAcks(tenantId, store.id, supplier.code)
        : expiryReportService.supplierPending(tenantId, store.id, supplier.code)
    } else if (view === 'products' && store && ack) p = expiryReportService.ackProducts(tenantId, store.id, ack)
    else { setLoading(false); return }

    p.then(setResult)
      .catch((err) => { setResult(null); setError(err instanceof Error ? err.message : 'Failed to load') })
      .finally(() => setLoading(false))
  }, [tenantId, view, store, supplier, supplierTab, ack])

  useEffect(() => { load() }, [load])

  // Reset the drill path whenever the tenant changes.
  useEffect(() => {
    setView('stores'); setStore(null); setSupplier(null); setAck(null)
  }, [tenantId])

  // --- Drill navigation ----------------------------------------------------
  const openStore = (row: Record<string, unknown>) => {
    setStore({ id: String(row.StoreId), name: String(row.StoreName) })
    setSupplier(null); setAck(null); setView('suppliers')
  }
  const openSupplier = (row: Record<string, unknown>) => {
    setSupplier({ code: String(row.SupplierCode), name: String(row.SupplierName) })
    setAck(null); setSupplierTab('acks'); setView('supplier')
  }
  const openAck = (row: Record<string, unknown>) => {
    setAck(String(row.AckNumber)); setView('products')
  }
  const goStores = () => { setView('stores'); setStore(null); setSupplier(null); setAck(null) }
  const goSuppliers = () => { setView('suppliers'); setSupplier(null); setAck(null) }
  const goSupplier = () => { setView('supplier'); setAck(null) }

  const rowClick = (row: Record<string, unknown>): (() => void) | undefined => {
    if (view === 'stores') return () => openStore(row)
    if (view === 'suppliers') return () => openSupplier(row)
    if (view === 'supplier' && supplierTab === 'acks') return () => openAck(row)
    return undefined
  }
  const drillable = view === 'stores' || view === 'suppliers' || (view === 'supplier' && supplierTab === 'acks')

  // --- Excel export --------------------------------------------------------
  const levelTitle = useMemo(() => {
    if (view === 'stores') return `Expiry — Store Summary — ${tenantName}`
    if (view === 'suppliers') return `Expiry — Suppliers — ${store?.name ?? ''}`
    if (view === 'supplier') return `Expiry — ${supplier?.name ?? ''} — ${supplierTab === 'acks' ? 'Acknowledgements' : 'Pending Details'}`
    if (view === 'products') return `Expiry — Ack ${ack} — Products`
    return 'Expiry Report'
  }, [view, tenantName, store, supplier, supplierTab, ack])

  const exportExcel = () => {
    if (!result || result.rows.length === 0) return
    const safe = (s: string) => s.replace(/[^\w.-]+/g, '_').slice(0, 40)
    void exportExpiryExcel({
      columns: result.columns,
      rows: result.rows,
      summary: result.summary,
      sheetName: view,
      fileName: safe(levelTitle),
      title: levelTitle,
    })
  }

  return (
    <div className="container-fluid px-0 rpt">
      <PageHeader title="Expiry Report" breadcrumb={['Expiry Report']} />

      <FilterBar compact className="rpt-bar" ariaLabel="Expiry report filters">
        <select className="form-select form-select-sm" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          {tenants.length === 0 && <option value="">Loading…</option>}
          {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
        </select>
        <button className="btn btn-outline-secondary btn-sm" disabled={!result || result.rows.length === 0} onClick={exportExcel}>
          <i className="bi bi-file-earmark-excel" /> Export Excel
        </button>
      </FilterBar>

      {/* Breadcrumb drill path */}
      <div className="expiry-crumbs" role="navigation" aria-label="Drill path">
        <button className={`expiry-crumb${view === 'stores' ? ' active' : ''}`} onClick={goStores}>Stores</button>
        {store && <><span className="sep">/</span><button className={`expiry-crumb${view === 'suppliers' ? ' active' : ''}`} onClick={goSuppliers}>{store.name.trim()}</button></>}
        {supplier && <><span className="sep">/</span><button className={`expiry-crumb${view === 'supplier' ? ' active' : ''}`} onClick={goSupplier}>{supplier.name.trim()}</button></>}
        {ack && view === 'products' && <><span className="sep">/</span><span className="expiry-crumb active">Ack {ack}</span></>}
      </div>

      {/* Tabs at supplier level: Acknowledgements | Pending details */}
      {view === 'supplier' && (
        <div className="expiry-tabs">
          <button className={`expiry-tab${supplierTab === 'acks' ? ' active' : ''}`} onClick={() => setSupplierTab('acks')}>Acknowledgements</button>
          <button className={`expiry-tab${supplierTab === 'pending' ? ' active' : ''}`} onClick={() => setSupplierTab('pending')}>Pending details</button>
        </div>
      )}

      {error ? (
        <ErrorState description={error} onRetry={load} />
      ) : loading && !result ? (
        <EmptyState icon="bi-hourglass-split" title="Loading…" description="Fetching expiry data." />
      ) : !result || result.rows.length === 0 ? (
        <EmptyState icon="bi-inbox" title="No data" description="No expiry records for this selection." />
      ) : (
        <div className="rpt-tablewrap">
          <table className="rpt-table">
            <thead>
              <tr>{result.columns.map((c) => <th key={c.key} className={`rpt-${c.align}`}>{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => {
                const onClick = rowClick(row)
                return (
                  <tr
                    key={i}
                    className={onClick ? 'expiry-row-link' : undefined}
                    onClick={onClick}
                    title={onClick ? 'Click to drill in' : undefined}
                  >
                    {result.columns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(row[c.key], c)}</td>)}
                  </tr>
                )
              })}
              {result.summary && (
                <tr className="rpt-total">
                  {result.columns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(result.summary![c.key], c)}</td>)}
                </tr>
              )}
            </tbody>
          </table>
          {drillable && <div className="expiry-hint"><i className="bi bi-info-circle" /> Click a row to drill in.</div>}
        </div>
      )}
    </div>
  )
}
