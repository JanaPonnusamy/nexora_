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
import { SupplierReviewPanel } from '../../components/procurement/SupplierReviewPanel'
import { ManualProductModal } from '../../components/procurement/ManualProductModal'
import { SupplierPicker } from '../../components/procurement/SupplierPicker'
import { SupplierStockTable, stockRowKey } from '../../components/procurement/SupplierStockTable'
import { SupplierStockDetail } from '../../components/procurement/SupplierStockDetail'
import { SupplierStockImportModal } from '../../components/procurement/SupplierStockImportModal'
import { autoAssignSupplier, effectiveCost, sortSuppliersByCost } from '../../components/procurement/purchaseValue'
import { money, num } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'

type View = 'purchase' | 'pending' | 'grn'
// Operational stages of the Purchase view (normalizes the previously-mixed screen).
type Stage = 'review' | 'assign' | 'optimize' | 'export'
type Banner = { kind: 'success' | 'danger'; text: string } | null

const STAGES: { key: Stage; label: string; icon: string }[] = [
  { key: 'review', label: 'Review Products', icon: 'bi-clipboard-check' },
  { key: 'assign', label: 'Assign Suppliers', icon: 'bi-diagram-3' },
  { key: 'optimize', label: 'Optimize', icon: 'bi-sliders' },
  { key: 'export', label: 'Export', icon: 'bi-box-arrow-up' },
]

const MOVEMENT = ['', 'FAST', 'MEDIUM', 'SLOW', 'NONMOVING']

