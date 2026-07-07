import type { PiDetail } from '../../../types/intelligence'
import { num, money, date } from '../../stock/format'

/**
 * Right-hand detail panel for the focused product: consolidated KPIs, commercial
 * terms (Purchase Rate / Margin / Last Purchase / MRP / Scheme) and the full
 * cross-store Stock Distribution (Suggested vs Current Stock per store). All
 * values come from the backend cache — nothing is recomputed here.
 */
export function IntelligenceDetail({ detail, loading }: { detail: PiDetail | null; loading: boolean }) {
  if (!detail) {
    return (
      <div className="pi-detail">
        <div className="pi-empty" style={{ flexDirection: 'column', gap: 8, color: '#94a3b8', padding: 20, textAlign: 'center' }}>
          <i className="bi bi-hand-index" style={{ fontSize: 26 }} />
          <div style={{ fontWeight: 600 }}>Select a product</div>
          <div style={{ fontSize: 12 }}>Choose a row to see supplier terms, margin, last purchase and the cross-store stock distribution.</div>
        </div>
      </div>
    )
  }

  const p = detail.product
  const maxScale = Math.max(
    1,
    ...detail.stores.flatMap((s) => [s.suggested_qty ?? 0, s.stock_qty ?? 0]),
  )

  return (
    <div className="pi-detail">
      <div className="pi-detail__head">
        <div className="pi-detail__name" title={p.product_name ?? undefined}>{p.product_name ?? p.product_code ?? '—'}</div>
        <div className="pi-detail__code">
          Code {p.product_code ?? '—'} · mapped in {p.mapped_store_count} store{p.mapped_store_count === 1 ? '' : 's'}
          {loading && <span> · <i className="bi bi-hourglass-split" /> loading…</span>}
        </div>
      </div>

      <div className="pi-detail__body">
        {/* Consolidated KPIs */}
        <section>
          <div className="pi-kpis">
            <div className="pi-kpi pi-kpi--sug"><b>{num(p.consolidated_suggest_qty)}</b><span>Suggested</span></div>
            <div className="pi-kpi pi-kpi--pur"><b>{num(p.consolidated_purchase_qty)}</b><span>Purchase</span></div>
            <div className="pi-kpi pi-kpi--trn"><b>{num(p.transfer_qty)}</b><span>Transfer</span></div>
          </div>
        </section>

        {/* Commercial terms */}
        <section>
          <div className="pi-detail__sec-title"><i className="bi bi-cash-coin" /> Commercial Terms</div>
          <div className="pi-terms">
            <div className="pi-term"><span>Purchase Rate</span><b>{money(p.ptr_cost)}</b></div>
            <div className="pi-term"><span>MRP</span><b>{money(p.mrp)}</b></div>
            <div className="pi-term"><span>Last Purchase</span><b>{money(p.last_purchase_rate)}</b></div>
            <div className="pi-term"><span>Margin</span><b>{p.margin != null ? `${num(p.margin)}%` : '—'}</b></div>
            <div className="pi-term"><span>Total Stock</span><b>{num(p.consolidated_stock_qty)}</b></div>
            <div className="pi-term"><span>Scheme</span><b>{p.offer_text ?? '—'}</b></div>
          </div>
        </section>

        {/* Stock distribution across stores */}
        <section>
          <div className="pi-detail__sec-title"><i className="bi bi-diagram-3" /> Stock Distribution</div>
          <div className="pi-dist">
            {detail.stores.length === 0 && <div style={{ color: '#94a3b8', fontSize: 12 }}>No stores mapped.</div>}
            {detail.stores.map((s) => {
              const stock = s.stock_qty ?? 0
              const sug = s.suggested_qty ?? 0
              return (
                <div className="pi-dist__row" key={s.cache_store_id}>
                  <span className="pi-dist__code" title={s.store_name ?? undefined}>{s.store_code ?? '—'}</span>
                  <span className="pi-dist__bar">
                    <span className="pi-dist__bar-stock" style={{ width: `${(stock / maxScale) * 100}%` }} />
                    <span className="pi-dist__bar-sug" style={{ width: `${(sug / maxScale) * 100}%` }} />
                  </span>
                  <span className="pi-dist__nums">
                    <b>{num(sug)}</b> / {num(stock)}
                    {s.non_moving_days != null && <span title="Non-moving days"> · {s.non_moving_days}d</span>}
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
