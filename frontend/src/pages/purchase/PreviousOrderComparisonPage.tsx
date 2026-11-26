// Previous Order Comparison -- standalone page extracted from the Compare
// Previous Order panel on LegacyOrderPage (see legacy-order/LegacyOrderPage.tsx).
// Reuses the exact same service calls, types, and VB.NET-ported backend
// comparison rules; no comparison logic is reimplemented here. LegacyOrderPage
// itself is left unchanged -- this page is additive, not a replacement.
import { useEffect, useMemo, useState } from 'react'
import { legacyOrderService } from '../../services/legacyOrderService'
import type { LegacyStore, PreviousOrder, PreviousOrderSupplier, RestorableOrderPreview, SupplierComparisonProduct } from '../../types/legacyOrder'
import { FilterBar, FilterSearch, FilterSelect } from '../../design-system/components/FilterBar'
import { useAuth } from '../../hooks/useAuth'
import { isSuperAdmin } from '../label-export/labelExportAccess'
import '../legacy-order/legacy-order.css'

function fmtDateTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

function fmtQty(value: number | null): string {
  return value == null ? '—' : String(value)
}

type Decision = {
  label: string
  tone: 'success' | 'partial' | 'danger' | 'neutral'
  remark: string
  qtyDiff: number | null
}

// Mirrors repository.compare_previous_order_supplier's two UPDATEs exactly
// (see backend/modules/legacy_order/repository.py) so the remark explains
// what Compare will actually do to this row, not a guessed outcome. Rule A
// (carry-forward/mark-only) and Rule B (stock-sold reopen) can both match
// the same row -- Rule B's SQL re-reads OrderQty AFTER Rule A's UPDATE has
// already run in the same batch, so when both match, B's reopened/reduced
// quantity is the row's final state, not A's carried-forward one. Each
// branch below states the SPECIFIC condition that fired it, so the label
// can never drift from the data the way a trailing catch-all would.
function deriveDecision(product: SupplierComparisonProduct): Decision {
  const prevQty = product.PreviousOrderedQty
  const currQty = product.CurrentOrderQty
  const prevStock = product.PreviousStock
  const currStock = product.CurrentStock
  const qtyDiff = currQty != null && prevQty != null ? currQty - prevQty : null

  const stockSold = prevStock != null && currStock != null && prevStock > currStock
  const zeroQty = currQty === 0
  const fullyAssigned = product.PreviousStatus === 1
  // Rule B: stock sold AND the quantity carried forward would now exceed
  // what's actually left to order.
  const ruleB = stockSold && qtyDiff != null && qtyDiff > 0

  if (ruleB) {
    return {
      label: 'Reopen after sale',
      tone: 'danger',
      remark: `Sold since yesterday's order (stock dropped ${fmtQty(prevStock)} → ${fmtQty(currStock)}) -- Compare will reduce the order by the ${fmtQty(prevQty)} already carried and reopen this line for a fresh quantity check ("After Order Sold").`,
      qtyDiff,
    }
  }
  if (zeroQty) {
    return {
      label: 'Eliminate',
      tone: 'partial',
      remark: 'Current order quantity is 0 for this product -- Compare will mark it reviewed (Status 2) without carrying a quantity forward, effectively excluding it from this order.',
      qtyDiff,
    }
  }
  if (fullyAssigned) {
    return {
      label: 'Include (carry forward)',
      tone: 'success',
      remark: `Yesterday's order had this fully assigned to a supplier (qty ${fmtQty(prevQty)}) -- Compare will carry that quantity and supplier forward onto today's order.`,
      qtyDiff,
    }
  }
  if (stockSold) {
    return {
      label: 'Mark reviewed',
      tone: 'partial',
      remark: `Stock dropped since yesterday (${fmtQty(prevStock)} → ${fmtQty(currStock)}) -- Compare will mark this line reviewed without changing today's quantity.`,
      qtyDiff,
    }
  }
  return {
    label: 'No match',
    tone: 'neutral',
    remark: 'No previous-order rule matches this product -- Compare will leave it untouched on the current order.',
    qtyDiff,
  }
}

