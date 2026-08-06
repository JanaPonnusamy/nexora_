import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { PageHeader } from '../../components/common/PageHeader'
import { BranchCard } from '../../components/stock/BranchCard'
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
import { InspectorPanel } from '../../design-system/components/InspectorPanel'
import { SegmentedTabs } from '../../design-system/components/SegmentedTabs'
import { KpiBar, StatCard } from '../../design-system/components/StatCard'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
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
    <InspectorPanel
      title={title}
      summary={<span className="text-muted">{description}</span>}
      empty
      emptyTitle="Waiting for data"
      emptyDescription={description}
    >
      <EmptyState icon={icon} title="Waiting for data" description={description} />
    </InspectorPanel>
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

  const debProduct = useDebouncedValue(productQuery)
  const debBatchNo = useDebouncedValue(batchNo)
  const debMrp = useDebouncedValue(mrp)
  const debBatchProduct = useDebouncedValue(batchProduct)
  const requestRef = useRef(0)

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

  useEffect(() => setActive(null), [tenantId])
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
      setActive({
        tenantId,
        storeId: card.store_id,
        storeName: card.store_name,
        storeCode: card.store_code,
        productCode: product.product_code,
        productName: product.product_name,
        stock: product.stock,
      })
    },
    [tenantId, push],
  )

  const activeStoreCount = result.summary.total_stores
  const activeProductCount = result.summary.total_products_found
  const storesWithStock = result.summary.stores_with_stock
  const totalStock = result.summary.total_stock_all_stores

  const header = (
    <div className="d-flex flex-column gap-3">
      <PageHeader
        title="Stock Availability"
        breadcrumb={['Operations', 'Inventory', 'Stock Availability']}
        description="Search products or batches across branches and inspect live stock, sales, purchase, and bill context."
      />
      <div className="ds-toolbar">
        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Tenant</span>
          <select
            className="form-select"
            aria-label="Tenant"
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
          >
            {tenants.length === 0 && <option value="">Loading...</option>}
            {tenants.map((tenant) => (
              <option key={tenant.tenant_id} value={tenant.tenant_id}>
                {tenant.tenant_name}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  )

  const kpis = (
    <KpiBar>
      <StatCard label="Branches Scanned" value={activeStoreCount.toLocaleString()} icon="bi-shop" loading={isLoading} />
      <StatCard label="Products Found" value={activeProductCount.toLocaleString()} icon="bi-box-seam" tone="primary" loading={isLoading} />
      <StatCard label="Branches With Stock" value={storesWithStock.toLocaleString()} icon="bi-check2-circle" tone="success" loading={isLoading} />
      <StatCard label="Total Stock" value={totalStock.toLocaleString()} icon="bi-archive" sub={mode === 'batch' ? 'Batch search results' : 'Product search results'} loading={isLoading} />
    </KpiBar>
  )

  const filters = (
    <div className="d-flex flex-column gap-3">
      <SegmentedTabs
        items={[
          { value: 'product', label: 'Product', description: 'Search by product name', icon: 'bi-search' },
          { value: 'batch', label: 'Batch / MRP', description: 'Search by batch attributes', icon: 'bi-upc-scan' },
        ]}
        activeValue={mode}
        ariaLabel="Search mode"
        onChange={setMode}
      />
      <div className="ds-toolbar">
        {mode === 'product' ? (
          <>
            <label className="ds-search-field flex-grow-1">
              <i className="bi bi-search" aria-hidden="true" />
              <input
                type="search"
                className="form-control"
                autoFocus
                value={productQuery}
                placeholder="Search product name"
                aria-label="Product name"
                onChange={(event) => setProductQuery(event.target.value)}
              />
            </label>
            <label className="form-check d-flex align-items-center gap-2 m-0">
              <input
                className="form-check-input"
                type="checkbox"
                checked={onlyStock}
                onChange={(event) => setOnlyStock(event.target.checked)}
              />
              <span className="form-check-label">In-stock only</span>
            </label>
          </>
        ) : (
          <>
            <label className="ds-search-field">
              <i className="bi bi-upc" aria-hidden="true" />
              <input
                type="search"
                className="form-control"
                value={batchNo}
                placeholder="Batch number"
                aria-label="Batch number"
                onChange={(event) => setBatchNo(event.target.value)}
              />
            </label>
            <label className="ds-search-field">
              <i className="bi bi-tag" aria-hidden="true" />
              <input
                type="search"
                className="form-control"
                inputMode="decimal"
                value={mrp}
                placeholder="MRP"
                aria-label="MRP"
                onChange={(event) => setMrp(event.target.value)}
              />
            </label>
            <label className="ds-search-field flex-grow-1">
              <i className="bi bi-search" aria-hidden="true" />
              <input
                type="search"
                className="form-control"
                value={batchProduct}
                placeholder="Product name"
                aria-label="Product name"
                onChange={(event) => setBatchProduct(event.target.value)}
              />
            </label>
          </>
        )}
      </div>
    </div>
  )

  const statusBar = (
    <div className="d-flex flex-wrap align-items-center gap-3">
      {STOCK_LEGEND.map((item) => (
        <span className="sa-legend__item" key={item.state}>
          <span className={`sa-dot sa-dot--${item.state}`} aria-hidden="true" />
          {item.label}
        </span>
      ))}
    </div>
  )

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
            activeStoreId={active?.storeId ?? null}
            activeProductCode={active?.productCode ?? null}
            onSelect={onSelectProduct}
          />
        ))}
      </div>
    )
  }, [active?.productCode, active?.storeId, error, hasSearched, isLoading, onSelectProduct, result.stores])

  return (
    <>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <WorkspaceShell
        header={header}
        kpis={kpis}
        filters={filters}
        statusBar={statusBar}
        fullWidth
      >
        <div className="d-flex flex-column gap-4">
          {branchResults}

          {active ? (
            <div className="d-flex flex-column gap-3">
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
          ) : hasSearched && result.stores.length > 0 ? (
            <InspectorPanel
              title="Select a product"
              summary="Choose a branch result to open batch, sales, purchase, bill, and movement details."
              empty
              emptyTitle="No product selected"
              emptyDescription="Select a row from the branch cards above to inspect product activity."
            />
          ) : (
            <div className="sa-detail__layout">
              <div className="sa-area sa-area--batch">
                <WaitingPanel title="Batch Details" icon="bi-layers" description="Batch rows will appear here once a product is selected." />
              </div>
              <div className="sa-area sa-area--sales">
                <WaitingPanel title="Recent Sales" icon="bi-cart-check" description="Sales history will appear here after the first product is opened." />
              </div>
              <div className="sa-area sa-area--purch">
                <WaitingPanel title="Recent Purchases" icon="bi-truck" description="Purchase history will appear here after the first product is opened." />
              </div>
              <div className="sa-area sa-area--bill">
                <WaitingPanel title="Bill Details" icon="bi-receipt" description="Bill line items will appear here after a sale is selected." />
              </div>
              <div className="sa-area sa-area--chart">
                <WaitingPanel title="Monthly Movement" icon="bi-bar-chart-line" description="Monthly movement will appear here once a product is loaded." />
              </div>
            </div>
          )}
        </div>
      </WorkspaceShell>
    </>
  )
}
