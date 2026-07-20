import { useCallback, useEffect, useRef, useState } from 'react'
import type { BranchCard as BranchCardData, ProductContext, StockProductRow, StockSearchResult } from '../../types/stock'
import type { Tenant } from '../../types/tenant'
import { stockService } from '../../services/stockService'
import { tenantService } from '../../services/tenantService'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { BranchCard } from '../../components/stock/BranchCard'
import { ToastStack, useToasts } from '../../components/stock/Toast'
import {
  BatchPanel,
  LatestBillPanel,
  MovementPanel,
  ProductContextBar,
  PurchasePanel,
  SalesPanel,
} from '../../components/stock/DetailPanels'
import type { SelectedBill } from '../../components/stock/DetailPanels'
import { STOCK_LEGEND } from '../../components/stock/format'
import { SxCard, SxCardBody, SxCardHead } from '../../components/sync/ui'
import '../../components/stock/stock-ui.css'

type SearchMode = 'product' | 'batch'

const EMPTY_RESULT: StockSearchResult = {
  stores: [],
  summary: { total_stores: 0, total_products_found: 0, stores_with_stock: 0, total_stock_all_stores: 0 },
}

function WaitingPanel({ title, icon, description }: { title: string; icon: string; description: string }) {
  return (
    <SxCard>
      <SxCardHead title={title} icon={icon} />
      <SxCardBody>
        <EmptyState icon={icon} title="Waiting for data" description={description} />
      </SxCardBody>
    </SxCard>
  )
}