export default function PreviousOrderComparisonPage() {
  const { user } = useAuth()
  // Restore stays admin-only (server-enforced via require_admin on the
  // restore endpoints, unchanged from LegacyOrderPage) -- isAdmin below
  // gates only the Restore button's visibility.
  const isAdmin = isSuperAdmin(user)

  const [stores, setStores] = useState<LegacyStore[]>([])
  const [storesLoading, setStoresLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [compareStore, setCompareStore] = useState('')
  const [orderSearch, setOrderSearch] = useState('')
  const [previousOrders, setPreviousOrders] = useState<PreviousOrder[]>([])
  const [selectedOrderId, setSelectedOrderId] = useState('')
  const [suppliers, setSuppliers] = useState<PreviousOrderSupplier[]>([])
  const [selectedSupplier, setSelectedSupplier] = useState('')
  const [reviewProducts, setReviewProducts] = useState<SupplierComparisonProduct[]>([])
  const [reviewLoading, setReviewLoading] = useState(false)
  const [openProductCode, setOpenProductCode] = useState<number | null>(null)
  const [compareBusy, setCompareBusy] = useState(false)
  const [compareMessage, setCompareMessage] = useState('')
  const [restorePreview, setRestorePreview] = useState<RestorableOrderPreview | null>(null)
  const [restoreBusy, setRestoreBusy] = useState(false)

  useEffect(() => {
    setStoresLoading(true)
    legacyOrderService.listStores()
      .then((storeList) => {
        setStores(storeList)
        setCompareStore((current) => current || (storeList[0]?.store_name ?? ''))
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setStoresLoading(false))
  }, [])

  useEffect(() => {
    if (!compareStore) return
    setPreviousOrders([])
    setSelectedOrderId('')
    setCompareMessage('')
    legacyOrderService.previousOrders(compareStore)
      .then((orders) => {
        setPreviousOrders(orders)
        if (orders.length) setSelectedOrderId(String(orders[0].order_id))
      })
      .catch((e: Error) => setError(e.message))
  }, [compareStore])

  useEffect(() => {
    if (!compareStore || !selectedOrderId) {
      setSuppliers([])
      setSelectedSupplier('')
      setReviewProducts([])
      return
    }
    legacyOrderService.previousOrderSuppliers(compareStore, Number(selectedOrderId))
      .then((rows) => {
        setSuppliers(rows)
        setSelectedSupplier('')
        setReviewProducts([])
      })
      .catch((e: Error) => setError(e.message))
  }, [compareStore, selectedOrderId])

  const compare = () => {
    if (!compareStore || !selectedOrderId) return
    setCompareBusy(true)
    setCompareMessage('')
    legacyOrderService.comparePreviousOrder(compareStore, Number(selectedOrderId))
      .then((result) => setCompareMessage(
        `Compared order ${result.order_id}. ${result.affected_rows} row updates applied.`,
      ))
      .catch((e: Error) => setError(e.message))
      .finally(() => setCompareBusy(false))
  }

  const compareSupplier = (supplierCode: string) => {
    if (!compareStore || !selectedOrderId) return
    setCompareBusy(true)
    setCompareMessage('')
    legacyOrderService.comparePreviousOrderSupplier(
      compareStore, Number(selectedOrderId), supplierCode,
    )
      .then((result) => setCompareMessage(
        `Compared supplier ${result.supplier_code}. ${result.affected_rows} row updates applied.`,
      ))
      .catch((e: Error) => setError(e.message))
      .finally(() => setCompareBusy(false))
  }

  const openRestorePreview = () => {
    if (!compareStore || !selectedOrderId) return
    setError(null)
    setRestorePreview(null)
    legacyOrderService.restorableOrderPreview(compareStore, Number(selectedOrderId))
      .then(setRestorePreview)
      .catch((e: Error) => setError(e.message))
  }

  const confirmRestore = () => {
    if (!restorePreview) return
    setRestoreBusy(true)
    legacyOrderService.restoreBackupOrder(restorePreview.store_name, restorePreview.order_id)
      .then((result) => {
        setCompareMessage(
          `Restored order #${result.source_order_id}. ${result.restored_count} row(s) restored.`,
        )
        setRestorePreview(null)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setRestoreBusy(false))
  }

  const reviewSupplier = (supplierCode: string) => {
    setSelectedSupplier(supplierCode)
    setReviewProducts([])
    setOpenProductCode(null)
    setReviewLoading(true)
    legacyOrderService.previousOrderSupplierProducts(
      compareStore, Number(selectedOrderId), supplierCode,
    )
      .then(setReviewProducts)
      .catch((e: Error) => setError(e.message))
      .finally(() => setReviewLoading(false))
  }

  // Picker label: display name, plus the tenant when two stores share it (.32: SMA).
  const storeLabel = (store: LegacyStore) => {
    const name = store.display_name || store.store_name
    const shared = stores.some((s) => s !== store && (s.display_name || s.store_name) === name)
    return shared && store.tenant_name ? `${name} · ${store.tenant_name}` : name
  }

  const filteredOrders = useMemo(() => {
    const term = orderSearch.trim().toLowerCase()
    if (!term) return previousOrders
    return previousOrders.filter((order) => String(order.order_id).includes(term))
  }, [previousOrders, orderSearch])

  return (
    <div className="legacy-order">
      <header className="lo-header">
        <div>
          <h1>Previous Order Comparison</h1>
          <p className="lo-note">Uses the original VB.NET comparison rules. Recent two-day orders are shown first, with the latest five as fallback.</p>
        </div>
      </header>

      {error && <div className="lo-error" role="alert">{error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button></div>}

      <section className="lo-card">
        <div className="lo-modern-compare">
          <FilterBar compact className="lo-compare-toprow" ariaLabel="Previous order filters">
            <FilterSelect label="Store" ariaLabel="Store" value={compareStore} onChange={setCompareStore}>
              {stores.map((store) => <option key={store.store_name} value={store.store_name}>{storeLabel(store)}</option>)}
            </FilterSelect>
            <FilterSearch value={orderSearch} placeholder="Search order #" ariaLabel="Search previous orders" onChange={setOrderSearch} />
          </FilterBar>

          {storesLoading && <div className="lo-empty">Loading stores…</div>}
          {!storesLoading && !stores.length && <div className="lo-empty">No active stores found.</div>}

          <div className="lo-compare-grid" role="listbox" aria-label="Previous orders">
            {filteredOrders.map((order) => (
              <button type="button" role="option" aria-selected={selectedOrderId === String(order.order_id)} className={`lo-order-tile${selectedOrderId === String(order.order_id) ? ' is-selected' : ''}`} key={order.order_id} onClick={() => setSelectedOrderId(String(order.order_id))}>
                <span className="lo-order-icon"><i className="bi bi-receipt" /></span>
                <span><strong>#{order.order_id}</strong><small>{fmtDateTime(order.wanted_date)}</small></span>
                <i className="bi bi-chevron-right" />
              </button>
            ))}
            {!filteredOrders.length && !storesLoading && <div className="lo-empty">No previous orders match.</div>}
          </div>

          {selectedOrderId && (
            <div className="lo-supplier-area">
              <div className="lo-compare-toolbar">
                <div><strong>Order #{selectedOrderId}</strong><small>{suppliers.length} suppliers available</small></div>
                <div className="lo-op-settings-actions">
                  {isAdmin && (
                    <button type="button" className="lo-btn" title="Restore this backup order's rows back onto the current order" disabled={compareBusy} onClick={openRestorePreview}>
                      <i className="bi bi-arrow-counterclockwise" /> Restore this order
                    </button>
                  )}
                  <button type="button" className="lo-btn" disabled={compareBusy} onClick={compare}>{compareBusy ? 'Comparing…' : 'Compare Entire Order'}</button>
                </div>
              </div>
              <div className="lo-supplier-grid">
                <div className="lo-supplier-head"><span>Supplier</span><span>Products</span><span>Action</span></div>
                {suppliers.map((supplier) => (
                  <button type="button" className={`lo-supplier-row${selectedSupplier === supplier.supplier_code ? ' is-selected' : ''}`} key={supplier.supplier_code} onClick={() => reviewSupplier(supplier.supplier_code)}>
                    <span><strong>{supplier.supplier_name}</strong><small>{supplier.supplier_code}</small></span>
                    <span className="lo-product-count">{supplier.product_count}</span>
                    <span className="lo-review-link">Review <i className="bi bi-arrow-right" /></span>
                  </button>
                ))}
                {!suppliers.length && <div className="lo-empty">No assigned suppliers in this backup order.</div>}
              </div>
            </div>
          )}
        </div>
        {compareMessage && <div className="lo-success"><i className="bi bi-check-circle" /> {compareMessage}</div>}
      </section>

      {selectedSupplier && (
        <div className="lo-drawer-backdrop" role="presentation" onClick={() => setSelectedSupplier('')}>
          <section className="lo-card lo-review-overlay" role="dialog" aria-label="Supplier comparison review" onClick={(e) => e.stopPropagation()}>
          <div className="lo-product-review">
            <div className="lo-review-header">
              <div>
                <span className="lo-eyebrow">Supplier comparison review</span>
                <h3>{suppliers.find((supplier) => supplier.supplier_code === selectedSupplier)?.supplier_name ?? selectedSupplier}</h3>
                <p>Order #{selectedOrderId} · {reviewProducts.length} products</p>
              </div>
              <div className="lo-review-header-actions">
                <span className="lo-chip lo-chip-running">Review required</span>
                <button type="button" className="lo-icon-btn" aria-label="Close" onClick={() => setSelectedSupplier('')}>×</button>
              </div>
            </div>
            <div className="lo-review-scroll">
              <table className="lo-table lo-review-table">
                <thead><tr><th>Product</th><th className="lo-num">Previous qty</th><th className="lo-num">Current qty</th><th className="lo-num">Qty diff</th><th>Decision</th><th aria-label="Action" /></tr></thead>
                <tbody>
                  {reviewProducts.map((product) => {
                    const decision = deriveDecision(product)
                    const code = product.CurrentProductCode ?? product.PreviousProductCode
                    const isOpen = openProductCode === code
                    return (
                      <tr key={product.PreviousProductCode} className={isOpen ? 'is-selected' : ''}>
                        <td><strong>{product.CurrentProductName ?? product.PreviousProductName}</strong><small className="lo-cell-sub">{product.PreviousProductCode}</small></td>
                        <td className="lo-num">{fmtQty(product.PreviousOrderedQty)}</td>
                        <td className="lo-num">{fmtQty(product.CurrentOrderQty)}</td>
                        <td className={`lo-num lo-qty-diff${decision.qtyDiff ? (decision.qtyDiff > 0 ? ' is-up' : ' is-down') : ' is-zero'}`}>
                          {decision.qtyDiff == null ? '—' : (decision.qtyDiff > 0 ? `+${decision.qtyDiff}` : decision.qtyDiff)}
                        </td>
                        <td><span className={`lo-chip lo-chip-${decision.tone}`}>{decision.label}</span></td>
                        <td>
                          <button type="button" className="lo-btn" onClick={() => setOpenProductCode(isOpen ? null : code)}>
                            {isOpen ? 'Close' : 'Details'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                  {!reviewProducts.length && <tr><td colSpan={6} className="lo-empty">{reviewLoading ? 'Loading product comparison…' : 'No products available for review.'}</td></tr>}
                </tbody>
              </table>
            </div>

            {openProductCode != null && (() => {
              const product = reviewProducts.find((p) => (p.CurrentProductCode ?? p.PreviousProductCode) === openProductCode)
              if (!product) return null
              const decision = deriveDecision(product)
              return (
                <div className="lo-product-card" role="region" aria-label="Product review detail">
                  <div className="lo-product-card-head">
                    <div>
                      <strong>{product.CurrentProductName ?? product.PreviousProductName}</strong>
                      <small className="lo-cell-sub">{product.CurrentProductCode ?? product.PreviousProductCode}</small>
                    </div>
                    <span className={`lo-chip lo-chip-${decision.tone}`}>{decision.label}</span>
                  </div>

                  <div className="lo-group-grid">
                    <div className="lo-group lo-group-yesterday">
                      <h4>Yesterday&rsquo;s order</h4>
                      <dl className="lo-meta">
                        <div><dt>Order qty</dt><dd>{fmtQty(product.PreviousOrderedQty)}</dd></div>
                        <div><dt>Stock then</dt><dd>{fmtQty(product.PreviousStock)}</dd></div>
                        <div><dt>Status</dt><dd>{product.PreviousStatus ?? '—'}</dd></div>
                        <div><dt>Remarks</dt><dd>{product.PreviousRemarks ?? '—'}</dd></div>
                      </dl>
                    </div>

                    <div className="lo-group lo-group-activity">
                      <h4>Purchase &amp; sales since</h4>
                      <dl className="lo-meta">
                        <div><dt>Stock received qty</dt><dd>{fmtQty(product.LastReceivedQty)}</dd></div>
                        <div><dt>Last received time</dt><dd>{fmtDateTime(product.LastGRNDate)}</dd></div>
                        <div><dt>Last sale qty</dt><dd>{fmtQty(product.CurrentSLSQty)}</dd></div>
                        <div><dt>Last sale time</dt><dd>{fmtDateTime(product.CurrentLastSaleDate)}</dd></div>
                      </dl>
                    </div>

                    <div className="lo-group lo-group-current">
                      <h4>Current order</h4>
                      <dl className="lo-meta">
                        <div><dt>Order qty</dt><dd>{fmtQty(product.CurrentOrderQty)}</dd></div>
                        <div><dt>Stock now</dt><dd>{fmtQty(product.CurrentStock)}</dd></div>
                        <div><dt>Wanted type</dt><dd>{product.CurrentWantedType ?? '—'}</dd></div>
                        <div><dt>Last received</dt><dd>{fmtDateTime(product.CurrentLastReceivedDate)}</dd></div>
                      </dl>
                    </div>

                    <div className={`lo-group lo-group-decision lo-group-decision-${decision.tone}`}>
                      <h4>Decision</h4>
                      <dl className="lo-meta">
                        <div><dt>Qty diff (current − previous)</dt><dd className={`lo-qty-diff${decision.qtyDiff ? (decision.qtyDiff > 0 ? ' is-up' : ' is-down') : ' is-zero'}`}>{decision.qtyDiff == null ? '—' : (decision.qtyDiff > 0 ? `+${decision.qtyDiff}` : decision.qtyDiff)}</dd></div>
                        <div><dt>Outcome</dt><dd>{decision.label}</dd></div>
                      </dl>
                      <p className="lo-decision-remark">{decision.remark}</p>
                    </div>
                  </div>
                </div>
              )
            })()}

            <div className="lo-review-footer">
              <div><strong>Review complete?</strong><small>This applies the VB.NET supplier comparison rules to these products.</small></div>
              <button type="button" className="lo-btn lo-btn-primary" disabled={reviewLoading || !reviewProducts.length || compareBusy} onClick={() => compareSupplier(selectedSupplier)}>
                {compareBusy ? 'Comparing…' : `Compare ${reviewProducts.length} Products`}
              </button>
            </div>
          </div>
          </section>
        </div>
      )}

      {restorePreview && (
        <div className="lo-drawer-backdrop" role="presentation" onClick={() => setRestorePreview(null)}>
          <aside className="lo-drawer" role="dialog" aria-label="Confirm restore" onClick={(e) => e.stopPropagation()}>
            <div className="lo-drawer-head">
              <h3>Restore order #{restorePreview.order_id} — {restorePreview.store_name}</h3>
              <button type="button" className="lo-icon-btn" aria-label="Close" onClick={() => setRestorePreview(null)}>×</button>
            </div>
            <div className="lo-drawer-body">
              <p>
                This backup was taken <strong>{fmtDateTime(restorePreview.backed_up_at)}</strong> and contains{' '}
                <strong>{restorePreview.product_count}</strong> product(s) across{' '}
                <strong>{restorePreview.suppliers.length}</strong> supplier(s).
              </p>
              <p className="lo-note">
                Restoring will overwrite the CURRENT order's matching rows (quantity, supplier assignment, status,
                remarks) with this backup's values. Products in the backup with no matching row on the current order
                will block the entire restore — nothing is partially applied. This cannot be undone from here.
              </p>
              {restorePreview.suppliers.length > 0 && (
                <table className="lo-table">
                  <thead><tr><th>Supplier</th><th className="lo-num">Products</th></tr></thead>
                  <tbody>
                    {restorePreview.suppliers.map((supplier) => (
                      <tr key={supplier.supplier_code}><td>{supplier.supplier_name}</td><td className="lo-num">{supplier.product_count}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="lo-op-settings-actions">
                <button type="button" className="lo-btn" onClick={() => setRestorePreview(null)}>Cancel</button>
                <button type="button" className="lo-btn lo-btn-danger" disabled={restoreBusy} onClick={confirmRestore}>
                  {restoreBusy ? 'Restoring…' : `Restore ${restorePreview.product_count} Product(s)`}
                </button>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
