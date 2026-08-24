import { useEffect, useMemo, useRef, useState } from 'react'
import type { SupplierListItem } from '../../types/legacyOrder'
import { useListNav } from '../../hooks/useListNav'

/** Searchable supplier picker for the Order Workspace toolbar.
 *
 *  The native <select> it replaces only supported first-letter jump navigation,
 *  which is unusable with hundreds of suppliers under one letter. This filters
 *  the already-loaded supplier list as you type (name OR code, substring match)
 *  and is keyboard-first: ↓ opens/next, ↑ prev, Enter selects, Esc closes.
 *  No extra backend call — `suppliers` is the full list already fetched by the
 *  page for the current store. */
export function SupplierSearchSelect({
  suppliers,
  value,
  onChange,
  disabled = false,
}: {
  suppliers: SupplierListItem[]
  value: SupplierListItem | null
  onChange: (supplier: SupplierListItem | null) => void
  disabled?: boolean
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  const term = q.trim().toLowerCase()
  const matches = useMemo(() => {
    const list = !term
      ? suppliers
      : suppliers.filter((s) =>
        s.supplier_name.toLowerCase().includes(term)
        || s.supplier_code.toLowerCase().includes(term))
    return list.slice(0, 50)
  }, [suppliers, term])

  const nav = useListNav(matches.length)

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown, true)
    return () => document.removeEventListener('pointerdown', onDown, true)
  }, [open])

  const pick = (supplier: SupplierListItem | null) => {
    onChange(supplier)
    setQ('')
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { setOpen(false); return }
    if (e.key === 'ArrowDown' && !open) { setOpen(true); return }
    if (!open || matches.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); nav.moveNext() }
    else if (e.key === 'ArrowUp') { e.preventDefault(); nav.movePrev() }
    else if (e.key === 'Enter') {
      e.preventDefault()
      const chosen = matches[nav.active]
      if (chosen) pick(chosen)
    }
  }

  if (value) {
    return (
      <div className="lo-suppick lo-suppick--picked" ref={wrapRef}>
        <i className="bi bi-truck" aria-hidden="true" />
        <span className="lo-suppick__name" title={value.supplier_name}>{value.supplier_name}</span>
        <button type="button" className="lo-icon-btn" title="Change supplier" aria-label="Change supplier" disabled={disabled} onClick={() => pick(null)}>
          <i className="bi bi-x-lg" />
        </button>
      </div>
    )
  }

  return (
    <div className="lo-suppick" ref={wrapRef}>
      <i className="bi bi-search" aria-hidden="true" />
      <input
        type="search"
        value={q}
        placeholder="Search supplier…"
        aria-label="Search supplier"
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-controls="lo-suppick-menu"
        disabled={disabled}
        onChange={(e) => { setQ(e.target.value); setOpen(true); nav.reset() }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && matches.length > 0 && (
        <ul className="lo-suppick__menu" id="lo-suppick-menu" role="listbox">
          {matches.map((s, i) => (
            // Supplier codes (UnifiedSupplierCODE) can repeat or be "None", so
            // the index keeps React keys unique for this display-only list.
            <li key={`${s.supplier_code}-${i}`} role="option" aria-selected={i === nav.active} ref={nav.itemRef(i)}>
              <button
                type="button"
                className={`lo-suppick__row${i === nav.active ? ' is-active' : ''}`}
                onMouseEnter={() => nav.setActive(i)}
                onClick={() => pick(s)}
              >
                <span className="lo-suppick__nm">{s.supplier_name}</span>
                <span className="lo-suppick__code">{s.supplier_code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
