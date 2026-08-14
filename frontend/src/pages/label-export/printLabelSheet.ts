import type { LabelSearchRow } from '../../types/labelExporter'

export interface PreparedLabelItem {
  product_code: string
  product_name: string
  unit_description: string
  sale_unit: number
  mrp: number
  current_sublocation: string
  quantity: number
}

export interface LabelPrintSettings {
  widthMm: number
  heightMm: number
  columns: number
  gapMm: number
  fontSizePt: number
}

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

export function buildPreparedLabelItem(row: LabelSearchRow): PreparedLabelItem {
  return {
    product_code: row.product_code ?? '',
    product_name: row.product_name ?? '',
    unit_description: row.unit_description ?? '',
    sale_unit: row.sale_unit ?? 0,
    mrp: row.mrp ?? 0,
    current_sublocation: row.current_sublocation ?? '',
    quantity: 1,
  }
}

export function printLabelSheet(items: PreparedLabelItem[], settings: LabelPrintSettings) {
  const expanded = items
    .slice()
    .sort((a, b) => a.product_name.localeCompare(b.product_name))
    .flatMap((item) => Array.from({ length: Math.max(1, item.quantity) }, () => item))

  if (expanded.length === 0) return

  const labelHtml = expanded
    .map(
      (item) => `
        <div class="label">
          <div class="name">${escapeHtml(item.product_name)}</div>
          <div class="meta">${escapeHtml(item.product_code)}</div>
          <div class="meta">${escapeHtml(item.unit_description || '-')}</div>
          <div class="meta">SU: ${escapeHtml(String(item.sale_unit))}</div>
          <div class="meta">MRP: ${escapeHtml(String(item.mrp || '0'))}</div>
          <div class="sub">SubLoc: ${escapeHtml(item.current_sublocation || '-')}</div>
        </div>`,
    )
    .join('')

  const html = `<!doctype html>
  <html>
    <head>
      <meta charset="utf-8" />
      <title>Label Export</title>
      <style>
        @page { size: A4 portrait; margin: 8mm; }
        * { box-sizing: border-box; }
        body { margin: 0; font-family: Arial, sans-serif; }
        .sheet {
          display: grid;
          grid-template-columns: repeat(${settings.columns}, ${settings.widthMm}mm);
          gap: ${settings.gapMm}mm;
          align-content: start;
        }
        .label {
          width: ${settings.widthMm}mm;
          min-height: ${settings.heightMm}mm;
          border: 0.3mm solid #111827;
          padding: 2.2mm;
          overflow: hidden;
          break-inside: avoid;
        }
        .name {
          font-size: ${settings.fontSizePt + 1}pt;
          font-weight: 700;
          line-height: 1.15;
          margin-bottom: 1.2mm;
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .meta, .sub {
          font-size: ${settings.fontSizePt}pt;
          line-height: 1.2;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .sub {
          margin-top: 1.5mm;
          font-weight: 700;
        }
      </style>
    </head>
    <body>
      <div class="sheet">${labelHtml}</div>
      <script>window.print()</script>
    </body>
  </html>`

  const popup = window.open('', '_blank', 'noopener,noreferrer,width=1200,height=900')
  if (!popup) return
  popup.document.open()
  popup.document.write(html)
  popup.document.close()
}
