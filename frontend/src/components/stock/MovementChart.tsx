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
  { key: 'pur',  label: 'Purchase',      short: 'PUR',  color: '#3b82f6' },  // blue-500
  { key: 'sal',  label: 'Sales',         short: 'SAL',  color: '#22c55e' },  // green-500
  { key: 'tin',  label: 'Transfer In',   short: 'TIN',  color: '#f59e0b' },  // amber-500
  { key: 'tout', label: 'Transfer Out',  short: 'TOUT', color: '#f43f5e' },  // rose-500
  { key: 'adj',  label: 'Adjustment',    short: 'ADJ',  color: '#a855f7' },  // purple-500
  { key: 'stk',  label: 'Stock',         short: 'STK',  color: '#ef4444' },  // red-500
]

function useElementSize() {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 640, h: 260 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect
      setSize({ w: Math.max(300, cr.width), h: Math.max(160, cr.height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, size] as const
}

export function MovementChart({ rows, flat = false }: { rows: MovementRow[]; flat?: boolean }) {
  const [hover, setHover]   = useState<number | null>(null)
  const [tip, setTip]       = useState({ x: 0, y: 0 })
  const [plotRef, { w: W, h: H }] = useElementSize()

  const data    = rows
  const n       = data.length || 1
  const focus   = hover ?? data.length - 1

  // Layout constants
  const padL  = 38   // left axis labels
  const padR  = 10
  const padT  = 20   // space for value labels above tallest bar
  const padB  = 28   // space for month labels below bars
  const plotW = Math.max(40, W - padL - padR)
  const plotH = Math.max(40, H - padT - padB)
  const baseY = padT + plotH  // y-coordinate of the baseline

  // Determine active series (at least one month with non-zero value)
  const activeSeries = SERIES.filter(s =>
    data.some(row => (Number(row[s.key]) || 0) !== 0)
  )
  // Use only active series for bar layout; fall back to all if nothing active
  const renderSeries = activeSeries.length > 0 ? activeSeries : SERIES

  const max = Math.max(
    1,
    ...data.flatMap(row => renderSeries.map(s => Math.abs(Number(row[s.key]) || 0))),
  )

  // Bar group layout
  const groupW    = plotW / n
  const groupGap  = Math.min(groupW * 0.28, 60)
  const innerW    = Math.max(renderSeries.length * 6, groupW - groupGap)
  const barGap    = Math.max(1.5, innerW * 0.025)
  const barW      = Math.max(4, (innerW - barGap * (renderSeries.length - 1)) / renderSeries.length)

  // Gridline values (0, 25%, 50%, 75%, 100%)
  const gridTicks = [0, 0.25, 0.5, 0.75, 1]

  return (
    <div className="sa-chart">
      <div
        className="sa-chart__plot"
        ref={plotRef}
        onMouseMove={(e) => setTip({ x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY })}
        onMouseLeave={() => setHover(null)}
      >
        {/* Month label overlay — top-right */}
        {!flat && (
          <span className="sa-chart__tag">
            <strong>{data[focus]?.period ?? ''}</strong>
            <i className="bi bi-hand-index-thumb" aria-hidden="true" /> hover a month
          </span>
        )}

        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Monthly movement bar chart"
          className="sa-chart__svg"
          preserveAspectRatio="none"
        >
          {/* ── Gridlines ── */}
          {gridTicks.map((t) => {
            const y = baseY - t * plotH
            return (
              <g key={t}>
                <line
                  x1={padL} y1={y} x2={W - padR} y2={y}
                  stroke="rgba(100,116,139,0.15)"
                  strokeWidth={t === 0 ? 1.5 : 1}
                  strokeDasharray={t === 0 ? undefined : '3 4'}
                />
                {t > 0 && (
                  <text x={padL - 6} y={y + 3.5} textAnchor="end" className="sa-chart__axis">
                    {num(Math.round(max * t))}
                  </text>
                )}
              </g>
            )
          })}

          {/* ── Baseline label (0) ── */}
          <text x={padL - 6} y={baseY + 3.5} textAnchor="end" className="sa-chart__axis">0</text>

          {/* ── Month groups ── */}
          {data.map((row, i) => {
            const groupX  = padL + i * groupW + (groupW - innerW) / 2
            const focused = i === focus

            return (
              <g key={row.period ?? i}>
                {/* Focused column highlight */}
                {focused && !flat && (
                  <rect
                    x={groupX - barGap}
                    y={padT}
                    width={innerW + barGap * 2}
                    height={plotH}
                    fill="rgba(99,102,241,0.06)"
                    rx={6}
                  />
                )}

                {/* Bars — only render when value > 0 */}
                {renderSeries.map((s, j) => {
                  const value = Number(row[s.key]) || 0
                  if (value === 0) return null  // skip zero bars entirely

                  const h      = (Math.abs(value) / max) * plotH
                  const x      = groupX + j * (barW + barGap)
                  const cx     = x + barW / 2
                  const barTop = baseY - h
                  // Label sits above the bar; clamp so it never goes above padT
                  const labelY = Math.max(padT + 10, barTop - 5)

                  return (
                    <g key={s.key} opacity={flat || focused ? 1 : 0.45}>
                      {/* Bar rectangle */}
                      <rect
                        x={x}
                        y={barTop}
                        width={Math.max(4, barW)}
                        height={h}
                        rx={Math.min(3, barW / 3)}
                        fill={s.color}
                      >
                        <title>{`${row.period ?? ''} · ${s.label}: ${num(value)}`}</title>
                      </rect>
                      {/* Value label above bar */}
                      <text
                        x={cx}
                        y={labelY}
                        textAnchor="middle"
                        className="sa-chart__barval"
                        fill={s.color}
                      >
                        {num(value)}
                      </text>
                    </g>
                  )
                })}

                {/* Invisible hover hit-area for the full group */}
                <rect
                  x={groupX - barGap}
                  y={padT}
                  width={innerW + barGap * 2}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />

                {/* Month label */}
                <text
                  x={groupX + innerW / 2}
                  y={H - 8}
                  textAnchor="middle"
                  className={`sa-chart__month${focused && !flat ? ' sa-chart__month--on' : ''}`}
                >
                  {row.period ?? ''}
                </text>
              </g>
            )
          })}
        </svg>

        {/* ── Hover tooltip ── */}
        {hover != null && data[hover] && (
          <div
            className="sa-chart__tip"
            style={{
              left: Math.min(Math.max(tip.x + 14, 4), Math.max(4, W - 172)),
              top:  Math.max(tip.y - 10, 4),
            }}
            role="tooltip"
          >
            <div className="sa-chart__tip-head">{data[hover].period ?? ''}</div>
            {SERIES.filter(s => (Number(data[hover][s.key]) || 0) > 0).map((s) => (
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

      {/* ── Bottom readout: focused-month values for every series ── */}
      <div className="sa-chart__readout">
        {SERIES.map((s) => {
          const val = Number(data[focus]?.[s.key]) || 0
          return (
            <div className="sa-chart__metric" key={s.key} title={s.label}>
              <span
                className="sa-chart__metric-val"
                style={{ color: val > 0 ? s.color : undefined }}
              >
                {num(val)}
              </span>
              <span className="sa-chart__metric-label">
                <span className="sa-chart__swatch" style={{ background: s.color }} />
                {s.short}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
