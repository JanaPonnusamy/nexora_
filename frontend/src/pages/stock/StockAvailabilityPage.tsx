import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { BranchCard } from '../../components/stock/BranchCard'
import type { BranchSelection } from '../../components/stock/BranchCard'
import {
  BatchPanel,
  LatestBillPanel,
  MovementPanel,
  ProductContextBar,
  PurchasePanel,
  SalesPanel,
} from '../../components/stock/DetailPanels'
import type { SelectedBill } from '../../components/stock/DetailPanels'
import { ToastStack, useToasts } from '../../components/stock/Toast'
import { STOCK_LEGEND } from '../../components/stock/format'
import '../../components/stock/stock-ui.css'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { stockService } from '../../services/stockService'
import { tenantService } from '../../services/tenantService'
import type { BranchCard as BranchCardData, ProductContext, StockProductRow, StockSearchResult } from '../../types/stock'
import type { Tenant } from '../../types/tenant'

type SearchMode = 'product' | 'batch'

const EMPTY_RESULT: StockSearchResult = {
  stores: [],
  summary: { total_stores: 0, total_products_found: 0, stores_with_stock: 0, total_stock_all_stores: 0 },
}

function WaitingPanel({ title, icon, description }: { title: string; icon: string; description: string }) {
  return (
    <div className="sx-card">
      <div className="sx-card__head"><span className="sx-card__title">{title}</span></div>
      <div className="sx-card__body">
        <div className="sa-detail__hint"><i className={`bi ${icon}`} aria-hidden="true" /> {description}</div>
      </div>
    </div>
  )
}

