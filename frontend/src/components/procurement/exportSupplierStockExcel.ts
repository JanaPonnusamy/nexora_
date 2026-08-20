// Supplier Live Stock -> Excel export (§ EXPORT EXCEL). Client-side only,
// mirrors exportDocument.ts's "no backend" pattern for the queue exports.
// Exports ONLY rows with a positive Order Qty, in the exact column set the
// buyer asked for, with a professional purchase-order layout (frozen header,
// autofilter, bold header, alternate row colors, right-aligned numerics).
import ExcelJS from 'exceljs'
import type { SupplierStockRow } from '../../types/procurement'
import { formatOffer } from './SupplierStockTable'

export async function exportSupplierStockExcel({
  supplierName,
  supplierCode,
  rows,
  draft,
  remarks,
  setBusy,
  notify,
}: {
  supplierName: string | null
  supplierCode: string
  rows: SupplierStockRow[]
  draft: Record<string, string>
  remarks: Record<string, string>
  setBusy?: (busy: boolean) => void
  notify?: (kind: 'success' | 'danger', text: string) => void
}) {
  const keyOf = (r: SupplierStockRow) => r.supplier_product_code ?? r.product_code ?? ''

  const orderedRows = rows
    .map((r) => ({ row: r, qty: Number(draft[keyOf(r)]) }))
    .filter(({ qty }) => !Number.isNaN(qty) && qty > 0)

  if (orderedRows.length === 0) {
    notify?.('danger', 'No products with an Order Qty to export.')
    return
  }

  setBusy?.(true)
  try {
    const wb = new ExcelJS.Workbook()
    wb.creator = 'Nexora Purchase Manager'
    wb.created = new Date()
    const ws = wb.addWorksheet('Purchase Order', {
      views: [{ state: 'frozen', ySplit: 1 }],
    })

    const columns: { header: string; key: string; width: number; numeric?: boolean }[] = [
      { header: 'Supplier Product Code', key: 'supplierProductCode', width: 20 },
      { header: 'Internal Product Code', key: 'internalProductCode', width: 20 },
      { header: 'Supplier Product Name', key: 'supplierProductName', width: 30 },
      { header: 'Internal Product Name', key: 'internalProductName', width: 30 },
      { header: 'Pack', key: 'pack', width: 12 },
      { header: 'Order Qty', key: 'orderQty', width: 12, numeric: true },
      { header: 'Offer', key: 'offer', width: 14 },
      { header: 'Remarks', key: 'remarks', width: 20 },
      { header: 'Supplier', key: 'supplier', width: 22 },
      { header: 'MRP', key: 'mrp', width: 12, numeric: true },
      { header: 'PTR', key: 'ptr', width: 12, numeric: true },
    ]
    ws.columns = columns.map((c) => ({ header: c.header, key: c.key, width: c.width }))

    for (const { row: r, qty } of orderedRows) {
      ws.addRow({
        supplierProductCode: r.supplier_product_code ?? '',
        internalProductCode: r.product_code ?? '',
        supplierProductName: r.supplier_product_name ?? '',
        internalProductName: r.product_name ?? '',
        pack: r.packing ?? '',
        orderQty: qty,
        offer: formatOffer(r) ?? '',
        remarks: remarks[keyOf(r)] ?? '',
        supplier: supplierName ?? supplierCode,
        mrp: r.mrp ?? '',
        ptr: r.ptr ?? '',
      })
    }

    // Header formatting — bold, filled, autofilter.
    const headerRow = ws.getRow(1)
    headerRow.font = { bold: true, color: { argb: 'FFFFFFFF' } }
    headerRow.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF2563EB' } }
    headerRow.alignment = { vertical: 'middle' }
    ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: columns.length } }

    // Alternate row colors + numeric right-alignment.
    columns.forEach((c, i) => {
      if (!c.numeric) return
      ws.getColumn(i + 1).alignment = { horizontal: 'right' }
    })
    for (let i = 2; i <= ws.rowCount; i++) {
      if (i % 2 === 0) {
        ws.getRow(i).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF1F5F9' } }
      }
    }

    // Auto-fit is approximated above via fixed widths (ExcelJS has no true
    // auto-fit); widen a column to the longest cell it actually holds so text
    // isn't clipped.
    columns.forEach((c, i) => {
      const col = ws.getColumn(i + 1)
      let max = c.header.length
      col.eachCell({ includeEmpty: false }, (cell) => {
        const len = String(cell.value ?? '').length
        if (len > max) max = len
      })
      col.width = Math.min(Math.max(max + 2, c.width), 45)
    })

    const buf = await wb.xlsx.writeBuffer()
    const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `PO_${supplierCode}_${new Date().toISOString().slice(0, 10)}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    notify?.('success', `Exported ${orderedRows.length} product${orderedRows.length === 1 ? '' : 's'} to Excel.`)
  } catch (err) {
    notify?.('danger', err instanceof Error ? err.message : 'Excel export failed.')
  } finally {
    setBusy?.(false)
  }
}
