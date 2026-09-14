// CSV/XLSX export for a single NMW bill (mirrors the desktop client's
// per-bill export, plus the Purchase Entry fields). Always exports exactly
// what the detail panel is showing -- the purchase-entry values are passed in
// from already-fetched state, never recomputed here, so the file can't drift
// from the screen.
import ExcelJS from 'exceljs'
import type { NmwPurchaseEntry, NmwSalesBill, NmwSalesBillItem, PurchaseStatus } from '../../types/nmwSalesReport'

const COLUMNS = [
  'Inv No', 'Type', 'Inv Date', 'Destination Store', 'Inv Amount',
  'Product Code', 'Product', 'Batch', 'Expiry', 'Qty', 'Free', 'MRP', 'PTR', 'Dis%',
  'Packing', 'Sublocation', 'Amount',
  'Purchase Entry Status', 'Purchase Entry No', 'Purchase Entry Date',
]

export function purchaseStatusLabel(status: PurchaseStatus | undefined | null): string {
  switch (status) {
    case 'completed':
      return 'Completed'
    case 'pending':
      return 'Pending'
    case 'not_found':
      return 'Not Found'
    case 'error':
      return 'Unable to check'
    default:
      return ''
  }
}

export interface NmwBillExportData {
  bill: NmwSalesBill
  items: NmwSalesBillItem[]
  purchaseEntry: NmwPurchaseEntry | null
  purchaseEntryFailed: boolean
}

type Cell = string | number

function buildRows({ bill, items, purchaseEntry, purchaseEntryFailed }: NmwBillExportData): Cell[][] {
  const purchaseStatus: PurchaseStatus = purchaseEntryFailed ? 'error' : (purchaseEntry?.purchase_status ?? bill.purchase_status)
  const entryNo = purchaseEntry?.entry_no ?? ''
  const entryDate = purchaseEntry?.entry_date ?? ''
  const lines = items.length ? items : [null]
  return lines.map((item) => [
    bill.bill_no ?? '',
    bill.bill_type ?? '',
    bill.bill_date ?? '',
    bill.dest_store_code ?? '',
    Number(bill.bill_amount ?? 0),
    item?.product_code ?? '',
    item?.product_name ?? '',
    item?.batch_no ?? '',
    item?.expiry_date ?? '',
    item ? Number(item.qty ?? 0) : '',
    item ? Number(item.free_qty ?? 0) : '',
    item ? Number(item.mrp ?? 0) : '',
    item ? Number(item.rate ?? 0) : '',
    item ? Number(item.discount_percentage ?? 0) : '',
    item?.packing ?? '',
    item?.sublocation ?? '',
    item ? Number(item.amount ?? 0) : '',
    purchaseStatusLabel(purchaseStatus),
    entryNo,
    entryDate,
  ])
}

function csvCell(value: Cell): string {
  const s = String(value ?? '')
  return /["\r\n,]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)
}

export function exportNmwBillCsv(data: NmwBillExportData, fileName: string) {
  const rows = buildRows(data)
  const text = [COLUMNS.join(','), ...rows.map((r) => r.map(csvCell).join(','))].join('\r\n')
  downloadBlob(new Blob([text], { type: 'text/csv;charset=utf-8;' }), fileName.endsWith('.csv') ? fileName : `${fileName}.csv`)
}

export async function exportNmwBillExcel(data: NmwBillExportData, fileName: string) {
  const rows = buildRows(data)
  const wb = new ExcelJS.Workbook()
  wb.creator = 'Axythic'
  wb.created = new Date()
  const ws = wb.addWorksheet('Bill', { views: [{ state: 'frozen', ySplit: 1 }] })
  const thin = { style: 'thin' as const, color: { argb: 'FFB0B0B0' } }
  const border = { top: thin, left: thin, bottom: thin, right: thin }

  const header = ws.addRow(COLUMNS)
  header.eachCell((cell) => {
    cell.font = { bold: true }
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEFEFEF' } }
    cell.border = border
  })

  rows.forEach((r) => {
    const row = ws.addRow(r)
    row.eachCell((cell) => {
      cell.border = border
    })
  })

  ws.columns.forEach((col, i) => {
    let maxLen = COLUMNS[i].length
    for (const r of rows) {
      const v = r[i]
      if (v != null && v !== '') maxLen = Math.max(maxLen, String(v).length)
    }
    col.width = Math.min(Math.max(maxLen + 2, 8), 40)
  })

  const buf = await wb.xlsx.writeBuffer()
  downloadBlob(
    new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
    fileName.endsWith('.xlsx') ? fileName : `${fileName}.xlsx`,
  )
}