export default function StockAvailabilityPage() {
  const { toasts, push, dismiss } = useToasts()
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState<string>('')
  const [mode, setMode] = useState<SearchMode>('product')
  const [productQuery, setProductQuery] = useState('')
  const [onlyStock, setOnlyStock] = useState(false)
  const [batchNo, setBatchNo] = useState('')
  const [mrp, setMrp] = useState('')
  const [batchProduct, setBatchProduct] = useState('')
  const [result, setResult] = useState<StockSearchResult>(EMPTY_RESULT)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [active, setActive] = useState<ProductContext | null>(null)
  const [selectedBill, setSelectedBill] = useState<SelectedBill | null>(null)
  // Per-store product selection, keyed by store_id — lets every branch card
  // highlight its own equivalent product independently (unlike `active`,
  // which is the single clicked source that drives the detail panels below).
  const [selections, setSelections] = useState<Record<string, BranchSelection>>({})

  const debProduct = useDebouncedValue(productQuery)
  const debBatchNo = useDebouncedValue(batchNo)
  const debMrp = useDebouncedValue(mrp)
  const debBatchProduct = useDebouncedValue(batchProduct)
  const requestRef = useRef(0)
  // Guards the cross-store sync cycle against recursively re-triggering
  // itself, and lets a superseded sync response (an older click's result
  // arriving after a newer click) be dropped instead of clobbering state.
  const isSynchronizingProductSelection = useRef(false)
  const syncTicketRef = useRef(0)

  useEffect(() => {
    tenantService
      .list()
      .then((rows) => {
        const activeTenants = rows.filter((tenant) => tenant.is_active)
        setTenants(activeTenants)
        if (activeTenants.length) setTenantId((current) => current || activeTenants[0].tenant_id)
      })
      .catch((err) => push('danger', err instanceof Error ? err.message : 'Failed to load tenants'))
  }, [push])

  useEffect(() => {
    setActive(null)
    setSelections({})
  }, [tenantId])
  useEffect(() => setSelectedBill(null), [active])

  useEffect(() => {
    if (!tenantId) return

    const hasProductTerms = debProduct.trim().length > 0
    const hasBatchTerms = [debBatchNo, debMrp, debBatchProduct].some((value) => value.trim().length > 0)
    const shouldSearch = mode === 'product' ? hasProductTerms : hasBatchTerms

    if (!shouldSearch) {
      setResult(EMPTY_RESULT)
      setHasSearched(false)
      setError(null)
      return
    }

    const ticket = ++requestRef.current
    setIsLoading(true)
    setError(null)
    const promise =
      mode === 'product'
        ? stockService.searchProducts(tenantId, debProduct.trim(), onlyStock)
        : stockService.searchBatches(tenantId, debBatchNo.trim(), debMrp.trim(), debBatchProduct.trim())

    promise
      .then((data) => {
        if (ticket !== requestRef.current) return
        setResult(data)
        setHasSearched(true)
      })
      .catch((err) => {
        if (ticket !== requestRef.current) return
        setError(err instanceof Error ? err.message : 'Search failed')
        setResult(EMPTY_RESULT)
      })
      .finally(() => {
        if (ticket === requestRef.current) setIsLoading(false)
      })
  }, [tenantId, mode, debProduct, onlyStock, debBatchNo, debMrp, debBatchProduct])

  const onSelectProduct = useCallback(
    (card: BranchCardData, product: StockProductRow) => {
      if (!product.product_code) {
        push('info', 'This product has no code and cannot be inspected.')
        return
      }
      // A row click while a sync cycle is in flight is a real user action
      // (e.g. a fast manual override in another store) — this guard only
      // stops the sync's OWN completion from ever re-entering this handler,
      // which it structurally can't anyway since it never calls onSelect.
      if (isSynchronizingProductSelection.current) return

      const productCode = product.product_code
      setActive({
        tenantId,
        storeId: card.store_id,
        storeName: card.store_name,
        storeCode: card.store_code,
        productCode,
        productName: product.product_name,
        stock: product.stock,
      })
      setSelections((prev) => ({
        ...prev,
        [card.store_id]: { productCode, matchType: 'SOURCE', score: 100 },
      }))

      const targetStoreIds = result.stores.map((s) => s.store_id).filter((id) => id !== card.store_id)
      if (targetStoreIds.length === 0) return

      const ticket = ++syncTicketRef.current
      isSynchronizingProductSelection.current = true
      stockService
        .syncSelection(tenantId, card.store_id, productCode, product.product_name, targetStoreIds)
        .then((res) => {
          if (ticket !== syncTicketRef.current) return // superseded by a newer click
          setSelections((prev) => {
            const next = { ...prev }
            for (const r of res.results) {
              if (r.product && r.match_type !== 'NO_MATCH') {
                next[r.store_id] = { productCode: r.product.product_code, matchType: r.match_type, score: r.score }
              } else {
                delete next[r.store_id] // no reliable match -> leave that store unselected
              }
            }
            return next
          })
        })
        .catch((err) => push('danger', err instanceof Error ? err.message : 'Cross-store product match failed'))
        .finally(() => {
          if (ticket === syncTicketRef.current) isSynchronizingProductSelection.current = false
        })
    },
    [tenantId, push, result.stores],
  )

  const activeStoreCount = result.summary.total_stores
  const activeProductCount = result.summary.total_products_found
  const storesWithStock = result.summary.stores_with_stock
  const totalStock = result.summary.total_stock_all_stores

  const branchResults = useMemo(() => {
    if (error) return <ErrorState description={error} onRetry={() => requestRef.current++} />

    if (!hasSearched && !isLoading) {
      return (
        <div className="sa-branches">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="sa-branch sa-branch--skeleton" />
          ))}
        </div>
      )
    }

    if (isLoading && result.stores.length === 0) {
      return (
        <div className="sa-branches">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="sa-branch sa-branch--skeleton" />
          ))}
        </div>
      )
    }

    if (result.stores.length === 0) {
      return (
        <EmptyState
          icon="bi-shop"
          title="No matches"
          description="No products matched your current search across the selected branches."
        />
      )
    }

    return (
      <div className="sa-branches">
        {result.stores.map((card) => (
          <BranchCard
            key={card.store_id}
            card={card}
            selection={selections[card.store_id] ?? null}
            onSelect={onSelectProduct}
          />
        ))}
      </div>
    )
  }, [error, hasSearched, isLoading, onSelectProduct, result.stores, selections])

  return (
    <div className="sa sx">
      <ToastStack toasts={toasts} onDismiss={dismiss} />

      {/* Compact header: title + live KPIs + tenant — one row (req: dense). */}
      <header className="sa-head">
        <h1 className="sa-head__title"><i className="bi bi-search" aria-hidden="true" />Stock Availability</h1>
        <div className="sa-head__right">
          <div className="sa-kpis" aria-label="Search summary">
            <span className="sa-kpi"><b>{activeStoreCount.toLocaleString()}</b><i>Branches</i></span>
            <span className="sa-kpi sa-kpi--accent"><b>{activeProductCount.toLocaleString()}</b><i>Products</i></span>
            <span className="sa-kpi sa-kpi--ok"><b>{storesWithStock.toLocaleString()}</b><i>With stock</i></span>
            <span className="sa-kpi"><b>{totalStock.toLocaleString()}</b><i>Total stock</i></span>
          </div>
          <label className="sa-tenant">
            <span className="sa-tenant__lbl">Tenant</span>
            <select aria-label="Tenant" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>
              {tenants.length === 0 && <option value="">Loading…</option>}
              {tenants.map((tenant) => (
                <option key={tenant.tenant_id} value={tenant.tenant_id}>{tenant.tenant_name}</option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {/* Compact search row: mode tabs + fields + legend. */}
      <div className="sa-search">
        <div className="sa-search__tabs" role="tablist" aria-label="Search mode">
          <button type="button" role="tab" aria-selected={mode === 'product'} className={`sa-search__tab${mode === 'product' ? ' sa-search__tab--active' : ''}`} onClick={() => setMode('product')}><i className="bi bi-search" aria-hidden="true" />Product</button>
          <button type="button" role="tab" aria-selected={mode === 'batch'} className={`sa-search__tab${mode === 'batch' ? ' sa-search__tab--active' : ''}`} onClick={() => setMode('batch')}><i className="bi bi-upc-scan" aria-hidden="true" />Batch / MRP</button>
        </div>
        <div className="sa-search__fields">
          {mode === 'product' ? (
            <>
              <div className="sa-field sa-field--grow"><i className="bi bi-search" aria-hidden="true" /><input autoFocus value={productQuery} placeholder="Search product name" aria-label="Product name" onChange={(e) => setProductQuery(e.target.value)} /></div>
              <label className="sa-check"><input type="checkbox" checked={onlyStock} onChange={(e) => setOnlyStock(e.target.checked)} /> In-stock only</label>
            </>
          ) : (
            <>
              <div className="sa-field"><i className="bi bi-upc" aria-hidden="true" /><input value={batchNo} placeholder="Batch number" aria-label="Batch number" onChange={(e) => setBatchNo(e.target.value)} /></div>
              <div className="sa-field"><i className="bi bi-tag" aria-hidden="true" /><input value={mrp} placeholder="MRP" aria-label="MRP" onChange={(e) => setMrp(e.target.value)} /></div>
              <div className="sa-field sa-field--grow"><i className="bi bi-search" aria-hidden="true" /><input value={batchProduct} placeholder="Product name" aria-label="Product name" onChange={(e) => setBatchProduct(e.target.value)} /></div>
            </>
          )}
        </div>
        <div className="sa-legend">
          {STOCK_LEGEND.map((item) => (
            <span className="sa-legend__item" key={item.state}>
              <span className={`sa-dot sa-dot--${item.state}`} aria-hidden="true" />
              {item.label}
            </span>
          ))}
        </div>
      </div>

      {/* Body fills the remaining viewport; branch cards + detail scroll internally. */}
      <div className="sa-body">
        <div className="sa-branches-head">
          <span className="sa-branches-head__title">
            {hasSearched
              ? `${activeProductCount.toLocaleString()} products across ${activeStoreCount.toLocaleString()} branches`
              : 'Search a product or batch to view branch stock'}
          </span>
        </div>

        {branchResults}

        {active ? (
          <div className="sa-detail">
            <ProductContextBar ctx={active} />
            <div className="sa-detail__layout">
              <div className="sa-area sa-area--batch"><BatchPanel ctx={active} /></div>
              <div className="sa-area sa-area--sales">
                <SalesPanel
                  ctx={active}
                  activeBillNo={selectedBill?.billNo ?? null}
                  onSelect={(row) =>
                    setSelectedBill({ billNo: row.bill_no ?? '', billDate: row.date ?? null, customer: row.customer ?? null })}
                />
              </div>
              <div className="sa-area sa-area--purch"><PurchasePanel ctx={active} /></div>
              <div className="sa-area sa-area--bill"><LatestBillPanel ctx={active} selected={selectedBill} /></div>
              <div className="sa-area sa-area--chart"><MovementPanel ctx={active} /></div>
            </div>
          </div>
        ) : (
          <div className="sa-detail">
            <div className="sa-detail__layout">
              <div className="sa-area sa-area--batch"><WaitingPanel title="Batch Details" icon="bi-layers" description={hasSearched ? 'Select a product above to load batch rows.' : 'Batch rows appear once a product is selected.'} /></div>
              <div className="sa-area sa-area--sales"><WaitingPanel title="Recent Sales" icon="bi-cart-check" description="Sales history appears after a product is opened." /></div>
              <div className="sa-area sa-area--purch"><WaitingPanel title="Recent Purchases" icon="bi-truck" description="Purchase history appears after a product is opened." /></div>
              <div className="sa-area sa-area--bill"><WaitingPanel title="Bill Details" icon="bi-receipt" description="Bill line items appear after a sale is selected." /></div>
              <div className="sa-area sa-area--chart"><WaitingPanel title="Monthly Movement" icon="bi-bar-chart-line" description="Monthly movement appears once a product is loaded." /></div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
