import { useCallback, useEffect, useState } from 'react'
import type { ProductContext, ProductDetails } from '../../types/stock'
import type { DecisionDetail, WorkspaceItem } from '../../types/procurement'
import { stockService } from '../../services/stockService'
import { procurementService } from '../../services/procurementService'
import { BatchPanel, PurchasePanel, SalesPanel } from '../stock/DetailPanels'
import type { DrawerTab } from './DetailColumn'
import { money, num, date } from '../stock/format'
import '../stock/stock-ui.css'

const TABS: { key: DrawerTab; label: string; icon: string }[] = [
  { key: 'info', label: 'Info', icon: 'bi-info-circle' },
  { key: 'history', label: 'History', icon: 'bi-clock-history' },
  { key: 'decision', label: 'Decision', icon: 'bi-lightbulb' },
]

/** The single product side drawer, merging Info + History + Decision into one
 *  tabbed surface. Reuses the Stock Availability product details, batch, sales
 *  and purchase panels; layers the procurement decision reason on top. */
export function ProductInfoDialog({
  tenantId,
  item,
  initialTab = 'info',
  onClose,
}: {
  tenantId: string
  item: WorkspaceItem
  initialTab?: DrawerTab
  onClose: () => void
}) {
  // The drawer remounts each time it is opened (its backdrop blocks the panel
  // behind it), so the initial tab from the triggering action is authoritative.
  const [tab, setTab] = useState<DrawerTab>(initialTab)

  const storeId = item.store_id ?? ''
  const productCode = item.product_code ?? ''
  const ctx: ProductContext = {
    tenantId,
    storeId,
    storeName: null,
    storeCode: null,
    productCode,
    productName: item.product_name,
    stock: item.current_stock_qty ?? 0,
  }

  const [details, setDetails] = useState<ProductDetails | null>(null)
  const [decision, setDecision] = useState<DecisionDetail | null>(null)

  const load = useCallback(() => {
    if (storeId && productCode) {
      stockService.productDetails(tenantId, storeId, productCode).then(setDetails).catch(() => setDetails(null))
    }
    procurementService.decision(tenantId, item.order_item_id).then(setDecision).catch(() => setDecision(null))
  }, [tenantId, storeId, productCode, item.order_item_id])
  useEffect(load, [load])

  const facts: { label: string; value: string }[] = [
    { label: 'MRP', value: money(details?.mrp) },
    { label: 'Sale Unit', value: details?.sale_unit ?? '—' },
    { label: 'Packing', value: details?.packing != null ? num(details.packing) : '—' },
    { label: 'Sub-Location', value: details?.sublocation ?? '—' },
    { label: 'In Stock', value: num(details?.total_stock ?? item.current_stock_qty ?? 0) },
    { label: 'Movement', value: item.movement_class ?? '—' },
    { label: 'Last Sale', value: date(details?.last_sale) },
    { label: 'Last Purchase', value: date(details?.last_purchase) },
  ]

  const hasCtx = Boolean(storeId && productCode)

  return (
    <>
      <div className="pm-drawer__backdrop" onClick={onClose} />
      <aside className="pm-drawer" role="dialog" aria-label="Product detail">
        <header className="pm-drawer__head">
          <div>
            <h5 className="mb-0">{item.product_name ?? item.product_code}</h5>
            <div className="small text-muted">{item.product_code}</div>
          </div>
          <button className="btn-close" aria-label="Close" onClick={onClose} />
        </header>

        <nav className="pm-drawer__tabs" role="tablist" aria-label="Product detail tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={`pm-drawer__tab${tab === t.key ? ' pm-drawer__tab--on' : ''}`}
              onClick={() => setTab(t.key)}
            >
              <i className={`bi ${t.icon}`} /> {t.label}
            </button>
          ))}
        </nav>

        <div className="pm-drawer__body">
          {tab === 'info' && (
            <>
              <section className="pm-info-facts">
                {facts.map((f) => (
                  <div className="pm-info-facts__cell" key={f.label}>
                    <span className="pm-info-facts__lbl">{f.label}</span>
                    <span className="pm-info-facts__val">{f.value}</span>
                  </div>
                ))}
              </section>

              {item.item_status === 'skipped' && (
                <section className="pm-info-reason">
                  <h6 className="pm-info-reason__title">
                    <i className="bi bi-slash-circle" aria-hidden="true" /> Skipped
                  </h6>
                  <div className="pm-info-reason__code">{item.skip_reason ?? 'Manual Decision'}</div>
                </section>
              )}

              {hasCtx && <section className="pm-info-hist"><BatchPanel ctx={ctx} /></section>}
            </>
          )}

          {tab === 'history' && hasCtx && (
            <>
              <section className="pm-info-hist"><PurchasePanel ctx={ctx} /></section>
              <section className="pm-info-hist"><SalesPanel ctx={ctx} /></section>
            </>
          )}

          {tab === 'decision' && (
            <>
              {decision ? (
                <section className="pm-info-reason">
                  <h6 className="pm-info-reason__title">
                    <i className="bi bi-lightbulb" aria-hidden="true" /> Decision Reason
                  </h6>
                  <div className="pm-info-reason__code">{decision.reason_code ?? '—'}</div>
                  {decision.reason_text && <p className="small mb-2">{decision.reason_text}</p>}

                  <div className="pm-info-facts pm-info-facts--decision">
                    <Cell label="Suggested" value={num(decision.suggested_qty)} />
                    <Cell label="Final Qty" value={num(decision.final_qty)} />
                    <Cell label="Cover Days" value={decision.days_cover != null ? `${decision.days_cover.toFixed(1)}` : '—'} />
                    <Cell label="Target Days" value={decision.target_days != null ? `${decision.target_days}` : '—'} />
                    <Cell label="Avg / Day" value={decision.avg_daily_sales != null ? decision.avg_daily_sales.toFixed(2) : '—'} />
                    <Cell label="Window Sales" value={num(decision.window_sales_qty)} />
                  </div>

                  {decision.business_rules_applied?.length > 0 && (
                    <ul className="pm-info-reason__rules">
                      {decision.business_rules_applied.map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  )}
                </section>
              ) : (
                <div className="pm-queue__hint">No decision detail available for this product.</div>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  )
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="pm-info-facts__cell">
      <span className="pm-info-facts__lbl">{label}</span>
      <span className="pm-info-facts__val">{value}</span>
    </div>
  )
}
