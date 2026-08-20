import type { LabelSearchRow } from '../../types/labelExporter'

/**
 * A label item prepared for the print sheet — carries the original search-row
 * data plus user-editable overrides (quantity, custom MRP text, etc.).
 */
export interface PreparedLabelItem {
  product_code: string
  product_name: string
  unit_description: string | null
  box_number: string | null
  mrp: number
  total_stock: number
  sale_days: number | null
  purchase_days: number | null
  /** Number of labels to print for this product (default 1). */
  quantity: number
  /** Optional MRP override text shown on the label. */
  mrpText: string
}

/** Convert a raw search row into a PreparedLabelItem with sensible defaults. */
export function buildPreparedLabelItem(row: LabelSearchRow): PreparedLabelItem {
  return {
    product_code: row.product_code,
    product_name: row.product_name,
    unit_description: row.unit_description,
    box_number: row.box_number,
    mrp: row.mrp,
    total_stock: row.total_stock,
    sale_days: row.sale_days,
    purchase_days: row.purchase_days,
    quantity: 1,
    mrpText: row.mrp != null ? String(row.mrp) : '',
  }
}

export interface PrintSettings {
  widthMm: number
  heightMm: number
  columns: number
  gapMm: number
  fontSizePt: number
}

/**
 * Open a print-ready window with a grid of labels laid out per the user's
 * size / column settings. Uses window.print() so the browser's native print
 * dialog handles paper selection and scaling.
 */
export function printLabelSheet(items: PreparedLabelItem[], settings: PrintSettings): void {
  if (items.length === 0) return

  const { widthMm, heightMm, columns, gapMm, fontSizePt } = settings

  // Expand items by quantity
  const expanded: PreparedLabelItem[] = []
  items.forEach((item) => {
    const qty = Math.max(1, Number(item.quantity) || 1)
    for (let i = 0; i < qty; i++) expanded.push(item)
  })

  const labelHtml = expanded
    .map(
      (item) => `
      <div class="label" style="width:${widthMm}mm; height:${heightMm}mm; font-size:${fontSizePt}pt;">
        <div class="label-name">${escapeHtml(item.product_name)}</div>
        ${item.unit_description ? `<div class="label-unit">${escapeHtml(item.unit_description)}</div>` : ''}
        <div class="label-mrp">MRP: ₹${escapeHtml(item.mrpText || String(item.mrp))}</div>
      </div>`,
    )
    .join('\n')

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Label Sheet</title>
  <style>
    @page { margin: 5mm; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: Arial, Helvetica, sans-serif;
      display: flex;
      flex-wrap: wrap;
      gap: ${gapMm}mm;
      padding: 2mm;
    }
    .label {
      border: 0.5px solid #ccc;
      padding: 1.5mm;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: center;
      page-break-inside: avoid;
    }
    .label-name {
      font-weight: 700;
      line-height: 1.2;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
    .label-unit {
      font-size: 0.85em;
      color: #555;
      margin-top: 0.5mm;
    }
    .label-mrp {
      font-weight: 600;
      margin-top: auto;
    }
    @media print {
      .label { border-color: #000; }
    }
  </style>
</head>
<body style="max-width: ${columns * (widthMm + gapMm)}mm;">
${labelHtml}
</body>
</html>`

  const win = window.open('', '_blank')
  if (!win) return
  win.document.write(html)
  win.document.close()
  win.focus()
  // Give the browser a moment to render before triggering print
  setTimeout(() => win.print(), 400)
}

function escapeHtml(text: string): string {
  const el = document.createElement('span')
  el.textContent = text
  return el.innerHTML
}
