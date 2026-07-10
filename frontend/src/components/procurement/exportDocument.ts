// Client-side Purchase Order document generation (no backend) — shared by the
// Supplier Review panel (Assign stage) and the Supplier Queue / Export Monitor
// panel, so both "Export Purchase Order" actions produce the identical document.
import type { SupplierQueueGroup, SupplierQueueProduct } from './SupplierQueuePanel'

function exportRows(group: SupplierQueueGroup, eq: (l: SupplierQueueProduct) => number) {
  return group.lines
    .filter((l) => l.exported || eq(l) > 0)
    .map((l) => ({
      product: l.product_name ?? l.product_code ?? '',
      ptr: l.ptr,
      offer: l.offer ?? '',
      finalQty: l.final_qty,
      exportQty: l.exported ? l.final_qty : eq(l),
    }))
}

/** Every live line at its full assigned quantity — the default "just export it" case. */
export const fullQty = (l: SupplierQueueProduct) => l.final_qty

export function downloadPurchaseOrderCsv(group: SupplierQueueGroup, eq: (l: SupplierQueueProduct) => number = fullQty) {
  const rows = exportRows(group, eq)
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`
  const lines = [
    ['Product', 'PTR', 'Offer', 'Final Qty', 'Export Qty'].join(','),
    ...rows.map((r) => [r.product, r.ptr, r.offer, r.finalQty, r.exportQty].map(esc).join(',')),
  ]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `PO_${group.supplier_code}_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export function printPurchaseOrderPdf(group: SupplierQueueGroup, eq: (l: SupplierQueueProduct) => number = fullQty) {
  const rows = exportRows(group, eq)
  const esc = (v: string) => v.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c] as string))
  const body = rows
    .map((r) => `<tr><td>${esc(r.product)}</td><td class="n">${r.ptr.toFixed(2)}</td><td>${esc(r.offer)}</td><td class="n">${r.finalQty}</td><td class="n">${r.exportQty}</td></tr>`)
    .join('')
  const w = window.open('', '_blank', 'width=800,height=900')
  if (!w) return
  w.document.write(`<!doctype html><html><head><title>PO ${esc(group.supplier_code)}</title><style>
    body{font-family:Segoe UI,Arial,sans-serif;padding:24px;color:#0f172a}
    h1{font-size:18px;margin:0 0 4px} .meta{color:#64748b;font-size:12px;margin-bottom:16px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left} th{background:#f8fafc}
    td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
  </style></head><body>
    <h1>Purchase Order — ${esc(group.supplier_name ?? group.supplier_code)}</h1>
    <div class="meta">Supplier ${esc(group.supplier_code)} · ${rows.length} products · Generated ${new Date().toLocaleString('en-IN')}</div>
    <table><thead><tr><th>Product</th><th class="n">PTR</th><th>Offer</th><th class="n">Final Qty</th><th class="n">Export Qty</th></tr></thead><tbody>${body}</tbody></table>
  </body></html>`)
  w.document.close()
  w.focus()
  w.print()
}
