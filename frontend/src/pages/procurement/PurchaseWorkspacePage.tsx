import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import { ApiError } from '../../services/apiClient'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type {
  Cycle,
  ManualProduct,
  PendingItem,
  PurchaseMode,
  Refresh,
  SupplierRow,
  SupplierStockRow,
  WorkspaceItem,
} from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { ProductGrid } from '../../components/procurement/ProductGrid'
import { DetailColumn } from '../../components/procurement/DetailColumn'
import type { DrawerTab, ViewAllKind } from '../../components/procurement/DetailColumn'
import { BillDrawer } from '../../components/procurement/BillDrawer'
import type { BillTarget } from '../../components/procurement/BillDrawer'
import { HistoryAllDialog } from '../../components/procurement/HistoryAllDialog'
import { SupplierRecPanel } from '../../components/procurement/SupplierRecPanel'
import { ProductInfoDialog } from '../../components/procurement/ProductInfoDialog'
import { SupplierQueuePanel } from '../../components/procurement/SupplierQueuePanel'
import type { SupplierQueueGroup } from '../../components/procurement/SupplierQueuePanel'
import { SupplierOptimizationPanel } from '../../components/procurement/SupplierOptimizationPanel'
import { downloadPurchaseOrderCsv } from '../../components/procurement/exportDocument'
import { ManualProductModal } from '../../components/procurement/ManualProductModal'
import { SupplierPicker } from '../../components/procurement/SupplierPicker'
import { SupplierStockTable, stockRowKey, formatOffer } from '../../components/procurement/SupplierStockTable'
import { SupplierStockImportModal } from '../../components/procurement/SupplierStockImportModal'
import {
  autoAssignSupplier,
  computeRankAssignment,
  effectiveCost,
  eligibleForAutoAssign,
  sortSuppliersByCost,
} from '../../components/procurement/purchaseValue'
import { SupplierRankPanel } from '../../components/procurement/SupplierRankPanel'
import { AutoAssignPreviewModal } from '../../components/procurement/AutoAssignPreviewModal'
import { money, num, date } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'

type View = 'purchase' | 'pending' | 'grn'
// Operational stages of the Purchase view (normalizes the previously-mixed screen).
type Stage = 'review' | 'assign' | 'optimize' | 'export'
type Banner = { kind: 'success' | 'danger'; text: string } | null

const STAGES: { key: Stage; label: string; icon: string }[] = [
  { key: 'review', label: 'Review Products', icon: 'bi-clipboard-check' },
  { key: 'assign', label: 'Assign Suppliers', icon: 'bi-diagram-3' },
  { key: 'optimize', label: 'Optimize', icon: 'bi-sliders' },
  // Not a required step — every supplier's Purchase Order can already be
  // exported from its own card in the Assign stage (Supplier Review panel).
  // This stage is a monitoring/history dashboard for the whole refresh.
  { key: 'export', label: 'Export Monitor', icon: 'bi-box-arrow-up' },
]

const MOVEMENT = ['', 'FAST', 'MEDIUM', 'SLOW', 'NONMOVING']

// Reject a request that opens a connection but never sends a response. `fetch`
// (see apiClient) has no timeout, so a single hung/dropped connection would
// otherwise never settle — and because the supplier-queue fan-out awaits every
// request, one stuck request pins the whole queue on its loading skeleton
// forever. A generous ceiling: real responses return in well under this.
const REQUEST_TIMEOUT_MS = 20_000
function withTimeout<T>(p: Promise<T>, ms = REQUEST_TIMEOUT_MS): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new ApiError('Request timed out', 0)), ms)
    p.then(
      (v) => { clearTimeout(timer); resolve(v) },
      (e) => { clearTimeout(timer); reject(e) },
    )
  })
}

const MODE_OPTIONS: { label: string; value: PurchaseMode }[] = [
  { label: 'Review All', value: 'review' },
  { label: 'Supplier Purchasing', value: 'supplier' },
  { label: 'Supplier Live Stock', value: 'supplier-stock' },
]

