import { useEffect, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { stockCheckReportService } from '../../services/stockCheckReportService'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useListNav } from '../../hooks/useListNav'

/** Compact sublocation search + select, same pattern as SupplierPicker: type
 *  to search, arrow keys to move, Enter to pick. Used for both the From and
 *  To range boxes on the Stock Check Report. */
export function SublocationPicker({
  tenantId,
  storeId,
  value,
  onChange,
  placeholder,
  ariaLabel,
}: {
  tenantId: string
  storeId: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  ariaLabel: string
}) {
  const [q, setQ] = useState(value)
  const debounced = useDebouncedValue(q)
  const [rows, setRows] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const nav = useListNav(rows.length)

  useEffect(() => setQ(value), [value])

  useEffect(() => {
    const term = debounced.trim()
    if (!tenantId || !storeId) {
      setRows([])
      return
    }
    let live = true
    stockCheckReportService
      .searchSublocations(tenantId, storeId, term)
      .then((r) => {
        if (!live) return
        setRows(r.sublocations)
        nav.reset()
      })
      .catch(() => live && setRows([]))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, storeId, debounced])

  const pick = (v: string) => {
    setQ(v)
    onChange(v)
    setOpen(false)
  }

  const onKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setOpen(false)
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

  return (
    <div className="position-relative">
      <input
        className="form-control"
        style={{ width: '9rem' }}
        value={q}
        placeholder={placeholder}
        aria-label={ariaLabel}
        role="combobox"
        aria-expanded={open && rows.length > 0}
        onChange={(e) => {
          setQ(e.target.value)
          onChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {open && rows.length > 0 && (
        <ul
          className="list-group position-absolute"
          style={{ zIndex: 20, minWidth: '9rem', maxHeight: '14rem', overflowY: 'auto' }}
        >
          {rows.map((r, i) => (
            <li key={r} ref={nav.itemRef(i)}>
              <button
                type="button"
                className={`list-group-item list-group-item-action py-1 px-2 small${i === nav.active ? ' active' : ''}`}
                onMouseEnter={() => nav.setActive(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(r)}
              >
                {r}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
