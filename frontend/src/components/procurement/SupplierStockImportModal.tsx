import { useEffect, useMemo, useState } from 'react'
import { procurementService } from '../../services/procurementService'
import type { SupplierStockPreview } from '../../types/procurement'

/**
 * Supplier stock Excel importer. Uploads the file for a preview (headers +
 * sample + a suggested map), lets the buyer map each Excel column to one of our
 * canonical columns — the three mandatory ones (product code, product name,
 * stock) must be matched — then imports, REPLACING the supplier's live stock.
 */
export function SupplierStockImportModal({
  tenantId,
  storeId,
  supplierCode,
  supplierName,
  file,
  actingUser,
  onClose,
  onImported,
}: {
  tenantId: string
  storeId: string
  supplierCode: string
  supplierName: string
  file: File
  actingUser: string
  onClose: () => void
  onImported: (inserted: number) => void
}) {
  const [preview, setPreview] = useState<SupplierStockPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setLoading(true)
    procurementService
      .supplierStockPreview(tenantId, storeId, supplierCode, file)
      .then((p) => {
        if (!live) return
        setPreview(p)
        setMapping({ ...p.suggested })
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : 'Could not read the file'))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [tenantId, storeId, supplierCode, file])

  // Each canonical target maps to at most one header (selecting it elsewhere
  // clears the previous holder).
  const assign = (header: string, value: string) =>
    setMapping((prev) => {
      const next: Record<string, string> = {}
      for (const [h, v] of Object.entries(prev)) {
        if (value && v === value && h !== header) continue // drop the old holder
        next[h] = v
      }
      next[header] = value
      return next
    })

  const mandatory = useMemo(
    () => (preview?.targets ?? []).filter((t) => t.mandatory).map((t) => t.value),
    [preview],
  )
  const assigned = useMemo(() => new Set(Object.values(mapping).filter(Boolean)), [mapping])
  const missing = mandatory.filter((m) => !assigned.has(m))

  const doImport = async () => {
    if (missing.length > 0) return
    setBusy(true)
    setError(null)
    try {
      const res = await procurementService.supplierStockImport(
        tenantId, storeId, supplierCode, file, mapping, actingUser || null,
      )
      onImported(res.inserted)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
      setBusy(false)
    }
  }

  return (
    <div className="pm-drawer__backdrop" style={{ zIndex: 1060 }} onClick={onClose}>
      <div className="pm-import" role="dialog" aria-label="Import supplier stock" onClick={(e) => e.stopPropagation()}>
        <header className="pm-import__head">
          <div>
            <h5 className="mb-0"><i className="bi bi-file-earmark-excel" /> Import Supplier Stock</h5>
            <div className="pm-import__sub">{supplierName} · {file.name}</div>
          </div>
          <button className="pm-iconbtn" onClick={onClose} aria-label="Close"><i className="bi bi-x-lg" /></button>
        </header>

        {loading ? (
          <div className="pm-import__msg">Reading file…</div>
        ) : error && !preview ? (
          <div className="pm-import__msg pm-import__msg--err">{error}</div>
        ) : preview ? (
          <>
            <div className="pm-import__hint">
              Match each column. <b>Product Code</b>, <b>Product Name</b> and <b>Stock</b> are required.
              Supplier code is taken from the selected supplier. Importing replaces this supplier's current stock.
            </div>

            <div className="pm-import__grid">
              <div className="pm-import__col">
                <div className="pm-import__coltitle">Column mapping</div>
                <table className="pm-import__map">
                  <thead><tr><th>Excel column</th><th>Maps to</th></tr></thead>
                  <tbody>
                    {preview.headers.map((h) => (
                      <tr key={h}>
                        <td className="pm-import__hdr">{h}</td>
                        <td>
                          <select
                            className="sx-select"
                            value={mapping[h] ?? ''}
                            onChange={(e) => assign(h, e.target.value)}
                          >
                            <option value="">— Ignore —</option>
                            {preview.targets.map((t) => (
                              <option key={t.value} value={t.value}>
                                {t.label}{t.mandatory ? ' *' : ''}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="pm-import__col">
                <div className="pm-import__coltitle">Preview</div>
                <div className="pm-import__samplewrap">
                  <table className="pm-import__sample">
                    <thead><tr>{preview.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
                    <tbody>
                      {preview.sample.map((row, i) => (
                        <tr key={i}>{preview.headers.map((_, j) => <td key={j}>{row[j] ?? ''}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {error && <div className="pm-import__msg pm-import__msg--err">{error}</div>}

            <footer className="pm-import__foot">
              {missing.length > 0 && (
                <span className="pm-import__warn">
                  Match required: {missing.map((m) => preview.targets.find((t) => t.value === m)?.label ?? m).join(', ')}
                </span>
              )}
              <div className="pm-import__actions">
                <button className="pm-btn pm-btn--ghost" onClick={onClose}>Cancel</button>
                <button className="pm-btn pm-btn--primary" disabled={busy || missing.length > 0} onClick={doImport}>
                  <i className="bi bi-upload" /> {busy ? 'Importing…' : 'Import & Replace'}
                </button>
              </div>
            </footer>
          </>
        ) : null}
      </div>
    </div>
  )
}
