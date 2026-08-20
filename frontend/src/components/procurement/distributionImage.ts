import type { DistributionRunItemProduct } from '../../types/procurement'

/** Renders a NEXORA Platform supplier-stock-distribution report as a PNG
 *  File, from the actual generated rows of one run item — used for the
 *  "Send WhatsApp Image" action. No mock data: caller passes the rows read
 *  back from that item's already-generated Excel file. */
export async function buildDistributionImage(opts: {
  sourceStoreCode: string
  targetStoreCode: string
  targetStoreName: string
  runDate: string
  rows: DistributionRunItemProduct[]
}): Promise<File> {
  const { sourceStoreCode, targetStoreCode, targetStoreName, runDate, rows } = opts

  const width = 900
  const rowHeight = 28
  const headerHeight = 190
  const footerHeight = 70
  const visibleRows = rows.slice(0, 60)
  const height = headerHeight + visibleRows.length * rowHeight + footerHeight + (rows.length > visibleRows.length ? 32 : 0)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas not supported in this browser')

  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, height)

  ctx.fillStyle = '#4f46e5'
  ctx.fillRect(0, 0, width, 96)
  ctx.fillStyle = '#ffffff'
  ctx.font = 'bold 22px Segoe UI, Arial'
  ctx.fillText('NEXORA PLATFORM', 24, 38)
  ctx.font = 'bold 16px Segoe UI, Arial'
  ctx.fillText('SUPPLIER STOCK DISTRIBUTION', 24, 64)
  ctx.font = '13px Segoe UI, Arial'
  ctx.fillText(`Source: ${sourceStoreCode}    Target: ${targetStoreCode} — ${targetStoreName}    Date: ${runDate}`, 24, 86)

  let y = 96 + 34
  ctx.fillStyle = '#111827'
  ctx.font = 'bold 14px Segoe UI, Arial'
  ctx.fillText('Product', 24, y)
  ctx.fillText('Qty', width - 220, y)
  ctx.fillText('Rack', width - 120, y)
  y += 10
  ctx.strokeStyle = '#e5e7eb'
  ctx.beginPath()
  ctx.moveTo(24, y)
  ctx.lineTo(width - 24, y)
  ctx.stroke()
  y += 20

  ctx.font = '13px Segoe UI, Arial'
  visibleRows.forEach((row, i) => {
    ctx.fillStyle = i % 2 === 0 ? '#111827' : '#374151'
    const name = row.name && row.name.length > 46 ? `${row.name.slice(0, 43)}...` : (row.name || row.code)
    ctx.fillText(name, 24, y)
    ctx.fillText(String(row.stock ?? 0), width - 220, y)
    ctx.fillText(row.rack || '—', width - 120, y)
    y += rowHeight
  })

  if (rows.length > visibleRows.length) {
    ctx.fillStyle = '#6b7280'
    ctx.font = 'italic 12px Segoe UI, Arial'
    ctx.fillText(`+ ${rows.length - visibleRows.length} more product(s) — see full Excel export`, 24, y)
    y += 32
  }

  const allTotalQty = rows.reduce((sum, r) => sum + (Number(r.stock) || 0), 0)
  ctx.strokeStyle = '#e5e7eb'
  ctx.beginPath()
  ctx.moveTo(24, y)
  ctx.lineTo(width - 24, y)
  ctx.stroke()
  y += 26
  ctx.fillStyle = '#111827'
  ctx.font = 'bold 13px Segoe UI, Arial'
  ctx.fillText(`Total Products: ${rows.length}`, 24, y)
  ctx.fillText(`Total Quantity: ${allTotalQty}`, width - 220, y)

  const blob: Blob = await new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not render image'))), 'image/png')
  })
  return new File([blob], `${sourceStoreCode}_Stock_${targetStoreCode}_${runDate}.png`, { type: 'image/png' })
}
