// Stock Check Report -> Excel export. Client-side only. Keeps the existing
// row payload/merge-per-product layout, but upgrades the workbook styling so
// the exported sheet opens as a clean stock-count worksheet with correct
// Excel data types, widths, alignment, borders, and freeze panes.
import ExcelJS from 'exceljs'
import type { StockCheckRow } from '../../types/stockCheckReport'
import { groupStockCheckRows, isExpired } from './stockCheckGrouping'

const CM_TO_IN = 1 / 2.54

const DATA_ROW_HEIGHT = 20
const HEADER_ROW_HEIGHT = 22
const HEADER_FILL: ExcelJS.Fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF2F2F2' } }
const thin = { style: 'thin' as const, color: { argb: 'FFD9D9D9' } }
const border = { top: thin, left: thin, bottom: thin, right: thin }

type ColumnKey =
  | 'productCode'
  | 'sublocation'
  | 'productName'
  | 'totalStock'
  | 'batchStock'
  | 'countedStock'
  | 'expiry'
  | 'mrp'
  | 'saleUnit'
  | 'batchCode'
  | 'pday'
  | 'sday'

const COLUMNS: Array<{
  header: string
  key: ColumnKey
  minWidth: number
  alignment: Partial<ExcelJS.Alignment>
  numFmt?: string
}> = [
  { header: 'Product Code', key: 'productCode', minWidth: 12, alignment: { horizontal: 'left', vertical: 'middle' }, numFmt: '@' },
  { header: 'Sublocation', key: 'sublocation', minWidth: 10, alignment: { horizontal: 'left', vertical: 'middle' } },
  { header: 'Product Name', key: 'productName', minWidth: 45, alignment: { horizontal: 'left', vertical: 'middle' } },
  { header: 'Total Stock', key: 'totalStock', minWidth: 12, alignment: { horizontal: 'right', vertical: 'middle' }, numFmt: '0' },
  { header: 'Stock', key: 'batchStock', minWidth: 10, alignment: { horizontal: 'right', vertical: 'middle' }, numFmt: '0' },
  { header: 'Counted Stock', key: 'countedStock', minWidth: 14, alignment: { horizontal: 'right', vertical: 'middle' }, numFmt: '0' },
  { header: 'Expiry Date', key: 'expiry', minWidth: 12, alignment: { horizontal: 'center', vertical: 'middle' }, numFmt: 'mmm-yyyy' },
  { header: 'MRP', key: 'mrp', minWidth: 10, alignment: { horizontal: 'right', vertical: 'middle' }, numFmt: '0.00' },
  { header: 'Sale Unit', key: 'saleUnit', minWidth: 8, alignment: { horizontal: 'center', vertical: 'middle' } },
  { header: 'Batch', key: 'batchCode', minWidth: 12, alignment: { horizontal: 'center', vertical: 'middle' } },
  { header: 'PDay', key: 'pday', minWidth: 8, alignment: { horizontal: 'right', vertical: 'top' }, numFmt: '0' },
  { header: 'SDay', key: 'sday', minWidth: 8, alignment: { horizontal: 'right', vertical: 'top' }, numFmt: '0' },
]

