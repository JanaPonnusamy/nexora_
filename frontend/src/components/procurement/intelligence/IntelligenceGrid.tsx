import { useCallback, useEffect, useRef, useState } from 'react'
import type { PiHover, PiRow, PiStoreColumn } from '../../../types/intelligence'
import { intelligenceService } from '../../../services/intelligenceService'
import { num, money, date } from '../../stock/format'

/**
 * Dynamic, spreadsheet-first intelligence grid. Columns are generated from the
 * `stores` prop (never hardcoded): Product · Consolidated Suggested ·
 * Consolidated Purchase · one column per active store (Suggested over Current
 * Stock). Unmapped store cells render blank. Hovering a store cell lazily loads
 * that store's sale/purchase history + non-moving days (on demand only).
 */
export function IntelligenceGrid({
  rows,
  stores,
  selectedId,
  onSelect,
}: {
  rows: PiRow[]
  stores: PiStoreColumn[]
  selectedId: string | null
  onSelect: (row: PiRow) => void
}) {
  const [hover, setHover] = useState<{ cacheId: string; storeId: string; x: number; y: number } | null>(null)
  const [hoverData, setHoverData] = useState<PiHover | null>(null)
  const [hoverLoading, setHoverLoading] = useState(false)
  const cacheRef = useRef<Map<string, PiHover>>(new Map())
  const timerRef = useRef<number | null>(null)

  const clearTimer = () => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = null
  }

  const scheduleHover = useCallback(
    (cacheId: string, storeId: string, rect: DOMRect) => {
      clearTimer()
      // Position to the right of the cell, flipping left near the viewport edge.
      const x = rect.right + 330 > window.innerWidth ? Math.max(8, rect.left - 328) : rect.right + 8
      const y = Math.min(rect.top, window.innerHeight - 390)
      timerRef.current = window.setTimeout(() => {
        setHover({ cacheId, storeId, x, y })
      }, 300)
    },
    [],
  )

  const leaveHover = () => {
    clearTimer()
    setHover(null)
  }

  useEffect(() => () => clearTimer(), [])

  // Lazy-load the hover payload when a hover target settles (cached per cell).
  useEffect(() => {
    if (!hover) {
      setHoverData(null)
      return
    }
    const key = `${hover.cacheId}|${hover.storeId}`
    const cached = cacheRef.current.get(key)
    if (cached) {
      setHoverData(cached)
      return
    }
    let live = true
    setHoverLoading(true)
    setHoverData(null)
    intelligenceService
      .hover(hover.cacheId, hover.storeId)
      .then((d) => {
        cacheRef.current.set(key, d)
        if (live) setHoverData(d)
      })
      .catch(() => live && setHoverData(null))
      .finally(() => live && setHoverLoading(false))
    return () => {
      live = false
    }
  }, [hover])

  return (
    <>
      <table className="pi-grid">
        <thead>
          <tr>
            <th style={{ minWidth: 220 }}>Product</th>
            <th className="pi-col--num pi-col--suggest" title="Sum of every store's suggested quantity">
              Cons. Suggested
            </th>
            <th className="pi-col--num pi-col--purchase" title="MAX(0, sum suggested − sum stock)">
              Cons. Purchase
            </th>
            {stores.map((s) => (
              <th key={s.store_id} className="pi-col--store">
                <span className="pi-th-store">
                  <b>{s.store_code ?? '—'}</b>
                  <span>Sug · Stock</span>
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const isTransfer = r.consolidated_purchase_qty === 0 && r.transfer_qty > 0
            return (
              <tr
                key={r.cache_id}
                className={`${selectedId === r.cache_id ? 'pi-row--sel ' : ''}${isTransfer ? 'pi-row--transfer' : ''}`}
                onClick={() => onSelect(r)}
              >
                <td>
                  <div className="pi-prod__name" title={r.product_name ?? undefined}>{r.product_name ?? '—'}</div>
                  <div className="pi-prod__code">{r.product_code ?? '—'}</div>
                </td>
                <td className="pi-col--num pi-col--suggest"><b>{num(r.consolidated_suggest_qty)}</b></td>
                <td className="pi-col--num pi-col--purchase">
                  <b>{num(r.consolidated_purchase_qty)}</b>
                  {isTransfer && <span className="pi-badge-transfer" title="Fully coverable by inter-store transfer">TRANSFER</span>}
                </td>
                {stores.map((s) => {
                  const cell = r.stores[s.store_id]
                  if (!cell) {
                    return (
                      <td key={s.store_id} className="pi-cell pi-cell--blank" aria-label="Not mapped">
                        <span className="pi-cell__dash">—</span>
                      </td>
                    )
                  }
                  const sug = cell.suggested_qty ?? 0
                  const stock = cell.stock_qty ?? 0
                  return (
                    <td
                      key={s.store_id}
                      className="pi-cell pi-cell--hoverable"
                      onMouseEnter={(e) => scheduleHover(r.cache_id, s.store_id, e.currentTarget.getBoundingClientRect())}
                      onMouseLeave={leaveHover}
                    >
                      <span className="pi-cell__stack">
                        <span className={`pi-cell__sug${sug === 0 ? ' pi-cell__sug--zero' : ''}`}>{num(sug)}</span>
                        <span className={`pi-cell__stk${stock <= 0 ? ' pi-cell__stk--out' : ''}`}>{num(stock)}</span>
                      </span>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>

      {hover && (
        <StoreCellHover data={hoverData} loading={hoverLoading} x={hover.x} y={hover.y} />
      )}
    </>
  )
}

/* ---- Hover popup ---------------------------------------------------------- */

function StoreCellHover({ data, loading, x, y }: { data: PiHover | null; loading: boolean; x: number; y: number }) {
  return (
    <div className="pi-hover" style={{ left: x, top: y }} role="tooltip">
      {loading || !data ? (
        <div className="pi-hover__loading"><i className="bi bi-hourglass-split" /> Loading history…</div>
      ) : !data.mapped ? (
        <div className="pi-hover__loading">Product not mapped in this store.</div>
      ) : (
        <>
          <div className="pi-hover__head">
            <div className="pi-hover__title">{data.product_name ?? data.product_code ?? '—'}</div>
            <div className="pi-hover__store">Code {data.product_code ?? '—'}</div>
          </div>
          <div className="pi-hover__kpis">
            <div className="pi-hover__kpi"><b>{date(data.last_sale_date)}</b><span>Last Sale</span></div>
            <div className="pi-hover__kpi"><b>{date(data.last_purchase_date)}</b><span>Last Purchase</span></div>
            <div className="pi-hover__kpi"><b>{data.non_moving_days ?? '—'}</b><span>Non-Moving Days</span></div>
          </div>
          <div className="pi-hover__body">
            <div className="pi-hover__sec">Sales History</div>
            {data.sales_history.length === 0 ? (
              <div className="pi-hover__store">No recent sales.</div>
            ) : (
              <table>
                <thead><tr><th>Date</th><th>Bill</th><th className="pi-hover__num">Qty</th></tr></thead>
                <tbody>
                  {data.sales_history.slice(0, 6).map((r, i) => (
                    <tr key={i}><td>{date(r.date)}</td><td>{r.bill_no ?? '—'}</td><td className="pi-hover__num">{num(r.qty)}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="pi-hover__sec">Purchase History</div>
            {data.purchase_history.length === 0 ? (
              <div className="pi-hover__store">No recent purchases.</div>
            ) : (
              <table>
                <thead><tr><th>Date</th><th className="pi-hover__num">Qty</th><th className="pi-hover__num">PTR</th></tr></thead>
                <tbody>
                  {data.purchase_history.slice(0, 6).map((r, i) => (
                    <tr key={i}><td>{date(r.date)}</td><td className="pi-hover__num">{num(r.qty)}</td><td className="pi-hover__num">{money(r.ptr)}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
