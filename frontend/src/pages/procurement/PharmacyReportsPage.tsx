import { useCallback, useEffect, useMemo, useState } from 'react'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { PageHeader } from '../../components/common/PageHeader'
import { tenantService } from '../../services/tenantService'
import { procurementReportsService } from '../../services/procurementReportsService'
import type { Tenant } from '../../types/tenant'
import type {
  PharmacyCompareStoreRow,
  PharmacyCompareSummary,
  PharmacyCompareResponse,
  PharmacyDashboardResponse,
  PharmacyMonthlyRow,
  PharmacyReportSource,
  PharmacyReportStoreSummary,
  PharmacyStoreAnalysisResponse,
} from '../../types/procurementReports'
import './pharmacy-reports.css'

type ReportMode = 'TREND' | 'COMPARE'

type Period = 'CURRENT_MONTH' | 'PREVIOUS_MONTH' | 'LAST_3_MONTHS' | 'LAST_6_MONTHS' | 'LAST_12_MONTHS' | 'FINANCIAL_YEAR' | 'CUSTOM'

const PERIODS: { value: Period; label: string }[] = [
  { value: 'CURRENT_MONTH', label: 'Current Month' },
  { value: 'PREVIOUS_MONTH', label: 'Previous Month' },
  { value: 'LAST_3_MONTHS', label: 'Last 3 Months' },
  { value: 'LAST_6_MONTHS', label: 'Last 6 Months' },
  { value: 'LAST_12_MONTHS', label: 'Last 12 Months' },
  { value: 'FINANCIAL_YEAR', label: 'Financial Year' },
  { value: 'CUSTOM', label: 'Custom Month Range' },
]

const INTERNAL_COMPARE_STORE_CODES = new Set(['NMW'])

function monthKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

function getPeriodRange(period: Period, customFrom: string, customTo: string) {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()
  if (period === 'CUSTOM') return { fromMonth: customFrom, toMonth: customTo }
  if (period === 'CURRENT_MONTH') return { fromMonth: monthKey(now), toMonth: monthKey(now) }
  if (period === 'PREVIOUS_MONTH') {
    const prev = new Date(y, m - 1, 1)
    return { fromMonth: monthKey(prev), toMonth: monthKey(prev) }
  }
  if (period === 'LAST_3_MONTHS') return { fromMonth: monthKey(new Date(y, m - 2, 1)), toMonth: monthKey(now) }
  if (period === 'LAST_6_MONTHS') return { fromMonth: monthKey(new Date(y, m - 5, 1)), toMonth: monthKey(now) }
  if (period === 'LAST_12_MONTHS') return { fromMonth: monthKey(new Date(y, m - 11, 1)), toMonth: monthKey(now) }
  const fy = now.getMonth() + 1 < 4 ? y - 1 : y
  return { fromMonth: `${fy}-04`, toMonth: `${fy + 1}-03` }
}

