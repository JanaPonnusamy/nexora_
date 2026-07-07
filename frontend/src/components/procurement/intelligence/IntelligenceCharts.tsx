import { useEffect, useRef, useState } from 'react'
import type { PiDetail } from '../../../types/intelligence'
import type { MovementRow, PurchaseRow } from '../../../types/stock'
import { num } from '../../stock/format'

/** Measures a container in pixels (charts draw in real coordinates so text is
 *  never distorted). */
function useSize() {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 220, h: 120 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect
      setSize({ w: Math.max(80, cr.width), h: Math.max(60, cr.height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, size] as const
}

type Point = { label: string; value: number }

/** Area + line trend over an ordered series. */
function MiniLine({ points, color }: { points: Point[]; color: string }) {
  const [ref, { w, h }] = useSize()
  if (points.length === 0) return <div ref={ref} className="pi-chart__empty">No data</div>
  const padL = 26, padB = 14, padT = 6, padR = 6
  const plotW = Math.max(10, w - padL - padR)
  const plotH = Math.max(10, h - padT - padB)
  const max = Math.max(1, ...points.map((p) => p.value))
  const n = points.length
  const x = (i: number) => padL + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW)
  const y = (v: number) => padT + plotH - (v / max) * plotH
  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const area = `${line} L${x(n - 1).toFixed(1)},${(padT + plotH).toFixed(1)} L${x(0).toFixed(1)},${(padT + plotH).toFixed(1)} Z`
  return (
    <div ref={ref} className="pi-chart__plot">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <text x={2} y={padT + 8} className="pi-chart__axis">{num(max)}</text>
        <line x1={padL} y1={padT + plotH} x2={w - padR} y2={padT + plotH} stroke="rgba(148,163,184,.3)" strokeWidth={1} />
        <path d={area} fill={color} opacity={0.13} />
        <path d={line} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value)} r={1.8} fill={color} />
        ))}
        {points.map((p, i) => (i % Math.ceil(n / 4 || 1) === 0 || i === n - 1) ? (
          <text key={`l${i}`} x={x(i)} y={h - 3} textAnchor="middle" className="pi-chart__lbl">{p.label}</text>
        ) : null)}
      </svg>
    </div>
  )
}

