import { useEffect, useMemo, useState } from 'react'
import type { PurchaseRow, SalesRow } from '../../types/stock'
import type { BillTarget } from './BillDrawer'
import type { ViewAllKind } from './DetailColumn'
import { stockService } from '../../services/stockService'
import { money, num, date } from '../stock/format'
import '../stock/stock-ui.css'

type HistoryRow = Partial<PurchaseRow & SalesRow>
type Col = { key: string; label: string; num?: boolean; get: (r: HistoryRow) => string | number | null }

const PURCHASE_COLS: Col[] = [
  { key: 'date', label: 'Date', get: (r) => r.date ?? null },
  { key: 'supplier', label: 'Supplier', get: (r) => r.supplier ?? '' },
  { key: 'qty', label: 'Qty', num: true, get: (r) => r.qty ?? 0 },
  { key: 'free', label: 'Free', num: true, get: (r) => r.free ?? 0 },
  { key: 'cost', label: 'Item Cost', num: true, get: (r) => r.cost ?? 0 },
  { key: 'ptr', label: 'PTR', num: true, get: (r) => r.ptr ?? 0 },
  { key: 'mrp', label: 'MRP', num: true, get: (r) => r.mrp ?? 0 },
]
const SALES_COLS: Col[] = [
  { key: 'date', label: 'Date', get: (r) => r.date ?? null },
  { key: 'bill_no', label: 'Bill', get: (r) => r.bill_no ?? '' },
  { key: 'customer', label: 'Customer', get: (r) => r.customer ?? '' },
  { key: 'qty', label: 'Qty', num: true, get: (r) => r.qty ?? 0 },
  { key: 'mrp', label: 'MRP', num: true, get: (r) => r.mrp ?? 0 },
  { key: 'salesman', label: 'Rep', get: (r) => r.salesman ?? '' },
]

/** Full Purchase / Sales history in a centered dialog with Search, Sort and
 *  CSV Export. Rows open their Bill Drawer. */
export function HistoryAllDialog({
  kind,
  tenantId,
  storeId,
  productCode,
  productName,
  onOpenBill,
  onClose,
}: {
  kind: ViewAllKind
  tenantId: string
  storeId: string
  productCode: string
  productName: string | null
  onOpenBill?: (t: BillTarget) => void
  onClose: () => void
}) {
  const cols = kind === 'purchase' ? PURCHASE_COLS : SALES_COLS
  const [rows, setRows] = useState<HistoryRow[] | null>(null)
  const [q, setQ] = useState('')
  const [sortKey, setSortKey] = useState('date')
  const [asc, setAsc] = useState(false)

  useEffect(() => {
    let live = true
    const p = kind === 'purchase'
      ? stockService.purchaseHistory(tenantId, storeId, productCode)
      : stockService.salesHistory(tenantId, storeId, productCode)
    p.then((r) => live && setRows(r)).catch(() => live && setRows([]))
    return () => { live = false }
  }, [kind, tenantId, storeId, productCode])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const view = useMemo(() => {
    const all = rows ?? []
    const needle = q.trim().toLowerCase()
    const filtered = needle
      ? all.filter((r) => cols.some((c) => String(c.get(r) ?? '').toLowerCase().includes(needle)))
      : all
    const col = cols.find((c) => c.key === sortKey) ?? cols[0]
    const sorted = [...filtered].sort((a, b) => {
      const va = col.get(a), vb = col.get(b)
      if (col.num) return (Number(va) || 0) - (Number(vb) || 0)
      return String(va ?? '').localeCompare(String(vb ?? ''))
    })
    return asc ? sorted : sorted.reverse()
  }, [rows, q, sortKey, asc, cols])

  const toggleSort = (key: string) => {
    if (key === sortKey) setAsc((v) => !v)
    else { setSortKey(key); setAsc(false) }
  }

  const exportCsv = () => {
    const header = cols.map((c) => c.label).join(',')
    const body = view
      .map((r) => cols.map((c) => `"${String(c.get(r) ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n')
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${kind}-history-${productCode}.csv`
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
  }

  const openBill = (r: HistoryRow) =>
    onOpenBill?.(kind === 'purchase'
      ? { kind: 'purchase', storeId, billId: r.grn_no ?? '', billDate: r.date, productCode, productName }
      : { kind: 'sales', storeId, billId: r.bill_no ?? '', billDate: r.date, productCode, productName })

  return (
    <>
      <div className="pm-modal__backdrop" onClick={onClose} />
      <div className="pm-modal pm-modal--wide" role="dialog" aria-label={`${kind} history`}>
        <header className="pm-drawer__head">
          <div>
            <h5 className="mb-0">
              <i className={`bi ${kind === 'purchase' ? 'bi-truck' : 'bi-cart-check'} me-2`} />
              {kind === 'purchase' ? 'Purchase' : 'Sales'} History
            </h5>
            <div className="small text-muted">{productName ?? productCode}</div>
          </div>
          <button className="btn-close" aria-label="Close" onClick={onClose} />
        </header>

        <div className="pm-modal__bar">
          <span className="sx-search">
            <i className="bi bi-search" aria-hidden="true" />
            <input type="search" value={q} placeholder="Search…" aria-label="Search history" onChange={(e) => setQ(e.target.value)} />
          </span>
          <span className="text-muted small">{view.length} row{view.length === 1 ? '' : 's'}</span>
          <span style={{ flex: 1 }} />
          <button className="pm-btn pm-btn--ghost" onClick={exportCsv} disabled={view.length === 0}>
            <i className="bi bi-download me-1" /> Export CSV
          </button>
        </div>

        <div className="pm-modal__body">
          {rows === null ? (
            <div className="pm-dsec__hint">Loading…</div>
          ) : view.length === 0 ? (
            <div className="pm-dsec__hint">No history.</div>
          ) : (
            <div className="pm-minitable-wrap">
              <table className="pm-minitable pm-minitable--click">
                <thead>
                  <tr>
                    {cols.map((c) => (
                      <th
                        key={c.key}
                        className={`${c.num ? 'sx-num' : ''} pm-sortth`}
                        onClick={() => toggleSort(c.key)}
                        title="Sort"
                      >
                        {c.label}
                        {sortKey === c.key && <i className={`bi ${asc ? 'bi-caret-up-fill' : 'bi-caret-down-fill'} ms-1`} />}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {view.map((r, i) => (
                    <tr key={i} onClick={() => openBill(r)} title={`Open ${kind} bill`}>
                      {cols.map((c) => (
                        <td key={c.key} className={c.num ? 'sx-num' : c.key === 'date' ? 'sx-dim' : ''}>
                          {c.key === 'date'
                            ? date(c.get(r) as string)
                            : c.num
                              ? (['cost', 'ptr', 'mrp'].includes(c.key) ? money(Number(c.get(r))) : num(Number(c.get(r))))
                              : (c.get(r) || '—')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
