import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { storeService } from '../../services/storeService'
import { tenantService } from '../../services/tenantService'
import { labelExporterService } from '../../services/labelExporterService'
import type {
  IncludeLabel,
  LabelSearchRow,
  LabelTrendRow,
  StockFilter,
  UnitDescriptionMode,
} from '../../types/labelExporter'
import type { TenantStore } from '../../types/store'
import type { Tenant } from '../../types/tenant'
import { buildPreparedLabelItem, printLabelSheet, type PreparedLabelItem } from './printLabelSheet'
import { canChangeLabelExportStore, isSuperAdmin } from './labelExportAccess'
import { useAuth } from '../../hooks/useAuth'
import { FilterBar } from '../../design-system/components/FilterBar'
import './label-export.css'

const REMARKS_PRESETS = [
  'Counter',
  'Consumer',
  'SYP',
  'Cold Storage',
  'Fragile',
  'High Value',
  'Fast Moving',
  'Slow Moving',
  'Check Unit Description',
]

function StockFilterLabel({ value }: { value: StockFilter }) {
  const labels: Record<StockFilter, string> = {
    all: 'Stock > 0 or zero stock sale within 90 days',
    in_stock: 'Stock > 0 only',
    zero_recent_sale: 'Stock = 0 and sale within 90 days',
    zero_stale: 'Stock = 0 and no sale in over 90 days',
  }
  return <>{labels[value]}</>
}

