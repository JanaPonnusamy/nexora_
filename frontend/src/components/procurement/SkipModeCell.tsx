import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { SKIP_MODES, DEFAULT_SKIP_MODE, skipModeLabel } from './skipModes'

/**
 * Planning-State cell for a Skipped row. A fully keyboard-driven combobox
 * (native <select> keyboard behaviour is unreliable across browsers and never
 * advanced the row), matching the spec:
 *
 *   ESC (in grid) → row parks focus here (closed)
 *   ENTER / DOWN  → open the mode list
 *   UP / DOWN     → change highlighted mode
 *   ENTER         → confirm mode → save immediately → advance to NEXT row
 *   ESC           → close without changing
 *
 * The trigger shows a skip icon + the CURRENT mode label (never a hard-coded
 * default) so the chosen mode is always visible after save.
 *
 * All keys it handles call stopPropagation so the grid's own ESC/ENTER handlers
 * never fire while the cell owns focus.
 */
export function SkipModeCell({
  id,
  value,
  onChange,
  onConfirm,
  onRestore,
}: {
  /** DOM id the grid focuses after an Esc-skip (`pm-skip-${index}`). */
  id: string
  /** Current skip_reason code (may be null → shows the default mode). */
  value: string | null | undefined
  /** Persist the newly chosen mode immediately (re-skip with this reason). */
  onChange: (code: string) => void
  /** Move focus to the next row's Final Qty after ENTER-confirm. */
  onConfirm: () => void
  /** Un-skip / restore this row. */
  onRestore: () => void
}) {
  const current = SKIP_MODES.some((m) => m.code === value) ? (value as string) : DEFAULT_SKIP_MODE
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(() => Math.max(0, SKIP_MODES.findIndex((m) => m.code === current)))
  const btnRef = useRef<HTMLButtonElement>(null)

  // When (re)opening, highlight the currently-selected mode.
  useEffect(() => {
    if (open) setHi(Math.max(0, SKIP_MODES.findIndex((m) => m.code === current)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const choose = (idx: number) => {
    const mode = SKIP_MODES[idx]
    if (!mode) return
    setOpen(false)
    if (mode.code !== current) onChange(mode.code)
    onConfirm() // advance to next row's Final Qty
  }

  const onKey = (e: ReactKeyboardEvent<HTMLElement>) => {
    if (!open) {
      if (e.key === 'Enter' || e.key === 'ArrowDown' || e.key === ' ') {
        e.preventDefault(); e.stopPropagation(); setOpen(true)
      } else if (e.key === 'Escape') {
        // Row is already skipped — swallow so the grid doesn't re-skip (which
        // would reset the mode to the default).
        e.stopPropagation()
      }
      return
    }
    // Open
    if (e.key === 'ArrowDown') { e.preventDefault(); e.stopPropagation(); setHi((h) => Math.min(h + 1, SKIP_MODES.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); e.stopPropagation(); setHi((h) => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); choose(hi) }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setOpen(false) }
    else if (e.key === 'Tab') { setOpen(false) }
  }

  return (
    <span className="pm-status-wrap">
      <span className={`pm-skipcell${open ? ' pm-skipcell--open' : ''}`}>
        <button
          id={id}
          ref={btnRef}
          type="button"
          className="pm-skipcell__btn"
          aria-haspopup="listbox"
          aria-expanded={open}
          title="Skip mode — Enter/Down to change"
          onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
          onKeyDown={onKey}
          onBlur={(e) => {
            // Close when focus leaves the whole cell (not when moving to the list).
            if (!e.currentTarget.parentElement?.contains(e.relatedTarget as Node)) setOpen(false)
          }}
        >
          <i className="bi bi-skip-forward-fill pm-skipcell__icon" aria-hidden="true" />
          <span className="pm-skipcell__label">{skipModeLabel(current)}</span>
          <i className="bi bi-caret-down-fill pm-skipcell__caret" aria-hidden="true" />
        </button>
        {open && (
          <ul className="pm-skipcell__menu" role="listbox">
            {SKIP_MODES.map((m, idx) => (
              <li
                key={m.code}
                role="option"
                aria-selected={idx === hi}
                className={`pm-skipcell__opt${idx === hi ? ' pm-skipcell__opt--hi' : ''}${m.code === current ? ' pm-skipcell__opt--cur' : ''}`}
                onMouseEnter={() => setHi(idx)}
                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); choose(idx) }}
              >
                <i className="bi bi-skip-forward-fill" aria-hidden="true" /> {m.label}
              </li>
            ))}
          </ul>
        )}
      </span>
      <button className="pm-linkbtn" title="Un-skip (restore)" onClick={(e) => { e.stopPropagation(); onRestore() }}>
        <i className="bi bi-arrow-counterclockwise" />
      </button>
    </span>
  )
}
