import { useEffect, useRef, useState } from 'react'
import type { MovementRow } from '../../types/stock'
import { num } from './format'

interface Series {
  key: keyof Pick<MovementRow, 'pur' | 'sal' | 'tin' | 'tout' | 'adj' | 'stk'>
  label: string
  short: string
  color: string
}

const SERIES: Series[] = [
  { key: 'pur', label: 'Purchase', short: 'PUR', color: '#2563eb' },     // blue
  { key: 'sal', label: 'Sales', short: 'SAL', color: '#16a34a' },        // green
  { key: 'tin', label: 'Transfer In', short: 'TIN', color: '#eab308' },  // yellow
  { key: 'tout', label: 'Transfer Out', short: 'TOUT', color: '#be185d' },// dark pink
  { key: 'adj', label: 'Adjustment', short: 'ADJ', color: '#7c3aed' },   // purple
  { key: 'stk', label: 'Stock', short: 'STK', color: '#dc2626' },        // red
]

/** Measures a container and reports its pixel size, updating on resize. */
function useElementSize() {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 640, h: 240 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect
      setSize({ w: Math.max(320, cr.width), h: Math.max(160, cr.height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, size] as const
}

/** Responsive grouped bar chart. Always shows the last 4 months returned by the
 *  API (months with no data render as blank), fills 100% of the panel, reserves
 *  the top 10% for value labels, and keeps the hover-month label as an overlay
 *  so no vertical space is wasted. */
/** `flat` (Purchase Manager only): render every month at equal brightness with no
 *  "current month" highlight, and drop the top overlay tag — the readout row below
 *  the chart is the single-row legend. The Stock module keeps the default look. */
export function MovementChart({ rows, flat = false }: { rows: MovementRow[]; flat?: boolean }) {
  const [hover, setHover] = useState<number | null>(null)
  const [tip, setTip] = useState({ x: 0, y: 0 })
  const [plotRef, { w: W, h: H }] = useElementSize()

  // Show every month the API returns (the last 4 months, empty ones included).
  const data = rows
  const n = data.length || 1
  const focus = hover ?? data.length - 1

  const padL = 46
  const padR = 14
  const padT = 6
  const padB = 26
  const plotW = Math.max(40, W - padL - padR)
  const plotH = Math.max(40, H - padT - padB)
  const baseY = padT + plotH
  const labelBand = plotH * 0.1
  const barAreaH = plotH - labelBand
  const barTopLimit = padT + labelBand

  const max = Math.max(
    1,
    ...data.flatMap((row) => SERIES.map((s) => Math.abs(Number(row[s.key]) || 0))),
  )

  const groupW = plotW / n
  const groupGap = Math.min(groupW * 0.3, 80)
  const innerW = Math.max(SERIES.length * 5, groupW - groupGap)
  const barGap = Math.max(2, innerW * 0.03)
  const barW = (innerW - barGap * (SERIES.length - 1)) / SERIES.length

  return (
    <div className="sa-chart">
      <div
        className="sa-chart__plot"
        ref={plotRef}
        onMouseMove={(e) => setTip({ x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY })}
        onMouseLeave={() => setHover(null)}
      >
        {!flat && (
          <span className="sa-chart__tag">
            <strong>{data[focus]?.period ?? ''}</strong>
            <i className="bi bi-hand-index-thumb" aria-hidden="true" /> hover a month
          </span>
        )}
        <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Monthly movement chart" className="sa-chart__svg" preserveAspectRatio="none">
          <defs>
            <linearGradient id="sa-chart-glass" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(255,255,255,0.55)" />
              <stop offset="100%" stopColor="rgba(255,255,255,0.05)" />
            </linearGradient>
          </defs>
          <rect x={padL - 8} y={barTopLimit - 4} width={plotW + 20} height={barAreaH + 8} rx={12} fill="url(#sa-chart-glass)" />

          {[0, 0.25, 0.5, 0.75, 1].map((t) => {
            const y = baseY - t * barAreaH
            return (
              <g key={t}>
                <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="rgba(100,116,139,0.18)" strokeWidth={1} />
                <text x={padL - 8} y={y + 4} textAnchor="end" className="sa-chart__axis">{num(Math.round(max * t))}</text>
              </g>
            )
          })}

          {data.map((row, i) => {
            const groupX = padL + i * groupW + (groupW - innerW) / 2
            const focused = i === focus
            return (
              <g key={row.period ?? i}>
                {SERIES.map((s, j) => {
                  const value = Number(row[s.key]) || 0
                  const h = (Math.abs(value) / max) * barAreaH
                  const x = groupX + j * (barW + barGap)
                  const cx = x + barW / 2
                  const top = baseY - h
                  const labelY = Math.max(barTopLimit - 2, top - 4)
                  return (
                    <g key={s.key} opacity={1}>
                      <rect x={x} y={top} width={Math.max(3, barW)} height={h} rx={3} fill={s.color}>
                        <title>{`${row.period ?? ''} · ${s.label}: ${num(value)}`}</title>
                      </rect>
                      <text x={cx} y={labelY} textAnchor="middle" className="sa-chart__barval" fill={s.color}>
                        {num(value)}
                      </text>
                    </g>
                  )
                })}
                <rect
                  x={groupX - barGap}
                  y={barTopLimit}
                  width={innerW + barGap * 2}
                  height={barAreaH}
                  fill="transparent"
                  rx={8}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
                <text x={groupX + innerW / 2} y={H - 7} textAnchor="middle" className={`sa-chart__month${focused && !flat ? ' sa-chart__month--on' : ''}`}>
                  {row.period ?? ''}
                </text>
              </g>
            )
          })}
        </svg>

        {/* Hover tooltip — the month + every series value (Purchase, Sales,
            Transfer In/Out, Adjustment, Stock). Follows the cursor. */}
        {hover != null && data[hover] && (
          <div
            className="sa-chart__tip"
            style={{
              left: Math.min(Math.max(tip.x + 12, 4), Math.max(4, W - 168)),
              top: Math.max(tip.y - 8, 4),
            }}
            role="tooltip"
          >
            <div className="sa-chart__tip-head">{data[hover].period ?? ''}</div>
            {SERIES.map((s) => (
              <div className="sa-chart__tip-row" key={s.key}>
                <span className="sa-chart__tip-key">
                  <span className="sa-chart__swatch" style={{ background: s.color }} />
                  {s.label}
                </span>
                <span className="sa-chart__tip-val">{num(Number(data[hover][s.key]) || 0)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="sa-chart__readout">
        {SERIES.map((s) => (
          <div className="sa-chart__metric" key={s.key} title={s.label}>
            <span className="sa-chart__metric-val" style={{ color: s.color }}>{num(Number(data[focus]?.[s.key]) || 0)}</span>
            <span className="sa-chart__metric-label">
              <span className="sa-chart__swatch" style={{ background: s.color }} />
              {s.short}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