export default function LabelExporterPage() {
  const { user } = useAuth()
  const canChangeStore = canChangeLabelExportStore(user)
  const admin = isSuperAdmin(user)

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<TenantStore[]>([])
  const [storeId, setStoreId] = useState('')

  const [searchText, setSearchText] = useState('')
  const [startsWith, setStartsWith] = useState('')
  const [unitDescription, setUnitDescription] = useState('')
  const [unitDescriptionMode, setUnitDescriptionMode] = useState<UnitDescriptionMode>('contains')
  const [unitDescriptionOptions, setUnitDescriptionOptions] = useState<string[]>([])
  const [boxNumber, setBoxNumber] = useState('')
  const [stockFilter, setStockFilter] = useState<StockFilter>('all')
  const [onlyNullSublocation, setOnlyNullSublocation] = useState(true)
  const [onlySaleUnitGtOne, setOnlySaleUnitGtOne] = useState(true)

  const [searchRows, setSearchRows] = useState<LabelSearchRow[]>([])
  const [selectedSearchCodes, setSelectedSearchCodes] = useState<Record<string, boolean>>({})
  const [activeSearchIndex, setActiveSearchIndex] = useState(0)
  const [labelList, setLabelList] = useState<PreparedLabelItem[]>([])
  const [activeLabelIndex, setActiveLabelIndex] = useState(0)
  const [lastBoxForLetter, setLastBoxForLetter] = useState<string | null>(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [subLocDrafts, setSubLocDrafts] = useState<Record<string, string>>({})
  const [remarksDrafts, setRemarksDrafts] = useState<Record<string, string>>({})
  const [savingCode, setSavingCode] = useState('')

  const [trendRows, setTrendRows] = useState<LabelTrendRow[]>([])
  const [trendLoading, setTrendLoading] = useState(false)

  const [labelWidthMm, setLabelWidthMm] = useState('50')
  const [labelHeightMm, setLabelHeightMm] = useState('25')
  const [labelColumns, setLabelColumns] = useState('4')
  const [labelGapMm, setLabelGapMm] = useState('2')
  const [labelFontSizePt, setLabelFontSizePt] = useState('8')
  const [showPrintSettings, setShowPrintSettings] = useState(false)

  const searchRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const labelRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const trendRequestRef = useRef(0)

  useEffect(() => {
    tenantService
      .list()
      .then((rows) => {
        const active = rows.filter((row) => row.is_active)
        setTenants(active)
        if (active.length) setTenantId((current) => current || active[0].tenant_id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load tenants'))
  }, [])

  useEffect(() => {
    if (!tenantId) return
    setStoreId('')
    storeService
      .getByTenant(tenantId)
      .then((rows) => {
        setStores(rows)
        const ownStore = rows.find((row) => row.store_id === user?.storeId)
        const defaultStore = (!canChangeStore && ownStore) || ownStore || rows[0]
        if (defaultStore) setStoreId((current) => current || defaultStore.store_id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load stores'))
  }, [tenantId, canChangeStore, user?.storeId])

  useEffect(() => {
    setSelectedSearchCodes({})
    setSearchRows([])
    setActiveSearchIndex(0)
    setUnitDescriptionOptions([])
    setLastBoxForLetter(null)
    setTrendRows([])
  }, [tenantId, storeId])

  useEffect(() => {
    if (boxNumber.trim()) {
      setOnlyNullSublocation(false)
    }
  }, [boxNumber])

  useEffect(() => {
    const row = searchRows[activeSearchIndex]
    if (!row?.product_code) return
    searchRowRefs.current[row.product_code]?.scrollIntoView({ block: 'nearest' })
  }, [activeSearchIndex, searchRows])

  useEffect(() => {
    const item = labelList[activeLabelIndex]
    if (!item?.product_code) return
    labelRowRefs.current[item.product_code]?.scrollIntoView({ block: 'nearest' })
  }, [activeLabelIndex, labelList])

  // Load the sales/purchase trend for whichever row is active.
  useEffect(() => {
    const row = searchRows[activeSearchIndex]
    if (!row?.product_code || !tenantId || !storeId) {
      setTrendRows([])
      return
    }
    const requestId = ++trendRequestRef.current
    setTrendLoading(true)
    labelExporterService
      .getProductTrend(tenantId, storeId, row.product_code)
      .then((result) => {
        if (trendRequestRef.current !== requestId) return
        setTrendRows(Array.isArray(result?.rows) ? result.rows : [])
      })
      .catch(() => {
        if (trendRequestRef.current !== requestId) return
        setTrendRows([])
      })
      .finally(() => {
        if (trendRequestRef.current !== requestId) return
        setTrendLoading(false)
      })
  }, [activeSearchIndex, searchRows, tenantId, storeId])

  async function runSearch() {
    if (!tenantId || !storeId) return
    setLoading(true)
    setError(null)
    try {
      const productResult = await labelExporterService.searchProducts({
        tenantId,
        storeId,
        q: searchText.trim(),
        startsWith: startsWith.trim(),
        unitDescription: unitDescription.trim(),
        unitDescriptionMode,
        boxNumber: boxNumber.trim(),
        stockFilter,
        onlyNullSublocation: boxNumber.trim() ? false : onlyNullSublocation,
        onlySaleUnitGtOne,
      })

      const nextSearchRows = Array.isArray(productResult?.rows) ? productResult.rows : []
      const nextUnitOptions = Array.isArray(productResult?.unit_descriptions) ? productResult.unit_descriptions : []

      setSearchRows(nextSearchRows)
      setUnitDescriptionOptions(nextUnitOptions)
      setLastBoxForLetter(productResult?.last_box_for_letter ?? null)
      setActiveSearchIndex(0)

      const nextSubLoc: Record<string, string> = {}
      const nextRemarks: Record<string, string> = {}
      nextSearchRows.forEach((row) => {
        nextSubLoc[row.product_code] = row.current_sublocation || ''
        nextRemarks[row.product_code] = row.remarks || ''
      })
      setSubLocDrafts(nextSubLoc)
      setRemarksDrafts(nextRemarks)

      if (nextSearchRows[0]?.product_code) selectSearchRow(0, nextSearchRows)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load label data')
    } finally {
      setLoading(false)
    }
  }

  function selectSearchRow(index: number, rows = searchRows) {
    if (index < 0 || index >= rows.length) return
    setActiveSearchIndex(index)
  }

  function toggleSearchRow(productCode: string) {
    setSelectedSearchCodes((current) => ({ ...current, [productCode]: !current[productCode] }))
  }

  function toggleSelectAll(checked: boolean) {
    const next: Record<string, boolean> = {}
    if (checked) {
      searchRows.forEach((row) => {
        if (row.product_code) next[row.product_code] = true
      })
    }
    setSelectedSearchCodes(next)
  }

  function addRowsToLabelList(rows: LabelSearchRow[]) {
    if (rows.length === 0) return
    setLabelList((current) => {
      const existing = new Map(current.map((item) => [item.product_code, item]))
      rows.forEach((row) => {
        const nextItem = buildPreparedLabelItem(row)
        if (!existing.has(nextItem.product_code)) {
          existing.set(nextItem.product_code, nextItem)
        }
      })
      const next = Array.from(existing.values()).sort((a, b) => a.product_name.localeCompare(b.product_name))
      setActiveLabelIndex(Math.max(0, next.length - 1))
      return next
    })
  }

  function addSelectedToLabelList() {
    addRowsToLabelList(searchRows.filter((row) => row.product_code && selectedSearchCodes[row.product_code]))
    setSelectedSearchCodes({})
  }

  function addActiveRowToLabelList() {
    const row = searchRows[activeSearchIndex]
    if (!row) return
    addRowsToLabelList([row])
  }

  function updateLabelItem(productCode: string, patch: Partial<PreparedLabelItem>) {
    setLabelList((current) =>
      current
        .map((item) => (item.product_code === productCode ? { ...item, ...patch } : item))
        .sort((a, b) => a.product_name.localeCompare(b.product_name)),
    )
  }

  function removeLabelItem(productCode: string) {
    setLabelList((current) => {
      const next = current.filter((item) => item.product_code !== productCode)
      setActiveLabelIndex((currentIndex) => Math.max(0, Math.min(currentIndex, next.length - 1)))
      return next
    })
  }

  function patchRow(productCode: string, patch: Partial<LabelSearchRow>) {
    setSearchRows((current) => current.map((row) => (row.product_code === productCode ? { ...row, ...patch } : row)))
  }

  async function setIncludeLabel(row: LabelSearchRow, value: IncludeLabel) {
    const nextValue = row.include_label === value ? null : value
    setSavingCode(row.product_code)
    setError(null)
    try {
      await labelExporterService.updateReview(tenantId, storeId, row.product_code, { include_label: nextValue })
      patchRow(row.product_code, { include_label: nextValue })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save review')
    } finally {
      setSavingCode('')
    }
  }

  async function saveRemarks(row: LabelSearchRow) {
    const draft = (remarksDrafts[row.product_code] || '').trim()
    if (draft === (row.remarks || '')) return
    setSavingCode(row.product_code)
    setError(null)
    try {
      await labelExporterService.updateReview(tenantId, storeId, row.product_code, { remarks: draft })
      patchRow(row.product_code, { remarks: draft || null })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save remarks')
    } finally {
      setSavingCode('')
    }
  }

  async function saveSubLocation(row: LabelSearchRow) {
    const draft = (subLocDrafts[row.product_code] || '').trim()
    if (draft === (row.current_sublocation || '')) return
    setSavingCode(row.product_code)
    setError(null)
    try {
      await labelExporterService.assignSublocation(tenantId, storeId, row.product_code, draft)
      patchRow(row.product_code, { current_sublocation: draft || null })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assign sublocation')
    } finally {
      setSavingCode('')
    }
  }

  const allVisibleSelected = searchRows.length > 0 && searchRows.every((row) => row.product_code && selectedSearchCodes[row.product_code])

  const totalLabels = useMemo(
    () => labelList.reduce((sum, item) => sum + Math.max(1, Number(item.quantity) || 1), 0),
    [labelList],
  )

  const remarksOptions = useMemo(() => {
    const used = searchRows.map((row) => row.remarks).filter((v): v is string => !!v)
    return Array.from(new Set([...REMARKS_PRESETS, ...used]))
  }, [searchRows])

  const activeTrendRow = searchRows[activeSearchIndex]
  const trendMax = useMemo(
    () => Math.max(1, ...trendRows.map((row) => Math.max(row.sale_qty, row.purchase_qty))),
    [trendRows],
  )

  function exportPrint() {
    printLabelSheet(labelList, {
      widthMm: Number(labelWidthMm) || 50,
      heightMm: Number(labelHeightMm) || 25,
      columns: Math.max(1, Number(labelColumns) || 4),
      gapMm: Number(labelGapMm) || 2,
      fontSizePt: Number(labelFontSizePt) || 8,
    })
  }

  function handleSearchGridKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (searchRows.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      selectSearchRow(Math.min(searchRows.length - 1, activeSearchIndex + 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      selectSearchRow(Math.max(0, activeSearchIndex - 1))
    } else if (event.key === 'Enter' && admin) {
      event.preventDefault()
      addActiveRowToLabelList()
    } else if (event.key === ' ' && admin) {
      event.preventDefault()
      const row = searchRows[activeSearchIndex]
      if (row?.product_code) toggleSearchRow(row.product_code)
    }
  }

  function handleLabelListKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (labelList.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveLabelIndex((current) => Math.min(labelList.length - 1, current + 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveLabelIndex((current) => Math.max(0, current - 1))
    } else if (event.key === 'Delete') {
      event.preventDefault()
      const item = labelList[activeLabelIndex]
      if (item) removeLabelItem(item.product_code)
    }
  }

  return (
    <div className="d-flex flex-column gap-3">
      <PageHeader title="Label Exporter" breadcrumb={['Operations', 'Inventory', 'Label Exporter']} />

      <FilterBar compact className="label-export-toolbar label-export-toolbar--compact" ariaLabel="Label export filters">
        <label className="label-export-field">
          <span className="label-export-field__label">Tenant</span>
          <select className="form-select form-select-sm" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading...</option>}
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>
            ))}
          </select>
        </label>

        <label className="label-export-field">
          <span className="label-export-field__label">Store</span>
          <select
            className="form-select form-select-sm"
            value={storeId}
            disabled={!canChangeStore}
            onChange={(e) => setStoreId(e.target.value)}
          >
            {stores.length === 0 && <option value="">Loading...</option>}
            {(canChangeStore ? stores : stores.filter((s) => s.store_id === storeId)).map((s) => (
              <option key={s.store_id} value={s.store_id}>{s.store_code} - {s.store_name}</option>
            ))}
          </select>
        </label>

        <label className="label-export-field label-export-field--search">
          <span className="label-export-field__label">Search</span>
          <input
            className="form-control form-control-sm"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Product / code"
          />
        </label>

        <label className="label-export-field label-export-field--letter">
          <span className="label-export-field__label">Letter</span>
          <input
            className="form-control form-control-sm"
            value={startsWith}
            onChange={(e) => setStartsWith(e.target.value.replace(/[^a-z]/gi, '').toUpperCase().slice(0, 1))}
            placeholder="A"
            maxLength={1}
          />
        </label>

        <label className="label-export-field">
          <span className="label-export-field__label">Unit mode</span>
          <select
            className="form-select form-select-sm"
            value={unitDescriptionMode}
            onChange={(e) => setUnitDescriptionMode(e.target.value as UnitDescriptionMode)}
          >
            <option value="contains">Contains</option>
            <option value="exact">Exact</option>
            <option value="null">Blank / NULL</option>
          </select>
        </label>

        <label className="label-export-field">
          <span className="label-export-field__label">Unit</span>
          <input
            className="form-control form-control-sm"
            list="label-export-unit-options"
            value={unitDescription}
            disabled={unitDescriptionMode === 'null'}
            onChange={(e) => setUnitDescription(e.target.value.toUpperCase())}
            placeholder={unitDescriptionMode === 'null' ? 'n/a' : 'Type unit'}
          />
          <datalist id="label-export-unit-options">
            {unitDescriptionOptions.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        </label>

        <label className="label-export-field">
          <span className="label-export-field__label">Box</span>
          <input
            className="form-control form-control-sm"
            value={boxNumber}
            onChange={(e) => setBoxNumber(e.target.value.toUpperCase())}
            placeholder="A005"
          />
        </label>

        <label className="label-export-field">
          <span className="label-export-field__label">Stock rule</span>
          <select
            className="form-select form-select-sm"
            value={stockFilter}
            onChange={(e) => setStockFilter(e.target.value as StockFilter)}
          >
            <option value="all"><StockFilterLabel value="all" /></option>
            <option value="in_stock"><StockFilterLabel value="in_stock" /></option>
            <option value="zero_recent_sale"><StockFilterLabel value="zero_recent_sale" /></option>
            <option value="zero_stale"><StockFilterLabel value="zero_stale" /></option>
          </select>
        </label>

        <div className="label-export-actions-row">
          <label className="label-export-toggle">
            <input
              className="form-check-input"
              type="checkbox"
              checked={onlyNullSublocation}
              disabled={!!boxNumber.trim()}
              onChange={(e) => setOnlyNullSublocation(e.target.checked)}
            />
            <span>SubLocation null</span>
          </label>

          <label className="label-export-toggle">
            <input className="form-check-input" type="checkbox" checked={onlySaleUnitGtOne} onChange={(e) => setOnlySaleUnitGtOne(e.target.checked)} />
            <span>SaleUnit &gt; 1</span>
          </label>

          <button className="btn btn-primary btn-sm label-export-search-btn" disabled={!tenantId || !storeId || loading} onClick={() => void runSearch()}>
            {loading ? 'Loading...' : 'Search'}
          </button>

          <Link className="btn btn-outline-secondary btn-sm label-export-search-btn" to="/label-exporter/box-workspace">
            Box Workspace
          </Link>
        </div>
      </FilterBar>

      <div className="label-export-status">
        <span>Last box: <strong>{lastBoxForLetter || '-'}</strong></span>
        <span>Rows: <strong>{searchRows.length}</strong></span>
        {admin && <span>Labels: <strong>{labelList.length}</strong> / <strong>{totalLabels}</strong></span>}
        {!admin && <span className="text-muted small">Review only - sublocation assignment and export are super-admin actions</span>}
      </div>

      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

      <div className="label-export-main-grid">
        <section className="card shadow-sm">
          <div className="card-header d-flex justify-content-between align-items-center">
            <strong>Products</strong>
            {admin && (
              <button className="btn btn-sm btn-success" disabled={searchRows.length === 0} onClick={() => addSelectedToLabelList()}>
                Add to label list
              </button>
            )}
          </div>
          <div className="card-body p-0">
            <div className="table-responsive label-export-scroll label-export-grid-focus" tabIndex={0} onKeyDown={handleSearchGridKeyDown}>
              <table className="table table-sm table-hover align-middle mb-0 label-export-table">
                <thead className="table-light">
                  <tr>
                    {admin && (
                      <th>
                        <input type="checkbox" checked={allVisibleSelected} onChange={(e) => toggleSelectAll(e.target.checked)} />
                      </th>
                    )}
                    <th>Code</th>
                    <th>Product</th>
                    <th>SubLoc</th>
                    <th>Unit</th>
                    <th className="text-end">MRP</th>
                    <th className="text-end">Packing</th>
                    <th className="text-end">Stock</th>
                    <th className="text-end">LRDays</th>
                    <th className="text-end">LSDays</th>
                    <th className="text-center">Include</th>
                    <th>Remarks</th>
                  </tr>
                </thead>
                <tbody>
                  {searchRows.length === 0 ? (
                    <tr><td colSpan={admin ? 12 : 11} className="text-center text-muted py-4">Run search to load products</td></tr>
                  ) : (
                    searchRows.map((row, index) => {
                      const code = row.product_code || ''
                      return (
                        <tr
                          key={code}
                          ref={(node) => { searchRowRefs.current[code] = node }}
                          className={index === activeSearchIndex ? 'table-primary' : ''}
                          onClick={() => selectSearchRow(index)}
                        >
                          {admin && (
                            <td onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" checked={!!selectedSearchCodes[code]} onChange={() => toggleSearchRow(code)} />
                            </td>
                          )}
                          <td>{row.product_code}</td>
                          <td>{row.product_name}</td>
                          <td onClick={(e) => e.stopPropagation()}>
                            {admin ? (
                              <input
                                className="form-control form-control-sm label-export-inline-input"
                                value={subLocDrafts[code] ?? ''}
                                disabled={savingCode === code}
                                onChange={(e) => setSubLocDrafts((current) => ({ ...current, [code]: e.target.value.toUpperCase() }))}
                                onBlur={() => void saveSubLocation(row)}
                              />
                            ) : (
                              row.current_sublocation || <span className="text-danger">NULL</span>
                            )}
                          </td>
                          <td>{row.unit_description || '-'}</td>
                          <td className="text-end">{row.mrp}</td>
                          <td className="text-end">{row.sale_unit}</td>
                          <td className="text-end">{row.total_stock}</td>
                          <td className="text-end">{row.purchase_days ?? '-'}</td>
                          <td className="text-end">{row.sale_days ?? '-'}</td>
                          <td className="text-center" onClick={(e) => e.stopPropagation()}>
                            <div className="btn-group btn-group-sm" role="group">
                              <button
                                type="button"
                                className={`btn ${row.include_label === 'Y' ? 'btn-success' : 'btn-outline-success'}`}
                                disabled={savingCode === code}
                                onClick={() => void setIncludeLabel(row, 'Y')}
                              >
                                Y
                              </button>
                              <button
                                type="button"
                                className={`btn ${row.include_label === 'N' ? 'btn-danger' : 'btn-outline-danger'}`}
                                disabled={savingCode === code}
                                onClick={() => void setIncludeLabel(row, 'N')}
                              >
                                N
                              </button>
                            </div>
                          </td>
                          <td onClick={(e) => e.stopPropagation()}>
                            <input
                              className="form-control form-control-sm"
                              list="label-export-remarks-options"
                              value={remarksDrafts[code] ?? ''}
                              disabled={savingCode === code}
                              placeholder="Counter, SYP, unit fix..."
                              onChange={(e) => setRemarksDrafts((current) => ({ ...current, [code]: e.target.value }))}
                              onBlur={() => void saveRemarks(row)}
                            />
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
              <datalist id="label-export-remarks-options">
                {remarksOptions.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </div>
          </div>
        </section>

        <section className="card shadow-sm">
          <div className="card-header">
            <strong>Product Trend {activeTrendRow ? `- ${activeTrendRow.product_name}` : ''}</strong>
          </div>
          <div className="card-body label-export-trend-panel">
            {!activeTrendRow ? (
              <div className="label-export-trend-empty">Select a product to view its sales/purchase trend</div>
            ) : trendLoading ? (
              <div className="label-export-trend-empty">Loading trend...</div>
            ) : trendRows.length === 0 ? (
              <div className="label-export-trend-empty">No monthly trend data for this product</div>
            ) : (
              <>
                <div className="label-export-trend-legend">
                  <span><span className="label-export-trend-legend-dot" style={{ background: 'var(--bs-primary, #0d6efd)' }} />Sale qty</span>
                  <span><span className="label-export-trend-legend-dot" style={{ background: 'var(--bs-success, #198754)' }} />Purchase qty</span>
                </div>
                <div className="label-export-trend-bars">
                  {trendRows.map((row) => (
                    <div className="label-export-trend-row" key={row.month}>
                      <span>{row.month}</span>
                      <span className="label-export-trend-track">
                        <span
                          className="label-export-trend-fill label-export-trend-fill--sale"
                          style={{ width: `${Math.min(100, (row.sale_qty / trendMax) * 100)}%` }}
                        />
                      </span>
                      <span className="label-export-trend-track">
                        <span
                          className="label-export-trend-fill label-export-trend-fill--purchase"
                          style={{ width: `${Math.min(100, (row.purchase_qty / trendMax) * 100)}%` }}
                        />
                      </span>
                      <span className="text-end small text-muted">{row.sale_qty}/{row.purchase_qty}</span>
                    </div>
                  ))}
                </div>
                <div className="small text-muted">Current stock in hand: {trendRows[0]?.stock_in_hand ?? '-'}</div>
              </>
            )}
          </div>
        </section>
      </div>

      {admin && (
        <section className="card shadow-sm">
          <div className="card-header d-flex justify-content-between align-items-center">
            <strong>Label List</strong>
            <div className="d-flex align-items-center gap-2">
              <button
                className={`btn btn-sm ${showPrintSettings ? 'btn-primary' : 'btn-outline-secondary'}`}
                type="button"
                onClick={() => setShowPrintSettings((current) => !current)}
                aria-label="Print settings"
              >
                <i className="bi bi-sliders" />
              </button>
              <button className="btn btn-sm btn-outline-primary" disabled={labelList.length === 0} onClick={() => exportPrint()}>
                Export Print / PDF
              </button>
            </div>
          </div>
          <div className="card-body d-flex flex-column gap-3">
            {showPrintSettings && (
              <div className="label-export-settings-panel">
                <div className="row g-2">
                  <div className="col-6">
                    <label className="d-flex flex-column gap-1 small">
                      <span className="text-muted">Label width (mm)</span>
                      <input className="form-control form-control-sm" value={labelWidthMm} onChange={(e) => setLabelWidthMm(e.target.value)} />
                    </label>
                  </div>
                  <div className="col-6">
                    <label className="d-flex flex-column gap-1 small">
                      <span className="text-muted">Label height (mm)</span>
                      <input className="form-control form-control-sm" value={labelHeightMm} onChange={(e) => setLabelHeightMm(e.target.value)} />
                    </label>
                  </div>
                  <div className="col-4">
                    <label className="d-flex flex-column gap-1 small">
                      <span className="text-muted">Columns</span>
                      <input className="form-control form-control-sm" value={labelColumns} onChange={(e) => setLabelColumns(e.target.value)} />
                    </label>
                  </div>
                  <div className="col-4">
                    <label className="d-flex flex-column gap-1 small">
                      <span className="text-muted">Gap (mm)</span>
                      <input className="form-control form-control-sm" value={labelGapMm} onChange={(e) => setLabelGapMm(e.target.value)} />
                    </label>
                  </div>
                  <div className="col-4">
                    <label className="d-flex flex-column gap-1 small">
                      <span className="text-muted">Font (pt)</span>
                      <input className="form-control form-control-sm" value={labelFontSizePt} onChange={(e) => setLabelFontSizePt(e.target.value)} />
                    </label>
                  </div>
                </div>
              </div>
            )}

            <div className="table-responsive label-export-scroll label-export-grid-focus" tabIndex={0} onKeyDown={handleLabelListKeyDown}>
              <table className="table table-sm align-middle mb-0 label-export-table">
                <thead className="table-light">
                  <tr>
                    <th>Product</th>
                    <th className="text-end">Qty</th>
                    <th className="text-end">Del</th>
                  </tr>
                </thead>
                <tbody>
                  {labelList.length === 0 ? (
                    <tr><td colSpan={3} className="text-center text-muted py-4">No products added</td></tr>
                  ) : (
                    labelList.map((item, index) => (
                      <tr
                        key={item.product_code}
                        ref={(node) => { labelRowRefs.current[item.product_code] = node }}
                        className={index === activeLabelIndex ? 'table-primary' : ''}
                        onClick={() => setActiveLabelIndex(index)}
                      >
                        <td>
                          <div className="fw-semibold">{item.product_name}</div>
                          <div className="small text-muted">{item.product_code} | {item.unit_description || '-'} | MRP {item.mrp}</div>
                        </td>
                        <td className="text-end label-export-qty-cell">
                          <input
                            className="form-control form-control-sm text-end"
                            value={item.quantity}
                            onChange={(e) => updateLabelItem(item.product_code, { quantity: Math.max(1, Number(e.target.value) || 1) })}
                          />
                        </td>
                        <td className="text-end">
                          <button className="btn btn-sm btn-outline-danger" onClick={() => removeLabelItem(item.product_code)}>Del</button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
