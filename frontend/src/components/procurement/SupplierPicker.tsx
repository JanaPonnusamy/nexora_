import { useEffect, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { SupplierRow } from '../../types/procurement'
import { procurementService } from '../../services/procurementService'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useListNav } from '../../hooks/useListNav'
import { money, num, date } from '../stock/format'

/** Per-supplier context shown in each search result, resolved from data already
 *  loaded for the current refresh (no extra query). `creditActive` is undefined
 *  when no credit source exists in the current schema. */
export interface SupplierPickMeta {
  assignedProducts: number
  purchaseValue: number
  status: string
  creditActive?: boolean | null
}

/** Compact supplier search + select used by the Supplier Purchasing and
 *  Supplier Available Stock modes.
 *
 *  Keyboard-first (no mouse required): the first result auto-highlights after a
 *  search; ↓/↑ move the highlight, Enter selects it, Esc closes the results, and
 *  Tab hands focus back to the product grid (via `onReturnToGrid`). */
export function SupplierPicker({
  tenantId,
  storeId,
  value,
  onPick,
  onReturnToGrid,
  metaOf,
}: {
  tenantId: string
  storeId?: string
  value: SupplierRow | null
  onPick: (supplier: SupplierRow | null) => void
  onReturnToGrid?: () => void
  metaOf?: (supplierCode: string) => SupplierPickMeta | undefined
}) {
  const [q, setQ] = useState('')
  const debounced = useDebouncedValue(q)
  const [rows, setRows] = useState<SupplierRow[]>([])
  const [open, setOpen] = useState(false)
  // Highlighted result index (keyboard) + auto-scroll — shared with every
  // other search dropdown in this module (ManualProductModal's product
  // search) via useListNav, so the index/scroll mechanics aren't duplicated.
  const nav = useListNav(rows.length)

  useEffect(() => {
    const term = debounced.trim()
    if (!term) {
      setRows([])
      return
    }
    let live = true
    procurementService
      .searchSuppliers(tenantId, term, storeId)
      .then((r) => {
        if (!live) return
        setRows(r)
        nav.reset() // auto-highlight the first result
        setOpen(true)
      })
      .catch(() => live && setRows([]))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, storeId, debounced])

  // A pick is about to unmount this input (renders the "picked" badge
  // instead) — hand focus somewhere real (the grid) rather than letting it
  // fall off into the void, so the keyboard-only flow never loses focus.
  const pick = (s: SupplierRow) => {
    onPick(s)
    setOpen(false)
    onReturnToGrid?.()
  }

  const onKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      nav.reset() // clear the highlight; typed text and input focus are untouched
      return
    }
    if (e.key === 'Tab') {
      if (e.shiftKey) return // let the browser move focus to the previous control
      // Accept the highlighted result before leaving, same as Enter — never
      // silently drop a highlighted-but-uncommitted choice. onReturnToGrid is
      // called exactly once below, whether or not a result was accepted.
      if (open && rows.length > 0) {
        const chosen = rows[nav.active]
        if (chosen) onPick(chosen)
      }
      setOpen(false)
      if (onReturnToGrid) {
        e.preventDefault()
        onReturnToGrid()
      }
      return
    }
    if (!open || rows.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      nav.moveNext()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      nav.movePrev()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const chosen = rows[nav.active]
      if (chosen) pick(chosen)
    }
  }

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
          role="combobox"
          aria-expanded={open && rows.length > 0}
          aria-controls="pm-suppick-menu"
          aria-activedescendant={open && rows.length > 0 ? `pm-suppick-opt-${nav.active}` : undefined}
          onChange={(e) => { setQ(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </span>
      {open && rows.length > 0 && (
        <ul className="pm-suppick__menu" id="pm-suppick-menu" role="listbox">
          {rows.map((s, i) => {
            const m = metaOf?.(s.supplier_code)
            return (
              <li key={s.supplier_code} id={`pm-suppick-opt-${i}`} role="option" aria-selected={i === nav.active} ref={nav.itemRef(i)}>
                <button
                  className={`pm-suppick__row${i === nav.active ? ' pm-suppick__opt--active' : ''}`}
                  onMouseEnter={() => nav.setActive(i)}
                  onClick={() => pick(s)}
                >
                  <span className="pm-suppick__line1">
                    <span className="pm-suppick__nm">{s.supplier_name ?? s.supplier_code}</span>
                    <span className="pm-suppick__code">{s.supplier_code}</span>
                  </span>
                  {m && (
                    <span className="pm-suppick__meta">
                      <span>{num(m.assignedProducts)} assigned</span>
                      <span>{m.purchaseValue > 0 ? money(m.purchaseValue) : '—'}</span>
                      <span>Last {date(s.last_grn_date)}</span>
                      <span className={`pm-suppick__st pm-suppick__st--${m.status.toLowerCase().replace(/\s+/g, '')}`}>{m.status}</span>
                      <span>Credit {m.creditActive == null ? '—' : m.creditActive ? 'Active' : 'No'}</span>
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
