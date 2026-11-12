import { useEffect, useState } from 'react'
import { quickStockService } from './quickStockService'
import type { QuickStockCore } from './types'

function money(v: number | null | undefined) {
  if (v == null) return '—'
  return v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function date(v: string | null | undefined) {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })
}

export interface QuickStockActiveProduct {
  tenantId: string
  storeId: string
  storeLabel: string
  productCode: string
  productName: string | null
}

export function QuickStockDetail({ active, onClose }: { active: QuickStockActiveProduct; onClose: () => void }) {
  const [core, setCore] = useState<QuickStockCore | null>(null)
  const [loading, setLoading] = useState(true)
  const [showPurchase, setShowPurchase] = useState(false)

  useEffect(() => {
    let live = true
    setLoading(true)
    quickStockService
      .productCore(active.tenantId, active.storeId, active.productCode)
      .then((data) => { if (live) setCore(data) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [active.tenantId, active.storeId, active.productCode])

  return (
    <div className="qs-detail">
      <div className="qs-detail__head">
        <span>{active.storeLabel} · {active.productName ?? active.productCode}</span>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button className="qs-toggle-purchase" onClick={() => setShowPurchase((v) => !v)}>
            {showPurchase ? 'Hide purchase' : 'Show purchase'}
          </button>
          <button className="qs-close-btn" onClick={onClose}>✕ Close</button>
        </div>
      </div>

      {loading ? (
        <div className="qs-panel__empty" style={{ padding: '1rem' }}>Loading…</div>
      ) : (
        <div className="qs-detail__panels">
          <div className="qs-panel">
            <div className="qs-panel__title">Batches</div>
            {core?.batches?.length ? (
              <table>
                <thead>
                  <tr><th>Batch</th><th className="qs-num">Stock</th><th>Expiry</th><th className="qs-num">PTR</th><th className="qs-num">MRP</th></tr>
                </thead>
                <tbody>
                  {core.batches.map((b, i) => (
                    <tr key={i}>
                      <td>{b.batch_no ?? '—'}</td>
                      <td className="qs-num">{b.stock ?? 0}</td>
                      <td>{date(b.expiry_date)}</td>
                      <td className="qs-num">{money(b.ptr)}</td>
                      <td className="qs-num">{money(b.mrp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div className="qs-panel__empty">No batch rows.</div>}
          </div>

          <div className="qs-panel">
            <div className="qs-panel__title">Recent Sales</div>
            {core?.sales?.length ? (
              <table>
                <thead>
                  <tr><th>Date</th><th>Bill</th><th>Customer</th><th className="qs-num">Qty</th><th className="qs-num">MRP</th></tr>
                </thead>
                <tbody>
                  {core.sales.slice(0, 10).map((s, i) => (
                    <tr key={i}>
                      <td>{date(s.date)}</td>
                      <td>{s.bill_no ?? '—'}</td>
                      <td>{s.customer ?? '—'}</td>
                      <td className="qs-num">{s.qty ?? 0}</td>
                      <td className="qs-num">{money(s.mrp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div className="qs-panel__empty">No recent sales.</div>}
          </div>

          {showPurchase && (
            <div className="qs-panel">
              <div className="qs-panel__title">Recent Purchases</div>
              {core?.purchases?.length ? (
                <table>
                  <thead>
                    <tr><th>Date</th><th className="qs-num">Qty</th><th className="qs-num">Cost</th><th className="qs-num">PTR</th><th className="qs-num">MRP</th></tr>
                  </thead>
                  <tbody>
                    {core.purchases.slice(0, 10).map((p, i) => (
                      <tr key={i}>
                        <td>{date(p.date)}</td>
                        <td className="qs-num">{p.qty ?? 0}</td>
                        <td className="qs-num">{money(p.cost)}</td>
                        <td className="qs-num">{money(p.ptr)}</td>
                        <td className="qs-num">{money(p.mrp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="qs-panel__empty">No recent purchases.</div>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
