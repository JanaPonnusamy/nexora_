import { useEffect, useState } from 'react'
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

const DEFAULTS = { format: 'excel' as Format, columns: [] as string[], order_qty_header: 'Order Qty', sort_by: 'product_name' as SortBy, export_folder_path: null as string | null }

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function blobToUint8Array(blob: Blob): Promise<Uint8Array> {
  return new Uint8Array(await blob.arrayBuffer())
}

/**
 * Export Settings — format (Excel default / PDF / Image), which optional
 * columns to include (S.No / Product Name / Order Qty / MRP are always on),
 * a renameable Order Qty header, a sort-by, and (desktop app only) a folder
 * to save straight into. Choices are remembered PER SUPPLIER, server-side
 * (procurement.supplier_export_settings) — the dialog pre-fills with what
 * was used last time for this exact supplier, no re-configuring every export.
 * Excel is generated server-side with a genuinely supplier-editable Status +
 * Available Qty pair (sheet-protected) so the completed sheet can be sent
 * back and re-imported (see SupplierReplyImportDialog).
 */
export function ExportSettingsDialog({
  tenantId,
  storeId,
  refreshId,
  group,
  eq,
  onClose,
  notify,
}: {
  tenantId: string
  storeId: string
  refreshId: string
  group: SupplierQueueGroup
  eq: (l: SupplierQueueProduct) => number
  onClose: () => void
  notify: (kind: 'success' | 'danger', text: string) => void
}) {
  const [loading, setLoading] = useState(true)
  const [format, setFormat] = useState<Format>(DEFAULTS.format)
  const [columns, setColumns] = useState<Set<string>>(new Set(DEFAULTS.columns))
  const [orderQtyHeader, setOrderQtyHeader] = useState(DEFAULTS.order_qty_header)
  const [sortBy, setSortBy] = useState<SortBy>(DEFAULTS.sort_by)
  const [exportFolder, setExportFolder] = useState<string | null>(DEFAULTS.export_folder_path)
  const [busy, setBusy] = useState(false)

  const isElectron = typeof window !== 'undefined' && window.uninex?.isElectron === true

  useEffect(() => {
    let live = true
    setLoading(true)
    procurementService
      .supplierExportSettings(tenantId, storeId, group.supplier_code)
      .then((s) => {
        if (!live) return
        setFormat(s.format)
        setColumns(new Set(s.columns))
        setOrderQtyHeader(s.order_qty_header)
        setSortBy(s.sort_by)
        setExportFolder(s.export_folder_path)
      })
      .catch(() => {
        // Fall back to defaults — the supplier has never exported before.
      })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [tenantId, storeId, group.supplier_code])

  const toggleColumn = (key: string) =>
    setColumns((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const pickFolder = async () => {
    const picked = await window.uninex?.pickFolder()
    if (picked) setExportFolder(picked)
  }

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
      const filename = `PO_${group.supplier_code}_${new Date().toISOString().slice(0, 10)}.${ext}`

      let savedTo: string | null = null
      if (isElectron && exportFolder) {
        const data = await blobToUint8Array(blob)
        const result = await window.uninex?.saveFile(exportFolder, filename, data)
        if (result?.ok) savedTo = result.path ?? exportFolder
        else notify('danger', result?.error ?? 'Could not save to the chosen folder — downloaded instead.')
      }
      if (!savedTo) downloadBlob(blob, filename)

      // Remember this supplier's choices for next time — server-side, so any
      // device/browser opening this supplier's export sees the same setup.
      procurementService
        .saveSupplierExportSettings(tenantId, storeId, group.supplier_code, {
          format, columns: [...columns], order_qty_header: orderQtyHeader.trim() || 'Order Qty',
          sort_by: sortBy, export_folder_path: exportFolder,
        })
        .catch(() => { /* best-effort — the export itself already succeeded */ })

      notify('success', savedTo ? `Saved to ${savedTo}` : `Exported ${liveLines.length} line(s) as ${format.toUpperCase()}`)
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
        {loading ? (
          <div className="pm-modal__body"><div className="pm-sq__hint">Loading this supplier's export settings…</div></div>
        ) : (
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

          {isElectron && (
            <div className="pm-expset__section">
              <div className="pm-expset__label">Export Folder</div>
              <div className="pm-expset__folder">
                <input
                  className="pm-input pm-expset__folderinput"
                  value={exportFolder ?? ''}
                  readOnly
                  placeholder="Not set — falls back to the browser download"
                />
                <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={pickFolder}>
                  <i className="bi bi-folder2-open" /> Browse…
                </button>
                {exportFolder && (
                  <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => setExportFolder(null)} title="Clear folder">
                    <i className="bi bi-x-lg" />
                  </button>
                )}
              </div>
            </div>
          )}

          {format === 'excel' && (
            <div className="pm-expset__hint">
              <i className="bi bi-info-circle" /> The Excel sheet adds Status (Available / Partial / Not Available)
              and Available Qty columns for the supplier to fill in and send back — every other cell is locked.
            </div>
          )}
        </div>
        )}
        <footer className="pm-modal__foot">
          <span className="sx-dim">{liveLines.length} product(s)</span>
          <button className="pm-btn pm-btn--ghost" onClick={onClose}>Cancel</button>
          <button className="pm-btn pm-btn--primary" onClick={runExport} disabled={busy || loading}>
            <i className="bi bi-box-arrow-up" /> {busy ? 'Exporting…' : 'Export'}
          </button>
        </footer>
      </div>
    </>
  )
}
