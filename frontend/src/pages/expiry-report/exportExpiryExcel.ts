// Generic ExcelJS export for any Expiry Report level. Takes the level's
// columns + rows (+ optional totals row) and writes a clean styled worksheet
// with correct data types, alignment, borders, a header fill and freeze panes.
import ExcelJS from 'exceljs'
import type { ExpiryColumn } from '../../types/expiryReport'

const HEADER_FILL: ExcelJS.Fill = {
  type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEFEFEF' },
}
const TOTAL_FILL: ExcelJS.Fill = {
  type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF7F2E7' },
}
const thin = { style: 'thin' as const, color: { argb: 'FFB0B0B0' } }
const border = { top: thin, left: thin, bottom: thin, right: thin }

function numFmt(fmt: ExpiryColumn['format']): string | undefined {
  if (fmt === 'money') return '#,##0.00'
  if (fmt === 'int') return '#,##0'
  if (fmt === 'date') return 'dd-mmm-yyyy'
  return undefined
}

function value(raw: unknown, fmt: ExpiryColumn['format']): string | number | Date | null {
  if (raw === null || raw === undefined || raw === '') return null
  if (fmt === 'money' || fmt === 'int') {
    const n = Number(raw)
    return Number.isFinite(n) ? n : String(raw)
  }
  if (fmt === 'date') {
    const d = new Date(String(raw))
    return Number.isNaN(d.getTime()) ? String(raw) : d
  }
  return String(raw)
}

export async function exportExpiryExcel({
  columns,
  rows,
  summary,
  sheetName,
  fileName,
  title,
}: {
  columns: ExpiryColumn[]
  rows: Record<string, unknown>[]
  summary: Record<string, unknown> | null
  sheetName: string
  fileName: string
  title?: string
}): Promise<void> {
  const wb = new ExcelJS.Workbook()
  wb.creator = 'Axythic'
  wb.created = new Date()
  const ws = wb.addWorksheet(sheetName.slice(0, 31) || 'Sheet1', {
    views: [{ state: 'frozen', ySplit: title ? 2 : 1 }],
  })

  let r = 1
  if (title) {
    ws.mergeCells(1, 1, 1, columns.length)
    const t = ws.getCell(1, 1)
    t.value = title
    t.font = { bold: true, size: 12 }
    t.alignment = { horizontal: 'left', vertical: 'middle' }
    r = 2
  }

  // Header row
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

  // Data rows
  for (const row of rows) {
    r += 1
    const xr = ws.getRow(r)
    columns.forEach((c, i) => {
      const cell = xr.getCell(i + 1)
      cell.value = value(row[c.key], c.format)
      const nf = numFmt(c.format)
      if (nf) cell.numFmt = nf
      cell.border = border
      cell.alignment = { horizontal: c.align, vertical: 'middle' }
    })
  }

  // Totals row
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

  // Column widths from content
  columns.forEach((c, i) => {
    const headerLen = c.label.length
    let maxLen = headerLen
    for (const row of rows) {
      const v = row[c.key]
      if (v != null) maxLen = Math.max(maxLen, String(v).length)
    }
    ws.getColumn(i + 1).width = Math.min(Math.max(maxLen + 2, 8), 40)
  })

  const buf = await wb.xlsx.writeBuffer()
  const blob = new Blob([buf], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName.endsWith('.xlsx') ? fileName : `${fileName}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}
