import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import type { MiniGridColumn } from './useMiniGridSettings'

interface GridSection {
  title: string
  columns: MiniGridColumn[]
  order: string[]
  widths: Record<string, number>
  padding: number
  onMove: (id: string, dir: -1 | 1) => void
  onWidth: (id: string, px: number) => void
  onPadding: (px: number) => void
  onReset: () => void
}

/**
 * Column order / width / padding settings for the Purchase History + Sales
 * History mini-grids — one gear icon (next to Info) opens both sections at
 * once. Opens fixed-position to the LEFT of the Product Detail panel
 * (anchorRect is that panel's own bounding rect, not the gear button's —
 * owner-directed placement), live-preview (every control applies instantly,
 * no Save button — same convention as the main Product Grid's ⚙ Settings).
 * Persisted per-user via useMiniGridSettings -> dbo.user_grid_settings.
 */
export function MiniGridSettingsPanel({
  anchorRect,
  sections,
  onClose,
}: {
  anchorRect: DOMRect
  sections: GridSection[]
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const style: React.CSSProperties = {
    position: 'fixed',
    top: Math.max(8, anchorRect.top),
    // Opens to the LEFT of the Product Detail panel, not anchored to the
    // gear button itself.
    right: window.innerWidth - anchorRect.left + 8,
    maxHeight: `calc(100vh - ${anchorRect.top + 16}px)`,
  }

  return createPortal(
    <div className="pm-mgs" style={style} ref={ref} role="dialog" aria-label="Grid settings">
      {sections.map((s) => (
        <section className="pm-mgs__section" key={s.title}>
          <div className="pm-mgs__head">
            <span>{s.title}</span>
            <button type="button" className="pm-linkbtn pm-linkbtn--sm" onClick={s.onReset}>Reset</button>
          </div>
          <label className="pm-mgs__padding">
            <span>Row padding (px)</span>
            <input
              type="number"
              min={0}
              max={16}
              value={s.padding}
              onChange={(e) => s.onPadding(Number(e.target.value))}
            />
          </label>
          <ul className="pm-mgs__cols">
            {s.order.map((id, i) => {
              const col = s.columns.find((c) => c.id === id)
              if (!col) return null
              return (
                <li key={id} className="pm-mgs__col">
                  <span className="pm-mgs__colname">{col.label}</span>
                  <input
                    type="number"
                    className="pm-mgs__width"
                    min={24}
                    max={300}
                    value={s.widths[id] ?? col.width}
                    onChange={(e) => s.onWidth(id, Number(e.target.value))}
                    aria-label={`${col.label} column width`}
                  />
                  <button
                    type="button"
                    className="pm-mgs__movebtn"
                    disabled={i === 0}
                    aria-label={`Move ${col.label} left`}
                    onClick={() => s.onMove(id, -1)}
                  >
                    <i className="bi bi-arrow-left" />
                  </button>
                  <button
                    type="button"
                    className="pm-mgs__movebtn"
                    disabled={i === s.order.length - 1}
                    aria-label={`Move ${col.label} right`}
                    onClick={() => s.onMove(id, 1)}
                  >
                    <i className="bi bi-arrow-right" />
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>,
    document.body,
  )
}
