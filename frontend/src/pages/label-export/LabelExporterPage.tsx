import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { storeService } from '../../services/storeService'
import { tenantService } from '../../services/tenantService'
import { labelExporterService } from '../../services/labelExporterService'
import type {
  IncludeLabel,
  LabelPurchaseRow,
  LabelSaleRow,
  LabelSearchRow,
  LabelTrendRow,
  ReviewStatusFilter,
  StockFilter,
  UnitDescriptionMode,
} from '../../types/labelExporter'
import type { TenantStore } from '../../types/store'
import type { Tenant } from '../../types/tenant'
import { buildPreparedLabelItem, printLabelSheet, type PreparedLabelItem } from './printLabelSheet'
import { canChangeLabelExportStore, isSuperAdmin } from './labelExportAccess'
import { useAuth } from '../../hooks/useAuth'
import { FilterBar } from '../../design-system/components/FilterBar'
import { UnitPicker } from './UnitPicker'
import { LocationPicker } from './LocationPicker'
import { AssignLocationsModal, type AssignableProduct } from './AssignLocationsModal'
import {
  assignmentBadge,
  computeCounters,
  currentUnitOf,
  deriveAssignment,
  isAssignable,
  isUnitCorrected,
  newLocationOf,
  oldLocationOf,
  oldUnitOf,
} from './labelStatus'
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