function money(value: number | null | undefined): string {
  return Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

function percent(value: number | null | undefined): string {
  return `${Number(value || 0).toFixed(2)}%`
}

function ratio(value: number | null | undefined): string {
  return Number(value || 0).toFixed(4)
}

function sourceLabel(value: PharmacyReportSource): string {
  return value === 'STORE_DB' ? 'Store DB' : 'Nexora Sync'
}

function formatMonth(value: string): string {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('en-US', { month: 'short', year: 'numeric' })
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function effectiveDaysInMonth(dateValue: string) {
  const d = new Date(dateValue)
  const now = new Date()
  if (d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()) {
    return now.getDate()
  }
  return new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()
}

function averageDailySales(sales: number | null | undefined, monthValue: string) {
  return Number(sales || 0) / Math.max(effectiveDaysInMonth(monthValue), 1)
}

function paidUpStock(closingStock: number | null | undefined, pendingAmount: number | null | undefined) {
  return Number(closingStock || 0) - Number(pendingAmount || 0)
}

function paidUpStockPercent(closingStock: number | null | undefined, pendingAmount: number | null | undefined) {
  const closing = Number(closingStock || 0)
  if (closing === 0) return 0
  return (paidUpStock(closingStock, pendingAmount) / closing) * 100
}

function growthPercent(previousValue: number, currentValue: number) {
  if (previousValue === 0) return currentValue === 0 ? 0 : 100
  return ((currentValue - previousValue) / previousValue) * 100
}

function isInternalCompareStore(row: PharmacyCompareStoreRow) {
  return INTERNAL_COMPARE_STORE_CODES.has((row.StoreCode || '').trim().toUpperCase())
}

function buildCompareSummary(rows: PharmacyCompareStoreRow[], monthA: string, monthB: string): PharmacyCompareSummary {
  const okRows = rows.filter((row) => row.Status === 'Success')
  const salesA = okRows.reduce((sum, row) => sum + Number(row.SalesA || 0), 0)
  const salesB = okRows.reduce((sum, row) => sum + Number(row.SalesB || 0), 0)
  const stockA = okRows.reduce((sum, row) => sum + Number(row.StockA || 0), 0)
  const stockB = okRows.reduce((sum, row) => sum + Number(row.StockB || 0), 0)
  const pendingA = okRows.reduce((sum, row) => sum + Number(row.PendingA || 0), 0)
  const pendingB = okRows.reduce((sum, row) => sum + Number(row.PendingB || 0), 0)
  const paidUpStockA = okRows.reduce((sum, row) => sum + Number(row.PaidUpStockA || 0), 0)
  const paidUpStockB = okRows.reduce((sum, row) => sum + Number(row.PaidUpStockB || 0), 0)
  const avgDailySalesA = salesA / Math.max(effectiveDaysInMonth(`${monthA}-01`), 1)
  const avgDailySalesB = salesB / Math.max(effectiveDaysInMonth(`${monthB}-01`), 1)

  return {
    StoresIncluded: okRows.length,
    SalesA: salesA,
    SalesB: salesB,
    SalesGrowthPercent: growthPercent(salesA, salesB),
    StockA: stockA,
    StockB: stockB,
    StockGrowthPercent: growthPercent(stockA, stockB),
    PendingA: pendingA,
    PendingB: pendingB,
    PaidUpStockA: paidUpStockA,
    PaidUpStockPercentA: stockA === 0 ? 0 : (paidUpStockA / stockA) * 100,
    PaidUpStockB: paidUpStockB,
    PaidUpStockPercentB: stockB === 0 ? 0 : (paidUpStockB / stockB) * 100,
    AvgDailySalesA: avgDailySalesA,
    AvgDailySalesB: avgDailySalesB,
    AvgDailySalesGrowthPercent: growthPercent(avgDailySalesA, avgDailySalesB),
    WorkingCapitalImpact: (stockB - stockA) + (pendingA - pendingB),
  }
}

function dailySalesGrowth(currentSales: number, previousSales: number, currentMonth: string, previousMonth: string) {
  const currentDaily = Number(currentSales || 0) / effectiveDaysInMonth(currentMonth)
  const previousDaily = Number(previousSales || 0) / effectiveDaysInMonth(previousMonth)
  if (previousDaily === 0) return null
  return ((currentDaily - previousDaily) / previousDaily) * 100
}

function growthBadge(value: number | null) {
  if (value === null) return <span className="pr-dim">-</span>
  if (value > 0) return <span className="pr-growth pr-growth--up">+{value.toFixed(2)}%</span>
  if (value < 0) return <span className="pr-growth pr-growth--down">{value.toFixed(2)}%</span>
  return <span>0.00%</span>
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className={`pr-kpi pr-kpi--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function TrendBars({ rows }: { rows: PharmacyMonthlyRow[] }) {
  const max = Math.max(...rows.map((r) => Number(r.Sales || 0)), 1)
  return (
    <div className="pr-bars" aria-label="Sales trend">
      {rows.map((row) => (
        <div key={row.MonthOfStatistics} className="pr-bar" title={`${formatMonth(row.MonthOfStatistics)}: ${money(row.Sales)}`}>
          <span style={{ height: `${Math.max(6, (Number(row.Sales || 0) / max) * 100)}%` }} />
          <em>{formatMonth(row.MonthOfStatistics).slice(0, 3)}</em>
        </div>
      ))}
    </div>
  )
}

export default function PharmacyReportsPage() {
  const today = useMemo(() => new Date(), [])
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [mode, setMode] = useState<ReportMode>('TREND')
  const [source, setSource] = useState<PharmacyReportSource>('NEXORA')
  const [period, setPeriod] = useState<Period>('LAST_12_MONTHS')
  const [customFrom, setCustomFrom] = useState(monthKey(new Date(today.getFullYear() - 1, today.getMonth(), 1)))
  const [customTo, setCustomTo] = useState(monthKey(today))
  const [monthA, setMonthA] = useState(monthKey(new Date(today.getFullYear() - 1, today.getMonth(), 1)))
  const [monthB, setMonthB] = useState(monthKey(today))
  const [dashboard, setDashboard] = useState<PharmacyDashboardResponse | null>(null)
  const [compare, setCompare] = useState<PharmacyCompareResponse | null>(null)
  const [analysis, setAnalysis] = useState<PharmacyStoreAnalysisResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const range = useMemo(() => getPeriodRange(period, customFrom, customTo), [period, customFrom, customTo])

  useEffect(() => {
    tenantService.list()
      .then((rows) => {
        const active = rows.filter((t) => t.is_active)
        setTenants(active)
        if (active.length) setTenantId((cur) => cur || active[0].tenant_id)
      })
      .catch(() => setTenants([]))
  }, [])

  const loadDashboard = useCallback(() => {
    if (!tenantId || !range.fromMonth || !range.toMonth) return
    setLoading(true)
    setError(null)
    setAnalysis(null)
    procurementReportsService.dashboard(tenantId, range.fromMonth, range.toMonth, source)
      .then(setDashboard)
      .catch((e) => {
        setDashboard(null)
        setError(e instanceof Error ? e.message : 'Failed to load pharmacy reports.')
      })
      .finally(() => setLoading(false))
  }, [tenantId, range.fromMonth, range.toMonth, source])

  const loadCompare = useCallback(() => {
    if (!tenantId || !monthA || !monthB) return
    setLoading(true)
    setError(null)
    procurementReportsService.compare(tenantId, monthA, monthB, source)
      .then(setCompare)
      .catch((e) => {
        setCompare(null)
        setError(e instanceof Error ? e.message : 'Failed to load month compare report.')
      })
      .finally(() => setLoading(false))
  }, [tenantId, monthA, monthB, source])

  const generate = mode === 'COMPARE' ? loadCompare : loadDashboard

  useEffect(() => {
    if (mode !== 'TREND') return
    const timer = window.setTimeout(loadDashboard, 0)
    return () => window.clearTimeout(timer)
  }, [mode, loadDashboard])

  useEffect(() => {
    if (mode !== 'COMPARE') return
    const timer = window.setTimeout(loadCompare, 0)
    return () => window.clearTimeout(timer)
  }, [mode, loadCompare])

  const sortedAnalysisRows = useMemo(
    () => [...(analysis?.rows ?? [])].sort((a, b) => new Date(a.MonthOfStatistics).getTime() - new Date(b.MonthOfStatistics).getTime()),
    [analysis],
  )

  const comparePrimaryStores = useMemo(
    () => (compare?.stores ?? []).filter((row) => !isInternalCompareStore(row)),
    [compare],
  )

  const compareInternalStores = useMemo(
    () => (compare?.stores ?? []).filter((row) => isInternalCompareStore(row)),
    [compare],
  )

  const compareDisplaySummary = useMemo(
    () => (compare ? buildCompareSummary(comparePrimaryStores, compare.month_a, compare.month_b) : null),
    [compare, comparePrimaryStores],
  )

  const analysisTotals = useMemo(() => {
    if (sortedAnalysisRows.length === 0) return null
    const totalSales = sortedAnalysisRows.reduce((sum, r) => sum + Number(r.Sales || 0), 0)
    const totalPurchase = sortedAnalysisRows.reduce((sum, r) => sum + Number(r.Purchase || 0), 0)
    const gpAverage = sortedAnalysisRows.reduce((sum, r) => sum + Number(r.GPPercent || 0), 0) / sortedAnalysisRows.length
    const best = sortedAnalysisRows.reduce((prev, cur) => (Number(cur.Sales || 0) > Number(prev.Sales || 0) ? cur : prev), sortedAnalysisRows[0])
    const first = sortedAnalysisRows[0]
    const last = sortedAnalysisRows[sortedAnalysisRows.length - 1]
    const previous = sortedAnalysisRows[sortedAnalysisRows.length - 2] ?? sortedAnalysisRows[0]
    return {
      totalSales,
      totalPurchase,
      gpAverage,
      bestMonth: formatMonth(best.MonthOfStatistics),
      openingStock: first.OpeningStock,
      closingStock: last.ClosingStock,
      supplierPending: last.PendingAmount,
      paidUpStock: paidUpStock(last.ClosingStock, last.PendingAmount),
      paidUpStockPercent: paidUpStockPercent(last.ClosingStock, last.PendingAmount),
      averageDailySales: totalSales / Math.max(sortedAnalysisRows.reduce((sum, row) => sum + effectiveDaysInMonth(row.MonthOfStatistics), 0), 1),
      workingCapitalImpact: (Number(last.ClosingStock || 0) - Number(first.OpeningStock || 0)) + (Number(first.PendingAmount || 0) - Number(last.PendingAmount || 0)),
      lastMonthGrowth: dailySalesGrowth(last.Sales, previous.Sales, last.MonthOfStatistics, previous.MonthOfStatistics),
    }
  }, [sortedAnalysisRows])

  const openStore = (row: PharmacyReportStoreSummary) => {
    setAnalysisLoading(true)
    setError(null)
    procurementReportsService.storeAnalysis(tenantId, row.StoreId, range.fromMonth, range.toMonth, source)
      .then(setAnalysis)
      .catch((e) => {
        setAnalysis(null)
        setError(e instanceof Error ? e.message : 'Failed to load store analysis.')
      })
      .finally(() => setAnalysisLoading(false))
  }

  const exportDashboard = async () => {
    if (!tenantId) return
    if (mode === 'COMPARE') {
      const blob = await procurementReportsService.compareExcel(tenantId, monthA, monthB, source)
      downloadBlob(blob, `Month_Compare_${monthA}_vs_${monthB}.xlsx`)
      return
    }
    const blob = await procurementReportsService.dashboardExcel(tenantId, range.fromMonth, range.toMonth, source)
    downloadBlob(blob, `All_Store_Summary_${range.fromMonth}_${range.toMonth}.xlsx`)
  }

  const exportStore = async () => {
    if (!tenantId || !analysis) return
    const blob = await procurementReportsService.storeAnalysisExcel(tenantId, analysis.store_id, range.fromMonth, range.toMonth, source)
    downloadBlob(blob, `${analysis.store_code}_Monthly_Analysis_${range.fromMonth}_${range.toMonth}.xlsx`)
  }

  return (
    <div className="container-fluid px-0 pr">
      <PageHeader title="Pharmacy Reports" breadcrumb={['Procurement', 'Pharmacy Reports']} />

      <div className="pr-toolbar">
        <select className="form-select form-select-sm" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          {tenants.length === 0 && <option value="">Loading...</option>}
          {tenants.map((tenant) => <option key={tenant.tenant_id} value={tenant.tenant_id}>{tenant.tenant_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Report mode" value={mode} onChange={(e) => setMode(e.target.value as ReportMode)}>
          <option value="TREND">Trend</option>
          <option value="COMPARE">Month Compare</option>
        </select>
        <select className="form-select form-select-sm" aria-label="Report source" value={source} onChange={(e) => setSource(e.target.value as PharmacyReportSource)}>
          <option value="NEXORA">Nexora Sync</option>
          <option value="STORE_DB">Store DB</option>
        </select>
        {mode === 'TREND' ? (
          <>
            <select className="form-select form-select-sm" aria-label="Period" value={period} onChange={(e) => setPeriod(e.target.value as Period)}>
              {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            {period === 'CUSTOM' && (
              <>
                <input type="month" className="form-control form-control-sm" aria-label="From month" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} />
                <input type="month" className="form-control form-control-sm" aria-label="To month" value={customTo} onChange={(e) => setCustomTo(e.target.value)} />
              </>
            )}
          </>
        ) : (
          <>
            <input type="month" className="form-control form-control-sm" aria-label="Month A" value={monthA} onChange={(e) => setMonthA(e.target.value)} />
            <span className="pr-vs">vs</span>
            <input type="month" className="form-control form-control-sm" aria-label="Month B" value={monthB} onChange={(e) => setMonthB(e.target.value)} />
          </>
        )}
        <button className="btn btn-primary btn-sm" disabled={!tenantId || loading} onClick={generate}>
          <i className="bi bi-play-fill" /> {loading ? 'Loading...' : 'Generate'}
        </button>
        <button
          className="btn btn-outline-secondary btn-sm"
          disabled={mode === 'COMPARE' ? !compare?.stores.length : !dashboard?.stores.length}
          onClick={exportDashboard}
        >
          <i className="bi bi-file-earmark-excel" /> Excel
        </button>
        <button className="btn btn-outline-secondary btn-sm" onClick={() => window.print()}>
          <i className="bi bi-printer" /> PDF
        </button>
      </div>

      {error && <ErrorState description={error} onRetry={generate} />}

      {mode === 'COMPARE' ? (
        !compare && !error ? (
          <EmptyState icon="bi-bar-chart" title="Loading comparison" description="The month compare report will appear here." />
        ) : compare ? (
          <>
            <section className="pr-kpis pr-kpis--compare">
              <Kpi label={`${formatMonth(`${compare.month_a}-01`)} Total Sales`} value={money(compareDisplaySummary?.SalesA)} tone="sales" />
              <Kpi label={`${formatMonth(`${compare.month_b}-01`)} Total Sales`} value={money(compareDisplaySummary?.SalesB)} tone="sales" />
              <Kpi label="Avg Sales / Day" value={`${money(compareDisplaySummary?.AvgDailySalesA)} -> ${money(compareDisplaySummary?.AvgDailySalesB)}`} tone="purchase" />
              <Kpi label="Closing Stock Movement" value={`${money(compareDisplaySummary?.StockA)} -> ${money(compareDisplaySummary?.StockB)}`} tone="stock" />
              <Kpi label="Supplier Pending Movement" value={`${money(compareDisplaySummary?.PendingA)} -> ${money(compareDisplaySummary?.PendingB)}`} tone="pending" />
              <Kpi label="Stores Included" value={String(compareDisplaySummary?.StoresIncluded ?? 0)} tone="invoice" />
            </section>

            <section className="pr-gridwrap">
              <table className="pr-table pr-table--compare">
                <thead>
                  <tr>
                    <th>Store</th>
                    <th className="pr-num">Sales<br />{formatMonth(`${compare.month_a}-01`)}</th>
                    <th className="pr-num">Sales<br />{formatMonth(`${compare.month_b}-01`)}</th>
                    <th className="pr-num">Sales Growth %</th>
                    <th className="pr-num">Avg Sales / Day<br />{formatMonth(`${compare.month_a}-01`)}</th>
                    <th className="pr-num">Avg Sales / Day<br />{formatMonth(`${compare.month_b}-01`)}</th>
                    <th className="pr-num">Avg Sales / Day Growth %</th>
                    <th className="pr-num">Closing Stock<br />{formatMonth(`${compare.month_a}-01`)}</th>
                    <th className="pr-num">Closing Stock<br />{formatMonth(`${compare.month_b}-01`)}</th>
                    <th className="pr-num">Stock Growth %</th>
                    <th className="pr-num">Paid-up Stock %<br />{formatMonth(`${compare.month_a}-01`)}</th>
                    <th className="pr-num">Paid-up Stock %<br />{formatMonth(`${compare.month_b}-01`)}</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {comparePrimaryStores.map((row) => (
                    <tr key={row.StoreId}>
                      <td><strong>{row.Store}</strong><span>{row.StoreCode} | {sourceLabel(row.Source ?? compare.source)}</span></td>
                      <td className="pr-num">{money(row.SalesA)}</td>
                      <td className="pr-num">{money(row.SalesB)}</td>
                      <td className="pr-num">{growthBadge(row.SalesGrowthPercent)}</td>
                      <td className="pr-num">{money(row.AvgDailySalesA)}</td>
                      <td className="pr-num">{money(row.AvgDailySalesB)}</td>
                      <td className="pr-num">{growthBadge(row.AvgDailySalesGrowthPercent)}</td>
                      <td className="pr-num">{money(row.StockA)}</td>
                      <td className="pr-num">{money(row.StockB)}</td>
                      <td className="pr-num">{growthBadge(row.StockGrowthPercent)}</td>
                      <td className="pr-num">{percent(row.PaidUpStockPercentA)}</td>
                      <td className="pr-num">{percent(row.PaidUpStockPercentB)}</td>
                      <td>
                        <span className={`pr-status ${row.Status === 'Success' ? 'pr-status--ok' : 'pr-status--bad'}`}>
                          {row.Status === 'Success' ? 'Connected' : 'Failed'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  <tr className="pr-totalrow">
                    <td><strong>Total</strong><span>Network stores only (NMW excluded)</span></td>
                    <td className="pr-num">{money(compareDisplaySummary?.SalesA)}</td>
                    <td className="pr-num">{money(compareDisplaySummary?.SalesB)}</td>
                    <td className="pr-num">{growthBadge(compareDisplaySummary?.SalesGrowthPercent ?? null)}</td>
                    <td className="pr-num">{money(compareDisplaySummary?.AvgDailySalesA)}</td>
                    <td className="pr-num">{money(compareDisplaySummary?.AvgDailySalesB)}</td>
                    <td className="pr-num">{growthBadge(compareDisplaySummary?.AvgDailySalesGrowthPercent ?? null)}</td>
                    <td className="pr-num">{money(compareDisplaySummary?.StockA)}</td>
                    <td className="pr-num">{money(compareDisplaySummary?.StockB)}</td>
                    <td className="pr-num">{growthBadge(compareDisplaySummary?.StockGrowthPercent ?? null)}</td>
                    <td className="pr-num">{percent(compareDisplaySummary?.PaidUpStockPercentA)}</td>
                    <td className="pr-num">{percent(compareDisplaySummary?.PaidUpStockPercentB)}</td>
                    <td><span className="pr-status pr-status--ok">Summary</span></td>
                  </tr>
                </tbody>
              </table>
            </section>

            {compareInternalStores.length > 0 && (
              <section className="pr-compare-summary">
                <div className="pr-analysis__head">
                  <div>
                    <h2>Internal Store Sales</h2>
                    <p>NMW is shown separately and is excluded from the network total sales and average sales/day.</p>
                  </div>
                </div>
                <section className="pr-gridwrap">
                  <table className="pr-table pr-table--compare">
                    <thead>
                      <tr>
                        <th>Store</th>
                        <th className="pr-num">Sales<br />{formatMonth(`${compare.month_a}-01`)}</th>
                        <th className="pr-num">Sales<br />{formatMonth(`${compare.month_b}-01`)}</th>
                        <th className="pr-num">Sales Growth %</th>
                        <th className="pr-num">Avg Sales / Day<br />{formatMonth(`${compare.month_a}-01`)}</th>
                        <th className="pr-num">Avg Sales / Day<br />{formatMonth(`${compare.month_b}-01`)}</th>
                        <th className="pr-num">Avg Sales / Day Growth %</th>
                        <th className="pr-num">Closing Stock<br />{formatMonth(`${compare.month_a}-01`)}</th>
                        <th className="pr-num">Closing Stock<br />{formatMonth(`${compare.month_b}-01`)}</th>
                        <th className="pr-num">Stock Growth %</th>
                        <th className="pr-num">Paid-up Stock %<br />{formatMonth(`${compare.month_a}-01`)}</th>
                        <th className="pr-num">Paid-up Stock %<br />{formatMonth(`${compare.month_b}-01`)}</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {compareInternalStores.map((row) => (
                        <tr key={row.StoreId}>
                          <td><strong>{row.Store}</strong><span>{row.StoreCode} | {sourceLabel(row.Source ?? compare.source)}</span></td>
                          <td className="pr-num">{money(row.SalesA)}</td>
                          <td className="pr-num">{money(row.SalesB)}</td>
                          <td className="pr-num">{growthBadge(row.SalesGrowthPercent)}</td>
                          <td className="pr-num">{money(row.AvgDailySalesA)}</td>
                          <td className="pr-num">{money(row.AvgDailySalesB)}</td>
                          <td className="pr-num">{growthBadge(row.AvgDailySalesGrowthPercent)}</td>
                          <td className="pr-num">{money(row.StockA)}</td>
                          <td className="pr-num">{money(row.StockB)}</td>
                          <td className="pr-num">{growthBadge(row.StockGrowthPercent)}</td>
                          <td className="pr-num">{percent(row.PaidUpStockPercentA)}</td>
                          <td className="pr-num">{percent(row.PaidUpStockPercentB)}</td>
                          <td>
                            <span className={`pr-status ${row.Status === 'Success' ? 'pr-status--ok' : 'pr-status--bad'}`}>
                              {row.Status === 'Success' ? 'Connected' : 'Failed'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              </section>
            )}

            <section className="pr-compare-summary">
              <div className="pr-compare-summary__grid">
                <div><span>{formatMonth(`${compare.month_a}-01`)} Closing Stock</span><strong>{money(compareDisplaySummary?.StockA)}</strong></div>
                <div><span>{formatMonth(`${compare.month_b}-01`)} Closing Stock</span><strong>{money(compareDisplaySummary?.StockB)}</strong></div>
                <div><span>{formatMonth(`${compare.month_a}-01`)} Supplier Pending</span><strong>{money(compareDisplaySummary?.PendingA)}</strong></div>
                <div><span>{formatMonth(`${compare.month_b}-01`)} Supplier Pending</span><strong>{money(compareDisplaySummary?.PendingB)}</strong></div>
                <div><span>{formatMonth(`${compare.month_a}-01`)} Paid-up Stock %</span><strong>{percent(compareDisplaySummary?.PaidUpStockPercentA)}</strong></div>
                <div><span>{formatMonth(`${compare.month_b}-01`)} Paid-up Stock %</span><strong>{percent(compareDisplaySummary?.PaidUpStockPercentB)}</strong></div>
                <div><span>{formatMonth(`${compare.month_a}-01`)} Avg Sales / Day</span><strong>{money(compareDisplaySummary?.AvgDailySalesA)}</strong></div>
                <div><span>{formatMonth(`${compare.month_b}-01`)} Avg Sales / Day</span><strong>{money(compareDisplaySummary?.AvgDailySalesB)}</strong></div>
              </div>
              <p className="pr-compare-note">
                Working capital impact for this compare: <strong>{money(compareDisplaySummary?.WorkingCapitalImpact)}</strong>.
                This uses stock increase plus supplier pending reduction. It is a cash/stock movement indicator, not accounting profit.
              </p>
            </section>
          </>
        ) : null
      ) : !dashboard && !error ? (
        <EmptyState icon="bi-bar-chart" title="Loading reports" description="The pharmacy report dashboard will appear here." />
      ) : dashboard ? (
        <>
          <section className="pr-kpis">
            <Kpi label="Total Sales" value={money(dashboard.kpi.Sales)} tone="sales" />
            <Kpi label="Total Purchase" value={money(dashboard.kpi.Purchase)} tone="purchase" />
            <Kpi label="Closing Stock" value={money(dashboard.kpi.ClosingStock)} tone="stock" />
            <Kpi label="Supplier Pending" value={money(dashboard.kpi.PendingAmount)} tone="pending" />
            <Kpi label="Pending Invoices" value={money(dashboard.kpi.PendingInvoices)} tone="invoice" />
            <Kpi label="Average GP %" value={percent(dashboard.kpi.GPPercent)} tone="gp" />
          </section>

          <div className="pr-summary">
            <span>Source: <strong>{sourceLabel(dashboard.source)}</strong></span>
            <span>Period: <strong>{range.fromMonth}</strong> to <strong>{range.toMonth}</strong></span>
          </div>

          <section className="pr-gridwrap">
            <table className="pr-table">
              <thead>
                <tr>
                  <th>Store</th>
                  <th className="pr-num">Sales</th>
                  <th className="pr-num">Purchase</th>
                  <th className="pr-num">Purchase Return</th>
                  <th className="pr-num">Closing Stock</th>
                  <th className="pr-num">Pending Amount</th>
                  <th className="pr-num">Pending Invoices</th>
                  <th className="pr-num">Purchase/Sales</th>
                  <th className="pr-num">Stock/Pending</th>
                  <th className="pr-num">GP</th>
                  <th className="pr-num">GP %</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.stores.map((row) => (
                  <tr key={row.StoreId}>
                    <td><strong>{row.Store}</strong><span>{row.StoreCode}</span></td>
                    <td className="pr-num">{money(row.Sales)}</td>
                    <td className="pr-num">{money(row.Purchase)}</td>
                    <td className="pr-num">{money(row.PurchaseReturn)}</td>
                    <td className="pr-num">{money(row.ClosingStock)}</td>
                    <td className="pr-num">{money(row.PendingAmount)}</td>
                    <td className="pr-num">{money(row.PendingInvoices)}</td>
                    <td className="pr-num">{ratio(row.PurchaseSalesRatio)}</td>
                    <td className="pr-num">{ratio(row.StockPendingRatio)}</td>
                    <td className="pr-num">{money(row.GP)}</td>
                    <td className="pr-num">{percent(row.GPPercent)}</td>
                    <td>
                      <span className={`pr-status ${row.Status === 'Success' ? 'pr-status--ok' : 'pr-status--bad'}`}>
                        {row.Status === 'Success' ? 'Connected' : 'Failed'}
                      </span>
                    </td>
                    <td>
                      <button className="btn btn-sm btn-outline-primary" disabled={analysisLoading} onClick={() => openStore(row)}>
                        Monthly Analysis
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}

      {analysis && analysisTotals && (
        <section className="pr-analysis" id="reportArea">
          <div className="pr-analysis__head">
            <div>
              <h2>Store Monthly Analysis</h2>
              <p>{analysis.store_name} | Code: {analysis.store_code} | {range.fromMonth} to {range.toMonth}</p>
            </div>
            <div className="pr-actions">
              <button className="btn btn-sm btn-outline-secondary" onClick={exportStore}><i className="bi bi-file-earmark-excel" /> Excel</button>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => window.print()}><i className="bi bi-printer" /> PDF</button>
            </div>
          </div>

          <section className="pr-kpis pr-kpis--compact">
            <Kpi label="Total Sales" value={money(analysisTotals.totalSales)} tone="sales" />
            <Kpi label="Purchase" value={money(analysisTotals.totalPurchase)} tone="purchase" />
            <Kpi label="Opening Stock" value={money(analysisTotals.openingStock)} tone="stock" />
            <Kpi label="Closing Stock" value={money(analysisTotals.closingStock)} tone="pending" />
            <Kpi label="GP %" value={percent(analysisTotals.gpAverage)} tone="gp" />
            <Kpi label="Best Month" value={analysisTotals.bestMonth} tone="invoice" />
          </section>

          <div className="pr-summary">
            <span>Source: <strong>{sourceLabel(analysis.source)}</strong></span>
            <span>Months: <strong>{sortedAnalysisRows.length}</strong></span>
            <span>Best Month: <strong>{analysisTotals.bestMonth}</strong></span>
            <span>Last Month Growth: <strong>{growthBadge(analysisTotals.lastMonthGrowth)}</strong></span>
          </div>

          <div className="pr-chart">
            <h3>Sales Trend</h3>
            <TrendBars rows={sortedAnalysisRows} />
          </div>

          <section className="pr-gridwrap">
            <table className="pr-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th className="pr-num">Sales</th>
                  <th className="pr-num">Avg Sales / Day</th>
                  <th className="pr-num">Sales Growth %</th>
                  <th className="pr-num">Purchase</th>
                  <th className="pr-num">Opening Stock</th>
                  <th className="pr-num">Closing Stock</th>
                  <th className="pr-num">Stock Growth %</th>
                  <th className="pr-num">Pending Amount</th>
                  <th className="pr-num">Paid-up Stock</th>
                  <th className="pr-num">Paid-up Stock %</th>
                  <th className="pr-num">GP</th>
                  <th className="pr-num">GP %</th>
                </tr>
              </thead>
              <tbody>
                {sortedAnalysisRows.map((row, index) => {
                  const previous = sortedAnalysisRows[index - 1]
                  const salesGrowth = previous
                    ? dailySalesGrowth(row.Sales, previous.Sales, row.MonthOfStatistics, previous.MonthOfStatistics)
                    : null
                  const stockGrowth = previous && Number(previous.ClosingStock || 0) !== 0
                    ? ((Number(row.ClosingStock || 0) - Number(previous.ClosingStock || 0)) / Number(previous.ClosingStock || 0)) * 100
                    : null
                  return (
                    <tr key={row.MonthOfStatistics}>
                      <td>{formatMonth(row.MonthOfStatistics)}</td>
                      <td className="pr-num">{money(row.Sales)}</td>
                      <td className="pr-num">{money(averageDailySales(row.Sales, row.MonthOfStatistics))}</td>
                      <td className="pr-num">{growthBadge(salesGrowth)}</td>
                      <td className="pr-num">{money(row.Purchase)}</td>
                      <td className="pr-num">{money(row.OpeningStock)}</td>
                      <td className="pr-num">{money(row.ClosingStock)}</td>
                      <td className="pr-num">{growthBadge(stockGrowth)}</td>
                      <td className="pr-num">{money(row.PendingAmount)}</td>
                      <td className="pr-num">{money(paidUpStock(row.ClosingStock, row.PendingAmount))}</td>
                      <td className="pr-num">{percent(paidUpStockPercent(row.ClosingStock, row.PendingAmount))}</td>
                      <td className="pr-num">{money(row.GP)}</td>
                      <td className="pr-num">{percent(row.GPPercent)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="pr-compare-summary">
            <div className="pr-compare-summary__grid">
              <div><span>{analysisTotals.bestMonth} Best Month</span><strong>{money(sortedAnalysisRows.reduce((best, row) => Math.max(best, Number(row.Sales || 0)), 0))}</strong></div>
              <div><span>{formatMonth(sortedAnalysisRows[sortedAnalysisRows.length - 1].MonthOfStatistics)} Closing Stock</span><strong>{money(analysisTotals.closingStock)}</strong></div>
              <div><span>{formatMonth(sortedAnalysisRows[sortedAnalysisRows.length - 1].MonthOfStatistics)} Supplier Pending</span><strong>{money(analysisTotals.supplierPending)}</strong></div>
              <div><span>{formatMonth(sortedAnalysisRows[sortedAnalysisRows.length - 1].MonthOfStatistics)} Paid-up Stock %</span><strong>{percent(analysisTotals.paidUpStockPercent)}</strong></div>
              <div><span>Average Sales / Day</span><strong>{money(analysisTotals.averageDailySales)}</strong></div>
              <div><span>Paid-up Stock Value</span><strong>{money(analysisTotals.paidUpStock)}</strong></div>
            </div>
            <p className="pr-compare-note">
              Working capital movement across the selected period: <strong>{money(analysisTotals.workingCapitalImpact)}</strong>.
              This combines stock increase and pending reduction, so it helps judge stock strength and collection quality, but it should not be treated as profit by itself.
            </p>
          </section>
        </section>
      )}
    </div>
  )
}