export async function exportStockCheckExcel({
  rows,
  storeCode,
  sublocationFrom,
  sublocationTo,
}: {
  rows: StockCheckRow[]
  storeCode: string
  sublocationFrom: string
  sublocationTo: string
}) {
  if (rows.length === 0) return

  const wb = new ExcelJS.Workbook()
  wb.creator = 'Nexora Stock Check Report'
  wb.created = new Date()
  const ws = wb.addWorksheet('stock_Check', { views: [{ state: 'frozen', ySplit: 1 }] })

  ws.columns = COLUMNS.map((c) => ({ header: c.header, key: c.key, width: c.minWidth }))

  const headerRow = ws.getRow(1)
  headerRow.height = HEADER_ROW_HEIGHT
  headerRow.font = { bold: true }
  headerRow.alignment = { vertical: 'middle', horizontal: 'center' }
  headerRow.eachCell((cell) => {
    cell.border = border
    cell.fill = HEADER_FILL
    cell.alignment = { vertical: 'middle', horizontal: 'center', wrapText: false }
  })

  const expiredFill: ExcelJS.Fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFFC7CE' } }
  const expiredFont: Partial<ExcelJS.Font> = { color: { argb: 'FF9C0006' }, bold: true }
  const nmFill: ExcelJS.Fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFFF2CC' } }
  const widthTracker = buildWidthTracker()

  const groups = groupStockCheckRows(rows)

  groups.forEach((sub) => {
    for (const product of sub.products) {
      const startRow = ws.rowCount + 1
      product.rows.forEach((r) => {
        const batchCode = (r.batch_code ?? '').slice(-5)
        const excelRow = ws.addRow({
          productCode: r.product_code ?? '',
          sublocation: r.sublocation ?? '',
          productName: (r.product_name ?? '') + (product.nonMoving ? ' (NM)' : ''),
          totalStock: r.total_stock,
          batchStock: r.batch_stock,
          countedStock: null,
          expiry: parseExcelDate(r.expiry_date),
          mrp: r.mrp,
          saleUnit: toExcelDisplayValue(r.sale_unit),
          batchCode: toExcelDisplayValue(batchCode),
          pday: r.purchase_days,
          sday: r.sale_days,
        })
        excelRow.height = DATA_ROW_HEIGHT
        applyRowStyles(excelRow)
        applyNumericTextMask(excelRow.getCell('saleUnit'), r.sale_unit)
        applyNumericTextMask(excelRow.getCell('batchCode'), batchCode)
        recordRowWidths(widthTracker, excelRow)
        if (isExpired(r.expiry_date)) {
          excelRow.getCell('expiry').fill = expiredFill
          excelRow.getCell('expiry').font = expiredFont
        }
        if (product.nonMoving) {
          excelRow.getCell('productName').fill = nmFill
        }
      })
      const endRow = ws.rowCount
      if (endRow > startRow) {
        for (const key of ['productCode', 'sublocation', 'productName', 'totalStock', 'pday', 'sday'] as ColumnKey[]) {
          ws.mergeCells(startRow, colIndex(key), endRow, colIndex(key))
          styleCell(ws.getCell(startRow, colIndex(key)), key)
        }
      }
    }
  })
  applyColumnWidths(ws, widthTracker)

  // ----- Page setup: copied from the legacy sheet's Print > Page Setup -----
  ws.pageSetup = {
    ...ws.pageSetup,
    paperSize: 9, // A4
    orientation: 'portrait',
    horizontalCentered: true,
    verticalCentered: false,
    fitToPage: false,
    scale: 100,
    margins: {
      // Top is taller than the legacy 0.9cm so a small header font (below)
      // never collides with row 1 — header text prints inside this gap.
      top: 1.3 * CM_TO_IN,
      bottom: 0.9 * CM_TO_IN,
      left: 0.8 * CM_TO_IN,
      right: 0.8 * CM_TO_IN,
      header: 0.5 * CM_TO_IN,
      footer: 0.8 * CM_TO_IN,
    },
    printTitlesRow: '1:1',
  }
  ws.headerFooter = {
    oddHeader: `&8&CStock Check Report — ${storeCode} — Sublocation ${sublocationFrom} to ${sublocationTo}`,
    oddFooter: '&L&D&C&P of &N&R&T',
  }

  const buf = await wb.xlsx.writeBuffer()
  const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `stock_check_${storeCode}_${sublocationFrom}-${sublocationTo}_${new Date().toISOString().slice(0, 10)}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}

function colIndex(key: ColumnKey): number {
  return COLUMNS.findIndex((c) => c.key === key) + 1
}

function buildWidthTracker(): Record<ColumnKey, number> {
  return COLUMNS.reduce(
    (acc, column) => {
      acc[column.key] = column.header.length
      return acc
    },
    {} as Record<ColumnKey, number>,
  )
}

function applyRowStyles(row: ExcelJS.Row) {
  COLUMNS.forEach((column) => {
    styleCell(row.getCell(column.key), column.key)
  })
}

function styleCell(cell: ExcelJS.Cell, key: ColumnKey) {
  const column = COLUMNS.find((item) => item.key === key)
  if (!column) return
  cell.border = border
  cell.alignment = { ...column.alignment, wrapText: false }
  if (column.numFmt && cell.value !== null && cell.value !== '') {
    cell.numFmt = column.numFmt
  }
}

function recordRowWidths(widthTracker: Record<ColumnKey, number>, row: ExcelJS.Row) {
  COLUMNS.forEach((column) => {
    const cell = row.getCell(column.key)
    const contentLength = displayLength(cell.value, column.key)
    widthTracker[column.key] = Math.max(widthTracker[column.key], contentLength)
  })
}

function applyColumnWidths(ws: ExcelJS.Worksheet, widthTracker: Record<ColumnKey, number>) {
  COLUMNS.forEach((column, index) => {
    const padding = column.key === 'productName' ? 4 : 2
    ws.getColumn(index + 1).width = Math.max(column.minWidth, widthTracker[column.key] + padding)
  })
}

function displayLength(value: ExcelJS.CellValue | null | undefined, key: ColumnKey): number {
  if (value === null || value === undefined) return 0
  if (value instanceof Date) return key === 'expiry' ? 10 : 0
  if (typeof value === 'number') {
    return key === 'mrp' ? value.toFixed(Number.isInteger(value) ? 0 : 2).length : `${Math.trunc(value)}`.length
  }
  if (typeof value === 'object' && 'richText' in value) {
    return value.richText.map((part) => part.text).join('').length
  }
  return `${value}`.length
}

function parseExcelDate(value: string | null): Date | null {
  if (!value) return null
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return null
  return new Date(year, month - 1, day)
}

function toExcelDisplayValue(value: string | null): string | number {
  const raw = `${value ?? ''}`.trim()
  if (!raw) return ''
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return raw
  return Number(raw)
}

function applyNumericTextMask(cell: ExcelJS.Cell, rawValue: string | null) {
  const raw = `${rawValue ?? ''}`.trim()
  if (!raw || !/^\d+$/.test(raw) || !/^0\d+$/.test(raw)) return
  cell.numFmt = '0'.repeat(raw.length)
}