/** Single-series bars (one bar per store). */
function MiniBars({ points, color }: { points: Point[]; color: string }) {
  const [ref, { w, h }] = useSize()
  if (points.length === 0) return <div ref={ref} className="pi-chart__empty">No data</div>
  const padL = 26, padB = 14, padT = 6, padR = 6
  const plotW = Math.max(10, w - padL - padR)
  const plotH = Math.max(10, h - padT - padB)
  const max = Math.max(1, ...points.map((p) => p.value))
  const n = points.length
  const bw = (plotW / n) * 0.6
  const gap = (plotW / n) * 0.4
  return (
    <div ref={ref} className="pi-chart__plot">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <text x={2} y={padT + 8} className="pi-chart__axis">{num(max)}</text>
        <line x1={padL} y1={padT + plotH} x2={w - padR} y2={padT + plotH} stroke="rgba(148,163,184,.3)" strokeWidth={1} />
        {points.map((p, i) => {
          const bh = (p.value / max) * plotH
          const x = padL + i * (bw + gap) + gap / 2
          return (
            <g key={i}>
              <rect x={x} y={padT + plotH - bh} width={bw} height={bh} rx={2} fill={color}>
                <title>{`${p.label}: ${num(p.value)}`}</title>
              </rect>
              <text x={x + bw / 2} y={padT + plotH - bh - 2} textAnchor="middle" className="pi-chart__lbl">{num(p.value)}</text>
              <text x={x + bw / 2} y={h - 3} textAnchor="middle" className="pi-chart__lbl">{p.label}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/** Grouped bars — Suggested vs Current Stock per store (Store Comparison). */
function MiniGroupedBars({ groups }: { groups: { label: string; a: number; b: number }[] }) {
  const [ref, { w, h }] = useSize()
  if (groups.length === 0) return <div ref={ref} className="pi-chart__empty">No data</div>
  const padL = 26, padB = 14, padT = 6, padR = 6
  const plotW = Math.max(10, w - padL - padR)
  const plotH = Math.max(10, h - padT - padB)
  const max = Math.max(1, ...groups.flatMap((g) => [g.a, g.b]))
  const n = groups.length
  const gw = plotW / n
  const bw = Math.min(14, (gw * 0.7) / 2)
  return (
    <div ref={ref} className="pi-chart__plot">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <text x={2} y={padT + 8} className="pi-chart__axis">{num(max)}</text>
        <line x1={padL} y1={padT + plotH} x2={w - padR} y2={padT + plotH} stroke="rgba(148,163,184,.3)" strokeWidth={1} />
        {groups.map((g, i) => {
          const cx = padL + i * gw + gw / 2
          const ha = (g.a / max) * plotH
          const hb = (g.b / max) * plotH
          return (
            <g key={i}>
              <rect x={cx - bw - 1} y={padT + plotH - ha} width={bw} height={ha} rx={2} fill="#4338ca"><title>{`${g.label} Suggested: ${num(g.a)}`}</title></rect>
              <rect x={cx + 1} y={padT + plotH - hb} width={bw} height={hb} rx={2} fill="#93c5fd"><title>{`${g.label} Stock: ${num(g.b)}`}</title></rect>
              <text x={cx} y={h - 3} textAnchor="middle" className="pi-chart__lbl">{g.label}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function Panel({ title, right, children }: { title: string; right?: string; children: React.ReactNode }) {
  return (
    <div className="pi-chart">
      <div className="pi-chart__h"><span>{title}</span>{right != null && <em>{right}</em>}</div>
      {children}
    </div>
  )
}

/**
 * The six intelligence charts. Movement-based trends (Sales / Purchase / Stock)
 * read the anchor store's monthly movement; Price Trend reads its purchase
 * history; Store Comparison and Non-Moving Trend read the per-store cache
 * distribution. All fed by the backend cache / stock reads — never recomputed.
 */
export function IntelligenceCharts({
  detail,
  movement,
  purchases,
  loading,
}: {
  detail: PiDetail | null
  movement: MovementRow[] | null
  purchases: PurchaseRow[] | null
  loading: boolean
}) {
  if (!detail) {
    return (
      <div className="pi-charts">
        <div className="pi-charts__title"><i className="bi bi-bar-chart-line" /> Analytics</div>
        <div className="pi-chart__empty" style={{ flex: 1 }}>Select a product to see its trends and cross-store comparison.</div>
      </div>
    )
  }

  const salesPts: Point[] = (movement ?? []).map((m) => ({ label: m.period ?? '', value: m.sal ?? 0 }))
  const purPts: Point[] = (movement ?? []).map((m) => ({ label: m.period ?? '', value: m.pur ?? 0 }))
  const stkPts: Point[] = (movement ?? []).map((m) => ({ label: m.period ?? '', value: m.stk ?? 0 }))
  const pricePts: Point[] = [...(purchases ?? [])]
    .filter((p) => (p.ptr ?? 0) > 0)
    .reverse()
    .slice(-10)
    .map((p, i) => ({ label: String(i + 1), value: p.ptr ?? 0 }))
  const dist = [...detail.stores].sort((a, b) => (a.store_code ?? '').localeCompare(b.store_code ?? ''))
  const cmp = dist.map((s) => ({ label: s.store_code ?? '—', a: s.suggested_qty ?? 0, b: s.stock_qty ?? 0 }))
  const nmv: Point[] = dist.map((s) => ({ label: s.store_code ?? '—', value: s.non_moving_days ?? 0 }))

  return (
    <div className="pi-charts">
      <div className="pi-charts__title">
        <i className="bi bi-bar-chart-line" /> Analytics — {detail.product.product_name ?? detail.product.product_code}
        <span className="pi-legend" style={{ marginLeft: 'auto' }}>
          <span><i style={{ background: '#4338ca' }} />Suggested</span>
          <span><i style={{ background: '#93c5fd' }} />Stock</span>
        </span>
      </div>
      <div className="pi-charts__grid">
        <Panel title="Sales Trend" right={loading ? '' : num(salesPts.reduce((s, p) => s + p.value, 0))}>
          <MiniLine points={salesPts} color="#16a34a" />
        </Panel>
        <Panel title="Purchase Trend" right={loading ? '' : num(purPts.reduce((s, p) => s + p.value, 0))}>
          <MiniLine points={purPts} color="#2563eb" />
        </Panel>
        <Panel title="Store Comparison">
          <MiniGroupedBars groups={cmp} />
        </Panel>
        <Panel title="Stock Trend">
          <MiniLine points={stkPts} color="#dc2626" />
        </Panel>
        <Panel title="Price Trend" right={pricePts.length ? `₹${num(pricePts[pricePts.length - 1].value)}` : ''}>
          <MiniLine points={pricePts} color="#7c3aed" />
        </Panel>
        <Panel title="Non-Moving Trend">
          <MiniBars points={nmv} color="#b45309" />
        </Panel>
      </div>
    </div>
  )
}
