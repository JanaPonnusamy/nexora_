// ExcelJS export for the Expiry Stock report, laid out for A4 printing:
// A4 paper, fit-to-width, the header row repeated on every printed page, and a
// page footer carrying the report date (left) and "Page N of M" (right).
import ExcelJS from 'exceljs'
import type { ExpiryStockColumn } from '../../types/expiryStock'

const HEADER_FILL: ExcelJS.Fill = {
  type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEFEFEF' },
}
const TOTAL_FILL: ExcelJS.Fill = {
  type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF7F2E7' },
}
const CUT_FILL: ExcelJS.Fill = {
  type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFDE7E7' },
}
const thin = { style: 'thin' as const, color: { argb: 'FFB0B0B0' } }
const border = { top: thin, left: thin, bottom: thin, right: thin }

function numFmt(fmt: ExpiryStockColumn['format']): string | undefined {
  if (fmt === 'money') return '#,##0.00'
  if (fmt === 'int') return '#,##0'
  if (fmt === 'qty') return '#,##0.##'
  if (fmt === 'date') return 'dd-mmm-yyyy'
  return undefined
}

function value(raw: unknown, fmt: ExpiryStockColumn['format']): string | number | Date | null {
  if (raw === null || raw === undefined || raw === '') return null
  if (fmt === 'money' || fmt === 'int' || fmt === 'qty') {
    const n = Number(raw)
    return Number.isFinite(n) ? n : String(raw)
  }
  if (fmt === 'date') {
    const d = new Date(String(raw))
    return Number.isNaN(d.getTime()) ? String(raw) : d
  }
  return String(raw)
}

interface ExpiryStockExcelOpts {
  columns: ExpiryStockColumn[]
  rows: Record<string, unknown>[]
  summary: Record<string, unknown> | null
  sheetName: string
  fileName: string
  title?: string
  orientation?: 'portrait' | 'landscape'
}

async function buildBlob({
  columns,
  rows,
  summary,
  sheetName,
  title,
  orientation = 'landscape',
}: ExpiryStockExcelOpts): Promise<Blob> {
  const wb = new ExcelJS.Workbook()
  wb.creator = 'Axythic'
  wb.created = new Date()

  const ws = wb.addWorksheet(sheetName.slice(0, 31) || 'Sheet1', {
    views: [{ state: 'frozen', ySplit: title ? 2 : 1 }],
    pageSetup: {
      paperSize: 9, // A4
      orientation,
      fitToPage: true,
      fitToWidth: 1,
      fitToHeight: 0,
      horizontalCentered: true,
      margins: { left: 0.4, right: 0.4, top: 0.5, bottom: 0.6,
                 header: 0.3, footer: 0.3 },
    },
  })

  // Repeat the header row on every printed page.
  ws.pageSetup.printTitlesRow = title ? '2:2' : '1:1'

  // Footer: date on the left, page number on the right (on every page).
  ws.headerFooter = {
    oddFooter: '&L&"Calibri,Regular"&9Printed: &D &T&R&"Calibri,Regular"&9Page &P of &N',
    evenFooter: '&L&"Calibri,Regular"&9Printed: &D &T&R&"Calibri,Regular"&9Page &P of &N',
  }

  let r = 1
  if (title) {
    ws.mergeCells(1, 1, 1, columns.length)
    const t = ws.getCell(1, 1)
    t.value = title
    t.font = { bold: true, size: 12 }
    t.alignment = { horizontal: 'left', vertical: 'middle' }
    r = 2
  }

  const header = ws.getRow(r)
  columns.forEach((c, i) => {
    const cell = header.getCell(i + 1)
    cell.value = c.label
    cell.font = { bold: true }
    cell.fill = HEADER_FILL
    cell.border = border
    cell.alignment = { horizontal: c.align, vertical: 'middle', wrapText: true }
  })
  header.height = 20

  for (const row of rows) {
    r += 1
    const xr = ws.getRow(r)
    const cutting = row._cutting === true
    columns.forEach((c, i) => {
      const cell = xr.getCell(i + 1)
      cell.value = value(row[c.key], c.format)
      const nf = numFmt(c.format)
      if (nf) cell.numFmt = nf
      cell.border = border
      cell.alignment = { horizontal: c.align, vertical: 'middle' }
      if (cutting) cell.fill = CUT_FILL
    })
  }

  if (summary) {
    r += 1
    const xr = ws.getRow(r)
    columns.forEach((c, i) => {
      const cell = xr.getCell(i + 1)
      cell.value = value(summary[c.key], c.format)
      const nf = numFmt(c.format)
      if (nf) cell.numFmt = nf
      cell.font = { bold: true }
      cell.fill = TOTAL_FILL
      cell.border = border
      cell.alignment = { horizontal: c.align, vertical: 'middle' }
    })
  }

  columns.forEach((c, i) => {
    let maxLen = c.label.length
    for (const row of rows) {
      const v = row[c.key]
      if (v != null) maxLen = Math.max(maxLen, String(v).length)
    }
    ws.getColumn(i + 1).width = Math.min(Math.max(maxLen + 2, 8), 40)
  })

  const buf = await wb.xlsx.writeBuffer()
  return new Blob([buf], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}

export async function exportExpiryStockExcel(opts: ExpiryStockExcelOpts): Promise<void> {
  const blob = await buildBlob(opts)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = opts.fileName.endsWith('.xlsx') ? opts.fileName : `${opts.fileName}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}
