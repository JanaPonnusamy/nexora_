import { useEffect, useMemo, useRef, useState } from 'react'
import { useListNav } from '../../hooks/useListNav'

/**
 * Compact, searchable box/location selector used *only while a New Loc cell
 * is being edited* — a manual override of a single product's box label,
 * bypassing the standard-box/SYP assignment engine (super-admin only, same
 * permission level as committing an assignment). Mirrors UnitPicker exactly:
 * type to filter, ↑/↓ to move, Enter to pick, Esc to cancel, and typing a
 * value that isn't in the list yet lets the reviewer commit it as new.
 */
export function LocationPicker({
  current,
  options,
  onPick,
  onCancel,
}: {
  current: string
  options: string[]
  onPick: (location: string) => void
  onCancel: () => void
}) {
  const [q, setQ] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const term = q.trim().toUpperCase()
  const matches = useMemo(() => {
    const list = term ? options.filter((loc) => loc.toUpperCase().includes(term)) : options
    // Let the reviewer commit a brand-new location that isn't in the list yet.
    if (term && !list.some((loc) => loc.toUpperCase() === term)) return [term, ...list].slice(0, 40)
    return list.slice(0, 40)
  }, [options, term])

  const nav = useListNav(matches.length)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const onDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) onCancel()
    }
    document.addEventListener('pointerdown', onDown, true)
    return () => document.removeEventListener('pointerdown', onDown, true)
  }, [onCancel])

  const commit = (location: string) => {
    const value = (location || '').trim().toUpperCase()
    if (value) onPick(value)
    else onCancel()
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Keep the grid's own key handler (Y/N/arrows) from also firing.
    e.stopPropagation()
    if (e.key === 'Escape') {
      e.preventDefault()
      onCancel()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      nav.moveNext()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      nav.movePrev()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      commit(matches[nav.active] ?? q)
    }
  }

  return (
    <div className="lx-unit-editor lx-loc-editor" ref={wrapRef} onClick={(e) => e.stopPropagation()}>
      <input
        ref={inputRef}
        className="form-control form-control-sm lx-unit-editor__input"
        value={q}
        placeholder={current || 'Search or type location…'}
        aria-label="Correct location"
        onChange={(e) => {
          setQ(e.target.value.toUpperCase())
          nav.reset()
        }}
        onKeyDown={onKeyDown}
      />
      {matches.length > 0 && (
        <ul className="lx-unit-editor__menu" role="listbox">
          {matches.map((loc, i) => (
            <li key={loc} role="option" aria-selected={i === nav.active} ref={nav.itemRef(i)}>
              <button
                type="button"
                className={`lx-unit-editor__row${i === nav.active ? ' is-active' : ''}`}
                onMouseEnter={() => nav.setActive(i)}
                onClick={() => commit(loc)}
              >
                {loc}
                {loc.toUpperCase() === current.toUpperCase() && <span className="lx-unit-editor__cur">current</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
