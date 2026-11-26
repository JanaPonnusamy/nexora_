import { useEffect, useRef, useState } from 'react'
import type { QuickStockMovementRow } from './types'

function exactQty(value: number) {
  const n = Number(value) || 0
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

const SERIES = [
  { key: 'pur' as const, label: 'Purchase', color: '#2563eb', light: '#7db0ff', dark: '#1a3fae' },
  { key: 'sal' as const, label: 'Sales', color: '#16a34a', light: '#67e08c', dark: '#12662f' },
  { key: 'stk' as const, label: 'Stock', color: '#dc2626', light: '#fb8686', dark: '#9c1414' },
]

function useChartSize() {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 220, h: 150 })
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect
      setSize({ w: Math.max(140, cr.width), h: Math.max(90, cr.height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, size] as const
}

/** Multi-color grouped-bar sales/purchase/stock trend — same visual model as
 * the procurement/Stock Availability charts (gradient bars, gridlines, hover
 * tooltip), sized to fill the panel it's given. */
export function QuickStockChart({ movement }: { movement: QuickStockMovementRow[] }) {
  const [plotRef, { w: W, h: H }] = useChartSize()
  const [hover, setHover] = useState<number | null>(null)
  const [tip, setTip] = useState({ x: 0, y: 0 })

  const months = movement ?? []
  if (months.length === 0) return <div className="qs-panel__empty">No trend data.</div>

  const max = Math.max(1, ...months.flatMap((m) => SERIES.map((s) => Math.abs(m[s.key] ?? 0))))
  const axisTopLabel = exactQty(Math.round(max))
  const padL = Math.max(30, Math.min(56, axisTopLabel.length * 4.8 + 10))
  const padR = 8
  const padT = 10
  const padB = 16
  const plotW = Math.max(30, W - padL - padR)
  const plotH = Math.max(30, H - padT - padB)
  const baseY = padT + plotH

  const n = months.length
  const groupW = plotW / n
  const groupGap = Math.min(groupW * 0.14, 12)
  const rawInnerW = Math.max(SERIES.length * 9, groupW - groupGap)
  const rawBarGap = Math.max(1, rawInnerW * 0.035)
  const barW = (rawInnerW - rawBarGap * (SERIES.length - 1)) / SERIES.length
  const barGap = rawBarGap
  const innerW = barW * SERIES.length + barGap * (SERIES.length - 1)

  const labelBand = Math.max(plotH * 0.14, 16)
  const barAreaH = plotH - labelBand
  const barTopLimit = padT + labelBand

  return (
    <div className="qs-trend2">
      <div
        className="qs-trend2__plot"
        ref={plotRef}
        onMouseMove={(e) => setTip({ x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY })}
        onMouseLeave={() => setHover(null)}
      >
        <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMinYMin meet" role="img" aria-label="Sales trend chart">
          <defs>
            {SERIES.map((s) => (
              <linearGradient key={s.key} id={`qs-bar-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.light} />
                <stop offset="48%" stopColor={s.color} />
                <stop offset="100%" stopColor={s.dark} />
              </linearGradient>
            ))}
          </defs>

          {[0, 0.5, 1].map((t) => {
            const y = baseY - t * barAreaH
            return (
              <g key={t}>
                <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="rgba(100,116,139,0.18)" strokeWidth={1} />
                <text x={padL - 5} y={y + 3} textAnchor="end" className="qs-trend2__axis">{exactQty(Math.round(max * t))}</text>
              </g>
            )
          })}

          {months.map((row, i) => {
            const groupX = padL + i * groupW + (groupW - innerW) / 2
            return (
              <g key={row.period ?? i}>
                {SERIES.map((s, j) => {
                  const value = row[s.key] ?? 0
                  const h = (Math.abs(value) / max) * barAreaH
                  const x = groupX + j * (barW + barGap)
                  const top = baseY - h
                  const cx = x + barW / 2
                  const labelY = Math.max(barTopLimit - 1, top - 3)
                  return (
                    <g key={s.key}>
                      <rect x={x} y={top} width={Math.max(4, barW)} height={h} rx={3} fill={`url(#qs-bar-${s.key})`}>
                        <title>{`${row.period ?? ''} · ${s.label}: ${exactQty(value)}`}</title>
                      </rect>
                      {h > 4 && (
                        <rect x={x + 1} y={top + 1} width={Math.max(1, Math.min(2.5, barW * 0.22))} height={Math.max(0, h - 2)} rx={1.5} fill="rgba(255,255,255,0.38)" />
                      )}
                      {value > 0 && (
                        <text x={cx} y={labelY} textAnchor="middle" className={`qs-trend2__barval qs-trend2__barval--${s.key}`}>{exactQty(value)}</text>
                      )}
                    </g>
                  )
                })}
                <rect
                  x={groupX - barGap} y={barTopLimit} width={innerW + barGap * 2} height={barAreaH}
                  fill="transparent" rx={6}
                  onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                />
                <text x={groupX + innerW / 2} y={H - 4} textAnchor="middle" className="qs-trend2__month">{row.period ?? ''}</text>
              </g>
            )
          })}
        </svg>

        {hover != null && months[hover] && (
          <div
            className="qs-trend2__tip"
            style={{ left: Math.min(Math.max(tip.x + 10, 4), Math.max(4, W - 120)), top: Math.max(tip.y - 6, 4) }}
            role="tooltip"
          >
            <div className="qs-trend2__tip-head">{months[hover].period ?? ''}</div>
            {SERIES.map((s) => (
              <div className="qs-trend2__tip-row" key={s.key}>
                <span className="qs-trend2__swatch" style={{ background: s.color }} />
                {s.label}: {exactQty(months[hover][s.key] ?? 0)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
