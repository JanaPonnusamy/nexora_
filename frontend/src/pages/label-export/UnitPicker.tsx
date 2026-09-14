import { useEffect, useMemo, useRef, useState } from 'react'
import { useListNav } from '../../hooks/useListNav'

/**
 * Compact, searchable unit selector used *only while a UNIT cell is being
 * edited* (spec §1). The grid shows plain read-only text normally; the page
 * mounts this in place of that text when the reviewer chooses to correct the
 * unit, and unmounts it on pick/cancel. Keyboard-first: type to filter,
 * ↑/↓ to move, Enter to pick, Esc to cancel, click/hover to select — the
 * same interaction model as the supplier picker (shared useListNav).
 */
export function UnitPicker({
  current,
  options,
  onPick,
  onCancel,
}: {
  current: string
  options: string[]
  onPick: (unit: string) => void
  onCancel: () => void
}) {
  const [q, setQ] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const term = q.trim().toUpperCase()
  const matches = useMemo(() => {
    const list = term ? options.filter((u) => u.toUpperCase().includes(term)) : options
    // Let the reviewer commit a brand-new unit that isn't in the list yet.
    if (term && !list.some((u) => u.toUpperCase() === term)) return [term, ...list].slice(0, 40)
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

  const commit = (unit: string) => {
    const value = (unit || '').trim().toUpperCase()
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
    <div className="lx-unit-editor" ref={wrapRef} onClick={(e) => e.stopPropagation()}>
      <input
        ref={inputRef}
        className="form-control form-control-sm lx-unit-editor__input"
        value={q}
        placeholder={current || 'Search unit…'}
        aria-label="Correct unit"
        onChange={(e) => {
          setQ(e.target.value.toUpperCase())
          nav.reset()
        }}
        onKeyDown={onKeyDown}
      />
      {matches.length > 0 && (
        <ul className="lx-unit-editor__menu" role="listbox">
          {matches.map((u, i) => (
            <li key={u} role="option" aria-selected={i === nav.active} ref={nav.itemRef(i)}>
              <button
                type="button"
                className={`lx-unit-editor__row${i === nav.active ? ' is-active' : ''}`}
                onMouseEnter={() => nav.setActive(i)}
                onClick={() => commit(u)}
              >
                {u}
                {u.toUpperCase() === current.toUpperCase() && <span className="lx-unit-editor__cur">current</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
