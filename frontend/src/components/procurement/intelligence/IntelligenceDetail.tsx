import type { PiDetail } from '../../../types/intelligence'
import { num, money, date } from '../../stock/format'

/**
 * The network decision for the focused product, and how it was reached:
 *
 *     network demand (every store's own suggested qty, each already net of that
 *     store's stock)  −  what the warehouse can serve off its shelf (transfer)
 *     =  what the warehouse must PURCHASE
 *
 * plus the commercial terms and each store's position. Nothing is recomputed
 * here — every figure comes from the backend build.
 */
export function IntelligenceDetail({ detail, loading }: { detail: PiDetail | null; loading: boolean }) {
  if (!detail) {
    return (
      <div className="pi-detail">
        <div className="pi-empty" style={{ flexDirection: 'column', gap: 8, color: '#94a3b8', padding: 20, textAlign: 'center' }}>
          <i className="bi bi-hand-index" style={{ fontSize: 26 }} />
          <div style={{ fontWeight: 600 }}>Select a product</div>
          <div style={{ fontSize: 12 }}>Choose a row to see how the network purchase quantity was derived, store by store.</div>
        </div>
      </div>
    )
  }

  const p = detail.product
  const maxScale = Math.max(
    1,
    ...detail.stores.flatMap((s) => [s.suggested_qty ?? 0, s.stock_qty ?? 0]),
  )
  const notInWarehouse = !p.warehouse_product_code

  return (
    <div className="pi-detail">
      <div className="pi-detail__head">
        <div className="pi-detail__name" title={p.product_name ?? undefined}>{p.product_name ?? p.product_code ?? '—'}</div>
        <div className="pi-detail__code">
          {p.supplier_product_code ? `Supplier ${p.supplier_code ?? '—'} · SPC ${p.supplier_product_code}` : `Code ${p.product_code ?? '—'}`}
          {' · '}{p.mapped_store_count} store{p.mapped_store_count === 1 ? '' : 's'}
          {p.confidence != null && <span title={p.match_method ?? undefined}> · {num(p.confidence)}% conf.</span>}
          {loading && <span> · <i className="bi bi-hourglass-split" /> loading…</span>}
        </div>
      </div>

      <div className="pi-detail__body">
        {/* The network decision */}
        <section>
          <div className="pi-kpis">
            <div className="pi-kpi pi-kpi--sug"><b>{num(p.consolidated_suggest_qty)}</b><span>Network Need</span></div>
            <div className="pi-kpi pi-kpi--pur"><b>{num(p.consolidated_purchase_qty)}</b><span>WH Purchase</span></div>
            <div className="pi-kpi pi-kpi--trn"><b>{num(p.transfer_qty)}</b><span>Transfer</span></div>
          </div>
          <div className="pi-formula">
            <span>{num(p.consolidated_suggest_qty)} needed by {p.mapped_store_count} store{p.mapped_store_count === 1 ? '' : 's'}</span>
            <span>− {num(p.warehouse_stock_qty ?? 0)} on the warehouse shelf</span>
            <b>= {num(p.consolidated_purchase_qty)} to buy</b>
          </div>
          {notInWarehouse && (
            <div className="pi-warn">
              <i className="bi bi-exclamation-triangle-fill" /> The warehouse does not stock this product — the network needs it anyway.
            </div>
          )}
        </section>

        {/* Commercial terms */}
        <section>
          <div className="pi-detail__sec-title"><i className="bi bi-cash-coin" /> Commercial Terms</div>
          <div className="pi-terms">
            <div className="pi-term"><span>Purchase Rate</span><b>{money(p.ptr_cost)}</b></div>
            <div className="pi-term"><span>MRP</span><b>{money(p.mrp)}</b></div>
            <div className="pi-term"><span>Last Purchase</span><b>{money(p.last_purchase_rate)}</b></div>
            <div className="pi-term"><span>Margin</span><b>{p.margin != null ? `${num(p.margin)}%` : '—'}</b></div>
            <div className="pi-term"><span>Network Sales</span><b>{num(p.total_sales_qty ?? 0)}</b></div>
            <div className="pi-term"><span>Network Stock</span><b>{num(p.consolidated_stock_qty)}</b></div>
          </div>
        </section>

        {/* Where the demand and the stock actually sit */}
        <section>
          <div className="pi-detail__sec-title"><i className="bi bi-diagram-3" /> Store Positions</div>
          <div className="pi-dist">
            {detail.stores.length === 0 && <div style={{ color: '#94a3b8', fontSize: 12 }}>No store carries this product.</div>}
            {detail.stores.map((s) => {
              const stock = s.stock_qty ?? 0
              const sug = s.suggested_qty ?? 0
              const out = sug > 0 && stock <= 0
              return (
                <div className="pi-dist__row" key={s.cache_store_id}>
                  <span className="pi-dist__code" title={s.store_name ?? undefined}>
                    {s.store_code ?? '—'}
                    {!!s.is_warehouse && <i className="bi bi-house-fill" title="Purchasing warehouse" />}
                  </span>
                  <span className="pi-dist__bar">
                    <span className="pi-dist__bar-stock" style={{ width: `${(stock / maxScale) * 100}%` }} />
                    <span className="pi-dist__bar-sug" style={{ width: `${(sug / maxScale) * 100}%` }} />
                  </span>
                  <span className="pi-dist__nums">
                    <b>{num(sug)}</b> / {num(stock)}
                    {out && <span className="pi-dist__out" title="Selling it, and out of stock"> OUT</span>}
                    {!s.in_vpl && <span title="Stock only — this store's VPL asked for nothing"> · stock only</span>}
                    {s.last_sale_date && <span title="Last sale"> · {date(s.last_sale_date)}</span>}
                  </span>
                </div>
              )
            })}
          </div>
        </section>
      </div>
    </div>
  )
}
