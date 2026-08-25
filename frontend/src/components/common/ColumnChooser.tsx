import { useEffect, useRef, useState } from 'react'

export interface ChooserColumn {
  key: string
  label: string
}

export interface ColumnPrefs {
  /** Ordered list of column keys (visible order). Keys not present are hidden. */
  order: string[]
  hidden: string[]
}

/**
 * A small dropdown that lets the user design which columns show and in what
 * order. Pure DOM (no external deps), so it renders identically in the browser
 * and in the Electron build. Preferences are owned by the parent (persisted in
 * localStorage) — this component only edits them.
 */
export function ColumnChooser({
  columns,
  prefs,
  onChange,
  onReset,
}: {
  columns: ChooserColumn[]
  prefs: ColumnPrefs
  onChange: (next: ColumnPrefs) => void
  onReset: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  // Effective order: saved order first (only known keys), then any new columns.
  const known = new Set(columns.map((c) => c.key))
  const ordered = [
    ...prefs.order.filter((k) => known.has(k)),
    ...columns.map((c) => c.key).filter((k) => !prefs.order.includes(k)),
  ]
  const labelOf = (k: string) => columns.find((c) => c.key === k)?.label ?? k
  const hidden = new Set(prefs.hidden)
  const visibleCount = ordered.filter((k) => !hidden.has(k)).length

  const toggle = (k: string) => {
    const next = new Set(hidden)
    if (next.has(k)) next.delete(k)
    else next.add(k)
    onChange({ order: ordered, hidden: [...next] })
  }
  const move = (k: string, dir: -1 | 1) => {
    const i = ordered.indexOf(k)
    const j = i + dir
    if (i < 0 || j < 0 || j >= ordered.length) return
    const next = [...ordered]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange({ order: next, hidden: [...hidden] })
  }

  return (
    <div className="colchooser" ref={ref}>
      <button
        type="button"
        className="btn btn-outline-secondary btn-sm"
        onClick={() => setOpen((v) => !v)}
        title="Choose and order columns"
      >
        <i className="bi bi-layout-three-columns" /> Columns ({visibleCount})
      </button>
      {open && (
        <div className="colchooser-panel" role="menu">
          <div className="colchooser-head">
            <span>Design columns</span>
            <button type="button" className="colchooser-reset" onClick={onReset}>Reset</button>
          </div>
          <ul className="colchooser-list">
            {ordered.map((k, idx) => (
              <li key={k}>
                <label className="colchooser-item">
                  <input
                    type="checkbox"
                    checked={!hidden.has(k)}
                    onChange={() => toggle(k)}
                  />
                  <span className="colchooser-label">{labelOf(k)}</span>
                </label>
                <span className="colchooser-move">
                  <button type="button" disabled={idx === 0} onClick={() => move(k, -1)} title="Move up" aria-label="Move up">▲</button>
                  <button type="button" disabled={idx === ordered.length - 1} onClick={() => move(k, 1)} title="Move down" aria-label="Move down">▼</button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Apply a preference set to the master column list -> ordered visible columns. */
export function applyColumnPrefs<T extends { key: string }>(columns: T[], prefs: ColumnPrefs): T[] {
  const byKey = new Map(columns.map((c) => [c.key, c]))
  const hidden = new Set(prefs.hidden)
  const ordered = [
    ...prefs.order.filter((k) => byKey.has(k)),
    ...columns.map((c) => c.key).filter((k) => !prefs.order.includes(k)),
  ]
  return ordered.filter((k) => !hidden.has(k)).map((k) => byKey.get(k)!)
}
