import { useState } from 'react'
import type { SupplierQueueGroup, SupplierQueueProduct } from './SupplierQueuePanel'
import { procurementService } from '../../services/procurementService'

type Format = 'excel' | 'pdf' | 'image'
type SortBy = 'product_name' | 'sub_location' | 'unit_description'

const OPTIONAL_COLUMNS: { key: string; label: string }[] = [
  { key: 'ptr', label: 'PTR' },
  { key: 'cost', label: 'Cost' },
  { key: 'offer', label: 'Offer' },
  { key: 'discount_pct', label: 'Dis %' },
  { key: 'product_code', label: 'Product Code' },
]

const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: 'product_name', label: 'Product Name' },
  { value: 'sub_location', label: 'Sub Location' },
  { value: 'unit_description', label: 'Unit Description' },
]

const STORAGE_KEY = 'pm-export-settings-v1'

interface SavedSettings {
  format: Format
  columns: string[]
  order_qty_header: string
  sort_by: SortBy
}

function loadSaved(): SavedSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { format: 'excel', columns: [], order_qty_header: 'Order Qty', sort_by: 'product_name', ...JSON.parse(raw) }
  } catch {
    // ignore corrupt/blocked storage — fall through to defaults
  }
  return { format: 'excel', columns: [], order_qty_header: 'Order Qty', sort_by: 'product_name' }
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Export Settings — format (Excel default / PDF / Image), which optional
 * columns to include (S.No / Product Name / Order Qty / MRP are always on),
 * a renameable Order Qty header, and a sort-by for the printed order. Excel
 * is generated server-side with a genuinely supplier-editable Status +
 * Available Qty pair (sheet-protected) so the completed sheet can be sent
 * back and re-imported (see SupplierReplyImportDialog).
 */
export function ExportSettingsDialog({
  tenantId,
  refreshId,
  group,
  eq,
  onClose,
  notify,
}: {
  tenantId: string
  refreshId: string
  group: SupplierQueueGroup
  eq: (l: SupplierQueueProduct) => number
  onClose: () => void
  notify: (kind: 'success' | 'danger', text: string) => void
}) {
  const saved = loadSaved()
  const [format, setFormat] = useState<Format>(saved.format)
  const [columns, setColumns] = useState<Set<string>>(new Set(saved.columns))
  const [orderQtyHeader, setOrderQtyHeader] = useState(saved.order_qty_header)
  const [sortBy, setSortBy] = useState<SortBy>(saved.sort_by)
  const [busy, setBusy] = useState(false)

  const toggleColumn = (key: string) =>
    setColumns((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const liveLines = group.lines.filter((l) => l.exported || eq(l) > 0)

  const runExport = async () => {
    if (liveLines.length === 0) {
      notify('danger', 'No products to export for this supplier.')
      return
    }
    setBusy(true)
    try {
      const opts = {
        items: liveLines.map((l) => ({ assignment_id: l.assignment_id, qty: l.exported ? l.final_qty : eq(l) })),
        format,
        columns: [...columns],
        order_qty_header: orderQtyHeader.trim() || 'Order Qty',
        sort_by: sortBy,
        supplier_code: group.supplier_code,
      }
      const blob = await procurementService.exportDocument(tenantId, refreshId, opts)
      const ext = format === 'excel' ? 'xlsx' : format === 'pdf' ? 'pdf' : 'png'
      downloadBlob(blob, `PO_${group.supplier_code}_${new Date().toISOString().slice(0, 10)}.${ext}`)
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ format, columns: [...columns], order_qty_header: orderQtyHeader, sort_by: sortBy }),
      )
      notify('success', `Exported ${liveLines.length} line(s) as ${format.toUpperCase()}`)
      onClose()
    } catch (e) {
      notify('danger', e instanceof Error ? e.message : 'Export failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="pm-drawer__backdrop" onClick={onClose} />
      <div className="pm-modal" role="dialog" aria-label="Export Settings">
        <header className="pm-modal__head">
          <h5 className="mb-0"><i className="bi bi-file-earmark-arrow-down me-2" />Export Settings — {group.supplier_name ?? group.supplier_code}</h5>
          <button className="btn-close" aria-label="Close" onClick={onClose} />
        </header>
        <div className="pm-modal__body">
          <div className="pm-expset__section">
            <div className="pm-expset__label">Format</div>
            <div className="pm-expset__formats">
              {(['excel', 'pdf', 'image'] as Format[]).map((f) => (
                <label key={f} className={`pm-expset__formatopt${format === f ? ' pm-expset__formatopt--on' : ''}`}>
                  <input type="radio" name="pm-expset-format" checked={format === f} onChange={() => setFormat(f)} />
                  {f === 'excel' ? 'Excel (default)' : f.toUpperCase()}
                </label>
              ))}
            </div>
          </div>

          <div className="pm-expset__section">
            <div className="pm-expset__label">Columns</div>
            <div className="pm-expset__cols">
              <label className="pm-chk pm-expset__mandatory"><input type="checkbox" checked disabled /> S.No</label>
              <label className="pm-chk pm-expset__mandatory"><input type="checkbox" checked disabled /> Product Name</label>
              <span className="pm-expset__ordercol">
                <label className="pm-chk pm-expset__mandatory"><input type="checkbox" checked disabled /></label>
                <input
                  className="pm-input pm-expset__headerinput"
                  value={orderQtyHeader}
                  onChange={(e) => setOrderQtyHeader(e.target.value)}
                  aria-label="Order Qty column header"
                  maxLength={40}
                />
                <span className="sx-dim">(Order Qty column — green)</span>
              </span>
              <label className="pm-chk pm-expset__mandatory"><input type="checkbox" checked disabled /> MRP</label>
              {OPTIONAL_COLUMNS.map((c) => (
                <label key={c.key} className="pm-chk">
                  <input type="checkbox" checked={columns.has(c.key)} onChange={() => toggleColumn(c.key)} />
                  {c.label}
                </label>
              ))}
            </div>
          </div>

          <div className="pm-expset__section">
            <div className="pm-expset__label">Sort By</div>
            <select className="sx-select" value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)}>
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {format === 'excel' && (
            <div className="pm-expset__hint">
              <i className="bi bi-info-circle" /> The Excel sheet adds Status (Available / Partial / Not Available)
              and Available Qty columns for the supplier to fill in and send back — every other cell is locked.
            </div>
          )}
        </div>
        <footer className="pm-modal__foot">
          <span className="sx-dim">{liveLines.length} product(s)</span>
          <button className="pm-btn pm-btn--ghost" onClick={onClose}>Cancel</button>
          <button className="pm-btn pm-btn--primary" onClick={runExport} disabled={busy}>
            <i className="bi bi-box-arrow-up" /> {busy ? 'Exporting…' : 'Export'}
          </button>
        </footer>
      </div>
    </>
  )
}
