import { useEffect, useState } from 'react'
import type { PiCharts, PiChartSeries } from '../../../types/intelligence'
import { intelligenceService } from '../../../services/intelligenceService'
import { num } from '../../stock/format'

/**
 * One chart per selected store (max six), all on screen at once, never scrolled.
 * Four months per store, one stacked bar per month:
 *
 *     bar  = INVENTORY ADDED   — Purchase (bottom) + Transfer In (top)
 *     overlay = Sales          — what left through the till
 *     tick below the axis      — Transfer Out
 *
 * so the manager reads inventory added against inventory removed at a glance.
 * Every store shares one scale, or a big store's bars would dwarf a small one's
 * and the comparison would lie. Each store is resolved INDEPENDENTLY by product
 * name (as the legacy analyser did): a store's chart never disappears because a
 * mapping edge is missing.
 */

const SALES = '#16a34a'
const PURCHASE = '#2563eb'
const TRANSFER = '#0d9488'

function short(period: string) {
  const [, m] = period.split('-')
  return ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m) - 1] ?? period
}

function StoreChart({
  series,
  max,
  selected,
  onSelect,
}: {
  series: PiChartSeries
  max: number
  selected: boolean
  onSelect: () => void
}) {
  const W = 200
  const H = 86
  const padX = 6
  const padT = 8
  const padB = 16          // month label + transfer-out ticks live here
  const plotW = W - padX * 2
  const plotH = H - padT - padB
  const n = series.points.length || 1
  const slot = plotW / n
  const bw = Math.min(22, slot * 0.5)
  const base = padT + plotH

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`pi-storechart${series.is_warehouse ? ' pi-storechart--wh' : ''}${selected ? ' pi-storechart--sel' : ''}`}
    >
      <div className="pi-storechart__h">
        <b>{series.store_code ?? '—'}{series.is_warehouse && <i className="bi bi-house-fill" />}</b>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="pi-storechart__svg" preserveAspectRatio="none">
        <line x1={padX} y1={base} x2={W - padX} y2={base} stroke="rgba(148,163,184,.4)" strokeWidth={1} />
        {series.points.map((p, i) => {
          const cx = padX + i * slot + slot / 2
          const hPur = (p.purchase_qty / max) * plotH
          const hIn = (p.transfer_in / max) * plotH
          const hSale = (p.sales_qty / max) * plotH
          const hOut = (p.transfer_out / max) * plotH
          const added = p.purchase_qty + p.transfer_in
          return (
            <g key={p.period}>
              {/* Inventory added — purchase at the bottom, transfer in stacked on top */}
              <rect x={cx - bw / 2} y={base - hPur} width={bw} height={hPur} fill={PURCHASE}>
                <title>{`${p.period} · purchased ${num(p.purchase_qty)}`}</title>
              </rect>
              <rect x={cx - bw / 2} y={base - hPur - hIn} width={bw} height={hIn} fill={TRANSFER}>
                <title>{`${p.period} · transferred in ${num(p.transfer_in)}`}</title>
              </rect>
              {/* Inventory removed — sales overlaid in front of what came in */}
              <rect x={cx - bw / 4} y={base - hSale} width={bw / 2} height={hSale} fill={SALES} fillOpacity={0.92}>
                <title>{`${p.period} · sold ${num(p.sales_qty)} · added ${num(added)}`}</title>
              </rect>
              {/* Transfer out — its own indicator below the axis */}
              {p.transfer_out > 0 && (
                <rect x={cx - bw / 2} y={base + 1} width={bw} height={Math.max(1.5, Math.min(4, hOut))} fill={TRANSFER} fillOpacity={0.55}>
                  <title>{`${p.period} · transferred out ${num(p.transfer_out)}`}</title>
                </rect>
              )}
              <text x={cx} y={H - 3} textAnchor="middle" className="pi-chart__lbl">{short(p.period)}</text>
            </g>
          )
        })}
      </svg>
    </button>
  )
}

export function IntelligenceCharts({
  cacheId,
  selectedStoreId,
  onSelectStore,
  months = 4,
}: {
  cacheId: string | null
  selectedStoreId: string | null
  onSelectStore: (storeId: string) => void
  months?: number
}) {
  const [data, setData] = useState<PiCharts | null>(null)

  useEffect(() => {
    if (!cacheId) { setData(null); return }
    let live = true
    intelligenceService.charts(cacheId, months)
      .then((d) => live && setData(d))
      .catch(() => live && setData(null))
    return () => { live = false }
  }, [cacheId, months])

  const series = (data?.series ?? []).slice(0, 6)
  const max = Math.max(
    1,
    ...series.flatMap((s) => s.points.flatMap((p) => [p.purchase_qty + p.transfer_in, p.sales_qty])),
  )

  return (
    <div className="pi-charts">
      <div className="pi-storecharts">
        {series.map((s) => (
          <StoreChart
            key={s.store_id}
            series={s}
            max={max}
            selected={s.store_id === selectedStoreId}
            onSelect={() => onSelectStore(s.store_id)}
          />
        ))}
      </div>
    </div>
  )
}
