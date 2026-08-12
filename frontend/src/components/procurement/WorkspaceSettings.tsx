import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { GridColumnConfig, GridColumnId } from './gridColumns'
import { COLUMN_LABELS, MANDATORY_COLUMNS } from './gridColumns'

const ZOOM_LEVELS = [75, 80, 90, 100, 110, 125]

/**
 * ⚙ Settings popover for the Purchase Workspace (spec §6/§20) — column
 * show/hide/reorder plus Zoom/Density. Purely a UI preference surface; it
 * only ever calls the setters passed in by the page, which persist via
 * settingsService/gridColumns — no business data flows through here.
 *
 * Rendered via a portal into document.body, positioned at fixed coordinates
 * derived from the anchor button. The toolbar row it's opened from
 * (.pm-toolbar__row--filters) scrolls horizontally (overflow-x: auto), which
 * the CSS spec silently upgrades its overflow-y to auto/clipping too — an
 * in-place absolutely-positioned popover was invisible (clipped to zero
 * height) even though its open/close state was correct. Portalling out of
 * that ancestor sidesteps the clip entirely.
 */
export function WorkspaceSettings({
  anchorRef,
  columnConfig,
  onColumnConfigChange,
  zoom,
  onZoomChange,
  density,
  onDensityChange,
  onClose,
}: {
  anchorRef: React.RefObject<HTMLElement | null>
  columnConfig: GridColumnConfig
  onColumnConfigChange: (next: GridColumnConfig) => void
  zoom: number
  onZoomChange: (next: number) => void
  density: 'normal' | 'compact'
  onDensityChange: (next: 'normal' | 'compact') => void
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null)

  useLayoutEffect(() => {
    const anchor = anchorRef.current
    if (!anchor) return
    const r = anchor.getBoundingClientRect()
    setPos({ top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) })
  }, [anchorRef])

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node
      if (ref.current && !ref.current.contains(target) && !anchorRef.current?.contains(target)) onClose()
    }
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onEsc)
    }
  }, [onClose, anchorRef])

  const toggleVisible = (id: GridColumnId) => {
    const visible = columnConfig.visible.includes(id)
      ? columnConfig.visible.filter((v) => v !== id)
      : [...columnConfig.visible, id]
    onColumnConfigChange({ ...columnConfig, visible })
  }

  const move = (id: GridColumnId, dir: -1 | 1) => {
    const order = [...columnConfig.order]
    const from = order.indexOf(id)
    const to = from + dir
    if (from < 0 || to < 0 || to >= order.length) return
    ;[order[from], order[to]] = [order[to], order[from]]
    onColumnConfigChange({ ...columnConfig, order })
  }

  // Render every configurable column in the user's saved order. Stock/
  // Suggested/Final Qty are "essential" (spec §4) — always visible, shown as
  // locked rows so the order can still be adjusted; Pack/Unit/Offer/Remarks
  // are the actually hideable ones.
  const rows = columnConfig.order

  if (!pos) return null

  return createPortal(
    <div
      className="pm-settings"
      ref={ref}
      role="dialog"
      aria-label="Workspace settings"
      style={{ position: 'fixed', top: pos.top, right: pos.right }}
    >
      <div className="pm-settings__section">
        <div className="pm-settings__title">Grid Columns</div>
        <div className="pm-settings__lockrow"><i className="bi bi-lock-fill" /> Product <span className="pm-settings__locktag">Always first</span></div>
        {rows.map((id, i) => {
          const locked = MANDATORY_COLUMNS.has(id)
          const visible = locked || columnConfig.visible.includes(id)
          return (
            <div key={id} className="pm-settings__row">
              <label className="pm-settings__check">
                <input
                  type="checkbox"
                  checked={visible}
                  disabled={locked}
                  onChange={() => toggleVisible(id)}
                />
                {COLUMN_LABELS[id]}
                {locked && <span className="pm-settings__locktag"><i className="bi bi-lock-fill" /> Required</span>}
              </label>
              <div className="pm-settings__reorder">
                <button type="button" disabled={i === 0} onClick={() => move(id, -1)} title="Move up"><i className="bi bi-chevron-up" /></button>
                <button type="button" disabled={i === rows.length - 1} onClick={() => move(id, 1)} title="Move down"><i className="bi bi-chevron-down" /></button>
              </div>
            </div>
          )
        })}
        <div className="pm-settings__lockrow"><i className="bi bi-lock-fill" /> Planning Status <span className="pm-settings__locktag">Always last</span></div>
      </div>

      <div className="pm-settings__section">
        <div className="pm-settings__title">Zoom</div>
        <div className="pm-settings__chips">
          {ZOOM_LEVELS.map((z) => (
            <button
              key={z}
              type="button"
              className={`pm-settings__chip${zoom === z ? ' pm-settings__chip--on' : ''}`}
              onClick={() => onZoomChange(z)}
            >
              {z}%
            </button>
          ))}
        </div>
      </div>

      <div className="pm-settings__section">
        <div className="pm-settings__title">Density</div>
        <div className="pm-settings__chips">
          <button
            type="button"
            className={`pm-settings__chip${density === 'normal' ? ' pm-settings__chip--on' : ''}`}
            onClick={() => onDensityChange('normal')}
          >
            Normal
          </button>
          <button
            type="button"
            className={`pm-settings__chip${density === 'compact' ? ' pm-settings__chip--on' : ''}`}
            onClick={() => onDensityChange('compact')}
          >
            Compact
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
