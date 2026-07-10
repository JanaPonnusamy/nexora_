import { useState } from 'react'
import type { SupplierQueueGroup } from './SupplierQueuePanel'
import { SupplierPicker } from './SupplierPicker'
import type { SupplierRow } from '../../types/procurement'
import { money, num } from '../stock/format'

/**
 * Supplier Review panel — the right column of the Supplier Assignment stage once
 * a supplier is selected. This is the COMPLETE per-supplier workflow (assign →
 * adjust → export → move on) so the buyer never has to leave the page to reach
 * the separate Export Monitor:
 *   product · qty · last-purchase cost (PTR) · line value · change · remove
 * plus the supplier's total purchase value, Minimum Order status, Assign
 * Selected, Export Purchase Order and Next Supplier.
 *
 * No new API: change/remove reuse the assignment endpoints; export reuses the
 * refresh export. Values come from the already-computed Supplier Queue group —
 * never fabricated, and shown as "Calculating…" while the group is loading.
 */
export function SupplierReviewPanel({
  tenantId,
  storeId,
  supplierCode,
  supplierName,
  group,
  loading,
  exporting,
  minOrder,
  checkedCount,
  onChangeSupplier,
  onRemove,
  onExport,
  onReload,
  onAssignSelected,
  onNextSupplier,
}: {
  tenantId: string
  storeId: string
  supplierCode: string
  supplierName: string
  group: SupplierQueueGroup | null
  loading: boolean
  exporting: boolean
  /** Configured Minimum Order Value for this supplier (0 = none configured). */
  minOrder: number
  /** Products currently checked in the grid — feeds Assign Selected. */
  checkedCount: number
  onChangeSupplier: (assignmentId: string, newSupplier: SupplierRow) => void
  onRemove: (assignmentId: string, orderItemId: string) => void
  onExport: (group: SupplierQueueGroup) => void
  onReload: () => void
  onAssignSelected: () => void
  /** Advance to the next supplier still requiring review, without exporting. */
  onNextSupplier: () => void
}) {
  // Which line is currently having its supplier changed (shows the picker inline).
  const [changing, setChanging] = useState<string | null>(null)
  // Explicit reassignment confirm (§7 — never silently overwrite): the picked
  // supplier waits here until the buyer confirms the move.
  const [pendingChange, setPendingChange] = useState<{ assignmentId: string; productName: string; supplier: SupplierRow } | null>(null)

  const lines = group?.lines ?? []
  const liveLines = lines.filter((l) => !l.exported)
  // Line value is only "real" when we have a PTR; otherwise show a dash, never ₹0.00.
  const lineValue = (ptr: number, qty: number) => (ptr > 0 ? money(ptr * qty) : '—')
  // §22 — every count here is scoped to the LIVE (not-yet-exported) lines, the
  // same set the table below renders, so this strip can never disagree with
  // the grid it summarizes. Total Assigned / Exported come straight from the
  // Supplier Queue aggregation (group.product_count / exported_count) — the
  // same numbers the collapsed card and supplierMetaOf already show.
  const totalValue = liveLines.reduce((a, l) => a + (l.ptr > 0 ? l.ptr * l.final_qty : 0), 0)
  const totalKnown = liveLines.some((l) => l.ptr > 0)
  const totalQty = liveLines.reduce((a, l) => a + l.final_qty, 0)
  const exportedCount = group?.exported_count ?? 0
  const totalAssigned = group?.product_count ?? 0
  // Same rule as the Assignment Summary bar (§ Assign toolbar): below a
  // configured minimum, the supplier isn't ready to export yet.
  const minReady = minOrder > 0 ? totalValue >= minOrder : totalAssigned > 0
  const minLabel = minOrder <= 0 ? 'No Minimum' : minReady ? 'Ready' : 'Below Min'
  const minCls = minOrder <= 0 ? 'pm-optstat--ready' : minReady ? 'pm-optstat--ok' : 'pm-optstat--short'

  return (
    <div className="pm-srv">
      <div className="pm-srv__head">
        <div className="pm-srv__id">
          <span className="pm-srv__name"><i className="bi bi-truck" /> {supplierName}</span>
          <span className="pm-srv__code">{supplierCode}</span>
        </div>
        <button className="pm-iconbtn" title="Reload this supplier" onClick={onReload} disabled={loading}>
          <i className="bi bi-arrow-repeat" />
        </button>
      </div>

      {loading ? (
        <div className="pm-srv__hint">Calculating supplier totals…</div>
      ) : (
        <>
          <div className="pm-srv__summary">
            <span className="pm-srv__stat"><b>{num(totalAssigned)}</b><span>Total Assigned</span></span>
            <span className="pm-srv__stat"><b>{num(liveLines.length)}</b><span>Pending Export</span></span>
            <span className="pm-srv__stat"><b>{num(exportedCount)}</b><span>Exported</span></span>
            <span className="pm-srv__stat"><b>{num(totalQty)}</b><span>Total Qty</span></span>
            <span className="pm-srv__stat pm-srv__stat--val">
              <b>{loading ? 'Calculating…' : totalKnown ? money(totalValue) : '—'}</b><span>Purchase Value</span>
            </span>
            <span className="pm-srv__stat">
              <b className={`pm-optstat ${minCls}`}>{minLabel}</b><span>Minimum Order Status</span>
            </span>
          </div>

          {!group || lines.length === 0 ? (
            <div className="pm-srv__hint">
              No products assigned to this supplier yet. Check products in the grid and use Assign Selected, or assign from the Supplier Recommendation panel.
            </div>
          ) : (
          <div className="pm-srv__tablewrap">
            <table className="pm-srv__table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th className="sx-num">Qty</th>
                  <th className="sx-num">Last Purchase</th>
                  <th className="sx-num">Value</th>
                  <th className="pm-srv__act">Actions</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.assignment_id} className={l.exported ? 'pm-srv__row--done' : ''}>
                    <td>
                      <div className="pm-prod__name">{l.product_name ?? l.product_code ?? '—'}</div>
                      <div className="pm-prod__meta">{l.product_code}{l.exported && <span className="pm-tag ms-1">exported</span>}</div>
                      {changing === l.assignment_id && (
                        <div className="pm-srv__change">
                          {pendingChange?.assignmentId === l.assignment_id ? (
                            <div className="pm-srv__confirm">
                              <span>
                                Already assigned to <b>{supplierName}</b>. Reassign{' '}
                                <b>{pendingChange.productName}</b> to <b>{pendingChange.supplier.supplier_name ?? pendingChange.supplier.supplier_code}</b>?
                              </span>
                              <div className="pm-srv__confirm-btns">
                                <button
                                  className="pm-btn pm-btn--danger pm-btn--sm"
                                  onClick={() => {
                                    onChangeSupplier(l.assignment_id, pendingChange.supplier)
                                    setPendingChange(null)
                                    setChanging(null)
                                  }}
                                >
                                  Reassign
                                </button>
                                <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => setPendingChange(null)}>Cancel</button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <SupplierPicker
                                tenantId={tenantId}
                                storeId={storeId}
                                value={null}
                                onPick={(s) => {
                                  if (s) setPendingChange({ assignmentId: l.assignment_id, productName: l.product_name ?? l.product_code ?? 'this product', supplier: s })
                                }}
                              />
                              <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => setChanging(null)}>Cancel</button>
                            </>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="sx-num">{num(l.final_qty)}</td>
                    <td className="sx-num">{l.ptr > 0 ? money(l.ptr) : '—'}</td>
                    <td className="sx-num">{lineValue(l.ptr, l.final_qty)}</td>
                    <td className="pm-srv__act">
                      {!l.exported && (
                        <div className="pm-srv__btns">
                          <button
                            className="pm-btn pm-btn--ghost pm-btn--sm"
                            onClick={() => setChanging((c) => (c === l.assignment_id ? null : l.assignment_id))}
                            title="Move this product to another supplier"
                          >
                            Change
                          </button>
                          <button
                            className="pm-btn pm-btn--danger pm-btn--sm"
                            onClick={() => onRemove(l.assignment_id, l.order_item_id)}
                            title="Remove this product from the supplier"
                          >
                            Remove
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}

          <div className="pm-srv__foot">
            <span className="pm-srv__foottotal">
              Supplier Total <b>{totalKnown ? money(totalValue) : '—'}</b>
            </span>
            <div className="pm-srv__footbtns">
              <button
                className="pm-btn pm-btn--ghost"
                onClick={onAssignSelected}
                disabled={checkedCount === 0}
                title="Assign the products checked in the grid to this supplier"
              >
                <i className="bi bi-check2-square" /> Assign Selected{checkedCount > 0 ? ` (${num(checkedCount)})` : ''}
              </button>
              <button
                className="pm-btn pm-btn--success"
                onClick={() => group && onExport(group)}
                disabled={exporting || !group || group.assignment_ids.length === 0}
                title="Export this supplier's assigned products as a Purchase Order"
              >
                <i className="bi bi-box-arrow-up" /> {exporting ? 'Exporting…' : 'Export Purchase Order'}
              </button>
              <button
                className="pm-btn pm-btn--ghost"
                onClick={onNextSupplier}
                title="Move to the next supplier still needing review"
              >
                Next Supplier <i className="bi bi-arrow-right" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
