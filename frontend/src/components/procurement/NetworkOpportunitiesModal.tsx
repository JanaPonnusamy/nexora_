import { useEffect, useState } from 'react'
import type { ManualProduct, NetworkOpportunity } from '../../types/procurement'
import { procurementService } from '../../services/procurementService'
import { num } from '../stock/format'

/** Network Opportunities — products this store shows as NON-MOVING locally but
 *  the network movement cache shows as genuinely moving elsewhere, and that
 *  aren't already on this store's Order Screen. Reads the persisted
 *  product_network_movement cache only (GET /network-opportunities) — no
 *  recomputation on open, no per-row store queries.
 *
 *  Discovery only: nothing here changes suggested_qty, VPL membership or
 *  supplier recommendation. Adding a row uses the EXACT SAME manual-add path
 *  (`onAdd`, passed down from PurchaseWorkspacePage) Add Product already uses
 *  — this is not a second "add to order" mechanism. */
export function NetworkOpportunitiesModal({
  tenantId,
  refreshId,
  busy,
  onAdd,
  onClose,
}: {
  tenantId: string
  refreshId: string
  busy: boolean
  onAdd: (product: ManualProduct, qty: number) => void | Promise<void>
  onClose: () => void
}) {
  const [rows, setRows] = useState<NetworkOpportunity[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addingCode, setAddingCode] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    procurementService
      .networkOpportunities(tenantId, refreshId, 1, 100)
      .then((page) => {
        setRows(page.items)
        setTotal(page.total)
      })
      .catch(() => setError('Could not load network opportunities.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, refreshId])

  const addRow = async (row: NetworkOpportunity) => {
    if (busy || addingCode) return
    setAddingCode(row.product_code)
    try {
      await onAdd(row, 1)
      // The product is now on this store's Order Screen (order_items), so the
      // next load() would exclude it anyway — remove it locally too, so the
      // buyer sees it drop out immediately without a round trip.
      setRows((prev) => prev.filter((r) => r.product_code !== row.product_code))
      setTotal((t) => Math.max(0, t - 1))
    } finally {
      setAddingCode(null)
    }
  }

  return (
    <>
      <div className="pm-drawer__backdrop" onClick={onClose} />
      <div className="pm-modal pm-modal--manual" role="dialog" aria-modal="true" aria-labelledby="pm-netopp-title">
        <header className="pm-modal__head">
          <div className="pm-manual__heading">
            <span>Network intelligence</span>
            <h2 id="pm-netopp-title">Network opportunities</h2>
            <p>Not moving in this store right now, but moving in other stores in your network.</p>
          </div>
          <button className="pm-manual__close" type="button" aria-label="Close dialog" onClick={onClose}>
            <i className="bi bi-x-lg" aria-hidden="true" />
          </button>
        </header>
        <div className="pm-modal__body">
          <div className="pm-modal__results">
            {loading ? (
              <div className="pm-manual__state">
                <i className="bi bi-arrow-repeat pm-manual__spinner" aria-hidden="true" />
                <b>Loading network opportunities…</b>
                <span>Reading the network movement cache.</span>
              </div>
            ) : error ? (
              <div className="pm-manual__state">
                <i className="bi bi-exclamation-triangle" aria-hidden="true" />
                <b>{error}</b>
                <span><button type="button" className="pm-btn" onClick={load}>Retry</button></span>
              </div>
            ) : rows.length === 0 ? (
              <div className="pm-manual__state">
                <i className="bi bi-diagram-3" aria-hidden="true" />
                <b>No network opportunities right now</b>
                <span>Nothing this store shows as non-moving is genuinely moving elsewhere in the network.</span>
              </div>
            ) : (
              <table className="sx-table">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Local</th>
                    <th>Network</th>
                    <th className="sx-num">Network sales</th>
                    <th>Active stores</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.product_code} className="sa-rowsel">
                      <td>
                        <div>{r.product_name ?? '—'}</div>
                        <div className="pm-prod__meta">{r.product_code}{r.unit ? ` • ${r.unit}` : ''}</div>
                      </td>
                      <td>
                        <span className="pm-tag pm-tag--local" title={`${num(r.local_sales_qty ?? 0)} units locally in the last ${r.rolling_days ?? 90}d`}>
                          {r.local_movement_class ?? '—'}
                        </span>
                      </td>
                      <td>
                        <span className="pm-tag pm-tag--network">{r.network_movement_class ?? '—'}</span>
                      </td>
                      <td className="sx-num">{num(r.network_sales_qty ?? 0)}</td>
                      <td>{r.active_store_count}/{r.mapped_store_count}</td>
                      <td>
                        <button
                          type="button"
                          className="pm-btn pm-btn--sm"
                          disabled={busy || addingCode === r.product_code}
                          onClick={() => addRow(r)}
                          title="Add to this refresh — same as Add Product"
                        >
                          {addingCode === r.product_code ? (
                            <i className="bi bi-arrow-repeat pm-manual__spinner" aria-hidden="true" />
                          ) : (
                            <i className="bi bi-plus-lg" aria-hidden="true" />
                          )}
                          {' '}Add
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
        <footer className="pm-modal__foot">
          <div className="pm-modal__sel">
            <span><small>{total} opportunit{total === 1 ? 'y' : 'ies'} found</small></span>
          </div>
          <button className="pm-btn pm-btn--primary" onClick={onClose}>Close</button>
        </footer>
      </div>
    </>
  )
}
