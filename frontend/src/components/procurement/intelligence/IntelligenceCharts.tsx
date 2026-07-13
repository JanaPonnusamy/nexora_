import { useEffect, useState } from 'react'
import type { PiCharts, PiChartSeries } from '../../../types/intelligence'
import { intelligenceService } from '../../../services/intelligenceService'
import { num } from '../../stock/format'

/**
 * Every store's transaction chart for the selected product — ALL of them on
 * screen at the same time, side by side, with no scrolling. The panel is a CSS
 * grid that lays the stores out to fill the space it is given, so 5-6 stores read
 * as one comparison rather than a list you have to scroll through.
 *
 * Each store is resolved INDEPENDENTLY, by product NAME, exactly as the legacy
 * VB.NET analyser did when it opened each store's own database. Stores are not
 * inter-linked here: a store's chart never disappears because a mapping edge is
 * missing. Every chart shares one month axis so the bars are comparable.
 */

const SALES = '#16a34a'
const PURCHASE = '#2563eb'

function short(period: string) {
  // "2026-04" -> "Apr"
  const [, m] = period.split('-')
  return ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m) - 1] ?? period
}

/** One store: sales vs purchase bars per month, drawn in a fixed viewBox that
 *  scales to whatever cell size the grid gives it (never overflows). */
function StoreChart({ series, max }: { series: PiChartSeries; max: number }) {
  const W = 200
  const H = 92
  const padL = 4
  const padB = 14
  const padT = 12
  const plotW = W - padL * 2
  const plotH = H - padT - padB
  const n = series.points.length || 1
  const slot = plotW / n
  const bw = Math.min(16, (slot * 0.62) / 2)
  const scale = Math.max(1, max)

  const total = series.points.reduce((s, p) => s + p.sales_qty, 0)

  return (
    <div className={`pi-storechart${series.is_warehouse ? ' pi-storechart--wh' : ''}`}>
      <div className="pi-storechart__h">
        <b>
          {series.store_code ?? '—'}
          {series.is_warehouse && <i className="bi bi-house-fill" title="Purchasing warehouse" />}
        </b>
        <em title={series.found ? (series.product_name ?? '') : 'This store has no product with that name'}>
          {series.found ? `sold ${num(total)}` : 'not found'}
        </em>
      </div>
      {!series.found ? (
        <div className="pi-storechart__empty">No product by this name</div>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="pi-storechart__svg" preserveAspectRatio="xMidYMid meet">
          <line x1={padL} y1={padT + plotH} x2={W - padL} y2={padT + plotH} stroke="rgba(148,163,184,.35)" strokeWidth={1} />
          {series.points.map((p, i) => {
            const cx = padL + i * slot + slot / 2
            const hs = (p.sales_qty / scale) * plotH
            const hp = (p.purchase_qty / scale) * plotH
            return (
              <g key={p.period}>
                <rect x={cx - bw - 1} y={padT + plotH - hs} width={bw} height={hs} rx={2} fill={SALES}>
                  <title>{`${p.period} · sold ${num(p.sales_qty)}`}</title>
                </rect>
                <rect x={cx + 1} y={padT + plotH - hp} width={bw} height={hp} rx={2} fill={PURCHASE}>
                  <title>{`${p.period} · purchased ${num(p.purchase_qty)}`}</title>
                </rect>
                {p.sales_qty > 0 && (
                  <text x={cx - bw / 2 - 1} y={padT + plotH - hs - 2} textAnchor="middle" className="pi-chart__lbl">
                    {num(p.sales_qty)}
                  </text>
                )}
                <text x={cx} y={H - 3} textAnchor="middle" className="pi-chart__lbl">{short(p.period)}</text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

export function IntelligenceCharts({
  cacheId,
  productName,
  months = 4,
}: {
  cacheId: string | null
  productName: string | null
  months?: number
}) {
  const [data, setData] = useState<PiCharts | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!cacheId) { setData(null); return }
    let live = true
    setLoading(true)
    setData(null)
    intelligenceService
      .charts(cacheId, months)
      .then((d) => live && setData(d))
      .catch(() => live && setData(null))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [cacheId, months])

  if (!cacheId) {
    return (
      <div className="pi-charts">
        <div className="pi-charts__title"><i className="bi bi-bar-chart-line" /> Store Transactions</div>
        <div className="pi-chart__empty" style={{ flex: 1 }}>Select a product to see every store's last {months} months.</div>
      </div>
    )
  }

  // One shared scale across every store, or a big store's bars would dwarf a
  // small store's and the comparison would lie.
  const max = Math.max(
    1,
    ...(data?.series ?? []).flatMap((s) => s.points.flatMap((p) => [p.sales_qty, p.purchase_qty])),
  )

  return (
    <div className="pi-charts">
      <div className="pi-charts__title">
        <i className="bi bi-bar-chart-line" /> Store Transactions — last {months} months
        <span className="pi-legend" style={{ marginLeft: 'auto' }}>
          <span><i style={{ background: SALES }} />Sold</span>
          <span><i style={{ background: PURCHASE }} />Purchased</span>
        </span>
      </div>
      {loading ? (
        <div className="pi-chart__empty" style={{ flex: 1 }}><i className="bi bi-hourglass-split" /> Loading store transactions…</div>
      ) : !data || data.series.length === 0 ? (
        <div className="pi-chart__empty" style={{ flex: 1 }}>No store data for {productName ?? 'this product'}.</div>
      ) : (
        <div className="pi-storecharts">
          {data.series.map((s) => (
            <StoreChart key={s.store_id} series={s} max={max} />
          ))}
        </div>
      )}
    </div>
  )
}
