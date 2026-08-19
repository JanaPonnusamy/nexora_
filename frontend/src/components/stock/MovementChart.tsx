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
  { key: 'pur', label: 'Purchase', short: 'PUR', color: '#1d4ed8' },
  { key: 'sal', label: 'Sales', short: 'SAL', color: '#15803d' },
  { key: 'tin', label: 'Transfer In', short: 'TIN', color: '#93c5fd' },
  { key: 'tout', label: 'Transfer Out', short: 'TOUT', color: '#86efac' },
  { key: 'adj', label: 'Adjustment', short: 'ADJ', color: '#7c3aed' },
  { key: 'stk', label: 'Stock', short: 'STK', color: '#dc2626' },
]

type FlatBar = {
  key: string
  label: string
  short: string
  color: string
  value: (row: MovementRow) => number
  parts?: { key: string; color: string; value: (row: MovementRow) => number }[]
}

const FLAT_BARS: FlatBar[] = [
  {
    key: 'inbound',
    label: 'Inbound',
    short: 'IN',
    color: '#1d4ed8',
    value: (row) => (Number(row.tin) || 0) + (Number(row.pur) || 0),
    parts: [
      { key: 'tin', color: '#93c5fd', value: (row) => Number(row.tin) || 0 },
      { key: 'pur', color: '#1d4ed8', value: (row) => Number(row.pur) || 0 },
    ],
  },
  {
    key: 'outbound',
    label: 'Outbound',
    short: 'OUT',
    color: '#15803d',
    value: (row) => (Number(row.tout) || 0) + (Number(row.sal) || 0),
    parts: [
      { key: 'tout', color: '#86efac', value: (row) => Number(row.tout) || 0 },
      { key: 'sal', color: '#15803d', value: (row) => Number(row.sal) || 0 },
    ],
  },
  { key: 'adj', label: 'Adjustment', short: 'ADJ', color: '#7c3aed', value: (row) => Number(row.adj) || 0 },
  { key: 'stk', label: 'Stock', short: 'STK', color: '#dc2626', value: (row) => Number(row.stk) || 0 },
]

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

export function MovementChart({ rows, flat = false }: { rows: MovementRow[]; flat?: boolean }) {
  const [hover, setHover] = useState<number | null>(null)
  const [tip, setTip] = useState({ x: 0, y: 0 })
  const [plotRef, { w: W, h: H }] = useElementSize()

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

  const max = flat
    ? Math.max(1, ...data.flatMap((row) => FLAT_BARS.map((bar) => Math.abs(bar.value(row)))))
    : Math.max(1, ...data.flatMap((row) => SERIES.map((series) => Math.abs(Number(row[series.key]) || 0))))

  const groupW = plotW / n
  const chartBars = flat ? FLAT_BARS.length : SERIES.length
  const groupGap = Math.min(groupW * 0.3, 80)
  const innerW = Math.max(chartBars * 8, groupW - groupGap)
  const barGap = Math.max(2, innerW * 0.04)
  const barW = (innerW - barGap * (chartBars - 1)) / chartBars

  return (
    <div className={`sa-chart${flat ? ' sa-chart--flat' : ''}`}>
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
            {/* Theme-aware via CSS classes (stop-color), not inline attrs — a
                fixed white gradient washed out the bars/gridlines under it in
                dark mode (readability bug, reported against the real
                rendered chart, not guessed). */}
            <linearGradient id="sa-chart-glass" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" className="sa-chart__glass-a" />
              <stop offset="100%" className="sa-chart__glass-b" />
            </linearGradient>
          </defs>
          <rect
            className="sa-chart__plotbg"
            x={padL - 8} y={barTopLimit - 4} width={plotW + 20} height={barAreaH + 8}
            rx={12} fill="url(#sa-chart-glass)"
          />

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
                {flat
                  ? FLAT_BARS.map((bar, j) => {
                      const value = bar.value(row)
                      const x = groupX + j * (barW + barGap)
                      const cx = x + barW / 2
                      const h = (Math.abs(value) / max) * barAreaH
                      const top = baseY - h
                      const labelY = Math.max(barTopLimit - 2, top - 4)
                      if (!bar.parts) {
                        return (
                          <g key={bar.key}>
                            <rect x={x} y={top} width={Math.max(4, barW)} height={h} rx={4} fill={bar.color}>
                              <title>{`${row.period ?? ''} · ${bar.label}: ${num(value)}`}</title>
                            </rect>
                            {value > 0 && (
                              <text x={cx} y={labelY} textAnchor="middle" className="sa-chart__barval" fill={bar.color}>
                                {num(value)}
                              </text>
                            )}
                          </g>
                        )
                      }
                      let offset = 0
                      return (
                        <g key={bar.key}>
                          {bar.parts.map((part) => {
                            const partValue = part.value(row)
                            const partH = (Math.abs(partValue) / max) * barAreaH
                            const partY = baseY - offset - partH
                            offset += partH
                            return (
                              <rect key={part.key} x={x} y={partY} width={Math.max(4, barW)} height={partH} rx={4} fill={part.color}>
                                <title>{`${row.period ?? ''} · ${bar.label}: ${num(value)}`}</title>
                              </rect>
                            )
                          })}
                          {value > 0 && (
                            <text x={cx} y={labelY} textAnchor="middle" className="sa-chart__barval" fill={bar.color}>
                              {num(value)}
                            </text>
                          )}
                        </g>
                      )
                    })
                  : SERIES.map((series, j) => {
                      const value = Number(row[series.key]) || 0
                      const h = (Math.abs(value) / max) * barAreaH
                      const x = groupX + j * (barW + barGap)
                      const cx = x + barW / 2
                      const top = baseY - h
                      const labelY = Math.max(barTopLimit - 2, top - 4)
                      return (
                        <g key={series.key}>
                          <rect x={x} y={top} width={Math.max(3, barW)} height={h} rx={3} fill={series.color}>
                            <title>{`${row.period ?? ''} · ${series.label}: ${num(value)}`}</title>
                          </rect>
                          {value > 0 && (
                            <text x={cx} y={labelY} textAnchor="middle" className="sa-chart__barval" fill={series.color}>
                              {num(value)}
                            </text>
                          )}
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
            {SERIES.map((series) => (
              <div className="sa-chart__tip-row" key={series.key}>
                <span className="sa-chart__tip-key">
                  <span className="sa-chart__swatch" style={{ background: series.color }} />
                  {series.label}
                </span>
                <span className="sa-chart__tip-val">{num(Number(data[hover][series.key]) || 0)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Purchase Manager's compact (flat) chart drops this readout row — it's
          pure vertical cost there (Purchase/Sales History need the room, and
          the same PUR/SAL/TIN/TOUT/ADJ/STK breakdown is already on hover via
          sa-chart__tip). The full Stock Availability chart keeps it. */}
      {!flat && (
        <div className="sa-chart__readout">
          {SERIES.map((series) => (
            <div className="sa-chart__metric" key={series.key} title={series.label}>
              <span className="sa-chart__metric-val" style={{ color: series.color }}>{num(Number(data[focus]?.[series.key]) || 0)}</span>
              <span className="sa-chart__metric-label">
                <span className="sa-chart__swatch" style={{ background: series.color }} />
                {series.short}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
