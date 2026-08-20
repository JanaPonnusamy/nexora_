import type { PiDetail, PiHistory } from '../../../types/intelligence'
import { date, money, num } from '../../stock/format'

/**
 * The network decision for the focused product, and how it was reached:
 *
 *     network need (every store's own suggested qty, each already net of that
 *     store's stock)  −  what the warehouse can serve off its shelf (transfer)
 *     =  what the warehouse must PURCHASE
 *
 * Nothing is recomputed here — every figure comes from the build cache. Store
 * Availability doubles as the store selector: picking a store loads THAT store's
 * purchase and sales history (and nothing else's).
 */

function recommendation(p: PiDetail['product']): string {
  if (p.consolidated_suggest_qty <= 0) return 'No store needs this right now — do not buy.'
  if (p.consolidated_purchase_qty <= 0) {
    return `Do not buy. Transfer ${num(p.transfer_qty)} from the warehouse shelf to cover the network.`
  }
  const out = p.stockout_store_count ?? 0
  const urgency = out > 0
    ? `${out} store${out === 1 ? ' is' : 's are'} selling it with zero stock — buy first.`
    : 'Buy for the network.'
  const xfer = p.transfer_qty > 0 ? ` Transfer ${num(p.transfer_qty)} from the shelf first.` : ''
  return `Purchase ${num(p.consolidated_purchase_qty)}. ${urgency}${xfer}`
}

export function IntelligenceDetail({
  detail,
  selectedStoreId,
  onSelectStore,
  history,
  historyLoading,
}: {
  detail: PiDetail | null
  selectedStoreId: string | null
  onSelectStore: (storeId: string) => void
  history: PiHistory | null
  historyLoading: boolean
}) {
  if (!detail) return <div className="pi-detail" />

  const p = detail.product
  const scale = Math.max(1, ...detail.stores.flatMap((s) => [s.suggested_qty ?? 0, s.stock_qty ?? 0]))
  const store = detail.stores.find((s) => s.store_id === selectedStoreId)

  return (
    <div className="pi-detail">
      <div className="pi-detail__head">
        <div className="pi-detail__name" title={p.product_name ?? undefined}>
          {p.product_name ?? p.product_code ?? '—'}
        </div>
        <div className="pi-detail__code">
          {p.supplier_product_code
            ? `${p.supplier_code ?? '—'} · ${p.supplier_product_code}`
            : `Code ${p.product_code ?? '—'}`}
          {' · '}{p.mapped_store_count} store{p.mapped_store_count === 1 ? '' : 's'}
          {p.confidence != null && <span title={p.match_method ?? undefined}> · {num(p.confidence)}% conf</span>}
        </div>
      </div>

      <div className="pi-detail__body">
        <div className="pi-kpis">
          <div className="pi-kpi pi-kpi--need"><b>{num(p.consolidated_suggest_qty)}</b><span>Network Need</span></div>
          <div className="pi-kpi pi-kpi--buy"><b>{num(p.consolidated_purchase_qty)}</b><span>WH Purchase</span></div>
          <div className="pi-kpi pi-kpi--xfer"><b>{num(p.transfer_qty)}</b><span>Transfer</span></div>
        </div>

        <div className="pi-rec">{recommendation(p)}</div>

        <div className="pi-terms">
          <div className="pi-term"><span>PTR</span><b>{money(p.ptr_cost)}</b></div>
          <div className="pi-term"><span>MRP</span><b>{money(p.mrp)}</b></div>
          <div className="pi-term"><span>Last Purchase</span><b>{money(p.last_purchase_rate)}</b></div>
          <div className="pi-term"><span>Margin</span><b>{p.margin != null ? `${num(p.margin)}%` : '—'}</b></div>
          <div className="pi-term"><span>Network Sales</span><b>{num(p.total_sales_qty ?? 0)}</b></div>
          <div className="pi-term"><span>Network Stock</span><b>{num(p.consolidated_stock_qty)}</b></div>
        </div>

        <div className="pi-sec">Store Availability</div>
        <div className="pi-dist">
          {detail.stores.map((s) => {
            const stock = s.stock_qty ?? 0
            const sug = s.suggested_qty ?? 0
            return (
              <button
                type="button"
                key={s.cache_store_id}
                className={`pi-dist__row${s.store_id === selectedStoreId ? ' pi-dist__row--sel' : ''}`}
                onClick={() => onSelectStore(s.store_id)}
                title={s.store_name ?? undefined}
              >
                <span className="pi-dist__code">
                  {s.store_code ?? '—'}
                  {!!s.is_warehouse && <i className="bi bi-house-fill" />}
                </span>
                <span className="pi-dist__bar">
                  <span className="pi-dist__bar-stock" style={{ width: `${(stock / scale) * 100}%` }} />
                  <span className="pi-dist__bar-sug" style={{ width: `${(sug / scale) * 100}%` }} />
                </span>
                <span className="pi-dist__nums">
                  <b>{num(sug)}</b>/{num(stock)}
                  {sug > 0 && stock <= 0 && <em className="pi-dist__out">OUT</em>}
                </span>
              </button>
            )
          })}
        </div>

        {/* History for the SELECTED store only — never every store at once. */}
        {store && (
          <>
            <div className="pi-sec">
              {store.store_code ?? 'Store'} · Purchase &amp; Sales
              {historyLoading && <i className="bi bi-hourglass-split" />}
            </div>
            <div className="pi-hist">
              <table>
                <thead><tr><th colSpan={3}>Purchase History</th></tr></thead>
                <tbody>
                  {(history?.purchase_history ?? []).slice(0, 5).map((r, i) => (
                    <tr key={i}>
                      <td>{date(r.date)}</td>
                      <td className="pi-num">{num(r.qty)}</td>
                      <td className="pi-num">{money(r.ptr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <table>
                <thead><tr><th colSpan={3}>Sales History</th></tr></thead>
                <tbody>
                  {(history?.sales_history ?? []).slice(0, 5).map((r, i) => (
                    <tr key={i}>
                      <td>{date(r.date)}</td>
                      <td>{r.bill_no ?? '—'}</td>
                      <td className="pi-num">{num(r.qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
