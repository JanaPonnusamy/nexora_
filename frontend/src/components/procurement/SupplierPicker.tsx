import { useEffect, useState } from 'react'
import type { SupplierRow } from '../../types/procurement'
import { procurementService } from '../../services/procurementService'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'

/** Compact supplier search + select used by the Supplier Purchasing and
 *  Supplier Available Stock modes. */
export function SupplierPicker({
  tenantId,
  storeId,
  value,
  onPick,
}: {
  tenantId: string
  storeId?: string
  value: SupplierRow | null
  onPick: (supplier: SupplierRow | null) => void
}) {
  const [q, setQ] = useState('')
  const debounced = useDebouncedValue(q)
  const [rows, setRows] = useState<SupplierRow[]>([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const term = debounced.trim()
    if (!term) {
      setRows([])
      return
    }
    let live = true
    procurementService
      .searchSuppliers(tenantId, term, storeId)
      .then((r) => live && setRows(r))
      .catch(() => live && setRows([]))
    return () => {
      live = false
    }
  }, [tenantId, storeId, debounced])

  if (value) {
    return (
      <div className="pm-suppick pm-suppick--picked">
        <i className="bi bi-truck" aria-hidden="true" />
        <span className="pm-suppick__name">{value.supplier_name ?? value.supplier_code}</span>
        <span className="pm-suppick__code">{value.supplier_code}</span>
        <button className="pm-iconbtn" title="Change supplier" onClick={() => { onPick(null); setQ('') }}>
          <i className="bi bi-x-lg" />
        </button>
      </div>
    )
  }

  return (
    <div className="pm-suppick">
      <span className="sx-search">
        <i className="bi bi-truck" aria-hidden="true" />
        <input
          type="search"
          value={q}
          placeholder="Search supplier…"
          aria-label="Search supplier"
          onChange={(e) => { setQ(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
        />
      </span>
      {open && rows.length > 0 && (
        <ul className="pm-suppick__menu">
          {rows.map((s) => (
            <li key={s.supplier_code}>
              <button onClick={() => { onPick(s); setOpen(false) }}>
                <span>{s.supplier_name ?? s.supplier_code}</span>
                <span className="pm-suppick__code">{s.supplier_code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