export default function StockAvailabilityPage() {
  const { toasts, push, dismiss } = useToasts()

  // ----- Tenant context -----------------------------------------------------
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState<string>('')

  useEffect(() => {
    tenantService
      .list()
      .then((rows) => {
        const active = rows.filter((tenant) => tenant.is_active)
        setTenants(active)
        if (active.length) setTenantId((current) => current || active[0].tenant_id)
      })
      .catch((err) => push('danger', err instanceof Error ? err.message : 'Failed to load tenants'))
  }, [push])

  // ----- Search state -------------------------------------------------------
  const [mode, setMode] = useState<SearchMode>('product')
  const [productQuery, setProductQuery] = useState('')
  const [onlyStock, setOnlyStock] = useState(false)
  const [batchNo, setBatchNo] = useState('')
  const [mrp, setMrp] = useState('')
  const [batchProduct, setBatchProduct] = useState('')

  const debProduct = useDebouncedValue(productQuery)
  const debBatchNo = useDebouncedValue(batchNo)
  const debMrp = useDebouncedValue(mrp)
  const debBatchProduct = useDebouncedValue(batchProduct)

  const [result, setResult] = useState<StockSearchResult>(EMPTY_RESULT)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [active, setActive] = useState<ProductContext | null>(null)
  const [selectedBill, setSelectedBill] = useState<SelectedBill | null>(null)

  // Drop the active product whenever the tenant changes.
  useEffect(() => setActive(null), [tenantId])
  // Reset the chosen bill whenever the active product changes.
  useEffect(() => setSelectedBill(null), [active])

  const requestRef = useRef(0)

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

  return (
    <div className="sa sx container-fluid px-0">
      <ToastStack toasts={toasts} onDismiss={dismiss} />

      <div className="sa-head">
        <h1 className="sa-head__title"><i className="bi bi-box-seam" aria-hidden="true" /> Stock Availability</h1>
        <label className="sa-tenant">
          <span className="sa-tenant__lbl">Tenant</span>
          <select
            className="sx-select"
            aria-label="Tenant"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
          >
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((tenant) => (
              <option key={tenant.tenant_id} value={tenant.tenant_id}>
                {tenant.tenant_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Single-row search: mode tabs · fields · filter · legend */}
      <div className="sa-search">
        <div className="sa-search__tabs" role="tablist" aria-label="Search mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'product'}
            className={`sa-search__tab${mode === 'product' ? ' sa-search__tab--active' : ''}`}
            onClick={() => setMode('product')}
          >
            <i className="bi bi-search" aria-hidden="true" /> Product
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'batch'}
            className={`sa-search__tab${mode === 'batch' ? ' sa-search__tab--active' : ''}`}
            onClick={() => setMode('batch')}
          >
            <i className="bi bi-upc-scan" aria-hidden="true" /> Batch / MRP
          </button>
        </div>

        {mode === 'product' ? (
          <>
            <span className="sa-field sa-field--grow">
              <i className="bi bi-search" aria-hidden="true" />
              <input
                type="search"
                autoFocus
                value={productQuery}
                placeholder="Search product name…"
                aria-label="Product name"
                onChange={(e) => setProductQuery(e.target.value)}
              />
            </span>
            <label className="sa-check">
              <input type="checkbox" checked={onlyStock} onChange={(e) => setOnlyStock(e.target.checked)} />
              In-stock only
            </label>
          </>
        ) : (
          <>
            <span className="sa-field">
              <i className="bi bi-upc" aria-hidden="true" />
              <input type="search" value={batchNo} placeholder="Batch number" aria-label="Batch number" onChange={(e) => setBatchNo(e.target.value)} />
            </span>
            <span className="sa-field">
              <i className="bi bi-tag" aria-hidden="true" />
              <input type="search" inputMode="decimal" value={mrp} placeholder="MRP" aria-label="MRP" onChange={(e) => setMrp(e.target.value)} />
            </span>
            <span className="sa-field sa-field--grow">
              <i className="bi bi-search" aria-hidden="true" />
              <input type="search" value={batchProduct} placeholder="Product name" aria-label="Product name" onChange={(e) => setBatchProduct(e.target.value)} />
            </span>
          </>
        )}

        <span className="sa-legend">
          {STOCK_LEGEND.map((item) => (
            <span className="sa-legend__item" key={item.state}>
              <span className={`sa-dot sa-dot--${item.state}`} aria-hidden="true" />
              {item.label}
            </span>
          ))}
        </span>
      </div>

      {/* Results */}
      <div className="sa-body">
        {error ? (
          <ErrorState description={error} onRetry={() => requestRef.current++} />
        ) : (
          <>
            <div className="sa-branches">
              {!hasSearched && !isLoading
                ? Array.from({ length: 5 }).map((_, i) => <div key={i} className="sa-branch sa-branch--skeleton" />)
                : isLoading && result.stores.length === 0
                  ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="sa-branch sa-branch--skeleton" />)
                  : result.stores.length === 0
                    ? (
                      <EmptyState icon="bi-shop" title="No matches" description="No products matched your search in any branch." />
                    )
                    : result.stores.map((card) => (
                        <BranchCard
                          key={card.store_id}
                          card={card}
                          activeStoreId={active?.storeId ?? null}
                          activeProductCode={active?.productCode ?? null}
                          onSelect={onSelectProduct}
                        />
                      ))}
            </div>

            {active ? (
              <div className="sa-detail">
                <ProductContextBar ctx={active} />
                <div className="sa-detail__layout">
                  <div className="sa-area sa-area--batch"><BatchPanel ctx={active} /></div>
                  <div className="sa-area sa-area--sales">
                    <SalesPanel
                      ctx={active}
                      activeBillNo={selectedBill?.billNo ?? null}
                      onSelect={(row) => setSelectedBill({ billNo: row.bill_no ?? '', billDate: row.date ?? null, customer: row.customer ?? null })}
                    />
                  </div>
                  <div className="sa-area sa-area--purch"><PurchasePanel ctx={active} /></div>
                  <div className="sa-area sa-area--bill"><LatestBillPanel ctx={active} selected={selectedBill} /></div>
                  <div className="sa-area sa-area--chart"><MovementPanel ctx={active} /></div>
                </div>
              </div>
            ) : hasSearched && result.stores.length > 0 ? (
              <div className="sa-detail__hint">
                <i className="bi bi-hand-index" aria-hidden="true" /> Select a product to view batch, sales, purchase and movement details.
              </div>
            ) : (
              <div className="sa-detail">
                <div className="sa-ctx">
                  <div className="sa-ctx__lead">
                    <i className="bi bi-hourglass-split" aria-hidden="true" />
                    <strong>Waiting for data</strong>
                    <span className="sa-tag">Search product or batch</span>
                  </div>
                </div>
                <div className="sa-detail__layout">
                  <div className="sa-area sa-area--batch">
                    <WaitingPanel title="Batch Details" icon="bi-layers" description="Batch rows will appear here as soon as a product is selected." />
                  </div>
                  <div className="sa-area sa-area--sales">
                    <WaitingPanel title="Recent Sales" icon="bi-cart-check" description="Sales history will appear here after the first result is selected." />
                  </div>
                  <div className="sa-area sa-area--purch">
                    <WaitingPanel title="Recent Purchases" icon="bi-truck" description="Purchase history will appear here after the first result is selected." />
                  </div>
                  <div className="sa-area sa-area--bill">
                    <WaitingPanel title="Bill Details" icon="bi-receipt" description="Bill line items will appear here after a sale is chosen." />
                  </div>
                  <div className="sa-area sa-area--chart">
                    <WaitingPanel title="Monthly Movement" icon="bi-bar-chart-line" description="Monthly movement will appear here once a product is loaded." />
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