// Run async `worker` over `list` with at most `limit` requests in flight at once,
// so a large fan-out (one request per assigned item) can never open hundreds of
// simultaneous connections and saturate the backend's request threadpool / SQL
// connections. `alive()` lets a superseded run stop issuing further requests the
// moment a newer run starts, instead of racing hundreds of stale calls to done.
async function runPool<T>(
  list: T[],
  limit: number,
  alive: () => boolean,
  worker: (item: T) => Promise<void>,
): Promise<void> {
  let cursor = 0
  const runners = Array.from({ length: Math.min(limit, list.length) }, async () => {
    while (cursor < list.length) {
      if (!alive()) return
      const item = list[cursor++]
      await worker(item)
    }
  })
  await Promise.all(runners)
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

  // Filters
  const [search, setSearch] = useState('')
  const [movement, setMovement] = useState('')
  // Planning-State filter (integrates with the grid's Planning State column).
  const [showPending, setShowPending] = useState(true)
  const [showFinalized, setShowFinalized] = useState(true)
  const [showAssigned, setShowAssigned] = useState(true)
  const [showSkipped, setShowSkipped] = useState(true)
  const [showManual, setShowManual] = useState(true)
  // Product Type filter (Product Master ProductType): '' all, '1' Pharma,
  // '0' Non-Pharma, '2' Others. Client-side only — never recalculates the VPL.
  const [productType, setProductType] = useState('')

  const [selectedId, setSelectedId] = useState<string | null>(null)
  // True while the keyboard "supplier zone" holds focus (rings the side panel).
  const [supplierZoneActive, setSupplierZoneActive] = useState(false)
  const [checked, setChecked] = useState<Set<string>>(new Set())

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
  const [busySupplier, setBusySupplier] = useState<string | null>(null)
  const [exportingAll, setExportingAll] = useState(false)

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
  // Adding a manual product returns 409 (not a bug — the backend correctly
  // rejects a duplicate) when that product is already a working item in this
  // refresh. Surface it as guidance instead of the raw backend detail text, and
  // never auto-retry: the operator decides the next step (search the grid).
  const failManualAdd = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.status === 409) {
        say('danger', 'Already in this refresh — search for it in the product grid instead of adding it again.')
      } else {
        fail(e)
      }
    },
    [fail, say],
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

  useEffect(() => {
    if (!tenantId || !selectedStoreId) { setRefreshes([]); setRefreshId(''); return }
    procurementService.refreshes(tenantId, selectedStoreId)
      .then((rows) => {
        setRefreshes(rows)
        // Keep a URL-provided / already-selected refresh; else clear on change.
        setRefreshId((c) => (c && rows.some((r) => r.refresh_id === c) ? c : ''))
      })
      .catch(fail)
  }, [tenantId, selectedStoreId, fail])

  // A new refresh always starts at the first stage (Review Products) and clears
  // any picked supplier — the stages are the normalized operational flow.
  useEffect(() => {
    setStage('review')
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
          search,
          movement_class: movement || undefined,
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
      })
      .catch((e) => {
        if (e instanceof DOMException && e.name === 'AbortError') return // superseded, not an error
        setError(e instanceof Error ? e.message : 'Failed to load')
      })
      .finally(() => {
        if (workspaceAbortRef.current === controller) setLoading(false)
      })
  }, [tenantId, refreshId, search, movement])

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
  // Match the selected supplier-stock row to its workspace item by ProductCode
  // (both share the store's ProductCode) — feeds the reused DetailColumn and the
  // inventory/decision fields with no extra fetch.
  const matchedStockItem = useMemo(() => {
    const code = selectedStockRow?.product_code
    return code ? items.find((i) => i.product_code === code) ?? null : null
  }, [selectedStockRow, items])
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
  const canWork = Boolean(tenantId && refreshId)

  const itemById = useMemo(() => {
    const m = new Map<string, WorkspaceItem>()
    items.forEach((i) => m.set(i.order_item_id, i))
    return m
  }, [items])

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
      const purchaseValue = g?.est_value ?? 0
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
      const raw = edits[item.order_item_id]
      const v = raw != null ? Number(raw) : item.final_qty ?? 0
      if (Number.isNaN(v) || v < 0) return
      // Exactly one request per real change: with no pending edit and a value that
      // already matches the server there is nothing to save. This is the main
      // source of duplicate /final-qty calls — pressing Enter/Down to advance
      // through already-finalised rows previously re-saved every row it passed.
      if (raw == null && v === (item.final_qty ?? 0)) return
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
      try {
        await procurementService.setFinalQty(tenantId, item.order_item_id, v, null, actingUser || null)
      } catch (e) {
        fail(e)
        if (!isOffline(e)) loadWorkspace()
      } finally {
        savingIds.current.delete(item.order_item_id)
      }
    },
    [edits, tenantId, actingUser, fail, loadWorkspace],
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
  // for. Drives the grid filter (item 7 — "based on supplier purchase history").
  useEffect(() => {
    if (mode !== 'supplier' || !supplier || !canWork) {
      setSupplierProductIds(null)
      return
    }
    let live = true
    procurementService
      .supplierProducts(tenantId, refreshId, supplier.supplier_code)
      .then((ids) => live && setSupplierProductIds(new Set(ids)))
      .catch(() => live && setSupplierProductIds(new Set()))
    return () => { live = false }
  }, [mode, supplier, tenantId, refreshId, canWork])

  // Client-side view toggles the server can't express. In Supplier Purchasing
  // mode, additionally show only the selected supplier's purchased products.
  const visibleItems = useMemo(() => {
    const narrowToSupplier = mode === 'supplier' && supplier && supplierProductIds !== null
    const planningState = (i: WorkspaceItem) => {
      if (i.item_status === 'skipped') return 'skipped'
      if ((i.assigned_qty ?? 0) > 0) return 'assigned'
      if (['review', 'partial'].includes(i.item_status) && (i.final_qty ?? 0) > 0) return 'finalized'
      return 'pending'
    }
    return items.filter((i) => {
      const st = planningState(i)
      if (st === 'pending' && !showPending) return false
      if (st === 'finalized' && !showFinalized) return false
      if (st === 'assigned' && !showAssigned) return false
      if (st === 'skipped' && !showSkipped) return false
      if (i.is_manual && !showManual) return false
      if (productType && String(i.product_type ?? '') !== productType) return false
      if (narrowToSupplier && !supplierProductIds!.has(i.order_item_id)) return false
      return true
    })
  }, [items, showPending, showFinalized, showAssigned, showSkipped, showManual, productType, mode, supplier, supplierProductIds])

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

  // In Supplier Purchasing mode, collapse the row icons to just the active supplier.
  const collapseToSupplier = mode === 'supplier' ? supplier?.supplier_code ?? null : null

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
    try {
      await procurementService.skip(tenantId, item.order_item_id, reason, actingUser || null)
    } catch (e) {
      fail(e)
      if (!isOffline(e)) loadWorkspace()
    }
  }
  const restore = async (item: WorkspaceItem) => {
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
    const remaining = item.remaining_qty ?? 0
    if (remaining <= 0) return say('danger', 'No remaining quantity to assign')
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
    } catch (e) {
      fail(e)
      if (!isOffline(e)) loadWorkspace()
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

  // Double click (or explicit Assign) = commit the assignment to the queue.
  const onCommitSupplier = useCallback(
    (item: WorkspaceItem, supplierCode: string) => {
      setSelectedSupplier((prev) => ({ ...prev, [item.order_item_id]: supplierCode }))
      assign(item, supplierCode)
    },
    // assign is stable enough for this flow; declared below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tenantId, actingUser],
  )

  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const toggleAll = (ids: string[], on: boolean) =>
    setChecked((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => (on ? next.add(id) : next.delete(id)))
      return next
    })

  // Shared assignment path: assign a specific set of order items to a supplier
  // and refresh assigned count / row status (loadWorkspace) + supplier totals
  // (loadQueue). The backend skips any product already actively assigned, so
  // manually-assigned products are never overwritten.
  const assignIds = async (supplierCode: string, ids: string[]) => {
    const code = supplierCode.trim()
    if (!code) return say('danger', 'Pick a supplier')
    if (ids.length === 0) return say('danger', 'Nothing to assign')
    try {
      const res = await procurementService.bulkAssign(tenantId, code, ids, actingUser || null)
      say('success', `Assigned ${res.assigned}${res.skipped ? `, skipped ${res.skipped} (already assigned)` : ''}`)
      // Remember the chosen supplier per row so the Recommendation panel shows it
      // green immediately.
      setSelectedSupplier((prev) => {
        const next = { ...prev }
        ids.forEach((id) => { next[id] = code })
        return next
      })
      setChecked(new Set())
      loadWorkspace()   // assigned count + product row status
      await loadQueue() // supplier totals
    } catch (e) {
      fail(e)
    }
  }

  // Assign Selected — the checked products.
  const bulkAssign = (supplierCode: string) => assignIds(supplierCode, [...checked])

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
    // Each call fans out one request per assigned item (Promise.all below), so
    // two overlapping runs (rapid supplier switches, one action chaining into
    // another) can resolve out of order. Only the LATEST run is allowed to
    // commit its result — an older, slower run's response is discarded instead
    // of racing it into state.
    const runId = ++queueRunRef.current
    setQueueLoading(true)
    try {
      const assignedItems = items.filter((i) => (i.assigned_qty ?? 0) > 0)
      const map = new Map<string, SupplierQueueGroup>()
      const locked = new Set<string>()
      // One /assignments request per assigned item, but capped at a few in flight
      // at once (and abandoned the instant a newer run supersedes this one). The
      // uncapped Promise.all here used to fire hundreds of simultaneous requests
      // on a real refresh, saturating the backend's request threadpool + SQL
      // connections — the root cause of the 502 / connection-reset cascade.
      await runPool(assignedItems, 6, () => runId === queueRunRef.current, async (it) => {
          const list = await procurementService.assignments(tenantId, it.order_item_id)
          const ptr = it.last_purchase_rate ?? it.ptr_cost ?? 0
          for (const a of list) {
            const g =
              map.get(a.supplier_code) ??
              {
                supplier_code: a.supplier_code, supplier_name: null,
                product_count: 0, total_qty: 0, est_value: 0, offer_count: 0,
                exported_count: 0, status: 'ready', exported_at: null,
                exported_by: null, export_batch_number: null,
                assignment_ids: [], lines: [],
              } as SupplierQueueGroup
            const qty = a.assigned_qty ?? 0
            const exported = a.assignment_status === 'exported'
            g.lines.push({
              assignment_id: a.assignment_id,
              order_item_id: it.order_item_id,
              product_name: it.product_name,
              product_code: it.product_code,
              ptr,
              mrp: it.mrp ?? null,
              offer: it.offer ?? null,
              final_qty: qty,
              exported,
            })
            g.product_count += 1
            g.total_qty += qty
            g.est_value += qty * ptr
            if (it.offer) g.offer_count += 1
            if (exported) {
              locked.add(it.order_item_id)
              g.exported_count += 1
              g.exported_at = a.exported_at ?? g.exported_at
              g.exported_by = a.export_uid ?? g.exported_by
              g.export_batch_number = a.export_batch_number ?? g.export_batch_number
            } else {
              g.assignment_ids.push(a.assignment_id)
            }
            map.set(a.supplier_code, g)
          }
      })
      if (runId !== queueRunRef.current) return // superseded by a newer call
      const groups = [...map.values()]
      groups.forEach((g) => {
        g.status = g.exported_count === 0 ? 'ready' : g.exported_count >= g.product_count ? 'exported' : 'partial'
      })
      groups.sort((a, b) => b.est_value - a.est_value)
      setQueueLines(groups)
      setLockedIds(locked)
    } catch (e) {
      if (runId === queueRunRef.current) fail(e)
    } finally {
      if (runId === queueRunRef.current) setQueueLoading(false)
    }
  }, [canWork, items, tenantId, fail])

  const exportGroup = async (group: SupplierQueueGroup, assignmentIds: string[]) => {
    if (assignmentIds.length === 0) return say('danger', 'Nothing to export for this supplier')
    setBusySupplier(group.supplier_code)
    try {
      const res = await procurementService.exportRefresh(tenantId, refreshId, actingUser, assignmentIds)
      say('success', `Exported ${res.exported_count} lines (${group.supplier_code})`)
      await loadQueue()
      loadWorkspace()
    } catch (e) {
      fail(e)
    } finally {
      setBusySupplier(null)
    }
  }

  const exportAll = async () => {
    setExportingAll(true)
    try {
      const res = await procurementService.exportRefresh(tenantId, refreshId, actingUser)
      say('success', `Exported ${res.exported_count} lines as ${res.export_batch_number}`)
      await loadQueue()
      loadWorkspace()
    } catch (e) {
      fail(e)
    } finally {
      setExportingAll(false)
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

  // Move to a stage; refresh the supplier totals when leaving Review so the
  // review/optimize/export panels always reflect the latest assignments.
  const goStage = (s: Stage) => {
    if (s === 'export' && !hasAssignments) return say('danger', 'Assign suppliers before exporting')
    if (s === 'review') setMode('review')
    if (s !== 'review') loadQueue()
    setStage(s)
  }

  // Auto Assign: give every finalized, still-unassigned product to exactly ONE
  // supplier chosen by the documented priority (Exact Product Mapping → Last
  // Purchase Supplier → Preferred Supplier — see autoAssignSupplier). Reuses the
  // bulk assignment API — one call per supplier, no new endpoint, no mock data.
  const autoAssign = async () => {
    const groups = new Map<string, string[]>()
    items.forEach((it) => {
      if (it.item_status === 'skipped') return
      if ((it.final_qty ?? 0) <= 0) return
      if ((it.remaining_qty ?? 0) <= 0) return
      const top = autoAssignSupplier(recommendations[it.order_item_id])
      if (!top) return
      if (!groups.has(top)) groups.set(top, [])
      groups.get(top)!.push(it.order_item_id)
    })
    if (groups.size === 0) return say('danger', 'Nothing to auto-assign — finalize quantities first')
    setAutoBusy(true)
    try {
      let assigned = 0
      for (const [code, ids] of groups) {
        const res = await procurementService.bulkAssign(tenantId, code, ids, actingUser || null)
        assigned += res.assigned
      }
      say('success', `Auto-assigned ${assigned} product${assigned === 1 ? '' : 's'} to their best-price supplier`)
      loadWorkspace()
      await loadQueue()
    } catch (e) {
      fail(e)
    } finally {
      setAutoBusy(false)
    }
  }

  const reviewChangeSupplier = async (assignmentId: string, newSupplier: SupplierRow) => {
    try {
      await procurementService.changeSupplier(tenantId, assignmentId, newSupplier.supplier_code, actingUser || null)
      say('success', `Moved to ${newSupplier.supplier_name ?? newSupplier.supplier_code}`)
      await loadQueue()
      loadWorkspace()
    } catch (e) {
      fail(e)
    }
  }
  const reviewRemove = async (assignmentId: string) => {
    try {
      await procurementService.removeAssignment(tenantId, assignmentId, actingUser || null)
      say('success', 'Removed from supplier')
      await loadQueue()
      loadWorkspace()
    } catch (e) {
      fail(e)
    }
  }

  // Refresh the supplier totals whenever a supplier is picked in the Assign stage
  // so the right-hand Supplier Review panel reflects the latest assignments.
  useEffect(() => {
    if (stage === 'assign' && supplier) loadQueue()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supplier, stage])

  /* ---- Manual product ---------------------------------------------------- */

  const addManual = async (product: ManualProduct, qty: number) => {
    setManualBusy(true)
    try {
      await procurementService.addManualItem(
        tenantId, refreshId, product.product_code, product.product_name ?? product.product_code, qty, actingUser || null,
      )
      say('success', `Added ${product.product_code}`)
      setManualOpen(false)
      loadWorkspace()
    } catch (e) {
      failManualAdd(e)
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
    if (!row.product_code) return say('danger', 'Row has no mapped product code')
    setManualBusy(true)
    try {
      await procurementService.addManualItem(
        tenantId, refreshId, row.product_code, row.supplier_product_name ?? row.product_code, qty, actingUser || null,
      )
      say('success', `Added ${qty} × ${row.product_code} — assign ${supplier?.supplier_code ?? 'a supplier'} in Review mode`)
      loadWorkspace()
    } catch (e) {
      failManualAdd(e)
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
    try {
      const r = await procurementService.finalizePending(tenantId, refreshId, actingUser || null)
      say('success', `Finalized ${r.finalized} pending items`)
      loadPending()
    } catch (e) {
      fail(e)
    }
  }
  const carryForwardPending = async (item: PendingItem) => {
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
          <select className="sx-select" aria-label="Refresh" value={refreshId} onChange={(e) => setRefreshId(e.target.value)}>
            <option value="">Select refresh…</option>
            {refreshes.map((r) => <option key={r.refresh_id} value={r.refresh_id}>{r.snapshot_name} · {r.snapshot_status}</option>)}
          </select>
        </div>
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
          {/* Operational stage stepper — normalizes the previously-mixed screen
              into Review → Assign → Optimize → Export. */}
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

          {/* Contextual toolbar — only for the grid stages (Review / Assign). */}
          {(stage === 'review' || stage === 'assign') && (
            <div className="pm-toolbar">
              {stage === 'assign' && (
                <div className="pm-toolbar__modes">
                  {MODE_OPTIONS.map((m) => (
                    <button key={m.value} className={`pm-mode${mode === m.value ? ' pm-mode--on' : ''}`} onClick={() => setMode(m.value)}>
                      {m.label}
                    </button>
                  ))}
                </div>
              )}
              {stage === 'review' ? (
                <>
                  <span className="sx-search">
                    <i className="bi bi-search" aria-hidden="true" />
                    <input ref={searchRef} type="search" value={search} placeholder="Search product…" aria-label="Search product" onChange={(e) => setSearch(e.target.value)} />
                  </span>
                  <select className="sx-select" aria-label="Movement filter" value={movement} onChange={(e) => setMovement(e.target.value)}>
                    {MOVEMENT.map((m) => <option key={m} value={m}>{m || 'Movement: all'}</option>)}
                  </select>
                  <select className="sx-select" aria-label="Product Type filter" value={productType} onChange={(e) => setProductType(e.target.value)}>
                    <option value="">Product Type: all</option>
                    <option value="1">Pharma</option>
                    <option value="0">Non-Pharma</option>
                    <option value="2">Others</option>
                  </select>
                  <label className="pm-chk"><input type="checkbox" checked={showPending} onChange={(e) => setShowPending(e.target.checked)} /> Pending Review</label>
                  <label className="pm-chk"><input type="checkbox" checked={showFinalized} onChange={(e) => setShowFinalized(e.target.checked)} /> Finalized</label>
                  <label className="pm-chk"><input type="checkbox" checked={showAssigned} onChange={(e) => setShowAssigned(e.target.checked)} /> Assigned</label>
                  <label className="pm-chk"><input type="checkbox" checked={showSkipped} onChange={(e) => setShowSkipped(e.target.checked)} /> Skipped</label>
                  <label className="pm-chk"><input type="checkbox" checked={showManual} onChange={(e) => setShowManual(e.target.checked)} /> Manual</label>
                  <div className="pm-toolbar__right">
                    <button className="pm-btn pm-btn--ghost" onClick={() => setManualOpen(true)}><i className="bi bi-plus-lg" /> Manual</button>
                    <button className="pm-btn pm-btn--ghost" onClick={loadWorkspace} title="Refresh"><i className="bi bi-arrow-repeat" /></button>
                  </div>
                </>
              ) : (
                <>
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
                  {mode === 'supplier-stock' && (
                    <>
                      <span className="sx-search">
                        <i className="bi bi-search" aria-hidden="true" />
                        <input type="search" value={stockSearch} placeholder="Search live stock…" aria-label="Search live stock" onChange={(e) => setStockSearch(e.target.value)} />
                      </span>
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
                  <div className="pm-toolbar__right">
                    <button className="pm-btn pm-btn--ghost" onClick={loadWorkspace} title="Refresh"><i className="bi bi-arrow-repeat" /></button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Assignment Summary — appears in the Assign stage once a supplier is
              picked (Supplier Purchasing). Assign Selected stays disabled until a
              supplier and at least one product are selected. */}
          {stage === 'assign' && mode === 'supplier' && supplier && (() => {
            const g = selectedGroup
            const alreadyAssigned = g?.product_count ?? 0
            const purchaseValue = g?.est_value ?? 0
            const min = minOrders[supplier.supplier_code] ?? 0
            const ready = min > 0 ? purchaseValue >= min : alreadyAssigned > 0
            const readyLabel = min > 0 ? (ready ? 'Ready' : 'Below Min') : alreadyAssigned > 0 ? 'No minimum' : 'New'
            return (
              <div className="pm-selbar">
                <span className="pm-selbar__item">
                  <span className="pm-selbar__k">Selected Supplier</span>
                  <b className="pm-selbar__v">{supplier.supplier_name ?? supplier.supplier_code}</b>
                </span>
                <span className="pm-selbar__item">
                  <span className="pm-selbar__k">Products Selected</span>
                  <b className="pm-selbar__v">{num(checked.size)}</b>
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
                <button className="pm-btn pm-btn--ghost" disabled={checked.size === 0} onClick={() => setChecked(new Set())}>
                  Clear Selection
                </button>
                <button className="pm-btn pm-btn--ghost" onClick={assignRemaining}>
                  <i className="bi bi-list-check" /> Assign Remaining
                </button>
                <button
                  className="pm-btn pm-btn--primary"
                  disabled={checked.size === 0}
                  onClick={() => bulkAssign(supplier.supplier_code)}
                >
                  <i className="bi bi-check2-square" /> Assign Selected ({num(checked.size)})
                </button>
              </div>
            )
          })()}

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
              groups={queueLines}
              loading={queueLoading}
              mode="review"
              focusSupplierCode={null}
              onLoad={loadQueue}
              onExport={exportGroup}
              onExportAll={exportAll}
              busySupplier={busySupplier}
              exportingAll={exportingAll}
            />
          ) : stage === 'assign' && mode === 'supplier-stock' ? (
            !supplier ? (
              <div className="pm-stockmode">
                <EmptyState icon="bi-truck" title="Pick a supplier" description="Choose a supplier to see their live stock intersected with the current VPL." />
              </div>
            ) : (
              <div className="pm-split pm-split--stock">
                {/* Left column: dashboard summary strip (its own space) above a
                    single scroll area that owns the grid — the sticky header now
                    has nothing above it inside the scroller, so no overlap. */}
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
                    />
                  </div>
                </div>
                <div className="pm-split__detail pm-stockdetail">
                  {selectedStockRow ? (
                    <>
                      <SupplierStockDetail
                        row={selectedStockRow}
                        item={matchedStockItem}
                        storeStock={selectedStockRow.product_code != null ? storeStockByCode.get(selectedStockRow.product_code) ?? null : null}
                        orderQty={Number(stockDraft[stockRowKey(selectedStockRow)]) || null}
                        supplierName={supplier.supplier_name ?? null}
                        onWhy={matchedStockItem ? () => openInfo(matchedStockItem, 'decision') : undefined}
                      />
                      <div className="pm-stockdetail__hist">
                        <DetailColumn
                          tenantId={tenantId}
                          item={matchedStockItem}
                          onOpenInfo={openInfo}
                          onOpenBill={setBill}
                          onViewAll={(kind) => matchedStockItem && setViewAll({ kind, item: matchedStockItem })}
                        />
                      </div>
                    </>
                  ) : (
                    <EmptyState icon="bi-hand-index" title="Select a product" description="Choose a row to see inventory, commercial terms, sales trend and history." />
                  )}
                </div>
              </div>
            )
          ) : error ? (
            <ErrorState description={error} onRetry={loadWorkspace} />
          ) : (
            <div className="pm-split pm-split--3">
              <div className="pm-split__grid">
                {visibleItems.length === 0 && !loading ? (
                  <EmptyState icon="bi-inbox" title="No products" description="No working items match the current filters." />
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
                    collapseToSupplier={collapseToSupplier}
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
                <SupplierRecPanel
                  item={selectedItem}
                  suppliers={selectedId ? recommendations[selectedId] ?? [] : []}
                  selectedCode={selectedId ? selectedSupplier[selectedId] ?? null : null}
                  assignedCode={
                    selectedItem && (selectedItem.assigned_qty ?? 0) > 0
                      ? selectedSupplier[selectedItem.order_item_id] ?? selectedItem.supplier_code ?? null
                      : null
                  }
                  liveCodes={liveCodes}
                  active={supplierZoneActive}
                  onSelect={(code) => selectedId && onSelectSupplier(selectedId, code)}
                  onCommit={mode === 'supplier' && supplier ? (it) => assign(it, supplier.supplier_code) : (it, code) => onCommitSupplier(it, code)}
                  onOpenInfo={openInfo}
                />
              </div>
              <div className="pm-split__detail">
                {stage === 'assign' && supplier ? (
                  <SupplierReviewPanel
                    tenantId={tenantId}
                    storeId={storeId}
                    supplierCode={supplier.supplier_code}
                    supplierName={supplier.supplier_name ?? supplier.supplier_code}
                    group={selectedGroup}
                    loading={queueLoading}
                    exporting={busySupplier === supplier.supplier_code}
                    onChangeSupplier={reviewChangeSupplier}
                    onRemove={reviewRemove}
                    onExport={(g) => exportGroup(g, g.assignment_ids)}
                    onReload={loadQueue}
                  />
                ) : (
                  <DetailColumn
                    tenantId={tenantId}
                    item={selectedItem}
                    onOpenInfo={openInfo}
                    onOpenBill={setBill}
                    onViewAll={(kind) => selectedItem && setViewAll({ kind, item: selectedItem })}
                  />
                )}
              </div>
            </div>
          )}

          {(stage === 'review' || stage === 'assign') && mode !== 'supplier-stock' && (
            <div className="pm-totals">
              <span className="pm-stat"><span className="pm-stat__k">Total Products</span><b className="pm-stat__v">{num(total || items.length)}</b></span>
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
                <button className="pm-btn pm-btn--primary" onClick={autoAssign} disabled={autoBusy}>
                  <i className="bi bi-magic" /> {autoBusy ? 'Assigning…' : 'Auto Assign Suppliers'}
                </button>
                <span className="pm-stagebar__hint">{num(assignedCount)} assigned</span>
                <span className="pm-stagebar__spacer" />
                <button className="pm-btn pm-btn--ghost" onClick={() => goStage('optimize')}>
                  Optimize <i className="bi bi-arrow-right" />
                </button>
                <button className="pm-btn pm-btn--ghost" disabled={!hasAssignments} onClick={() => goStage('export')}>
                  Review Suppliers <i className="bi bi-arrow-right" />
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
                  Continue to Export <i className="bi bi-arrow-right" />
                </button>
              </>
            )}
            {stage === 'export' && (
              <>
                <button className="pm-btn pm-btn--ghost" onClick={() => goStage('optimize')}>
                  <i className="bi bi-arrow-left" /> Back to Optimize
                </button>
                <span className="pm-stagebar__hint">Export a single supplier from its card, or use Export All.</span>
              </>
            )}
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