// Base units always offered in the correction picker, merged with whatever
// units actually exist in the store (spec §1 example list).
const BASE_UNITS = ['TAB', 'SYP', 'CAP', 'LOT', 'PACK', 'BOT', 'STRIP', 'CREAM', 'NOS', 'ML', 'GM', 'KIT', 'TUBE', 'INJ', 'DROPS', 'SACHET']

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
  const [reviewStatus, setReviewStatus] = useState<ReviewStatusFilter>('')
  const [onlyNullSublocation, setOnlyNullSublocation] = useState(true)
  const [onlySaleUnitGtOne, setOnlySaleUnitGtOne] = useState(true)

  const [searchRows, setSearchRows] = useState<LabelSearchRow[]>([])
  const [selectedSearchCodes, setSelectedSearchCodes] = useState<Record<string, boolean>>({})
  const [activeSearchIndex, setActiveSearchIndex] = useState(0)
  const [editingUnitCode, setEditingUnitCode] = useState<string | null>(null)
  const [editingLocationCode, setEditingLocationCode] = useState<string | null>(null)
  const [labelList, setLabelList] = useState<PreparedLabelItem[]>([])
  const [activeLabelIndex, setActiveLabelIndex] = useState(0)
  const [lastBoxForLetter, setLastBoxForLetter] = useState<string | null>(null)
  const [showAssign, setShowAssign] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<{ text: string; kind: 'ok' | 'err' } | null>(null)

  const [remarksDrafts, setRemarksDrafts] = useState<Record<string, string>>({})
  const [savingCode, setSavingCode] = useState('')

  const [trendRows, setTrendRows] = useState<LabelTrendRow[]>([])
  const [saleRows, setSaleRows] = useState<LabelSaleRow[]>([])
  const [purchaseRows, setPurchaseRows] = useState<LabelPurchaseRow[]>([])
  const [detailLoading, setDetailLoading] = useState(false)

  const [labelWidthMm, setLabelWidthMm] = useState('50')
  const [labelHeightMm, setLabelHeightMm] = useState('25')
  const [labelColumns, setLabelColumns] = useState('4')
  const [labelGapMm, setLabelGapMm] = useState('2')
  const [labelFontSizePt, setLabelFontSizePt] = useState('8')
  const [showPrintSettings, setShowPrintSettings] = useState(false)

  const searchRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const gridScrollRef = useRef<HTMLDivElement>(null)
  const labelRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const detailRequestRef = useRef(0)
  const toastTimer = useRef<number | undefined>(undefined)

  function flash(text: string, kind: 'ok' | 'err' = 'ok') {
    setToast({ text, kind })
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), kind === 'ok' ? 1400 : 2800)
  }

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
    setSaleRows([])
    setPurchaseRows([])
  }, [tenantId, storeId])

  useEffect(() => {
    if (boxNumber.trim()) setOnlyNullSublocation(false)
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

  // Load trend + recent sales + recent purchases for the ACTIVE row only
  // (spec §21: detailed history is per-focused-product, not per-list-row).
  useEffect(() => {
    const row = searchRows[activeSearchIndex]
    if (!row?.product_code || !tenantId || !storeId) {
      setTrendRows([])
      setSaleRows([])
      setPurchaseRows([])
      return
    }
    const requestId = ++detailRequestRef.current
    setDetailLoading(true)
    Promise.allSettled([
      labelExporterService.getProductTrend(tenantId, storeId, row.product_code),
      labelExporterService.getProductSales(tenantId, storeId, row.product_code),
      labelExporterService.getProductPurchases(tenantId, storeId, row.product_code),
    ])
      .then(([trend, sales, purchases]) => {
        if (detailRequestRef.current !== requestId) return
        setTrendRows(trend.status === 'fulfilled' && Array.isArray(trend.value?.rows) ? trend.value.rows : [])
        setSaleRows(sales.status === 'fulfilled' && Array.isArray(sales.value?.rows) ? sales.value.rows : [])
        setPurchaseRows(purchases.status === 'fulfilled' && Array.isArray(purchases.value?.rows) ? purchases.value.rows : [])
      })
      .finally(() => {
        if (detailRequestRef.current === requestId) setDetailLoading(false)
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
        reviewStatus,
      })

      const nextSearchRows = Array.isArray(productResult?.rows) ? productResult.rows : []
      const nextUnitOptions = Array.isArray(productResult?.unit_descriptions) ? productResult.unit_descriptions : []

      setSearchRows(nextSearchRows)
      setUnitDescriptionOptions(nextUnitOptions)
      setLastBoxForLetter(productResult?.last_box_for_letter ?? null)
      setActiveSearchIndex(0)
      setSelectedSearchCodes({})
      setEditingUnitCode(null)
      setEditingLocationCode(null)

      const nextRemarks: Record<string, string> = {}
      nextSearchRows.forEach((row) => {
        nextRemarks[row.product_code] = row.remarks || ''
      })
      setRemarksDrafts(nextRemarks)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load label data')
    } finally {
      setLoading(false)
    }
  }

  function selectSearchRow(index: number, rows = searchRows) {
    if (index < 0 || index >= rows.length) return
    setActiveSearchIndex(index)
    // Focus the grid container so single-key review (Y/N), Space and arrows
    // work immediately after a click — without stealing focus from an open
    // unit/location editor.
    if (!editingUnitCode && !editingLocationCode) gridScrollRef.current?.focus({ preventScroll: true })
  }

  function toggleSearchRow(productCode: string) {
    setSelectedSearchCodes((current) => ({ ...current, [productCode]: !current[productCode] }))
  }

  function toggleSelectAll(checked: boolean) {
    const next: Record<string, boolean> = {}
    if (checked) searchRows.forEach((row) => { if (row.product_code) next[row.product_code] = true })
    setSelectedSearchCodes(next)
  }

  function patchRow(productCode: string, patch: Partial<LabelSearchRow>) {
    setSearchRows((current) => current.map((row) => (row.product_code === productCode ? { ...row, ...patch } : row)))
  }

  // ---- Review (auto-save) ----
  async function setIncludeLabel(row: LabelSearchRow, value: IncludeLabel) {
    const nextValue = row.include_label === value ? null : value
    setSavingCode(row.product_code)
    setError(null)
    try {
      await labelExporterService.updateReview(tenantId, storeId, row.product_code, { include_label: nextValue })
      patchRow(row.product_code, { include_label: nextValue })
      flash(nextValue ? `✓ ${nextValue === 'Y' ? 'Included' : 'Excluded'}` : '✓ Cleared')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save review')
      flash('Save failed', 'err')
    } finally {
      setSavingCode('')
    }
  }

  async function saveRemarks(row: LabelSearchRow) {
    const draft = (remarksDrafts[row.product_code] || '').trim()
    if (draft === (row.remarks || '')) return
    setSavingCode(row.product_code)
    try {
      await labelExporterService.updateReview(tenantId, storeId, row.product_code, { remarks: draft })
      patchRow(row.product_code, { remarks: draft || null })
      flash('✓ Saved')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save remarks')
      flash('Save failed', 'err')
    } finally {
      setSavingCode('')
    }
  }

  // ---- Unit correction (auto-save) ----
  async function applyUnitCorrection(row: LabelSearchRow, newUnit: string) {
    setEditingUnitCode(null)
    const current = currentUnitOf(row)
    if (!newUnit || newUnit.toUpperCase() === current.toUpperCase()) return
    const capturedOld = oldUnitOf(row) // master unit; backend stores it once
    setSavingCode(row.product_code)
    setError(null)
    try {
      await labelExporterService.correctUnit(tenantId, storeId, row.product_code, newUnit, capturedOld)
      patchRow(row.product_code, {
        corrected_unit: newUnit,
        old_unit_description: row.old_unit_description || capturedOld,
      })
      flash(`✓ Unit → ${newUnit}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to correct unit')
      flash('Save failed', 'err')
    } finally {
      setSavingCode('')
    }
  }

  // ---- Location correction (manual box override, any store user, auto-save) ----
  async function applyLocationCorrection(row: LabelSearchRow, newLocation: string) {
    setEditingLocationCode(null)
    const current = newLocationOf(row)
    if (!newLocation || newLocation.toUpperCase() === current.toUpperCase()) return
    const capturedOld = current || oldLocationOf(row) // last assigned box; backend stores it once
    setSavingCode(row.product_code)
    setError(null)
    try {
      await labelExporterService.correctLocation(tenantId, storeId, row.product_code, newLocation, capturedOld)
      patchRow(row.product_code, {
        assigned_sublocation: newLocation,
        old_sublocation: row.old_sublocation || capturedOld,
      })
      flash(`✓ Location → ${newLocation}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to correct location')
      flash('Save failed', 'err')
    } finally {
      setSavingCode('')
    }
  }

  // ---- Bulk review (one backend call) ----
  async function bulkReview(value: IncludeLabel) {
    const selected = Object.keys(selectedSearchCodes).filter((c) => selectedSearchCodes[c])
    const codes = selected.length ? selected : searchRows.map((r) => r.product_code).filter(Boolean)
    if (codes.length === 0) return
    setLoading(true)
    setError(null)
    try {
      await labelExporterService.bulkReview(tenantId, storeId, codes, value)
      const codeSet = new Set(codes)
      setSearchRows((current) => current.map((row) => (codeSet.has(row.product_code) ? { ...row, include_label: value } : row)))
      flash(`✓ ${codes.length} marked ${value}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to bulk update')
      flash('Bulk update failed', 'err')
    } finally {
      setLoading(false)
    }
  }

  // ---- Label list (print) ----
  function addRowsToLabelList(rows: LabelSearchRow[]) {
    if (rows.length === 0) return
    setLabelList((current) => {
      const existing = new Map(current.map((item) => [item.product_code, item]))
      rows.forEach((row) => {
        const nextItem = buildPreparedLabelItem(row)
        if (!existing.has(nextItem.product_code)) existing.set(nextItem.product_code, nextItem)
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
    if (row) addRowsToLabelList([row])
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

  const counters = useMemo(() => computeCounters(searchRows), [searchRows])

  const unitPickerOptions = useMemo(
    () => Array.from(new Set([...BASE_UNITS, ...unitDescriptionOptions.map((u) => u.toUpperCase())])),
    [unitDescriptionOptions],
  )

  // Boxes already assigned in the loaded rows, so the reviewer can reuse one
  // instead of retyping it; typing a value not here still commits as new.
  const locationPickerOptions = useMemo(() => {
    const used = searchRows.map((row) => newLocationOf(row)).filter((v) => v)
    return Array.from(new Set(used)).sort()
  }, [searchRows])

  const remarksOptions = useMemo(() => {
    const used = searchRows.map((row) => row.remarks).filter((v): v is string => !!v)
    return Array.from(new Set([...REMARKS_PRESETS, ...used]))
  }, [searchRows])

  // Assignable = Review=Y AND Pending; restrict to selection if any (spec §12).
  const assignRows = useMemo(() => {
    const pending = searchRows.filter(isAssignable)
    const selected = Object.keys(selectedSearchCodes).filter((c) => selectedSearchCodes[c])
    return selected.length ? pending.filter((r) => selectedSearchCodes[r.product_code]) : pending
  }, [searchRows, selectedSearchCodes])

  const assignProducts: AssignableProduct[] = useMemo(
    () => assignRows.map((r) => ({ product_code: r.product_code, product_name: r.product_name, currentUnit: currentUnitOf(r) })),
    [assignRows],
  )

  const activeRow = searchRows[activeSearchIndex]
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
    if (editingUnitCode || editingLocationCode) return // the picker owns keys while a cell is being edited
    const row = searchRows[activeSearchIndex]
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        selectSearchRow(Math.min(searchRows.length - 1, activeSearchIndex + 1))
        break
      case 'ArrowUp':
        event.preventDefault()
        selectSearchRow(Math.max(0, activeSearchIndex - 1))
        break
      case 'y':
      case 'Y':
        event.preventDefault()
        if (row) void setIncludeLabel(row, 'Y')
        break
      case 'n':
      case 'N':
        event.preventDefault()
        if (row) void setIncludeLabel(row, 'N')
        break
      case ' ':
        event.preventDefault()
        if (row?.product_code) toggleSearchRow(row.product_code)
        break
      case 'Enter':
        if (admin) {
          event.preventDefault()
          addActiveRowToLabelList()
        }
        break
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
    <div className="d-flex flex-column gap-3 lx-page">
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
          <select className="form-select form-select-sm" value={storeId} disabled={!canChangeStore} onChange={(e) => setStoreId(e.target.value)}>
            {stores.length === 0 && <option value="">Loading...</option>}
            {(canChangeStore ? stores : stores.filter((s) => s.store_id === storeId)).map((s) => (
              <option key={s.store_id} value={s.store_id}>{s.store_code} - {s.store_name}</option>
            ))}
          </select>
        </label>

        <label className="label-export-field label-export-field--search">
          <span className="label-export-field__label">Search</span>
          <input className="form-control form-control-sm" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Product / code" />
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
          <select className="form-select form-select-sm" value={unitDescriptionMode} onChange={(e) => setUnitDescriptionMode(e.target.value as UnitDescriptionMode)}>
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
          <span className="label-export-field__label">Review</span>
          <select className="form-select form-select-sm" value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value as ReviewStatusFilter)}>
            <option value="">All</option>
            <option value="unreviewed">Not reviewed</option>
            <option value="Y">Included (Y)</option>
            <option value="N">Excluded (N)</option>
          </select>
        </label>

        <label className="label-export-field">
          <span className="label-export-field__label">Box</span>
          <input className="form-control form-control-sm" value={boxNumber} onChange={(e) => setBoxNumber(e.target.value.toUpperCase())} placeholder="A005" />
        </label>

        <label className="label-export-field">
          <span className="label-export-field__label">Stock rule</span>
          <select className="form-select form-select-sm" value={stockFilter} onChange={(e) => setStockFilter(e.target.value as StockFilter)}>
            <option value="all"><StockFilterLabel value="all" /></option>
            <option value="in_stock"><StockFilterLabel value="in_stock" /></option>
            <option value="zero_recent_sale"><StockFilterLabel value="zero_recent_sale" /></option>
            <option value="zero_stale"><StockFilterLabel value="zero_stale" /></option>
          </select>
        </label>

        <div className="label-export-actions-row">
          <label className="label-export-toggle">
            <input className="form-check-input" type="checkbox" checked={onlyNullSublocation} disabled={!!boxNumber.trim()} onChange={(e) => setOnlyNullSublocation(e.target.checked)} />
            <span>SubLocation null</span>
          </label>
          <label className="label-export-toggle">
            <input className="form-check-input" type="checkbox" checked={onlySaleUnitGtOne} onChange={(e) => setOnlySaleUnitGtOne(e.target.checked)} />
            <span>SaleUnit &gt; 1</span>
          </label>
          <button className="btn btn-primary btn-sm label-export-search-btn" disabled={!tenantId || !storeId || loading} onClick={() => void runSearch()}>
            {loading ? 'Loading...' : 'Search'}
          </button>
          <Link className="btn btn-outline-secondary btn-sm label-export-search-btn" to="/label-exporter/box-workspace">Box Workspace</Link>
        </div>
      </FilterBar>

      {/* Workflow counters (spec §11) */}
      <div className="lx-counters">
        <Counter label="Total" value={counters.total} />
        <Counter label="Reviewed" value={counters.reviewed} />
        <Counter label="Included" value={counters.included} tone="ok" />
        <Counter label="Excluded" value={counters.excluded} tone="muted" />
        <Counter label="Remaining" value={counters.remaining} tone="warn" />
        <Counter label="Location pending" value={counters.locationPending} tone="warn" />
        <Counter label="Assigned" value={counters.assigned} tone="ok" />
        <span className="lx-counters__spacer" />
        {lastBoxForLetter && <span className="lx-counters__note">Last box: <strong>{lastBoxForLetter}</strong></span>}
      </div>

      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

      <div className="label-export-main-grid">
        <section className="card shadow-sm lx-products-card">
          <div className="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
            <strong>Products</strong>
            <div className="d-flex align-items-center gap-2 flex-wrap">
              <button className="btn btn-sm btn-outline-success" disabled={searchRows.length === 0 || loading} onClick={() => void bulkReview('Y')}>Mark all Y</button>
              <button className="btn btn-sm btn-outline-danger" disabled={searchRows.length === 0 || loading} onClick={() => void bulkReview('N')}>Mark all N</button>
              <button className="btn btn-sm btn-primary" disabled={assignRows.length === 0} onClick={() => setShowAssign(true)}>
                Assign Locations ({assignRows.length})
              </button>
              {admin && (
                <button className="btn btn-sm btn-success" disabled={searchRows.length === 0} onClick={() => addSelectedToLabelList()}>Add to labels</button>
              )}
            </div>
          </div>
          <div className="card-body p-0">
            <div ref={gridScrollRef} className="table-responsive label-export-scroll label-export-grid-focus" tabIndex={0} onKeyDown={handleSearchGridKeyDown}>
              <table className="table table-sm align-middle mb-0 label-export-table lx-review-table">
                <thead className="table-light">
                  <tr>
                    <th className="lx-col-check"><input type="checkbox" checked={allVisibleSelected} onChange={(e) => toggleSelectAll(e.target.checked)} aria-label="Select all" /></th>
                    <th className="text-end lx-col-num">#</th>
                    <th>Code</th>
                    <th>Product</th>
                    <th>Old Unit</th>
                    <th>Unit</th>
                    <th>Old Loc</th>
                    <th>New Loc</th>
                    <th className="text-end">Stock</th>
                    <th className="text-end">Sale D</th>
                    <th className="text-end">Pur D</th>
                    <th className="text-center">Review</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {searchRows.length === 0 ? (
                    <tr><td colSpan={13} className="text-center text-muted py-4">Run search to load products</td></tr>
                  ) : (
                    searchRows.map((row, index) => {
                      const code = row.product_code || ''
                      const oldUnit = oldUnitOf(row)
                      const curUnit = currentUnitOf(row)
                      const corrected = isUnitCorrected(row)
                      const newLoc = newLocationOf(row)
                      const badge = assignmentBadge(deriveAssignment(row))
                      const excluded = row.include_label === 'N'
                      return (
                        <tr
                          key={code}
                          ref={(node) => { searchRowRefs.current[code] = node }}
                          className={`lx-row${index === activeSearchIndex ? ' lx-row--active' : ''}${excluded ? ' lx-row--excluded' : ''}`}
                          onClick={() => selectSearchRow(index)}
                        >
                          <td className="lx-col-check" onClick={(e) => e.stopPropagation()}>
                            <input type="checkbox" checked={!!selectedSearchCodes[code]} onChange={() => toggleSearchRow(code)} aria-label={`Select ${row.product_name}`} />
                          </td>
                          <td className="text-end lx-col-num">{index + 1}</td>
                          <td className="lx-col-code">{row.product_code}</td>
                          <td className="lx-col-product">{row.product_name}</td>
                          <td className="lx-col-oldunit text-muted">{oldUnit || '—'}</td>
                          <td className="lx-col-unit" onClick={(e) => e.stopPropagation()}>
                            {editingUnitCode === code ? (
                              <UnitPicker
                                current={curUnit}
                                options={unitPickerOptions}
                                onPick={(u) => void applyUnitCorrection(row, u)}
                                onCancel={() => setEditingUnitCode(null)}
                              />
                            ) : (
                              <button
                                type="button"
                                className={`lx-unit-chip${corrected ? ' lx-unit-chip--changed' : ''}`}
                                disabled={savingCode === code}
                                title={corrected ? `Corrected from ${oldUnit}` : 'Click to correct unit'}
                                onClick={() => { selectSearchRow(index); setEditingUnitCode(code) }}
                              >
                                <span className="lx-unit-chip__val">{curUnit || '—'}</span>
                                {corrected && <span className="lx-unit-chip__flag" aria-label="unit corrected">⚠</span>}
                                <i className="bi bi-caret-down-fill lx-unit-chip__caret" aria-hidden="true" />
                              </button>
                            )}
                          </td>
                          <td className="lx-col-oldloc text-muted">{oldLocationOf(row) || '—'}</td>
                          <td className="lx-col-newloc" onClick={(e) => e.stopPropagation()}>
                            {editingLocationCode === code ? (
                              <LocationPicker
                                current={newLoc}
                                options={locationPickerOptions}
                                onPick={(loc) => void applyLocationCorrection(row, loc)}
                                onCancel={() => setEditingLocationCode(null)}
                              />
                            ) : (
                              <button
                                type="button"
                                className="lx-unit-chip"
                                disabled={savingCode === code}
                                title={newLoc ? `Manually move from ${newLoc}` : 'Click to assign a location'}
                                onClick={() => { selectSearchRow(index); setEditingLocationCode(code) }}
                              >
                                <span className="lx-unit-chip__val">{newLoc ? <span className="lx-newloc">{newLoc}</span> : <span className="text-muted">—</span>}</span>
                                <i className="bi bi-caret-down-fill lx-unit-chip__caret" aria-hidden="true" />
                              </button>
                            )}
                          </td>
                          <td className="text-end">{row.total_stock}</td>
                          <td className="text-end">{row.sale_days ?? '—'}</td>
                          <td className="text-end">{row.purchase_days ?? '—'}</td>
                          <td className="text-center lx-col-review" onClick={(e) => e.stopPropagation()}>
                            <div className="btn-group btn-group-sm lx-yn" role="group">
                              <button type="button" className={`btn ${row.include_label === 'Y' ? 'btn-success' : 'btn-outline-success'}`} disabled={savingCode === code} onClick={() => void setIncludeLabel(row, 'Y')}>Y</button>
                              <button type="button" className={`btn ${row.include_label === 'N' ? 'btn-danger' : 'btn-outline-danger'}`} disabled={savingCode === code} onClick={() => void setIncludeLabel(row, 'N')}>N</button>
                            </div>
                          </td>
                          <td className="lx-col-status">
                            <span className={`lx-badge ${badge.className}`}><span className="lx-badge__glyph">{badge.glyph}</span>{badge.label}</span>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Right-side product detail panel (spec §7) */}
        <section className="card shadow-sm lx-detail-card">
          <div className="card-header"><strong>Product Detail</strong></div>
          <div className="card-body lx-detail-body">
            {!activeRow ? (
              <div className="label-export-trend-empty">Select a product to review its detail</div>
            ) : (
              <>
                <div className="lx-detail-head">
                  <div className="lx-detail-name">{activeRow.product_name}</div>
                  <div className="lx-detail-sub">{activeRow.product_code}</div>
                </div>

                <dl className="lx-detail-facts">
                  <div><dt>Stock</dt><dd>{activeRow.total_stock}</dd></div>
                  <div>
                    <dt>Unit</dt>
                    <dd>
                      {isUnitCorrected(activeRow) ? (
                        <span className="lx-detail-change"><span className="text-muted">{oldUnitOf(activeRow)}</span> → <strong>{currentUnitOf(activeRow)}</strong> <span className="lx-unit-chip__flag">⚠</span></span>
                      ) : (currentUnitOf(activeRow) || '—')}
                    </dd>
                  </div>
                  <div>
                    <dt>Location</dt>
                    <dd>
                      {newLocationOf(activeRow) ? (
                        <span className="lx-detail-change"><span className="text-muted">{oldLocationOf(activeRow) || '—'}</span> → <strong>{newLocationOf(activeRow)}</strong></span>
                      ) : (oldLocationOf(activeRow) || <span className="text-muted">Unassigned</span>)}
                    </dd>
                  </div>
                  <div><dt>Status</dt><dd><span className={`lx-badge ${assignmentBadge(deriveAssignment(activeRow)).className}`}>{assignmentBadge(deriveAssignment(activeRow)).label}</span></dd></div>
                </dl>

                <label className="lx-detail-remarks">
                  <span className="label-export-field__label">Remarks</span>
                  <input
                    className="form-control form-control-sm"
                    list="label-export-remarks-options"
                    value={remarksDrafts[activeRow.product_code] ?? ''}
                    placeholder="Counter, SYP, unit fix…"
                    onChange={(e) => setRemarksDrafts((current) => ({ ...current, [activeRow.product_code]: e.target.value }))}
                    onBlur={() => void saveRemarks(activeRow)}
                  />
                  <datalist id="label-export-remarks-options">
                    {remarksOptions.map((option) => (<option key={option} value={option} />))}
                  </datalist>
                </label>

                <div className="lx-detail-section">
                  <div className="lx-detail-section__title">Monthly trend {detailLoading && <span className="text-muted small">· loading…</span>}</div>
                  {trendRows.length === 0 ? (
                    <div className="text-muted small">No monthly trend data</div>
                  ) : (
                    <>
                      <div className="label-export-trend-legend">
                        <span><span className="label-export-trend-legend-dot" style={{ background: 'var(--bs-primary, #0d6efd)' }} />Sale</span>
                        <span><span className="label-export-trend-legend-dot" style={{ background: 'var(--bs-success, #198754)' }} />Purchase</span>
                      </div>
                      <div className="label-export-trend-bars">
                        {trendRows.map((row) => (
                          <div className="label-export-trend-row" key={row.month}>
                            <span>{row.month}</span>
                            <span className="label-export-trend-track"><span className="label-export-trend-fill label-export-trend-fill--sale" style={{ width: `${Math.min(100, (row.sale_qty / trendMax) * 100)}%` }} /></span>
                            <span className="label-export-trend-track"><span className="label-export-trend-fill label-export-trend-fill--purchase" style={{ width: `${Math.min(100, (row.purchase_qty / trendMax) * 100)}%` }} /></span>
                            <span className="text-end small text-muted">{row.sale_qty}/{row.purchase_qty}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                <div className="lx-detail-two">
                  <div className="lx-detail-section">
                    <div className="lx-detail-section__title">Recent sales</div>
                    {saleRows.length === 0 ? <div className="text-muted small">None</div> : (
                      <ul className="lx-detail-list">
                        {saleRows.slice(0, 6).map((s, i) => (
                          <li key={i}><span>{s.bill_time?.slice(0, 10) ?? '—'}</span><span>{s.qty}</span><span className="text-muted">{s.customer || s.salesman || ''}</span></li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div className="lx-detail-section">
                    <div className="lx-detail-section__title">Recent purchases</div>
                    {purchaseRows.length === 0 ? <div className="text-muted small">None</div> : (
                      <ul className="lx-detail-list">
                        {purchaseRows.slice(0, 6).map((p, i) => (
                          <li key={i}><span>{p.grn_date ?? '—'}</span><span>{p.stock}</span><span className="text-muted">{p.supplier_name || ''}</span></li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </section>
      </div>

      {admin && (
        <section className="card shadow-sm">
          <div className="card-header d-flex justify-content-between align-items-center">
            <strong>Label List <span className="text-muted small">({labelList.length} / {totalLabels} labels)</span></strong>
            <div className="d-flex align-items-center gap-2">
              <button className={`btn btn-sm ${showPrintSettings ? 'btn-primary' : 'btn-outline-secondary'}`} type="button" onClick={() => setShowPrintSettings((current) => !current)} aria-label="Print settings"><i className="bi bi-sliders" /></button>
              <button className="btn btn-sm btn-outline-primary" disabled={labelList.length === 0} onClick={() => exportPrint()}>Export Print / PDF</button>
            </div>
          </div>
          <div className="card-body d-flex flex-column gap-3">
            {showPrintSettings && (
              <div className="label-export-settings-panel">
                <div className="row g-2">
                  <div className="col-6"><label className="d-flex flex-column gap-1 small"><span className="text-muted">Label width (mm)</span><input className="form-control form-control-sm" value={labelWidthMm} onChange={(e) => setLabelWidthMm(e.target.value)} /></label></div>
                  <div className="col-6"><label className="d-flex flex-column gap-1 small"><span className="text-muted">Label height (mm)</span><input className="form-control form-control-sm" value={labelHeightMm} onChange={(e) => setLabelHeightMm(e.target.value)} /></label></div>
                  <div className="col-4"><label className="d-flex flex-column gap-1 small"><span className="text-muted">Columns</span><input className="form-control form-control-sm" value={labelColumns} onChange={(e) => setLabelColumns(e.target.value)} /></label></div>
                  <div className="col-4"><label className="d-flex flex-column gap-1 small"><span className="text-muted">Gap (mm)</span><input className="form-control form-control-sm" value={labelGapMm} onChange={(e) => setLabelGapMm(e.target.value)} /></label></div>
                  <div className="col-4"><label className="d-flex flex-column gap-1 small"><span className="text-muted">Font (pt)</span><input className="form-control form-control-sm" value={labelFontSizePt} onChange={(e) => setLabelFontSizePt(e.target.value)} /></label></div>
                </div>
              </div>
            )}

            <div className="table-responsive label-export-scroll label-export-grid-focus" tabIndex={0} onKeyDown={handleLabelListKeyDown}>
              <table className="table table-sm align-middle mb-0 label-export-table">
                <thead className="table-light"><tr><th>Product</th><th className="text-end">Qty</th><th className="text-end">Del</th></tr></thead>
                <tbody>
                  {labelList.length === 0 ? (
                    <tr><td colSpan={3} className="text-center text-muted py-4">No products added</td></tr>
                  ) : (
                    labelList.map((item, index) => (
                      <tr key={item.product_code} ref={(node) => { labelRowRefs.current[item.product_code] = node }} className={index === activeLabelIndex ? 'lx-row--active' : ''} onClick={() => setActiveLabelIndex(index)}>
                        <td><div className="fw-semibold">{item.product_name}</div><div className="small text-muted">{item.product_code} | {item.unit_description || '-'} | MRP {item.mrp}</div></td>
                        <td className="text-end label-export-qty-cell"><input className="form-control form-control-sm text-end" value={item.quantity} onChange={(e) => updateLabelItem(item.product_code, { quantity: Math.max(1, Number(e.target.value) || 1) })} /></td>
                        <td className="text-end"><button className="btn btn-sm btn-outline-danger" onClick={() => removeLabelItem(item.product_code)}>Del</button></td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {toast && <div className={`lx-toast lx-toast--${toast.kind}`} role="status">{toast.text}</div>}

      {showAssign && (
        <AssignLocationsModal
          tenantId={tenantId}
          storeId={storeId}
          products={assignProducts}
          defaultLetter={startsWith}
          canCommit={admin}
          onClose={() => setShowAssign(false)}
          onCommitted={() => { setShowAssign(false); flash('✓ Locations assigned'); void runSearch() }}
        />
      )}
    </div>
  )
}

function Counter({ label, value, tone }: { label: string; value: number; tone?: 'ok' | 'warn' | 'muted' }) {
  return (
    <div className={`lx-counter${tone ? ` lx-counter--${tone}` : ''}`}>
      <span className="lx-counter__value">{value}</span>
      <span className="lx-counter__label">{label}</span>
    </div>
  )
}