export default function PurchaseWorkspacePage() {
  const [params] = useSearchParams()
  const urlTenant = params.get('tenant') ?? ''
  const urlRefresh = params.get('refresh') ?? ''

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState(urlTenant)
  const [stores, setStores] = useState<Store[]>([])
  const [selectedStoreId, setSelectedStoreId] = useState('')
  // Cycles for the selected store (open + closed) drive the Cycle selector.
  const [cycles, setCycles] = useState<Cycle[]>([])
  const [cycleId, setCycleId] = useState('')
  const [refreshes, setRefreshes] = useState<Refresh[]>([])
  const [refreshId, setRefreshId] = useState(urlRefresh)
  const actingUser = useActingUser()
  const [banner, setBanner] = useState<Banner>(null)

  // Supplier recommendations (batched) + the row's locally-selected supplier.
  const [recommendations, setRecommendations] = useState<Record<string, SupplierRow[]>>({})
  const [selectedSupplier, setSelectedSupplier] = useState<Record<string, string>>({})
  // Supplier Purchasing mode: order-item ids the picked supplier has bought.
  const [supplierProductIds, setSupplierProductIds] = useState<Set<string> | null>(null)

  const [mode, setMode] = useState<PurchaseMode>('review')
  const [view, setView] = useState<View>('purchase')
  // Current operational stage of the Purchase view.
  const [stage, setStage] = useState<Stage>('review')
  const [autoBusy, setAutoBusy] = useState(false)

  const [items, setItems] = useState<WorkspaceItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The refresh_id the currently-loaded `items` actually belong to — set only
  // once a workspace fetch resolves. Lets the eager Supplier Queue load tell
  // "still the old refresh's rows" apart from "the new refresh's rows are in"
  // (items.length > 0 alone can't: both cases are non-empty during a refresh
  // switch, which used to join fresh assignment rows against a stale itemById
  // and silently render an empty Supplier Queue until a manual Reload).
  const [itemsRefreshId, setItemsRefreshId] = useState('')

  // Filters
  const [search, setSearch] = useState('')
  const [movement, setMovement] = useState('')
  // Planning-State filter (integrates with the grid's Planning State column).
  const [showPending, setShowPending] = useState(true)
  const [showFinalized, setShowFinalized] = useState(true)
  const [showAssigned, setShowAssigned] = useState(true)
  const [showSkipped, setShowSkipped] = useState(true)
  const [showDeferred, setShowDeferred] = useState(true)
  const [showManual, setShowManual] = useState(true)
  // Product Type filter (Product Master ProductType): '' all, '1' Pharma,
  // '0' Non-Pharma, '2' Others. Client-side only — never recalculates the VPL.
  const [productType, setProductType] = useState('')
  // "Has Offer" filter: only products in THIS refresh's VPL that the store has
  // bought with free qty at least once (sync.PurchaseTrans, FreeQty > 0 on any
  // past purchase — a flat discount % is a price, not an offer). Fetched once
  // per refresh (store-scoped, not supplier-scoped) — client-side filter only,
  // it never recalculates the VPL and it composes with every other filter.
  const [offerOnly, setOfferOnly] = useState(false)
  const [offerProductCodes, setOfferProductCodes] = useState<Set<string> | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  // True while the keyboard "supplier zone" holds focus (rings the side panel).
  const [supplierZoneActive, setSupplierZoneActive] = useState(false)
  // The grid checkbox is NOT a selection state — it means "included for the
  // current supplier's export". It is ON automatically the instant a product
  // finalizes and OFF while not finalized; Space Bar only lets the buyer pull
  // a specific product OUT of (or back INTO) an otherwise-automatic export
  // set, it never sets the qty/status itself. Modeled as a sparse override
  // map on top of the derived default (below) rather than raw boolean state,
  // so re-finalizing a row always snaps it back to ON with no stale override.
  const [checkOverrides, setCheckOverrides] = useState<Record<string, boolean>>({})

  // Staged Final Qty edits (saved immediately on Enter/blur) + export lock.
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [lockedIds, setLockedIds] = useState<Set<string>>(new Set())

  const [info, setInfo] = useState<{ item: WorkspaceItem; tab: DrawerTab } | null>(null)
  const openInfo = useCallback((item: WorkspaceItem, tab: DrawerTab = 'info') => setInfo({ item, tab }), [])
  // Bill Drawer (purchase/sales) + full-history "View All" dialog.
  const [bill, setBill] = useState<BillTarget | null>(null)
  const [viewAll, setViewAll] = useState<{ kind: ViewAllKind; item: WorkspaceItem } | null>(null)
  const [manualOpen, setManualOpen] = useState(false)
  const [manualBusy, setManualBusy] = useState(false)

  // Supplier Queue
  const [queueLines, setQueueLines] = useState<SupplierQueueGroup[]>([])
  const [queueLoading, setQueueLoading] = useState(false)
  // Set when a queue rebuild fails outright (no supplier data could be loaded)
  // so the panel can offer Retry instead of showing the loading skeleton forever.
  const [queueError, setQueueError] = useState<string | null>(null)
  const [busySupplier, setBusySupplier] = useState<string | null>(null)
  const [exportingAll, setExportingAll] = useState(false)
  const [exportingSelected, setExportingSelected] = useState(false)

  // Configured Minimum Order Value per supplier (batch-loaded once per store).
  const [minOrders, setMinOrders] = useState<Record<string, number>>({})

  // Supplier context (modes 2/3) + live stock
  const [supplier, setSupplier] = useState<SupplierRow | null>(null)
  const [stockSearch, setStockSearch] = useState('')
  const [supplierStock, setSupplierStock] = useState<SupplierStockRow[]>([])
  const [supplierStockLoading, setSupplierStockLoading] = useState(false)
  const [supplierStockError, setSupplierStockError] = useState<string | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [stockReloadKey, setStockReloadKey] = useState(0)
  // Supplier-stock row selection + order-qty draft, lifted here so the
  // persistent Product Details panel tracks the focused row.
  const [stockSelectedKey, setStockSelectedKey] = useState<string | null>(null)
  const [stockDraft, setStockDraft] = useState<Record<string, string>>({})

  // Pending + GRN
  const [pending, setPending] = useState<PendingItem[]>([])
  const [pendingDraft, setPendingDraft] = useState<Record<string, string>>({})
  const [pendingSel, setPendingSel] = useState<Set<string>>(new Set())
  const [pendingBusy, setPendingBusy] = useState(false)
  const [grnNumber, setGrnNumber] = useState('')

  const importInputRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  // Cancels a prior in-flight workspace fetch when a newer one starts (debounce
  // timer firing again, an error-path reload, a manual refresh click, etc.) so a
  // slow, stale response can never overwrite fresher state.
  const workspaceAbortRef = useRef<AbortController | null>(null)
  // Order-item ids with a Final Qty save in flight — dedupes Enter/blur so one
  // row can never fire two concurrent /final-qty requests.
  const savingIds = useRef<Set<string>>(new Set())
  // Order-item ids with a supplier assignment in flight — dedupes rapid double
  // Enter/click in the Supplier Recommendation panel (§11).
  const assigningIds = useRef<Set<string>>(new Set())
  // Guards loadQueue against overlapping runs — it fans out one request per
  // assigned item, so two concurrent calls (rapid supplier switches, chained
  // actions) could otherwise resolve out of order and let a stale result win.
  const queueRunRef = useRef(0)

  const say = useCallback((kind: 'success' | 'danger', text: string) => {
    setBanner({ kind, text })
    window.setTimeout(() => setBanner(null), 4000)
  }, [])
  const fail = useCallback(
    (e: unknown) => say('danger', e instanceof Error ? e.message : 'Request failed'),
    [say],
  )
  // A connectivity failure (server unreachable / proxy 502-504) — as opposed to a
  // real 4xx business rejection. When offline we must NOT auto-reload to reconcile:
  // that follow-up request would just fail too, amplifying into a request storm.
  // Show the one banner and stop; the workspace ErrorState already offers Retry.
  const isOffline = (e: unknown) =>
    e instanceof ApiError && (e.status === 0 || e.status === 502 || e.status === 503 || e.status === 504)

  useEffect(() => {
    tenantService
      .list()
      .then((rows) => {
        const active = rows.filter((t) => t.is_active)
        setTenants(active)
        if (active.length) setTenantId((c) => c || active[0].tenant_id)
      })
      .catch(fail)
    storeService.list().then(setStores).catch(() => setStores([]))
  }, [fail])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )

  // Procurement is store-based: default to the first store, keep it valid on
  // tenant change.
  useEffect(() => {
    setSelectedStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  // Load the store's cycles + refreshes together, then default-select the
  // CURRENT OPEN cycle (else the latest CLOSED one, read-only) so the buyer
  // never has to hunt for "which cycle is active".
  useEffect(() => {
    if (!tenantId || !selectedStoreId) { setCycles([]); setRefreshes([]); setCycleId(''); setRefreshId(''); return }
    let live = true
    Promise.all([
      procurementService.cycles(tenantId, selectedStoreId),
      procurementService.refreshes(tenantId, selectedStoreId),
    ])
      .then(([cyc, refs]) => {
        if (!live) return
        setCycles(cyc)
        setRefreshes(refs)
        const open = cyc.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE')
        const latest = [...cyc].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))[0]
        // A URL-provided refresh pins its own cycle; otherwise open-first.
        const urlCycle = urlRefresh ? refs.find((r) => r.refresh_id === urlRefresh)?.cycle_id : undefined
        setCycleId((cur) =>
          cur && cyc.some((c) => c.cycle_id === cur) ? cur : (urlCycle ?? open?.cycle_id ?? latest?.cycle_id ?? ''),
        )
      })
      .catch(fail)
    return () => { live = false }
  }, [tenantId, selectedStoreId, fail, urlRefresh])

  // Refreshes belonging to the selected cycle, latest first.
  const refreshesInCycle = useMemo(
    () => refreshes
      .filter((r) => r.cycle_id === cycleId)
      .sort((a, b) => (b.refresh_no ?? 0) - (a.refresh_no ?? 0)),
    [refreshes, cycleId],
  )

  // Never auto-select an old refresh when a newer one exists — snap to the
  // latest refresh in the selected cycle (keeps a valid manual pick / URL one).
  useEffect(() => {
    setRefreshId((cur) => {
      if (cur && refreshesInCycle.some((r) => r.refresh_id === cur)) return cur
      if (urlRefresh && refreshesInCycle.some((r) => r.refresh_id === urlRefresh)) return urlRefresh
      return refreshesInCycle[0]?.refresh_id ?? ''
    })
  }, [refreshesInCycle, urlRefresh])

  // The selected cycle + its read-only state. A CLOSED cycle is view-only:
  // search / filter / print / view only — no qty edit, assign, export,
  // finalize, skip or decision change.
  const selectedCycle = useMemo(() => cycles.find((c) => c.cycle_id === cycleId) ?? null, [cycles, cycleId])
  const readOnly = (selectedCycle?.status ?? '').toUpperCase() === 'CLOSED'

  // Single gate every mutating action calls first — a closed cycle refuses the
  // write and tells the buyer why, so no edit can slip past a disabled control.
  const guardRW = useCallback((): boolean => {
    if (readOnly) {
      say('danger', 'This cycle is closed — read-only. Only viewing, search, filter and print are available.')
      return false
    }
    return true
  }, [readOnly, say])

  // A new refresh always starts at the first stage (Review Products) in Review
  // All mode and clears any picked supplier — a sensible default, not a hard
  // gate (mode stays freely switchable afterwards, independent of stage — §1).
  useEffect(() => {
    setStage('review')
    setMode('review')
    setSupplier(null)
  }, [refreshId])

  // Minimum Order Value per supplier — one batched read per store (drives the
  // Assignment Summary + supplier-search status; no per-product query).
  useEffect(() => {
    if (!tenantId || !selectedStoreId) { setMinOrders({}); return }
    let live = true
    procurementService
      .minOrders(tenantId, selectedStoreId)
      .then((m) => live && setMinOrders(m))
      .catch(() => live && setMinOrders({}))
    return () => { live = false }
  }, [tenantId, selectedStoreId])

  // "Has Offer" product codes — one batched read per refresh (store-scoped).
  useEffect(() => {
    if (!tenantId || !refreshId) { setOfferProductCodes(null); return }
    let live = true
    procurementService
      .productsWithOffers(tenantId, refreshId)
      .then((codes) => live && setOfferProductCodes(new Set(codes)))
      .catch(() => live && setOfferProductCodes(new Set()))
    return () => { live = false }
  }, [tenantId, refreshId])

  // Batched supplier recommendations for the whole refresh (one round-trip) —
  // powers the Product Grid supplier icons in every mode.
  useEffect(() => {
    setSelectedSupplier({})
    if (!tenantId || !refreshId) {
      setRecommendations({})
      return
    }
    let live = true
    procurementService
      .supplierRecommendations(tenantId, refreshId, 8)
      .then((rows) => {
        if (!live) return
        const map: Record<string, SupplierRow[]> = {}
        // Cheapest-first everywhere (grid keyboard order + side panel agree).
        rows.forEach((r) => { map[r.order_item_id] = sortSuppliersByCost(r.suppliers) })
        setRecommendations(map)
      })
      .catch(() => live && setRecommendations({}))
    return () => { live = false }
  }, [tenantId, refreshId])

  // search/movement are Review-stage-only controls (not shown once the buyer
  // moves to Assign/Optimize/Export). Derived to a boolean (not raw `stage`)
  // so loadWorkspace's identity — and therefore a refetch — only changes when
  // crossing the Review boundary, not on every Assign→Optimize→Export step.
  const isReviewStage = stage === 'review'
  const loadWorkspace = useCallback(() => {
    // Supersede any request already in flight before starting a new one.
    workspaceAbortRef.current?.abort()
    if (!tenantId || !refreshId) {
      setItems([])
      return
    }
    const controller = new AbortController()
    workspaceAbortRef.current = controller
    setLoading(true)
    setError(null)
    procurementService
      .workspace(
        tenantId, refreshId,
        {
          // A leftover search term used to silently narrow `items` outside
          // Review, which fed the Supplier Queue's assignment join and made
          // real assignments for products outside that search vanish from
          // the Export list — only apply these filters while reviewing.
          search: isReviewStage ? search : undefined,
          movement_class: isReviewStage ? (movement || undefined) : undefined,
          // Load the whole refresh (no artificial 300 cap). Typical cycles are
          // 700–1000 rows; the grid renders them behind an internal scroll.
          // TODO: true row virtualization for very large (2000+) cycles.
          page_size: 5000,
        },
        controller.signal,
      )
      .then((p) => {
        setItems(p.items)
        setTotal(p.total ?? p.items.length)
        setItemsRefreshId(refreshId)
      })
      .catch((e) => {
        if (e instanceof DOMException && e.name === 'AbortError') return // superseded, not an error
        setError(e instanceof Error ? e.message : 'Failed to load')
      })
      .finally(() => {
        if (workspaceAbortRef.current === controller) setLoading(false)
      })
  }, [tenantId, refreshId, search, movement, isReviewStage])

  useEffect(() => {
    const id = window.setTimeout(loadWorkspace, 250)
    return () => window.clearTimeout(id)
  }, [loadWorkspace])

  const storeId = useMemo(() => items.find((i) => i.store_id)?.store_id ?? '', [items])

  // Current store stock keyed by mapped ProductCode, sourced from the workspace
  // items already loaded for this refresh — lets Supplier Live Stock show the
  // store-vs-supplier comparison the buyer needs with no extra API call.
  const storeStockByCode = useMemo(() => {
    const m = new Map<string, number>()
    items.forEach((i) => {
      if (i.product_code) m.set(i.product_code, i.current_stock_qty ?? 0)
    })
    return m
  }, [items])

  // Seed order-qty draft + select the first row whenever the live-stock set
  // changes (supplier switch / search / import).
  useEffect(() => {
    setStockDraft(
      Object.fromEntries(
        supplierStock.map((r) => [stockRowKey(r), String(r.final_qty ?? r.suggested_qty ?? r.minimum_qty ?? 0)]),
      ),
    )
    setStockSelectedKey(supplierStock.length ? stockRowKey(supplierStock[0]) : null)
  }, [supplierStock])

  const selectedStockRow = useMemo(
    () => supplierStock.find((r) => stockRowKey(r) === stockSelectedKey) ?? null,
    [supplierStock, stockSelectedKey],
  )
  // Every workspace item keyed by ProductCode — lets Supplier Live Stock drive
  // the SAME Supplier Recommendation + Product Detail panels Review All uses
  // for ANY row (not just the selected one, e.g. for keyboard Right/Enter),
  // with no extra fetch (items are already loaded for this refresh).
  const stockItemByCode = useMemo(() => {
    const m = new Map<string, WorkspaceItem>()
    items.forEach((i) => { if (i.product_code) m.set(i.product_code, i) })
    return m
  }, [items])
  // Match the selected supplier-stock row to its workspace item by ProductCode
  // (both share the store's ProductCode) — feeds the reused DetailColumn and the
  // inventory/decision fields with no extra fetch.
  const matchedStockItem = useMemo(() => {
    const code = selectedStockRow?.product_code
    return code ? stockItemByCode.get(code) ?? null : null
  }, [selectedStockRow, stockItemByCode])
  const stockSummary = useMemo(() => {
    const products = supplierStock.length
    const available = supplierStock.filter((r) => (r.available_stock ?? 0) > 0).length
    const totalStock = supplierStock.reduce((s, r) => s + (r.available_stock ?? 0), 0)
    return { products, available, outOfStock: products - available, totalStock }
  }, [supplierStock])
  // Supplier Live Stock shows only Assigned / Skipped states (never
  // Pending/Finalized — those belong to the Review workflow). Derived from the
  // matched workspace item by ProductCode; same skipped-first rule as the grid.
  const stockStatusByCode = useMemo(() => {
    const m = new Map<string, 'assigned' | 'skipped'>()
    items.forEach((i) => {
      if (!i.product_code) return
      if (i.item_status === 'skipped') m.set(i.product_code, 'skipped')
      else if ((i.assigned_qty ?? 0) > 0) m.set(i.product_code, 'assigned')
    })
    return m
  }, [items])
  // Order-item ids checkable in Supplier Live Stock, keyed by ProductCode — the
  // checkbox means "included for export" (§ CHECKBOX RULE), not a selection
  // state, so an already-assigned/finalized row stays checkable (it's the
  // normal, default-ON case); only export-locked or skipped rows are excluded
  // (nothing left to export / never finalized). Feeds the SAME derived
  // `checked` set + `bulkAssign` path Supplier Purchasing already uses.
  const stockCheckableByCode = useMemo(() => {
    const m = new Map<string, string>()
    items.forEach((i) => {
      if (!i.product_code) return
      if (lockedIds.has(i.order_item_id)) return
      if (i.item_status === 'skipped') return
      m.set(i.product_code, i.order_item_id)
    })
    return m
  }, [items, lockedIds])
  const canWork = Boolean(tenantId && refreshId)

  const itemById = useMemo(() => {
    const m = new Map<string, WorkspaceItem>()
    items.forEach((i) => m.set(i.order_item_id, i))
    return m
  }, [items])

  // One product → one supplier (§1/§2): the live (non-exported) assignment per
  // order item, sourced from the same bulk assignments feed the Supplier Queue
  // already loads — no new endpoint, and it survives a page reload (unlike the
  // session-only `selectedSupplier` state). Exported lines are excluded since
  // they're locked/no longer reassignable.
  const assignedByItem = useMemo(() => {
    const m = new Map<string, { assignmentId: string; supplierCode: string; supplierName: string | null }>()
    for (const g of queueLines) {
      for (const l of g.lines) {
        if (l.exported) continue
        m.set(l.order_item_id, { assignmentId: l.assignment_id, supplierCode: g.supplier_code, supplierName: g.supplier_name })
      }
    }
    return m
  }, [queueLines])

  // Every order-item id genuinely tied to the picked supplier — LIVE or
  // EXPORTED — used only by the Supplier Purchasing grid filter below.
  // `assignedByItem` deliberately drops exported lines (they're locked/no
  // longer reassignable — correct for the one-supplier guard), but that same
  // exclusion was leaking into the grid filter: once a supplier's assigned
  // products were exported, they vanished from its Supplier Purchasing view
  // entirely (unless PurchaseTrans already had a synced-back receipt for the
  // exact SKU) — the supplier's own badge/summary counts (sourced from the
  // same queueLines) kept showing the real total, so the grid silently fell
  // out of sync with the number right next to it ("117 assigned" / "No
  // products"). This set restores the missing bridge.
  const supplierAllItemIds = useMemo(() => {
    if (mode !== 'supplier' || !supplier) return null
    const g = queueLines.find((x) => x.supplier_code === supplier.supplier_code)
    return new Set(g?.lines.map((l) => l.order_item_id) ?? [])
  }, [mode, supplier, queueLines])

  // Staged Final Qty edits that differ from the server value (and are editable).
  const dirtyIds = useMemo(() => {
    const s = new Set<string>()
    for (const [id, raw] of Object.entries(edits)) {
      const it = itemById.get(id)
      if (!it || it.item_status === 'skipped' || lockedIds.has(id)) continue
      const v = Number(raw)
      if (!Number.isNaN(v) && v >= 0 && v !== (it.final_qty ?? 0)) s.add(id)
    }
    return s
  }, [edits, itemById, lockedIds])

  const effectiveFinal = useCallback(
    (item: WorkspaceItem) => {
      const raw = edits[item.order_item_id]
      const v = raw != null ? Number(raw) : NaN
      return !Number.isNaN(v) && v >= 0 ? v : item.final_qty ?? 0
    },
    [edits],
  )

  // Totals track the *current supplier* cost: Final Qty × effective PTR (selected
  // supplier → assigned → top recommendation → item rate).
  const totalPurchaseValue = useMemo(
    () =>
      items.reduce(
        (a, it) =>
          a +
          effectiveFinal(it) *
            effectiveCost(it, recommendations[it.order_item_id], selectedSupplier[it.order_item_id]),
        0,
      ),
    [items, effectiveFinal, recommendations, selectedSupplier],
  )

  // Supplier code -> display name, harvested from the recommendations and the
  // loaded queue (both already carry supplier names) — feeds the Optimization panel.
  const supplierNames = useMemo(() => {
    const m = new Map<string, string>()
    Object.values(recommendations).forEach((list) =>
      list.forEach((s) => { if (s.supplier_code && s.supplier_name) m.set(s.supplier_code, s.supplier_name) }),
    )
    queueLines.forEach((g) => { if (g.supplier_name) m.set(g.supplier_code, g.supplier_name) })
    return m
  }, [recommendations, queueLines])
  const nameOf = useCallback((code: string) => supplierNames.get(code) ?? code, [supplierNames])

  // Per-supplier context for the search dropdown, resolved from data already
  // loaded for this refresh (Supplier Queue + Minimum Order config) — no extra
  // query. Credit is not modelled in the current schema, so it stays unknown.
  const supplierMetaOf = useCallback(
    (code: string) => {
      const g = queueLines.find((x) => x.supplier_code === code)
      const assignedProducts = g?.product_count ?? 0
      const purchaseValue = g?.live_value ?? 0
      const min = minOrders[code] ?? 0
      const status = assignedProducts === 0 ? 'New' : min > 0 && purchaseValue < min ? 'Below Min' : 'Ready'
      return { assignedProducts, purchaseValue, status, creditActive: null }
    },
    [queueLines, minOrders],
  )

  const onEditChange = (id: string, value: string) => setEdits((d) => ({ ...d, [id]: value }))

  // Enter on a Final Qty cell = Save Row immediately (keyboard workflow). Applies
  // the edit optimistically to the row and clears its dirty edit — no full
  // workspace reload, so focus and scroll position never jump for the operator.
  const saveRow = useCallback(
    async (item: WorkspaceItem) => {
      if (!guardRW()) return
      const raw = edits[item.order_item_id]
      const v = raw != null ? Number(raw) : item.final_qty ?? 0
      if (Number.isNaN(v) || v < 0) return
      // Exactly one request per real change: with no pending edit and a value
      // that already matches the server there is nothing to save — but ONLY
      // once the row is already finalised. A still-"Not Reviewed" (draft) row
      // must still hit the API even with an unchanged qty (e.g. the operator
      // accepts the pre-filled suggested qty as-is via Enter/Down): otherwise
      // item_status never flips to 'review' and the row stays stuck at Not
      // Reviewed forever. This was the actual cause of Enter/Down appearing to
      // "do nothing" — the finalize call itself was being skipped as a no-op.
      const alreadyFinalized = ['review', 'assigned', 'partial'].includes(item.item_status)
      if (raw == null && v === (item.final_qty ?? 0) && alreadyFinalized) return
      // Never let a second Enter (or an Enter immediately followed by the blur of
      // the same cell) fire a duplicate save while the first is still in flight.
      if (savingIds.current.has(item.order_item_id)) return
      savingIds.current.add(item.order_item_id)
      setItems((list) =>
        list.map((it) =>
          it.order_item_id === item.order_item_id
            ? {
                ...it,
                final_qty: v,
                // Qty > 0 finalises the row and clears any Skip mode (a re-quantified
                // skipped row automatically un-skips → Finalized). Backend
                // set_final_qty mirrors this (item_status='review', skip_reason=NULL).
                item_status: v > 0 ? 'review' : it.item_status,
                skip_reason: v > 0 ? null : it.skip_reason,
                remaining_qty: Math.max(0, v - (it.assigned_qty ?? 0)),
              }
            : it,
        ),
      )
      setEdits((d) => {
        const next = { ...d }
        delete next[item.order_item_id]
        return next
      })
      // A genuine finalize (or re-zero) transition always reverts the checkbox
      // to the default rule — ON the instant it finalizes, no stale Space Bar
      // override survives a real save (§ CHECKBOX RULE — "no user click required").
      setCheckOverrides((prev) => {
        if (!(item.order_item_id in prev)) return prev
        const next = { ...prev }
        delete next[item.order_item_id]
        return next
      })
      try {
        await procurementService.setFinalQty(tenantId, item.order_item_id, v, null, actingUser || null)
      } catch (e) {
        fail(e)
        if (!isOffline(e)) loadWorkspace()
      } finally {
        savingIds.current.delete(item.order_item_id)
      }
    },
    [edits, tenantId, actingUser, fail, loadWorkspace, guardRW],
  )

  // Ctrl/⌘+F focuses the product search. (Everything saves immediately now —
  // there is no batch Save workflow, so Ctrl+S is intentionally gone.)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || view !== 'purchase' || mode !== 'review') return
      if (e.key.toLowerCase() === 'f') {
        e.preventDefault()
        searchRef.current?.focus()
        searchRef.current?.select()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [view, mode])

  // Supplier Purchasing mode: which products this supplier has purchase history
  // for. Drives the grid filter — VPL ∩ supplier purchase history. `null` means
  // "not yet loaded" (no supplier picked, or the fetch is still in flight) and
  // must NEVER be treated as "show everything" by the filter below — that was
  // the bug (grid showed the full unfiltered VPL while this was null/loading).
  const [supplierProductsLoading, setSupplierProductsLoading] = useState(false)
  useEffect(() => {
    if (mode !== 'supplier' || !supplier || !canWork) {
      setSupplierProductIds(null)
      setSupplierProductsLoading(false)
      return
    }
    let live = true
    setSupplierProductIds(null) // clear the previous supplier's ids immediately
    setSupplierProductsLoading(true)
    // ids come back as order_item_id strings (existing endpoint, scoped to this
    // refresh + supplier's purchase history — reused as-is, no API change).
    // SQL Server's CAST(uniqueidentifier AS VARCHAR) renders UPPERCASE here,
    // matching the workspace items' own order_item_id casing exactly (verified
    // live) — do NOT lowercase these: that silently broke every `.has()` check
    // below against `i.order_item_id` and was the actual cause of "Showing 0 of
    // N" for suppliers with real purchase history (e.g. supplier 94 / 51 real
    // matches all silently rejected by the case mismatch).
    procurementService
      .supplierProducts(tenantId, refreshId, supplier.supplier_code)
      .then((ids) => live && setSupplierProductIds(new Set(ids)))
      .catch(() => live && setSupplierProductIds(new Set()))
      .finally(() => live && setSupplierProductsLoading(false))
    return () => { live = false }
  }, [mode, supplier, tenantId, refreshId, canWork])

  // Client-side view toggles the server can't express. In Supplier Purchasing
  // mode, additionally show only the selected supplier's purchased products.
  const visibleItems = useMemo(() => {
    const planningState = (i: WorkspaceItem) => {
      if (i.item_status === 'skipped') return 'skipped'
      if ((i.assigned_qty ?? 0) > 0) return 'assigned'
      if (i.item_status === 'deferred') return 'deferred'
      if (['review', 'partial'].includes(i.item_status) && (i.final_qty ?? 0) > 0) return 'finalized'
      return 'pending'
    }
    return items.filter((i) => {
      const st = planningState(i)
      if (st === 'pending' && !showPending) return false
      if (st === 'finalized' && !showFinalized) return false
      if (st === 'assigned' && !showAssigned) return false
      if (st === 'deferred' && !showDeferred) return false
      if (st === 'skipped' && !showSkipped) return false
      if (i.is_manual && !showManual) return false
      // Category filter — client-side only, never touches assignments (§5).
      if (productType && String(i.product_type ?? '') !== productType) return false
      // Has Offer filter — client-side only, never touches assignments.
      // offerProductCodes === null means "not loaded yet" and must HIDE
      // everything while offerOnly is on (same not-yet-loaded rule the
      // Supplier Purchasing filter already uses below).
      if (offerOnly) {
        if (!offerProductCodes || !i.product_code || !offerProductCodes.has(i.product_code)) return false
      }
      // Supplier Purchasing filter: VPL ∩ this supplier's purchase history,
      // plus anything already assigned to this exact supplier. No supplier
      // picked, or the purchase-history fetch hasn't resolved yet, must HIDE
      // every product — never fall back to showing the unfiltered VPL (that
      // was the bug: supplierProductIds === null used to mean "no filter").
      if (mode === 'supplier') {
        if (!supplier || supplierProductIds === null) return false
        // Already tied to this exact supplier (live OR exported) — always
        // show it, regardless of whether it still matches the VPL ∩
        // purchase-history set (an exported line's receipt may not have
        // synced back into PurchaseTrans yet).
        if (supplierAllItemIds?.has(i.order_item_id)) {
          // no-op — falls through to the final `return true`
        } else {
          const a = assignedByItem.get(i.order_item_id)
          if (a) {
            if (a.supplierCode !== supplier.supplier_code) return false
          } else if (!supplierProductIds.has(i.order_item_id)) {
            return false
          }
        }
      }
      return true
    })
  }, [items, showPending, showFinalized, showAssigned, showDeferred, showSkipped, showManual, productType, offerOnly, offerProductCodes, mode, supplier, supplierProductIds, assignedByItem, supplierAllItemIds])

  // Supplier codes with live stock for the active supplier (mode 3). Marks that
  // supplier's icon "live"; degrades to the normal recommendation otherwise.
  const liveCodes = useMemo(() => {
    if (mode !== 'supplier-stock') return null
    const codes = new Set<string>()
    supplierStock.forEach((r) => {
      if ((r.available_stock ?? 0) > 0 && r.supplier_code) codes.add(r.supplier_code)
    })
    return codes
  }, [mode, supplierStock])

  const selectedItem = useMemo(
    () => visibleItems.find((i) => i.order_item_id === selectedId) ?? null,
    [visibleItems, selectedId],
  )

  // Footer stats. Current Row = 1-based position of the selection in the current
  // (filtered) view. Pending Review = rows in the whole refresh still awaiting a
  // decision (neither finalised/assigned nor skipped).
  const currentRowNo = useMemo(
    () => visibleItems.findIndex((i) => i.order_item_id === selectedId) + 1,
    [visibleItems, selectedId],
  )
  const REVIEWED = new Set(['review', 'assigned', 'partial', 'skipped'])
  const FINALIZED_STATES = new Set(['review', 'assigned', 'partial'])
  const isFinalizedRow = (it: WorkspaceItem) => FINALIZED_STATES.has(it.item_status) && (it.final_qty ?? 0) > 0

  // Effective checkbox state (§ CHECKBOX RULE): ON by default the instant a
  // product is finalized, OFF while it isn't — `checkOverrides` only records a
  // deliberate Space Bar deviation from that default, and finalizing (or
  // skipping) a row clears its override so it snaps back to the rule.
  const checked = useMemo(() => {
    const s = new Set<string>()
    items.forEach((it) => {
      const on = checkOverrides[it.order_item_id] ?? isFinalizedRow(it)
      if (on) s.add(it.order_item_id)
    })
    return s
  }, [items, checkOverrides])

  const pendingReview = useMemo(
    () => items.filter((i) => !REVIEWED.has(i.item_status) && (i.final_qty ?? 0) === 0).length,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items],
  )

  // Keep the selection valid whenever the visible list changes (a save/skip/
  // assign, a filter toggle, a supplier switch). Adjusted DURING RENDER, guarded
  // by comparing against the previous `visibleItems` reference — React's
  // documented pattern for "adjusting state when a prop changes"
  // (https://react.dev/learn/you-might-not-need-an-effect). This used to live in
  // a useEffect keyed on [visibleItems, selectedId]: a keyboard-driven
  // save-and-advance changes both `items` (new visibleItems) and `selectedId` in
  // one batch, that effect could reassign `selectedId` again, which re-armed
  // ProductGrid's own selection-reset effect, and under the wrong timing the
  // cascade never settled — "Maximum update depth exceeded". Resolving it
  // in-render (single pass, no extra effect flush) removes that race entirely.
  const [prevVisibleItems, setPrevVisibleItems] = useState(visibleItems)
  if (visibleItems !== prevVisibleItems) {
    setPrevVisibleItems(visibleItems)
    if (visibleItems.length === 0) {
      if (selectedId !== null) setSelectedId(null)
    } else if (!visibleItems.some((i) => i.order_item_id === selectedId)) {
      setSelectedId(visibleItems[0].order_item_id)
    }
  }

  /* ---- Row actions ------------------------------------------------------- */

  // Skip is optimistic (no full workspace reload): qty → 0, status → skipped,
  // row greys immediately; the network call reconciles in the background.
  const skip = async (item: WorkspaceItem, reason: string) => {
    if (!guardRW()) return
    setItems((list) =>
      list.map((it) =>
        it.order_item_id === item.order_item_id
          ? // Persist the chosen skip mode optimistically so the Planning State
            // cell renders the actual selection (not the default) after save.
            { ...it, item_status: 'skipped', final_qty: 0, remaining_qty: 0, skip_reason: reason }
          : it,
      ),
    )
    setEdits((d) => {
      const next = { ...d }
      delete next[item.order_item_id]
      return next
    })
    // No longer finalized — revert the checkbox to its default (OFF) too.
    setCheckOverrides((prev) => {
      if (!(item.order_item_id in prev)) return prev
      const next = { ...prev }
      delete next[item.order_item_id]
      return next
    })
    try {
      await procurementService.skip(tenantId, item.order_item_id, reason, actingUser || null)
    } catch (e) {
      fail(e)
      if (!isOffline(e)) loadWorkspace()
    }
  }
  const restore = async (item: WorkspaceItem) => {
    if (!guardRW()) return
    setItems((list) =>
      list.map((it) => (it.order_item_id === item.order_item_id ? { ...it, item_status: 'review' } : it)),
    )
    try {
      await procurementService.restore(tenantId, item.order_item_id, actingUser || null)
    } catch (e) {
      fail(e)
      if (!isOffline(e)) loadWorkspace()
    }
  }

  // Assign is optimistic (no full workspace reload) so the keyboard flow stays
  // fast: remaining → 0, assigned bumps, the row's supplier is remembered so the
  // side panel shows it green. The network call reconciles in the background.
  const assign = async (item: WorkspaceItem, supplierCode: string) => {
    if (!guardRW()) return
    const remaining = item.remaining_qty ?? 0
    if (remaining <= 0) return say('danger', 'No remaining quantity to assign')
    // §11 — a rapid double Enter/click must never fire two POSTs for the same row.
    if (assigningIds.current.has(item.order_item_id)) return
    assigningIds.current.add(item.order_item_id)
    setSelectedSupplier((prev) => ({ ...prev, [item.order_item_id]: supplierCode }))
    setItems((list) =>
      list.map((it) =>
        it.order_item_id === item.order_item_id
          ? {
              ...it,
              assigned_qty: (it.assigned_qty ?? 0) + remaining,
              remaining_qty: 0,
              supplier_code: supplierCode,
              item_status: it.item_status === 'skipped' ? it.item_status : 'assigned',
            }
          : it,
      ),
    )
    try {
      await procurementService.assign(tenantId, item.order_item_id, supplierCode, remaining, actingUser || null)
      await loadQueue() // keeps assignedByItem (assignment_id) in sync for the reassign flow
    } catch (e) {
      fail(e)
      if (!isOffline(e)) loadWorkspace()
    } finally {
      assigningIds.current.delete(item.order_item_id)
    }
  }

  // Single click on a supplier icon = select only (highlight + update Cost).
  const onSelectSupplier = useCallback(
    (orderItemId: string, supplierCode: string) =>
      setSelectedSupplier((prev) =>
        prev[orderItemId] === supplierCode
          ? prev // already selected — no-op
          : { ...prev, [orderItemId]: supplierCode },
      ),
    [],
  )

  // Double click (or explicit Assign / keyboard Enter) = commit the assignment.
  // One product → one supplier (§1/§2): a product already assigned to a
  // DIFFERENT supplier is never silently overwritten here — the backend would
  // reject it anyway (409), but catching it client-side skips the round trip
  // and points the buyer at the real reassignment path (Change Supplier in
  // the Assign stage's Supplier Review panel, which confirms before moving
  // it — §7). Assigning to the SAME supplier again is just a no-op.
  const onCommitSupplier = useCallback(
    (item: WorkspaceItem, supplierCode: string) => {
      const existing = assignedByItem.get(item.order_item_id)
      if (existing && existing.supplierCode === supplierCode) return
      if (existing) {
        say('danger', `Already assigned to ${existing.supplierName ?? existing.supplierCode}. Use Change Supplier to reassign.`)
        return
      }
      setSelectedSupplier((prev) => ({ ...prev, [item.order_item_id]: supplierCode }))
      assign(item, supplierCode)
    },
    // assign is stable enough for this flow; declared above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tenantId, actingUser, assignedByItem, say],
  )

  // Space Bar / header checkbox: record a deliberate deviation from the
  // finalized-by-default rule. Never touches Final Qty or Planning State.
  const toggle = (id: string) =>
    setCheckOverrides((prev) => ({ ...prev, [id]: !checked.has(id) }))
  const toggleAll = (ids: string[], on: boolean) =>
    setCheckOverrides((prev) => {
      const next = { ...prev }
      ids.forEach((id) => { next[id] = on })
      return next
    })

  // Shared assignment path: assign a specific set of order items to a supplier
  // and refresh assigned count / row status (loadWorkspace) + supplier totals
  // (loadQueue). The backend skips any product already actively assigned, so
  // manually-assigned products are never overwritten.
  const assignIds = async (supplierCode: string, ids: string[]) => {
    if (!guardRW()) return
    const code = supplierCode.trim()
    if (!code) return say('danger', 'Pick a supplier')
    if (ids.length === 0) return say('danger', 'Nothing to assign')
    try {
      const res = await procurementService.bulkAssign(tenantId, code, ids, actingUser || null)
      say('success', `Assigned ${res.assigned}${res.skipped ? `, skipped ${res.skipped} (already assigned)` : ''}`)
      // §23 — patch exactly the rows the backend actually assigned, from its own
      // per-item results (qty included), instead of a full workspace reload.
      const okIds = new Set<string>()
      const qtyById = new Map<string, number>()
      for (const r of res.results) {
        if (r.status === 'assigned') { okIds.add(r.order_item_id); qtyById.set(r.order_item_id, r.qty ?? 0) }
      }
      setSelectedSupplier((prev) => {
        const next = { ...prev }
        okIds.forEach((id) => { next[id] = code })
        return next
      })
      setItems((list) =>
        list.map((it) =>
          okIds.has(it.order_item_id)
            ? {
                ...it,
                assigned_qty: (it.assigned_qty ?? 0) + (qtyById.get(it.order_item_id) ?? 0),
                remaining_qty: 0,
                supplier_code: code,
                item_status: it.item_status === 'skipped' ? it.item_status : 'assigned',
              }
            : it,
        ),
      )
      // No checkbox reset needed here: these rows were already finalized
      // (a prerequisite for being assign-eligible) and therefore already
      // default-checked — assigning a supplier doesn't change that.
      await loadQueue() // assignment changes + supplier totals (§23 — no full workspace reload)
    } catch (e) {
      fail(e)
    }
  }

  // Assign Selected — the checked products, scoped to what's actually shown
  // for the CURRENT supplier's view (Supplier Purchasing's already-filtered
  // grid, or Supplier Live Stock's matched rows). `checked` now defaults to
  // every finalized product refresh-wide (§ CHECKBOX RULE), so without this
  // scope a click here would try to bulk-assign finalized products belonging
  // to other suppliers' context too, not just the ones on screen.
  const bulkAssign = (supplierCode: string) => {
    const scopedIds = mode === 'supplier'
      ? new Set(visibleItems.map((i) => i.order_item_id))
      : new Set(stockCheckableByCode.values())
    assignIds(supplierCode, [...checked].filter((id) => scopedIds.has(id)))
  }

  // Assign Remaining — every currently UNASSIGNED, finalized product that the
  // selected supplier can supply (a candidate in its recommendations). Products
  // already assigned (to any supplier) are excluded, so nothing is overwritten.
  const assignRemaining = () => {
    if (!supplier) return
    const code = supplier.supplier_code
    const ids = items
      .filter(
        (it) =>
          it.item_status !== 'skipped' &&
          it.item_status !== 'deferred' && // §5/§9 — deferred rows are excluded from every bulk path
          (it.assigned_qty ?? 0) === 0 &&
          (it.final_qty ?? 0) > 0 &&
          (recommendations[it.order_item_id]?.some((r) => r.supplier_code === code) ?? false),
      )
      .map((it) => it.order_item_id)
    if (ids.length === 0) return say('danger', `No unassigned products that ${supplier.supplier_name ?? code} supplies`)
    assignIds(code, ids)
  }

  /* ---- Supplier queue + export ------------------------------------------- */

  // Recalculate supplier totals from the current draft assignments (does not
  // regenerate the VPL). Groups every assignment — exported and not — by supplier
  // so the queue can show Ready / Pending / Exported cards with product lines.
  const loadQueue = useCallback(async () => {
    if (!canWork) return
    // Two overlapping runs (rapid supplier switches, one action chaining into
    // another) can resolve out of order. Only the LATEST run is allowed to
    // commit its result — an older, slower run's response is discarded instead
    // of racing it into state.
    const runId = ++queueRunRef.current
    setQueueLoading(true)
    setQueueError(null)
    try {
      // Every live assignment for the refresh, one round-trip (was one
      // /assignments request per assigned item — the fan-out that saturated the
      // backend's request threadpool + SQL connections on a real refresh).
      const list = await withTimeout(procurementService.refreshAssignments(tenantId, refreshId)).catch(() => null)
      if (runId !== queueRunRef.current) return // superseded by a newer call
      if (list === null) {
        setQueueLines([])
        setLockedIds(new Set())
        setQueueError('Could not load the supplier queue. Retry to try again.')
        return
      }
      const map = new Map<string, SupplierQueueGroup>()
      const locked = new Set<string>()
      for (const a of list) {
        // The workspace item is used for the richer display fields (name,
        // MRP, offer) when it's loaded — but a real assignment is NEVER
        // dropped from the queue just because itemById doesn't (yet, or
        // transiently) have a matching row. Falling back to the assignment's
        // own product_code keeps the Supplier Queue / Export list complete
        // even if the workspace item list is momentarily narrower than the
        // full assignment set (e.g. still loading, or filtered elsewhere).
        const it = itemById.get(a.order_item_id)
        // Real purchase history (sync.PurchaseTrans) is authoritative when
        // present — vp.mrp/ptr_cost are never actually written by the VPL
        // generator, so these fallbacks rarely fire in practice but are kept
        // for products with no purchase history at all.
        const ptr = a.pt_ptr ?? it?.last_purchase_rate ?? it?.ptr_cost ?? 0
        const cost = a.pt_cost ?? null
        const mrp = a.pt_mrp ?? it?.mrp ?? null
        // supplier_stock (manual Live Stock import) is a fresher feed than
        // purchase history when a buyer has actually mapped it — it wins.
        const hasLiveStockOffer = (a.offer_scheme ?? 0) > 0 && (a.offer_free ?? 0) > 0
        const offer = hasLiveStockOffer
          ? formatOffer({ scheme: a.offer_scheme ?? null, free: a.offer_free ?? null, discount: null })
          : a.pt_offer ?? null
        const offerSourceLabel =
          a.pt_offer_source_date || a.pt_offer_source_supplier_name
            ? `Last received ${a.pt_offer_source_date ? date(a.pt_offer_source_date) : '—'}${
                a.pt_offer_source_supplier_name ? ` · ${a.pt_offer_source_supplier_name}` : ''
              }`
            : null
        const g =
          map.get(a.supplier_code) ??
          {
            supplier_code: a.supplier_code, supplier_name: null,
            product_count: 0, total_qty: 0, est_value: 0, live_value: 0, offer_count: 0,
            exported_count: 0, status: 'ready', exported_at: null,
            exported_by: null, export_batch_number: null,
            assignment_ids: [], lines: [],
          } as SupplierQueueGroup
        const qty = a.assigned_qty ?? 0
        const exported = a.assignment_status === 'exported'
        g.lines.push({
          assignment_id: a.assignment_id,
          order_item_id: a.order_item_id,
          product_name: it?.product_name ?? null,
          product_code: it?.product_code ?? a.product_code ?? null,
          ptr,
          cost,
          mrp,
          offer,
          discount_pct: a.pt_discount_pct ?? null,
          offer_source_label: offerSourceLabel,
          final_qty: qty,
          exported,
        })
        g.product_count += 1
        g.total_qty += qty
        g.est_value += qty * ptr
        // Purchase Value shown while a supplier is being actively worked
        // (Assignment Summary bar, supplier search meta) must always reflect
        // what's CURRENTLY pending — never include lines already exported in
        // a prior batch, or the figure keeps growing stale as export history
        // accumulates instead of resetting to the live working set.
        if (!exported) g.live_value += qty * ptr
        if (offer) g.offer_count += 1
        if (exported) {
          locked.add(a.order_item_id)
          g.exported_count += 1
          g.exported_at = a.exported_at ?? g.exported_at
          g.exported_by = a.export_uid ?? g.exported_by
          g.export_batch_number = a.export_batch_number ?? g.export_batch_number
        } else {
          g.assignment_ids.push(a.assignment_id)
        }
        map.set(a.supplier_code, g)
      }
      const groups = [...map.values()]
      groups.forEach((g) => {
        g.status = g.exported_count === 0 ? 'ready' : g.exported_count >= g.product_count ? 'exported' : 'partial'
        // The assignments feed itself carries no supplier name (just the
        // code) — backfill from the batched recommendations, which already
        // LEFT JOIN sync.Suppliers for real names. Read fresh each call (not
        // baked in at group-creation time) so a supplier queue built before
        // recommendations finished loading still self-corrects on the next
        // loadQueue() run instead of freezing on the bare code forever.
        const realName = supplierNames.get(g.supplier_code)
        if (realName) g.supplier_name = realName
      })
      groups.sort((a, b) => b.est_value - a.est_value)
      setQueueLines(groups)
      setLockedIds(locked)
      setQueueError(null)
    } catch (e) {
      if (runId === queueRunRef.current) {
        setQueueError(e instanceof Error ? e.message : 'Failed to load the supplier queue.')
        fail(e)
      }
    } finally {
      if (runId === queueRunRef.current) setQueueLoading(false)
    }
  }, [canWork, itemById, tenantId, refreshId, fail, supplierNames])

  // Eagerly load the refresh's assignments as soon as the workspace items are
  // in (not only when the buyer reaches the Assign/Optimize/Export stage) so
  // `assignedByItem` — and therefore "Assigned to X" / the one-supplier guard
  // — is correct from the very first render, including right after a reload.
  //
  // Gated on itemsRefreshId === refreshId (not just items.length > 0): on a
  // Refresh switch, `items` still holds the PREVIOUS refresh's rows for a
  // moment while the new fetch is in flight — items.length > 0 stays true
  // through that gap, so this used to fire loadQueue immediately with a stale
  // itemById, join every fresh assignment row against the wrong refresh's
  // items, drop them all, and render an empty Supplier Queue until a manual
  // Reload. itemsRefreshId only updates once loadWorkspace's fetch actually
  // resolves, so this now waits for items/itemById to genuinely match.
  const itemsReady = itemsRefreshId === refreshId && items.length > 0
  useEffect(() => {
    if (canWork && itemsReady) loadQueue()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canWork, tenantId, refreshId, itemsReady])
  // Covers the gap between "workspace selected" and "the first loadQueue call
  // has actually started" (queueLoading is still its initial `false` there) —
  // without this, the Assign/Export panels would flash "No suppliers
  // available" for a moment before the real fetch kicks off (§5 — never show
  // an empty page while data is still on its way in).
  const queuePending = canWork && !itemsReady

  // Returns whether the export actually happened, so callers (e.g. the Assign
  // stage's Export + Next Supplier flow) never advance/download on a failure.
  // `announce` is false when a caller wants to show its own combined message
  // instead of this one flashing first.
  const exportGroup = async (group: SupplierQueueGroup, assignmentIds: string[], announce = true) => {
    if (!guardRW()) return
    if (assignmentIds.length === 0) { say('danger', 'Nothing to export for this supplier'); return false }
    setBusySupplier(group.supplier_code)
    try {
      const res = await procurementService.exportRefresh(tenantId, refreshId, actingUser, assignmentIds)
      if (announce) say('success', `Exported ${res.exported_count} lines (${group.supplier_code})`)
      // §23 — export only stamps the assignment rows (assignment_status/export
      // fields); it never changes an order item's own qty/status, so the queue
      // reload (which already recomputes lockedIds) is enough — no full
      // workspace reload.
      await loadQueue()
      return true
    } catch (e) {
      fail(e)
      return false
    } finally {
      setBusySupplier(null)
    }
  }

  // Plain per-supplier Export (§14): resolves the CURRENT live assignment set
  // on the backend at request time (supplier_code, not a client id snapshot),
  // so it can never miss an assignment made after the last queue reload or
  // send an empty export while real assignments exist.
  const exportSupplierLive = async (supplierCode: string) => {
    if (!guardRW()) return
    if (busySupplier) return // §11-style guard: no overlapping export requests
    setBusySupplier(supplierCode)
    try {
      const res = await procurementService.exportRefresh(tenantId, refreshId, actingUser, undefined, supplierCode)
      say('success', `Exported ${res.exported_count} lines (${supplierCode})`)
      await loadQueue() // §23 — export status only, no full workspace reload
    } catch (e) {
      fail(e)
    } finally {
      setBusySupplier(null)
    }
  }

  const exportAll = async () => {
    if (!guardRW()) return
    if (exportingAll) return // §11-style guard: no overlapping export requests
    setExportingAll(true)
    try {
      const res = await procurementService.exportRefresh(tenantId, refreshId, actingUser)
      say('success', `Exported ${res.exported_count} lines as ${res.export_batch_number}`)
      await loadQueue() // §23 — export status only, no full workspace reload
    } catch (e) {
      fail(e)
    } finally {
      setExportingAll(false)
    }
  }

  // Export Selected Suppliers (§12) — a buyer-checked subset, one per-supplier
  // export call each (same live-resolve path exportSupplierLive already uses),
  // sequential so requests never race the shared busySupplier guard.
  const exportSelectedSuppliers = async (supplierCodes: string[]) => {
    if (!guardRW()) return
    if (exportingSelected || supplierCodes.length === 0) return
    setExportingSelected(true)
    let total = 0
    let failed = 0
    try {
      for (const code of supplierCodes) {
        try {
          const res = await procurementService.exportRefresh(tenantId, refreshId, actingUser, undefined, code)
          total += res.exported_count
        } catch {
          failed += 1
        }
      }
      say(
        failed > 0 ? 'danger' : 'success',
        `Exported ${total} lines across ${supplierCodes.length - failed} supplier${supplierCodes.length - failed === 1 ? '' : 's'}${failed > 0 ? ` · ${failed} failed` : ''}`,
      )
      await loadQueue()
    } finally {
      setExportingSelected(false)
    }
  }

  /* ---- Stages, Auto Assign & Supplier Review ----------------------------- */

  // Assignment progress gates the later stages (Supplier Queue / Export stay
  // hidden until at least one product has been assigned to a supplier — #7).
  const assignedCount = useMemo(() => items.filter((i) => (i.assigned_qty ?? 0) > 0).length, [items])
  const hasAssignments = assignedCount > 0

  // The selected supplier's Queue group feeds the right-hand Supplier Review panel.
  const selectedGroup = useMemo(
    () => (supplier ? queueLines.find((g) => g.supplier_code === supplier.supplier_code) ?? null : null),
    [queueLines, supplier],
  )

  // Suppliers that still have live (not-yet-exported) assigned products — the
  // set "Next Supplier" cycles through, so it never lands on a supplier with
  // nothing left to review.
  const suppliersNeedingReview = useMemo(
    () => queueLines.filter((g) => g.assignment_ids.length > 0),
    [queueLines],
  )
  // Only supplier_code/supplier_name are ever read off the picked supplier
  // downstream (grid filter, Supplier Review panel, min-order lookup) — the
  // Supplier Queue group already carries both, so no extra lookup is needed.
  const supplierRowFromGroup = (g: SupplierQueueGroup): SupplierRow => ({
    supplier_code: g.supplier_code,
    supplier_name: g.supplier_name,
    purchase_frequency: null,
    last_grn_date: null,
    last_grn_no: null,
    last_purchase_rate: null,
    avg_lead_days: null,
  })

  // Next Supplier (manual): move on from the current supplier — whether or not
  // it was exported — to whichever supplier needing review comes after it in
  // the queue, wrapping around. Never jumps back to the first supplier in the
  // list ("do not return the user to the beginning" — it always continues from
  // the current position). Stops with a clear message once nobody is left.
  const advanceToNextSupplier = useCallback(() => {
    const list = suppliersNeedingReview
    if (list.length === 0) { say('success', 'All suppliers have been reviewed'); setSupplier(null); return }
    const curCode = supplier?.supplier_code
    const idx = curCode ? list.findIndex((g) => g.supplier_code === curCode) : -1
    const ordered = idx >= 0 ? [...list.slice(idx + 1), ...list.slice(0, idx + 1)] : list
    const next = ordered.find((g) => g.supplier_code !== curCode) ?? ordered[0]
    setSupplier(supplierRowFromGroup(next))
  }, [suppliersNeedingReview, supplier, say])

  // Export Purchase Order + auto-advance (§3): resolve the next supplier BEFORE
  // exporting (the just-exported supplier's own assignment_ids will be empty
  // afterwards, so it naturally falls out of `suppliersNeedingReview` once
  // loadQueue's result lands — no need to wait for that fresh state here).
  const exportAndAdvance = async (group: SupplierQueueGroup) => {
    const list = suppliersNeedingReview
    const idx = list.findIndex((g) => g.supplier_code === group.supplier_code)
    const ordered = idx >= 0 ? [...list.slice(idx + 1), ...list.slice(0, idx)] : list
    const next = ordered.find((g) => g.supplier_code !== group.supplier_code) ?? null
    // Export only the lines still checked "Included for export" (§ CHECKBOX
    // RULE) — a Space Bar uncheck holds a specific product back from this
    // export run without touching its assignment or Final Qty.
    const exportIds = group.lines.filter((l) => !l.exported && checked.has(l.order_item_id)).map((l) => l.assignment_id)
    if (exportIds.length === 0) { say('danger', 'Nothing checked for export — press Space to include at least one product.'); return }
    const ok = await exportGroup(group, exportIds, false)
    if (!ok) return
    downloadPurchaseOrderCsv(group)
    if (next) {
      setSupplier(supplierRowFromGroup(next))
      say('success', `Exported ${group.supplier_code} — moved to ${next.supplier_name ?? next.supplier_code}`)
    } else {
      setSupplier(null)
      say('success', `Exported ${group.supplier_code} — all suppliers reviewed`)
    }
  }

  // Move to a stage; refresh the supplier totals when leaving Review so the
  // review/optimize/export panels always reflect the latest assignments.
  // Mode is independent of stage (§1) — navigating stages no longer resets it.
  const goStage = (s: Stage) => {
    if (s === 'export' && !hasAssignments) return say('danger', 'Assign suppliers before exporting')
    if (s !== 'review') loadQueue()
    setStage(s)
  }

  // Auto Assign: give every finalized, still-unassigned product to exactly ONE
  // supplier chosen by the documented priority (Exact Product Mapping → Last
  // Purchase Supplier → Preferred Supplier — see autoAssignSupplier). Reuses the
  // bulk assignment API — one call per supplier, no new endpoint, no mock data.
  // Auto Supplier Assignment (§15/§16) — manual always outranks auto. Scope is
  // strictly: finalized (Final Qty set), not skipped/locked, and NOT already
  // carrying a supplier (remaining_qty > 0 — every assignment path in this app
  // commits the full remaining qty in one shot, so remaining_qty <= 0 reliably
  // means "already owned by a supplier", whether that assignment was made
  // manually or by a previous Auto Assign run). Products excluded here are
  // never sent to the backend at all, so their Supplier / Final Qty / Review
  // Status can't change — and the backend's one-supplier rule (assign_bulk)
  // is a second, authoritative guard against the narrow race where a manual
  // assignment lands while this bulk call is already in flight.
  // "Pharma Only" scopes Auto Assign to Pharma-classified products
  // (product_type === 1) — a buyer-facing opt-in, off by default (every
  // product type is eligible unless explicitly narrowed).
  const [pharmaOnly, setPharmaOnly] = useState(false)
  // Cost mode = today's weighted score (mapping/recency/frequency/PTR/live
  // stock). Rank mode = greedy by the buyer's manual Supplier Rank (see
  // SupplierRankPanel / computeRankAssignment) — two distinct algorithms,
  // never blended.
  const [assignMode, setAssignMode] = useState<'cost' | 'rank'>('cost')
  const [autoAssignPreview, setAutoAssignPreview] = useState<{
    groups: { supplier_code: string; order_item_ids: string[] }[]
    droppedBelowMin: { supplier_code: string; count: number }[]
  } | null>(null)

  // Eligible products for the ACTIVE Pharma Only setting — also the exact
  // scope the Supplier Rank panel's live "Possible Products" preview uses.
  const autoAssignEligible = useMemo(
    () => eligibleForAutoAssign(items, lockedIds, pharmaOnly),
    [items, lockedIds, pharmaOnly],
  )

  // Step 1 — compute candidate assignments (never calls the assignment API)
  // and open the preview. Auto Supplier Assignment (§15/§16) — manual always
  // outranks auto; only genuinely Reviewed, unassigned, non-skipped/locked/
  // deferred products are ever candidates (eligibleForAutoAssign), so the
  // backend's own one-supplier guard is a second, defensive check only.
  const prepareAutoAssign = async () => {
    if (autoAssignEligible.length === 0) {
      return say('danger', 'Nothing to auto-assign — finalize quantities for unassigned products first')
    }
    const rawGroups: Record<string, string[]> = {}
    const minProductsByCode: Record<string, number> = {}
    if (assignMode === 'rank') {
      setAutoBusy(true)
      try {
        const settings = await procurementService.supplierSettings(tenantId, selectedStoreId)
        const ranks: Record<string, number | null> = {}
        const autoFlags: Record<string, boolean> = {}
        settings.forEach((s) => {
          ranks[s.supplier_code] = s.export_rank
          autoFlags[s.supplier_code] = s.auto_assign
          minProductsByCode[s.supplier_code] = s.min_products
        })
        const result = computeRankAssignment(autoAssignEligible, recommendations, ranks, autoFlags)
        Object.assign(rawGroups, result.assignedItems)
      } catch (e) {
        fail(e)
        setAutoBusy(false)
        return
      }
      setAutoBusy(false)
    } else {
      autoAssignEligible.forEach((it) => {
        const recs = recommendations[it.order_item_id]
        const top = autoAssignSupplier(recs)
        if (!top) return
        const supRow = recs?.find((r) => r.supplier_code === top)
        if (supRow?.min_products != null) minProductsByCode[top] = supRow.min_products
        if (!rawGroups[top]) rawGroups[top] = []
        rawGroups[top].push(it.order_item_id)
      })
    }
    // A supplier that would only receive a lonely handful of products (below
    // its configured minimum, default 2) is dropped entirely — those products
    // stay unassigned for manual review rather than trickling a single line.
    const droppedBelowMin: { supplier_code: string; count: number }[] = []
    const groups: { supplier_code: string; order_item_ids: string[] }[] = []
    for (const [code, ids] of Object.entries(rawGroups)) {
      if (ids.length === 0) continue
      const min = minProductsByCode[code] ?? 2
      if (ids.length < min) droppedBelowMin.push({ supplier_code: code, count: ids.length })
      else groups.push({ supplier_code: code, order_item_ids: ids })
    }
    if (groups.length === 0 && droppedBelowMin.length === 0) {
      return say('danger', 'No purchase history found for eligible products')
    }
    setAutoAssignPreview({ groups, droppedBelowMin })
  }

  // Step 2 — the buyer confirmed the preview; now actually assign.
  const commitAutoAssign = async () => {
    if (!guardRW()) return
    if (!autoAssignPreview) return
    setAutoBusy(true)
    try {
      let assigned = 0
      let raceSkipped = 0 // caught by the backend's own guard mid-run (§7/§12)
      let failed = 0
      for (const g of autoAssignPreview.groups) {
        try {
          const res = await procurementService.bulkAssign(tenantId, g.supplier_code, g.order_item_ids, actingUser || null)
          assigned += res.assigned
          raceSkipped += res.skipped
        } catch {
          failed += g.order_item_ids.length
        }
      }
      const parts = [`Assigned ${assigned}`]
      if (raceSkipped > 0) parts.push(`Skipped ${raceSkipped} (already assigned)`)
      const belowMinTotal = autoAssignPreview.droppedBelowMin.reduce((a, d) => a + d.count, 0)
      if (belowMinTotal > 0) parts.push(`${belowMinTotal} left unassigned (below supplier minimum)`)
      if (failed > 0) parts.push(`Failed ${failed}`)
      say(failed > 0 ? 'danger' : 'success', `Auto Assign — ${parts.join(' · ')}`)
      setAutoAssignPreview(null)
      loadWorkspace()
      await loadQueue()
    } catch (e) {
      fail(e)
    } finally {
      setAutoBusy(false)
    }
  }

  // Changing supplier never touches the order item's own qty/status (it's
  // still fully assigned, just to a different supplier) — the queue reload
  // alone keeps assignedByItem / the review panel / the grid's Assigned tag
  // correct, no full workspace reload needed (§23).
  const reviewChangeSupplier = async (assignmentId: string, newSupplier: SupplierRow) => {
    if (!guardRW()) return
    try {
      await procurementService.changeSupplier(tenantId, assignmentId, newSupplier.supplier_code, actingUser || null)
      say('success', `Moved to ${newSupplier.supplier_name ?? newSupplier.supplier_code}`)
      await loadQueue()
    } catch (e) {
      fail(e)
    }
  }
  // Removing a supplier DOES revert the order item's own status (assigned →
  // review/draft) — reconcile just that one row from the server instead of
  // reloading the whole workspace (§23).
  const reviewRemove = async (assignmentId: string, orderItemId: string) => {
    if (!guardRW()) return
    try {
      await procurementService.removeAssignment(tenantId, assignmentId, actingUser || null)
      say('success', 'Removed from supplier')
      const fresh = await procurementService.getOrderItem(tenantId, orderItemId)
      setItems((list) => list.map((it) => (it.order_item_id === orderItemId ? fresh : it)))
      await loadQueue()
    } catch (e) {
      fail(e)
    }
  }

  // Refresh the supplier totals whenever a supplier is picked in Supplier
  // Purchasing mode (any stage — mode is independent of stage, §1) so the
  // right-hand Supplier Review panel reflects the latest assignments.
  useEffect(() => {
    if (mode === 'supplier' && supplier) loadQueue()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supplier, mode])

  /* ---- Manual product ---------------------------------------------------- */

  const addManual = async (product: ManualProduct, qty: number) => {
    if (!guardRW()) return
    if (manualBusy) return // guard against a duplicate submit racing this one
    setManualBusy(true)
    try {
      const res = await procurementService.addManualItem(
        tenantId, refreshId, product.product_code, product.product_name ?? product.product_code, qty, actingUser || null,
      )
      say('success', res.already_exists ? `${product.product_code} is already in this refresh` : `Added ${product.product_code}`)
      setManualOpen(false)
      loadWorkspace()
    } catch (e) {
      fail(e)
    } finally {
      setManualBusy(false)
    }
  }

  /* ---- Supplier Live Stock ----------------------------------------------- */

  useEffect(() => {
    if (mode !== 'supplier-stock' || !supplier || !canWork) {
      setSupplierStock([])
      return
    }
    let live = true
    setSupplierStockLoading(true)
    setSupplierStockError(null)
    const t = window.setTimeout(() => {
      procurementService
        .supplierStock(tenantId, refreshId, supplier.supplier_code, stockSearch || undefined)
        .then((rows) => live && setSupplierStock(rows))
        .catch((e) => {
          if (!live) return
          setSupplierStock([])
          setSupplierStockError(
            e instanceof ApiError && e.status === 404
              ? 'The supplier-stock endpoint is not enabled on this server yet.'
              : e instanceof Error ? e.message : 'Failed to load supplier stock',
          )
        })
        .finally(() => live && setSupplierStockLoading(false))
    }, 250)
    return () => {
      live = false
      window.clearTimeout(t)
    }
  }, [mode, supplier, tenantId, refreshId, canWork, stockSearch, stockReloadKey])

  const orderSupplierStock = async (row: SupplierStockRow, qty: number) => {
    if (!guardRW()) return
    if (!row.product_code) return say('danger', 'Row has no mapped product code')
    if (manualBusy) return // guard against a duplicate submit racing this one
    setManualBusy(true)
    try {
      const res = await procurementService.addManualItem(
        tenantId, refreshId, row.product_code, row.supplier_product_name ?? row.product_code, qty, actingUser || null,
      )
      say(
        'success',
        res.already_exists
          ? `${row.product_code} is already in this refresh — assign ${supplier?.supplier_code ?? 'a supplier'} in Review mode`
          : `Added ${qty} × ${row.product_code} — assign ${supplier?.supplier_code ?? 'a supplier'} in Review mode`,
      )
      loadWorkspace()
    } catch (e) {
      fail(e)
    } finally {
      setManualBusy(false)
    }
  }

  const onImportPick = (file: File | null) => {
    if (importInputRef.current) importInputRef.current.value = ''
    if (!file) return
    if (!supplier || !storeId) {
      say('danger', 'Pick a supplier first, then import their stock file.')
      return
    }
    setImportFile(file)
  }

  /* ---- Pending + GRN ----------------------------------------------------- */

  const loadPending = useCallback(() => {
    if (!canWork) return
    procurementService
      .pending(tenantId, refreshId)
      .then((p) => {
        setPending(p.items)
        setPendingDraft(Object.fromEntries(p.items.map((i) => [i.order_item_id, String(i.remaining_qty ?? 0)])))
        setPendingSel(new Set())
      })
      .catch(fail)
  }, [canWork, tenantId, refreshId, fail])

  useEffect(() => {
    if (view === 'pending') loadPending()
  }, [view, loadPending])

  const focusPending = (index: number) => {
    const el = document.getElementById(`pending-input-${index}`) as HTMLInputElement | null
    el?.focus()
    el?.select()
  }
  const savePendingRow = async (item: PendingItem, index: number) => {
    if (!guardRW()) return
    const value = Number(pendingDraft[item.order_item_id] ?? '0')
    if (Number.isNaN(value) || value < 0) return say('danger', 'Enter a non-negative number')
    try {
      if (value <= 0) await procurementService.skipPending(tenantId, item.order_item_id, actingUser || null)
      else await procurementService.adjustPending(tenantId, item.order_item_id, value, actingUser || null)
      focusPending(index + 1)
    } catch (e) {
      fail(e)
    }
  }
  const onPendingKey = (e: ReactKeyboardEvent<HTMLInputElement>, item: PendingItem, index: number) => {
    if (e.key === 'Enter') { e.preventDefault(); savePendingRow(item, index) }
    else if (e.key === 'ArrowDown') { e.preventDefault(); focusPending(index + 1) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusPending(index - 1) }
    else if (e.key === 'Escape') { e.preventDefault(); setPendingDraft((d) => ({ ...d, [item.order_item_id]: '0' })) }
  }
  const finalizePending = async () => {
    if (!guardRW()) return
    try {
      const r = await procurementService.finalizePending(tenantId, refreshId, actingUser || null)
      say('success', `Finalized ${r.finalized} pending items`)
      loadPending()
    } catch (e) {
      fail(e)
    }
  }
  const carryForwardPending = async (item: PendingItem) => {
    if (!guardRW()) return
    try {
      await procurementService.carryForwardPending(tenantId, item.order_item_id, actingUser || null)
      say('success', 'Carried forward to next refresh')
      loadPending()
    } catch (e) {
      fail(e)
    }
  }
  // Bulk processing: apply one action to many pending items at once.
  const bulkPending = async (action: 'carry' | 'skip' | 'finalize', ids: string[]) => {
    if (!guardRW()) return
    if (ids.length === 0) return say('danger', 'Select at least one pending item')
    setPendingBusy(true)
    try {
      const r = await procurementService.bulkPending(tenantId, refreshId, action, ids, actingUser || null)
      const verb = action === 'carry' ? 'Carried' : action === 'skip' ? 'Skipped' : 'Finalized'
      say('success', `${verb} ${r.processed} pending item${r.processed === 1 ? '' : 's'}`)
      loadPending()
    } catch (e) {
      fail(e)
    } finally {
      setPendingBusy(false)
    }
  }
  // Supplier-wise carry: carry every pending item for one supplier.
  const carrySupplier = (supplierCode: string) => {
    const ids = pending.filter((p) => (p.supplier_code ?? '') === supplierCode).map((p) => p.order_item_id)
    bulkPending('carry', ids)
  }
  const downloadPendingReport = async () => {
    try {
      const blob = await procurementService.pendingReport(tenantId, refreshId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `pending-${refreshId.slice(0, 8)}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      fail(e)
    }
  }
  const submitGrn = async () => {
    if (!guardRW()) return
    if (!grnNumber.trim()) return say('danger', 'Enter the Last GRN number')
    try {
      const res = await procurementService.submitGrn(tenantId, refreshId, grnNumber.trim(), actingUser || null)
      say('success', `GRN ${res.last_grn_number}: completed ${res.items_completed}, pending ${res.items_pending}`)
    } catch (e) {
      fail(e)
    }
  }

  return (
    <div className="pm">
      <header className="pm-top">
        <div className="pm-top__ctx">
          <span className="pm-top__brand"><i className="bi bi-cart-check" /> Purchase Manager</span>
          <select className="sx-select" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
          <select className="sx-select" aria-label="Store" value={selectedStoreId} onChange={(e) => setSelectedStoreId(e.target.value)}>
            <option value="">Select store…</option>
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </select>
          {/* Cycle selector — current OPEN cycle is auto-selected; previous
              CLOSED cycles stay viewable (read-only). */}
          <select className="sx-select" aria-label="Cycle" value={cycleId} onChange={(e) => setCycleId(e.target.value)}>
            <option value="">Select cycle…</option>
            {cycles.map((c) => (
              <option key={c.cycle_id} value={c.cycle_id}>
                {c.name}{(c.status ?? '').toUpperCase() === 'ACTIVE' ? '' : ' · Closed'}
              </option>
            ))}
          </select>
          {/* Refresh selector — scoped to the selected cycle, latest first. */}
          <select className="sx-select" aria-label="Refresh" value={refreshId} onChange={(e) => setRefreshId(e.target.value)}>
            <option value="">{refreshesInCycle.length ? 'Select refresh…' : 'No refreshes'}</option>
            {refreshesInCycle.map((r) => <option key={r.refresh_id} value={r.refresh_id}>{r.snapshot_name} · {r.snapshot_status}</option>)}
          </select>
          {readOnly && (
            <span className="pm-ro-badge" title="This cycle is closed — viewing only">
              <i className="bi bi-lock-fill" /> Read Only · Closed Cycle
            </span>
          )}
        </div>
        {/* Stage stepper rides the header row rather than owning a second full-
            width row of its own — the row had ~60% empty space and the detail
            panel below needs the height (Sales History was falling off-screen). */}
        {canWork && view === 'purchase' && (
          <nav className="pm-stages" aria-label="Purchase workflow stages">
            {STAGES.map((st, i) => {
              const active = stage === st.key
              const locked = st.key === 'export' && !hasAssignments
              return (
                <button
                  key={st.key}
                  className={`pm-stage${active ? ' pm-stage--on' : ''}${locked ? ' pm-stage--locked' : ''}`}
                  aria-current={active ? 'step' : undefined}
                  disabled={locked}
                  title={locked ? 'Assign suppliers first' : st.label}
                  onClick={() => goStage(st.key)}
                >
                  <span className="pm-stage__no">{i + 1}</span>
                  <span className="pm-stage__lbl"><i className={`bi ${st.icon}`} /> {st.label}</span>
                </button>
              )
            })}
          </nav>
        )}
        <div className="pm-top__views">
          {(['purchase', 'pending', 'grn'] as View[]).map((v) => (
            <button key={v} className={`pm-vtab${view === v ? ' pm-vtab--on' : ''}`} onClick={() => setView(v)}>
              {v === 'purchase' ? 'Purchase' : v === 'pending' ? 'Pending' : 'GRN'}
            </button>
          ))}
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      {!canWork ? (
        <EmptyState icon="bi-clipboard-check" title="Select a tenant and refresh" description="Choose a generated refresh to open the Purchase Manager workspace." />
      ) : view === 'pending' ? (
        <PendingView
          pending={pending}
          draft={pendingDraft}
          setDraft={setPendingDraft}
          onKey={onPendingKey}
          onFinalize={finalizePending}
          onCarry={carryForwardPending}
          selected={pendingSel}
          setSelected={setPendingSel}
          busy={pendingBusy}
          onBulk={bulkPending}
          onCarrySupplier={carrySupplier}
          onReport={downloadPendingReport}
        />
      ) : view === 'grn' ? (
        <div className="pm-grn">
          <div className="pm-grn__row">
            <span>Last GRN Number</span>
            <input className="pm-top__user" value={grnNumber} placeholder="e.g. 4567" onChange={(e) => setGrnNumber(e.target.value)} />
            <button className="pm-btn pm-btn--primary" onClick={submitGrn}>Submit &amp; Reconcile</button>
          </div>
          <p className="text-muted small mt-2">Entering the Last GRN triggers store sync and reconciles received quantities against assignments automatically.</p>
        </div>
      ) : (
        <>
          {/* The stage stepper (Review → Assign → Optimize → Export) lives in the
              page header row above, not here. */}

          {/* Contextual toolbar — only for the grid stages (Review / Assign).
              Review Mode (Review All / Supplier Purchasing / Supplier Live
              Stock) is independent of the stage stepper — a buyer can be in
              any mode while still Reviewing, and Supplier Purchasing keeps
              its full Assign/Reassign/Remove/Export panel available in any
              stage (see the right-detail-column condition below). Search /
              Movement stay Review-stage-only: they're server query params
              that only ever applied while `isReviewStage` (loadWorkspace),
              to avoid silently narrowing the Supplier Queue's assignment join. */}
          {/* Fixed two-row layout: every control owns a permanent slot of a
              fixed width, so switching mode/stage only empties a slot — it
              never re-flows the row or moves the other controls. */}
          {(stage === 'review' || stage === 'assign') && (
            <div className="pm-toolbar">
              <div className="pm-toolbar__row">
                <div className="pm-toolbar__modes">
                  {MODE_OPTIONS.map((m) => (
                    <button key={m.value} className={`pm-mode${mode === m.value ? ' pm-mode--on' : ''}`} onClick={() => setMode(m.value)}>
                      {m.label}
                    </button>
                  ))}
                </div>
                <div className="pm-slot pm-slot--search">
                  {isReviewStage && (
                    <span className="sx-search">
                      <i className="bi bi-search" aria-hidden="true" />
                      <input ref={searchRef} type="search" value={search} placeholder="Search product…" aria-label="Search product" onChange={(e) => setSearch(e.target.value)} />
                    </span>
                  )}
                </div>
                <div className="pm-slot pm-slot--select">
                  {isReviewStage && (
                    <select className={`sx-select${movement ? ' sx-select--active' : ''}`} aria-label="Movement filter" value={movement} onChange={(e) => setMovement(e.target.value)}>
                      {MOVEMENT.map((m) => <option key={m} value={m}>{m || 'Movement: all'}</option>)}
                    </select>
                  )}
                </div>
                {/* Category filter is available in every mode/stage (§5) — it
                    only narrows the grid view, it never touches assignments. */}
                <div className="pm-slot pm-slot--select">
                  {mode !== 'supplier-stock' && (
                    <select className={`sx-select${productType ? ' sx-select--active' : ''}`} aria-label="Product Type filter" value={productType} onChange={(e) => setProductType(e.target.value)}>
                      <option value="">Product Type: all</option>
                      <option value="1">Pharma</option>
                      <option value="0">Non-Pharma</option>
                      <option value="2">Others</option>
                    </select>
                  )}
                </div>
                {/* Has Offer belongs with the scope filters, not the planning
                    states below: it narrows WHICH products are worth buying
                    (ever purchased with free qty), it says nothing about how
                    far a product got through review. */}
                <div className="pm-slot pm-slot--offer">
                  {mode !== 'supplier-stock' && (
                    <label className="pm-chk pm-chk--offer" title="Only products this store has bought with free qty at least once (purchase history)">
                      <input type="checkbox" checked={offerOnly} onChange={(e) => setOfferOnly(e.target.checked)} />
                      <i className="bi bi-tag" aria-hidden="true" /> Has Offer
                    </label>
                  )}
                </div>
                <div className="pm-slot pm-slot--supplier">
                  {mode !== 'review' && (
                    <SupplierPicker
                      tenantId={tenantId}
                      storeId={storeId}
                      value={supplier}
                      onPick={setSupplier}
                      onReturnToGrid={() => (document.querySelector('.pm-grid-wrap') as HTMLElement | null)?.focus()}
                      metaOf={supplierMetaOf}
                    />
                  )}
                </div>
                <div className="pm-toolbar__right">
                  {isReviewStage && (
                    <button className="pm-btn pm-btn--ghost" onClick={() => setManualOpen(true)}><i className="bi bi-plus-lg" /> Manual</button>
                  )}
                  <button className="pm-btn pm-btn--ghost" onClick={loadWorkspace} title="Refresh"><i className="bi bi-arrow-repeat" /></button>
                </div>
              </div>

              {/* Second row keeps its height in every mode, so the grid below
                  never jumps when the filters change. */}
              <div className="pm-toolbar__row pm-toolbar__row--filters">
                {mode !== 'supplier-stock' && (
                  <>
                    <span className="pm-toolbar__label">Show</span>
                    {/* The supplier workspace is assignment-based, not
                        review-based (§18): default shows every state (all six
                        stay checked), these are opt-in narrower views, never an
                        automatic hide. */}
                    <label className="pm-chk"><input type="checkbox" checked={showPending} onChange={(e) => setShowPending(e.target.checked)} /> Pending Review</label>
                    <label className="pm-chk"><input type="checkbox" checked={showFinalized} onChange={(e) => setShowFinalized(e.target.checked)} /> Finalized</label>
                    <label className="pm-chk"><input type="checkbox" checked={showAssigned} onChange={(e) => setShowAssigned(e.target.checked)} /> Assigned</label>
                    <label className="pm-chk"><input type="checkbox" checked={showDeferred} onChange={(e) => setShowDeferred(e.target.checked)} /> Deferred</label>
                    <label className="pm-chk"><input type="checkbox" checked={showSkipped} onChange={(e) => setShowSkipped(e.target.checked)} /> Skipped</label>
                    <label className="pm-chk"><input type="checkbox" checked={showManual} onChange={(e) => setShowManual(e.target.checked)} /> Manual</label>
                  </>
                )}
                {mode === 'supplier-stock' && (
                  <>
                    <div className="pm-slot pm-slot--search">
                      <span className="sx-search">
                        <i className="bi bi-search" aria-hidden="true" />
                        <input type="search" value={stockSearch} placeholder="Search live stock…" aria-label="Search live stock" onChange={(e) => setStockSearch(e.target.value)} />
                      </span>
                    </div>
                    <button
                      className="pm-btn pm-btn--import"
                      disabled={!supplier}
                      title={supplier ? 'Import this supplier’s stock from Excel' : 'Select a supplier first'}
                      onClick={() => importInputRef.current?.click()}
                    >
                      <i className="bi bi-upload" /> Import Stock
                    </button>
                    <input ref={importInputRef} type="file" accept=".xls,.xlsx,.csv" hidden onChange={(e) => onImportPick(e.target.files?.[0] ?? null)} />
                  </>
                )}
                {/* Makes every filter above accountable — a filter that hides
                    everything now says so instead of leaving a blank grid. */}
                {mode !== 'supplier-stock' && (
                  <span className="pm-toolbar__count">
                    Showing <b>{visibleItems.length}</b> of {items.length}
                    {offerOnly && offerProductCodes && <> · <i className="bi bi-tag" /> {offerProductCodes.size} on offer</>}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Assignment Summary — appears whenever Supplier Purchasing OR
              Supplier Live Stock mode has a supplier picked, in any stage
              (mode is now independent of stage — §1). Assign Selected stays
              disabled until a supplier and at least one product are selected;
              reused as-is for Supplier Live Stock's checkbox bulk-assign. */}
          {(mode === 'supplier' || mode === 'supplier-stock') && supplier && (() => {
            const g = selectedGroup
            const alreadyAssigned = g?.product_count ?? 0
            const purchaseValue = g?.live_value ?? 0
            const min = minOrders[supplier.supplier_code] ?? 0
            const ready = min > 0 ? purchaseValue >= min : alreadyAssigned > 0
            const readyLabel = min > 0 ? (ready ? 'Ready' : 'Below Min') : alreadyAssigned > 0 ? 'No minimum' : 'New'
            // Included-for-export count scoped to what Assign Selected will
            // actually act on for THIS supplier's view — `checked` itself
            // defaults to every finalized product refresh-wide.
            const scopedIds = mode === 'supplier'
              ? new Set(visibleItems.map((i) => i.order_item_id))
              : new Set(stockCheckableByCode.values())
            const scopedCheckedCount = [...checked].filter((id) => scopedIds.has(id)).length
            return (
              <div className="pm-selbar">
                <span className="pm-selbar__item">
                  <span className="pm-selbar__k">Selected Supplier</span>
                  <b className="pm-selbar__v">{supplier.supplier_name ?? supplier.supplier_code}</b>
                </span>
                <span className="pm-selbar__item">
                  <span className="pm-selbar__k">Included for Export</span>
                  <b className="pm-selbar__v">{num(scopedCheckedCount)}</b>
                </span>
                <span className="pm-selbar__item">
                  <span className="pm-selbar__k">Already Assigned</span>
                  <b className="pm-selbar__v">{num(alreadyAssigned)}</b>
                </span>
                <span className="pm-selbar__item">
                  <span className="pm-selbar__k">Purchase Value</span>
                  <b className="pm-selbar__v">{queueLoading ? 'Calculating…' : purchaseValue > 0 ? money(purchaseValue) : '—'}</b>
                </span>
                <span className="pm-selbar__item">
                  <span className="pm-selbar__k">Minimum Order</span>
                  <b className="pm-selbar__v">{min > 0 ? money(min) : '—'}</b>
                </span>
                <span className="pm-selbar__item">
                  <span className="pm-selbar__k">Status</span>
                  <b className={`pm-optstat ${ready ? 'pm-optstat--ok' : 'pm-optstat--short'}`}>{readyLabel}</b>
                </span>
                <span className="pm-selbar__spacer" />
                <button className="pm-btn pm-btn--ghost" disabled={scopedCheckedCount === 0} onClick={() => toggleAll([...scopedIds].filter((id) => checked.has(id)), false)} title="Exclude every currently-included product from the next export">
                  Clear Selection
                </button>
                <button className="pm-btn pm-btn--ghost" onClick={assignRemaining}>
                  <i className="bi bi-list-check" /> Assign Remaining
                </button>
                <button
                  className="pm-btn pm-btn--primary"
                  disabled={scopedCheckedCount === 0}
                  onClick={() => bulkAssign(supplier.supplier_code)}
                >
                  <i className="bi bi-check2-square" /> Assign Selected ({num(scopedCheckedCount)})
                </button>
                {/* Export + Next Supplier — moved here from the old supplier
                    statistics panel (now retired in favour of the shared
                    Product Detail panel — the buyer reviews PRODUCTS here,
                    these two stay as compact workflow shortcuts only). */}
                <button
                  className="pm-btn pm-btn--success"
                  disabled={busySupplier === supplier.supplier_code || !g || g.assignment_ids.length === 0}
                  onClick={() => g && exportAndAdvance(g)}
                  title="Export this supplier's assigned products as a Purchase Order"
                >
                  <i className="bi bi-box-arrow-up" /> {busySupplier === supplier.supplier_code ? 'Exporting…' : 'Export'}
                </button>
                <button className="pm-btn pm-btn--ghost" onClick={advanceToNextSupplier} title="Move to the next supplier still needing review">
                  Next Supplier <i className="bi bi-arrow-right" />
                </button>
              </div>
            )
          })()}

          {stage === 'assign' && (
            <SupplierRankPanel
              tenantId={tenantId}
              storeId={storeId || selectedStoreId}
              eligibleItems={autoAssignEligible}
              recommendations={recommendations}
              nameOf={nameOf}
              notify={say}
            />
          )}

          {stage === 'optimize' ? (
            <SupplierOptimizationPanel
              tenantId={tenantId}
              refreshId={refreshId}
              storeId={storeId}
              actingUser={actingUser}
              nameOf={nameOf}
              notify={say}
              onApplied={() => { loadQueue(); loadWorkspace() }}
            />
          ) : stage === 'export' ? (
            <SupplierQueuePanel
              tenantId={tenantId}
              storeId={storeId || selectedStoreId}
              refreshId={refreshId}
              actingUser={actingUser}
              notify={say}
              groups={queueLines}
              loading={queueLoading || queuePending}
              error={queueError}
              mode="review"
              focusSupplierCode={null}
              onLoad={loadQueue}
              onExport={exportGroup}
              onExportSupplier={exportSupplierLive}
              onExportAll={exportAll}
              onExportSelected={exportSelectedSuppliers}
              exportingSelected={exportingSelected}
              busySupplier={busySupplier}
              exportingAll={exportingAll}
            />
          ) : mode === 'supplier-stock' ? (
            !supplier ? (
              <div className="pm-stockmode">
                <EmptyState icon="bi-truck" title="Pick a supplier" description="Choose a supplier to see their live stock intersected with the current VPL." />
              </div>
            ) : (
              // SAME 3-column split as Review All / Supplier Purchasing (grid |
              // Supplier Recommendation | Product Detail) — the old 2-column
              // "supplier stock stats" layout (SupplierStockDetail) is retired;
              // the per-row supply/discount/scheme facts it duplicated already
              // live as grid columns, and the buyer reviews the PRODUCT here,
              // not a supplier stat card.
              <div className="pm-split pm-split--3">
                <div className="pm-split__grid pm-stockgrid">
                  {supplierStock.length > 0 && (
                    <div className="pm-sxcards">
                      <span className="pm-sxcard"><span className="pm-sxcard__k">Supplier</span><b className="pm-sxcard__v">{supplier.supplier_name ?? supplier.supplier_code}</b></span>
                      <span className="pm-sxcard"><span className="pm-sxcard__k">Products</span><b className="pm-sxcard__v">{num(stockSummary.products)}</b></span>
                      <span className="pm-sxcard"><span className="pm-sxcard__k">Available</span><b className="pm-sxcard__v pm-sxcard__v--ok">{num(stockSummary.available)}</b></span>
                      <span className="pm-sxcard"><span className="pm-sxcard__k">Out of Stock</span><b className={`pm-sxcard__v${stockSummary.outOfStock > 0 ? ' pm-sxcard__v--warn' : ''}`}>{num(stockSummary.outOfStock)}</b></span>
                      <span className="pm-sxcard"><span className="pm-sxcard__k">Total Stock</span><b className="pm-sxcard__v">{num(stockSummary.totalStock)}</b></span>
                    </div>
                  )}
                  <div className="pm-stockgrid__scroll">
                    <SupplierStockTable
                      rows={supplierStock}
                      loading={supplierStockLoading}
                      error={supplierStockError}
                      onOrder={orderSupplierStock}
                      busy={manualBusy}
                      storeStockByCode={storeStockByCode}
                      statusByCode={stockStatusByCode}
                      selectedKey={stockSelectedKey}
                      onSelect={(r) => setStockSelectedKey(stockRowKey(r))}
                      draft={stockDraft}
                      onDraftChange={(key, value) => setStockDraft((d) => ({ ...d, [key]: value }))}
                      checkableByCode={stockCheckableByCode}
                      checked={checked}
                      onToggle={toggle}
                      onToggleAll={toggleAll}
                      itemByCode={stockItemByCode}
                      recommendations={recommendations}
                      selectedSupplier={selectedSupplier}
                      onSelectSupplier={onSelectSupplier}
                      onCommitSupplier={onCommitSupplier}
                      onSupplierFocusChange={setSupplierZoneActive}
                    />
                  </div>
                </div>
                <div className="pm-split__suppliers">
                  <SupplierRecPanel
                    item={matchedStockItem}
                    suppliers={matchedStockItem ? recommendations[matchedStockItem.order_item_id] ?? [] : []}
                    selectedCode={matchedStockItem ? selectedSupplier[matchedStockItem.order_item_id] ?? null : null}
                    assignedCode={
                      matchedStockItem && (matchedStockItem.assigned_qty ?? 0) > 0
                        ? selectedSupplier[matchedStockItem.order_item_id] ??
                          assignedByItem.get(matchedStockItem.order_item_id)?.supplierCode ??
                          matchedStockItem.supplier_code ??
                          null
                        : null
                    }
                    assignedName={matchedStockItem ? assignedByItem.get(matchedStockItem.order_item_id)?.supplierName ?? null : null}
                    liveCodes={liveCodes}
                    active={supplierZoneActive}
                    onSelect={(code) => matchedStockItem && onSelectSupplier(matchedStockItem.order_item_id, code)}
                    onCommit={(it, code) => onCommitSupplier(it, code)}
                    onOpenInfo={openInfo}
                  />
                </div>
                <div className="pm-split__detail">
                  <DetailColumn
                    tenantId={tenantId}
                    item={matchedStockItem}
                    onOpenInfo={openInfo}
                    onOpenBill={setBill}
                    onViewAll={(kind) => matchedStockItem && setViewAll({ kind, item: matchedStockItem })}
                    assignedSupplier={matchedStockItem ? assignedByItem.get(matchedStockItem.order_item_id) ?? null : null}
                    onChangeSupplier={reviewChangeSupplier}
                    offerInfo={
                      selectedStockRow && formatOffer(selectedStockRow)
                        ? { supplierName: supplier?.supplier_name ?? supplier?.supplier_code ?? null, label: formatOffer(selectedStockRow)!, discount: selectedStockRow.discount }
                        : null
                    }
                    onRemoveAssignment={
                      matchedStockItem
                        ? () => {
                            const a = assignedByItem.get(matchedStockItem.order_item_id)
                            if (a) reviewRemove(a.assignmentId, matchedStockItem.order_item_id)
                          }
                        : undefined
                    }
                  />
                </div>
              </div>
            )
          ) : error ? (
            <ErrorState description={error} onRetry={loadWorkspace} />
          ) : (
            <div className="pm-split pm-split--3">
              <div className="pm-split__grid">
                {mode === 'supplier' && !supplier ? (
                  <EmptyState icon="bi-truck" title="Select a supplier to review products." />
                ) : mode === 'supplier' && supplierProductsLoading ? (
                  <EmptyState icon="bi-hourglass-split" title="Loading purchase history…" />
                ) : visibleItems.length === 0 && !loading ? (
                  <EmptyState
                    icon="bi-inbox"
                    title="No products"
                    description={
                      mode === 'supplier'
                        ? `${supplier?.supplier_name ?? supplier?.supplier_code} has no purchase history in this refresh.`
                        : 'No working items match the current filters.'
                    }
                  />
                ) : (
                  <ProductGrid
                    items={visibleItems}
                    selectedId={selectedId}
                    selectable={mode === 'supplier'}
                    checked={checked}
                    lockedIds={lockedIds}
                    edits={edits}
                    dirtyIds={dirtyIds}
                    recommendations={recommendations}
                    selectedSupplier={selectedSupplier}
                    onSelectSupplier={onSelectSupplier}
                    onCommitSupplier={onCommitSupplier}
                    onSupplierFocusChange={setSupplierZoneActive}
                    onEditChange={onEditChange}
                    onSaveRow={saveRow}
                    onSelect={(it) => setSelectedId(it.order_item_id)}
                    onToggle={toggle}
                    onToggleAll={toggleAll}
                    onSkip={skip}
                    onRestore={restore}
                  />
                )}
              </div>
              <div className="pm-split__suppliers">
                {/* onCommit always assigns to the supplier whose CARD was acted on.
                    Supplier Purchasing used to force the toolbar's supplier here,
                    so a product could never be moved to a different supplier from
                    this panel. */}
                <SupplierRecPanel
                  item={selectedItem}
                  suppliers={selectedId ? recommendations[selectedId] ?? [] : []}
                  selectedCode={selectedId ? selectedSupplier[selectedId] ?? null : null}
                  assignedCode={
                    selectedItem && (selectedItem.assigned_qty ?? 0) > 0
                      ? selectedSupplier[selectedItem.order_item_id] ??
                        assignedByItem.get(selectedItem.order_item_id)?.supplierCode ??
                        selectedItem.supplier_code ??
                        null
                      : null
                  }
                  assignedName={selectedItem ? assignedByItem.get(selectedItem.order_item_id)?.supplierName ?? null : null}
                  liveCodes={liveCodes}
                  active={supplierZoneActive}
                  onSelect={(code) => selectedId && onSelectSupplier(selectedId, code)}
                  onCommit={(it, code) => onCommitSupplier(it, code)}
                  onOpenInfo={openInfo}
                />
              </div>
              <div className="pm-split__detail">
                {/* One shared Product Detail panel for every mode (§ Supplier
                    Purchasing / Supplier Live Stock parity) — the buyer is
                    reviewing PRODUCTS here, not supplier statistics. Change /
                    Remove assignment stay reachable per-product via the header. */}
                <DetailColumn
                  tenantId={tenantId}
                  item={selectedItem}
                  onOpenInfo={openInfo}
                  onOpenBill={setBill}
                  onViewAll={(kind) => selectedItem && setViewAll({ kind, item: selectedItem })}
                  assignedSupplier={selectedItem ? assignedByItem.get(selectedItem.order_item_id) ?? null : null}
                  onChangeSupplier={reviewChangeSupplier}
                  onRemoveAssignment={
                    selectedItem
                      ? () => {
                          const a = assignedByItem.get(selectedItem.order_item_id)
                          if (a) reviewRemove(a.assignmentId, selectedItem.order_item_id)
                        }
                      : undefined
                  }
                />
              </div>
            </div>
          )}

          {/* Totals + stage actions share one footer row: separately they cost two
              near-empty rows of height the detail panel needed. */}
          <div className="pm-footbar">
          {(stage === 'review' || stage === 'assign') && mode !== 'supplier-stock' && (
            <div className="pm-totals">
              {mode === 'supplier' ? (
                <span className="pm-stat"><span className="pm-stat__k">Products</span><b className="pm-stat__v">Showing {num(visibleItems.length)} of {num(total || items.length)}</b></span>
              ) : (
                <span className="pm-stat"><span className="pm-stat__k">Total Products</span><b className="pm-stat__v">{num(total || items.length)}</b></span>
              )}
              <span className="pm-stat"><span className="pm-stat__k">Current Row</span><b className="pm-stat__v">{currentRowNo > 0 ? `${currentRowNo} / ${num(visibleItems.length)}` : '—'}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Pending Review</span><b className={`pm-stat__v${pendingReview > 0 ? ' pm-stat__v--warn' : ''}`}>{num(pendingReview)}</b></span>
              <span className="pm-stat"><span className="pm-stat__k">Assigned</span><b className="pm-stat__v">{num(assignedCount)}</b></span>
              <span className="pm-stat pm-stat--value">
                <span className="pm-stat__k">Purchase Value</span>
                <b className="pm-totals__v">{money(totalPurchaseValue)}</b>
              </span>
            </div>
          )}

          {/* Stage action bar — the clear per-stage next steps. */}
          <div className="pm-stagebar">
            {stage === 'review' && (
              <>
                <span className="pm-stagebar__hint">
                  {pendingReview > 0
                    ? `${num(pendingReview)} product${pendingReview === 1 ? '' : 's'} still pending review`
                    : 'All products reviewed'}
                </span>
                <span className="pm-stagebar__spacer" />
                <button className="pm-btn pm-btn--primary" onClick={() => goStage('assign')}>
                  Finalize Review <i className="bi bi-arrow-right" />
                </button>
              </>
            )}
            {stage === 'assign' && (
              <>
                <button className="pm-btn pm-btn--primary" onClick={prepareAutoAssign} disabled={autoBusy}>
                  <i className="bi bi-magic" /> {autoBusy ? 'Preparing…' : 'Auto Assign Suppliers'}
                </button>
                <select
                  className="sx-select"
                  aria-label="Auto Assign mode"
                  value={assignMode}
                  onChange={(e) => setAssignMode(e.target.value as 'cost' | 'rank')}
                  title="Cost: today's weighted score (mapping/recency/frequency/PTR). Rank: your manual Supplier Rank order."
                >
                  <option value="cost">Auto Assign: by Cost</option>
                  <option value="rank">Auto Assign: by Rank</option>
                </select>
                <label className="pm-chk" title="Only auto-assign Pharma-classified products">
                  <input type="checkbox" checked={pharmaOnly} onChange={(e) => setPharmaOnly(e.target.checked)} /> Pharma Only
                </label>
                <span className="pm-stagebar__hint">{num(assignedCount)} assigned</span>
                <span className="pm-stagebar__spacer" />
                <button className="pm-btn pm-btn--ghost" onClick={() => goStage('optimize')}>
                  Optimize <i className="bi bi-arrow-right" />
                </button>
                <button
                  className="pm-btn pm-btn--ghost"
                  disabled={!hasAssignments}
                  onClick={() => goStage('export')}
                  title="Optional — every supplier can already be exported from its own card above"
                >
                  Export Monitor <i className="bi bi-arrow-right" />
                </button>
              </>
            )}
            {stage === 'optimize' && (
              <>
                <button className="pm-btn pm-btn--ghost" onClick={() => goStage('assign')}>
                  <i className="bi bi-arrow-left" /> Back to Assign
                </button>
                <span className="pm-stagebar__spacer" />
                <button className="pm-btn pm-btn--primary" disabled={!hasAssignments} onClick={() => goStage('export')}>
                  View Export Monitor <i className="bi bi-arrow-right" />
                </button>
              </>
            )}
            {stage === 'export' && (
              <>
                <button className="pm-btn pm-btn--ghost" onClick={() => goStage('optimize')}>
                  <i className="bi bi-arrow-left" /> Back to Optimize
                </button>
                <span className="pm-stagebar__hint">
                  Monitoring dashboard for the whole refresh — export a single supplier from its card, use Export All, or export directly from each supplier's Assign panel.
                </span>
              </>
            )}
          </div>
          </div>
        </>
      )}

      {info && (
        <ProductInfoDialog
          tenantId={tenantId}
          item={info.item}
          initialTab={info.tab}
          onClose={() => setInfo(null)}
        />
      )}
      {bill && (
        <BillDrawer tenantId={tenantId} target={bill} onClose={() => setBill(null)} />
      )}
      {viewAll && (
        <HistoryAllDialog
          kind={viewAll.kind}
          tenantId={tenantId}
          storeId={viewAll.item.store_id ?? storeId}
          productCode={viewAll.item.product_code ?? ''}
          productName={viewAll.item.product_name ?? null}
          onOpenBill={(t) => { setViewAll(null); setBill(t) }}
          onClose={() => setViewAll(null)}
        />
      )}
      {manualOpen && (
        <ManualProductModal tenantId={tenantId} storeId={storeId} busy={manualBusy} onAdd={addManual} onClose={() => setManualOpen(false)} />
      )}
      {importFile && supplier && storeId && (
        <SupplierStockImportModal
          tenantId={tenantId}
          storeId={storeId}
          supplierCode={supplier.supplier_code}
          supplierName={supplier.supplier_name ?? supplier.supplier_code}
          file={importFile}
          actingUser={actingUser}
          onClose={() => setImportFile(null)}
          onImported={(n) => {
            setImportFile(null)
            setStockReloadKey((k) => k + 1)
            say('success', `Imported ${n} stock line${n === 1 ? '' : 's'} for ${supplier.supplier_code}`)
          }}
        />
      )}
      {autoAssignPreview && (
        <AutoAssignPreviewModal
          groups={autoAssignPreview.groups}
          droppedBelowMin={autoAssignPreview.droppedBelowMin}
          itemById={itemById}
          recommendations={recommendations}
          nameOf={nameOf}
          mode={assignMode}
          busy={autoBusy}
          onConfirm={commitAutoAssign}
          onClose={() => setAutoAssignPreview(null)}
        />
      )}

    </div>
  )
}

/* ---- Pending view (kept from the operational flow) ---------------------- */

function PendingView({
  pending, draft, setDraft, onKey, onFinalize, onCarry,
  selected, setSelected, busy, onBulk, onCarrySupplier, onReport,
}: {
  pending: PendingItem[]
  draft: Record<string, string>
  setDraft: React.Dispatch<React.SetStateAction<Record<string, string>>>
  onKey: (e: ReactKeyboardEvent<HTMLInputElement>, item: PendingItem, index: number) => void
  onFinalize: () => void
  onCarry: (item: PendingItem) => void
  selected: Set<string>
  setSelected: React.Dispatch<React.SetStateAction<Set<string>>>
  busy: boolean
  onBulk: (action: 'carry' | 'skip' | 'finalize', ids: string[]) => void
  onCarrySupplier: (supplierCode: string) => void
  onReport: () => void
}) {
  const allIds = pending.map((p) => p.order_item_id)
  const allChecked = allIds.length > 0 && allIds.every((id) => selected.has(id))
  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const toggleAll = () => setSelected(allChecked ? new Set() : new Set(allIds))

  // Group rows by supplier so the buyer can carry a whole supplier at once.
  const groups = new Map<string, PendingItem[]>()
  for (const p of pending) {
    const key = p.supplier_code ?? ''
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(p)
  }
  const selIds = [...selected]

  let rowIndex = -1
  return (
    <div className="pm-pending">
      <div className="pm-pending__bar">
        <button className="pm-btn pm-btn--ghost" disabled={busy || selIds.length === 0} onClick={() => onBulk('carry', selIds)}>Carry selected</button>
        <button className="pm-btn pm-btn--ghost" disabled={busy || selIds.length === 0} onClick={() => onBulk('skip', selIds)}>Skip selected</button>
        <button className="pm-btn pm-btn--ghost" disabled={busy || selIds.length === 0} onClick={() => onBulk('finalize', selIds)}>Finalize selected</button>
        <span className="text-muted small">{selIds.length} selected</span>
        <span className="pm-pending__spacer" style={{ flex: 1 }} />
        <button className="pm-btn pm-btn--ghost" onClick={onReport}><i className="bi bi-file-earmark-spreadsheet me-1" />Report</button>
        <button className="pm-btn pm-btn--ghost" disabled={busy} onClick={onFinalize}>Finalize all</button>
      </div>
      {pending.length === 0 ? (
        <EmptyState icon="bi-check2-circle" title="No pending" description="Nothing remaining to review for this refresh." />
      ) : (
        <table className="pm-grid">
          <thead>
            <tr>
              <th className="pm-grid__chk"><input type="checkbox" checked={allChecked} onChange={toggleAll} aria-label="Select all" /></th>
              <th>Product</th><th className="sx-num">Final</th><th className="sx-num">Received</th>
              <th className="sx-num pm-grid__final">Pending</th><th>Status</th><th className="pm-grid__act">Carry</th>
            </tr>
          </thead>
          <tbody>
            {[...groups.entries()].map(([supplierCode, rows]) => (
              <Fragment key={supplierCode || '—'}>
                <tr className="pm-grid__group">
                  <td colSpan={7}>
                    <span className="pm-grid__group-name"><i className="bi bi-truck me-1" />{supplierCode || 'Unassigned supplier'}</span>
                    <span className="text-muted small ms-2">{rows.length} item{rows.length === 1 ? '' : 's'}</span>
                    {supplierCode && (
                      <button className="pm-btn pm-btn--ghost pm-btn--sm ms-2" disabled={busy} onClick={() => onCarrySupplier(supplierCode)}>
                        Carry all →
                      </button>
                    )}
                  </td>
                </tr>
                {rows.map((p) => {
                  rowIndex += 1
                  const i = rowIndex
                  return (
                    <tr key={p.order_item_id}>
                      <td className="pm-grid__chk"><input type="checkbox" checked={selected.has(p.order_item_id)} onChange={() => toggle(p.order_item_id)} aria-label="Select item" /></td>
                      <td>
                        <div className="pm-prod__name">{p.product_name ?? '—'}{p.is_manual && <span className="pm-tag pm-tag--manual ms-1">manual</span>}</div>
                        <div className="pm-prod__meta">{p.product_code}</div>
                      </td>
                      <td className="sx-num">{p.final_qty ?? 0}</td>
                      <td className="sx-num">{p.received_qty ?? 0}</td>
                      <td className="sx-num pm-grid__final">
                        <input
                          id={`pending-input-${i}`}
                          className="pm-qty"
                          value={draft[p.order_item_id] ?? ''}
                          onChange={(e) => setDraft((d) => ({ ...d, [p.order_item_id]: e.target.value }))}
                          onKeyDown={(e) => onKey(e, p, i)}
                        />
                      </td>
                      <td><span className="pm-badge pm-badge--muted">{p.pending_status ?? p.item_status}</span></td>
                      <td className="pm-grid__act">
                        <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => onCarry(p)}>Carry →</button>
                      </td>
                    </tr>
                  )
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
