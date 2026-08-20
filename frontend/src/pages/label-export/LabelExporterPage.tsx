import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { storeService } from '../../services/storeService'
import { tenantService } from '../../services/tenantService'
import { labelExporterService } from '../../services/labelExporterService'
import type { LabelSearchRow } from '../../types/labelExporter'
import type { TenantStore } from '../../types/store'
import type { Tenant } from '../../types/tenant'
import { buildPreparedLabelItem, printLabelSheet, type PreparedLabelItem } from './printLabelSheet'
import { canChangeLabelExportStore } from './labelExportAccess'
import { useAuth } from '../../hooks/useAuth'
import { FilterBar } from '../../design-system/components/FilterBar'
import './label-export.css'

type StockFilter = 'all' | 'in_stock' | 'zero_recent_sale'

export default function LabelExporterPage() {
  const { user } = useAuth()
  const canChangeStore = canChangeLabelExportStore(user)
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<TenantStore[]>([])
  const [storeId, setStoreId] = useState('')

  const [searchText, setSearchText] = useState('')
  const [startsWith, setStartsWith] = useState('')
  const [unitDescription, setUnitDescription] = useState('')
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

  const [labelWidthMm, setLabelWidthMm] = useState('50')
  const [labelHeightMm, setLabelHeightMm] = useState('25')
  const [labelColumns, setLabelColumns] = useState('4')
  const [labelGapMm, setLabelGapMm] = useState('2')
  const [labelFontSizePt, setLabelFontSizePt] = useState('8')
  const [showPrintSettings, setShowPrintSettings] = useState(false)

  const searchRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const labelRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})

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

  const allVisibleSelected = searchRows.length > 0 && searchRows.every((row) => row.product_code && selectedSearchCodes[row.product_code])

  const totalLabels = useMemo(
    () => labelList.reduce((sum, item) => sum + Math.max(1, Number(item.quantity) || 1), 0),
    [labelList],
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
    } else if (event.key === 'Enter') {
      event.preventDefault()
      addActiveRowToLabelList()
    } else if (event.key === ' ') {
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
          <span className="label-export-field__label">Unit</span>
          <input
            className="form-control form-control-sm"
            list="label-export-unit-options"
            value={unitDescription}
            onChange={(e) => setUnitDescription(e.target.value.toUpperCase())}
            placeholder="Type unit"
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
            <option value="all">Stock &gt; 0 or zero stock sale within 90 days</option>
            <option value="in_stock">Stock &gt; 0 only</option>
            <option value="zero_recent_sale">Stock = 0 and sale within 90 days</option>
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
        <span>Labels: <strong>{labelList.length}</strong> / <strong>{totalLabels}</strong></span>
      </div>

      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

      <div className="label-export-grid label-export-grid--split">
        <section className="card shadow-sm">
          <div className="card-header d-flex justify-content-between align-items-center">
            <strong>Assign Products</strong>
            <button className="btn btn-sm btn-success" disabled={searchRows.length === 0} onClick={() => addSelectedToLabelList()}>
              Add to label list
            </button>
          </div>
          <div className="card-body p-0">
            <div className="table-responsive label-export-scroll label-export-grid-focus" tabIndex={0} onKeyDown={handleSearchGridKeyDown}>
              <table className="table table-sm table-hover align-middle mb-0 label-export-table">
                <thead className="table-light">
                  <tr>
                    <th>
                      <input type="checkbox" checked={allVisibleSelected} onChange={(e) => toggleSelectAll(e.target.checked)} />
                    </th>
                    <th>Code</th>
                    <th>Product</th>
                    <th>SubLoc</th>
                    <th>Unit</th>
                    <th className="text-end">MRP</th>
                    <th className="text-end">SaleUnit</th>
                    <th className="text-end">Stock</th>
                    <th className="text-end">PDay</th>
                    <th className="text-end">SDay</th>
                  </tr>
                </thead>
                <tbody>
                  {searchRows.length === 0 ? (
                    <tr><td colSpan={10} className="text-center text-muted py-4">Run search to load products</td></tr>
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
                          <td onClick={(e) => e.stopPropagation()}>
                            <input type="checkbox" checked={!!selectedSearchCodes[code]} onChange={() => toggleSearchRow(code)} />
                          </td>
                          <td>{row.product_code}</td>
                          <td>{row.product_name}</td>
                          <td>{row.current_sublocation || <span className="text-danger">NULL</span>}</td>
                          <td>{row.unit_description || '-'}</td>
                          <td className="text-end">{row.mrp}</td>
                          <td className="text-end">{row.sale_unit}</td>
                          <td className="text-end">{row.total_stock}</td>
                          <td className="text-end">{row.purchase_days ?? '-'}</td>
                          <td className="text-end">{row.sale_days ?? '-'}</td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

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
      </div>
    </div>
  )
}
