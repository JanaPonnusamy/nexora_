import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { SupplierRow, WorkspaceItem } from '../../types/procurement'
import { num } from '../stock/format'
import { DEFAULT_SKIP_MODE } from './skipModes'
import { SkipModeCell } from './SkipModeCell'
import { preferredSupplier } from './purchaseValue'

const REVIEWED_STATES = ['review', 'assigned', 'partial']

// Keys that edit text / move the caret INSIDE a cell editor. While the caret is
// inside an input these must reach the browser untouched (Excel/Tally/Busy feel)
// — the grid must never hijack them to move between cells. ArrowLeft/ArrowRight
// are intentionally NOT here: the spec maps Right → Supplier Recommendation and
// Left → back to Final Qty, so the grid owns horizontal keys.
const CARET_KEYS = new Set(['Home', 'End', 'Backspace', 'Delete'])

/** True when the event originates from a real text editor (input/textarea/
 *  contenteditable) — i.e. the text caret is live inside a cell. */
function isTextEditor(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el || !el.tagName) return false
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable === true
}

/** The two keyboard "zones" a selected row can be in. */
type Zone = 'qty' | 'supplier'

export function ProductGrid({
  items,
  selectedId,
  edits,
  dirtyIds,
  lockedIds,
  selectable = false,
  checked,
  recommendations,
  selectedSupplier,
  collapseToSupplier,
  onSelectSupplier,
  onCommitSupplier,
  onSupplierFocusChange,
  onEditChange,
  onSaveRow,
  onSelect,
  onSkip,
  onRestore,
  onDefer,
  onToggle,
  onToggleAll,
}: {
  items: WorkspaceItem[]
  selectedId: string | null
  edits: Record<string, string>
  dirtyIds: Set<string>
  lockedIds: Set<string>
  selectable?: boolean
  checked?: Set<string>
  /** Supplier recommendations keyed by order_item_id (Product Grid icons). */
  recommendations?: Record<string, SupplierRow[]>
  /** Locally-selected supplier per row (not yet committed). */
  selectedSupplier?: Record<string, string>
  /** In Supplier Purchasing mode, collapse recommendations to just this supplier. */
  collapseToSupplier?: string | null
  onSelectSupplier?: (orderItemId: string, supplierCode: string) => void
  onCommitSupplier?: (item: WorkspaceItem, supplierCode: string) => void
  /** Fires when the keyboard enters/leaves the Supplier Recommendation zone, so
   *  the external supplier panel can show itself as active. */
  onSupplierFocusChange?: (active: boolean) => void
  onEditChange: (id: string, value: string) => void
  /** Commit the current Final Qty edit for one row immediately (Enter = Save Row). */
  onSaveRow?: (item: WorkspaceItem) => void
  onSelect: (item: WorkspaceItem) => void
  onSkip: (item: WorkspaceItem, reason: string) => void
  onRestore: (item: WorkspaceItem) => void
  /** Space Bar — Assignment Deferred: keeps Final Qty, excludes the row from
   *  Auto/Bulk Assignment. Un-defer reuses `onRestore` (same as un-skip). */
  onDefer?: (item: WorkspaceItem) => void
  onToggle?: (id: string) => void
  onToggleAll?: (ids: string[], on: boolean) => void
}) {
  const wrapRef = useRef<HTMLDivElement>(null)

  // Keyboard zone + supplier cursor for the active row. The zone resets to Final
  // Qty whenever the selected row changes (including a mouse click), so keyboard
  // navigation always continues cleanly from the active row.
  const [zone, setZone] = useState<Zone>('qty')
  const [supIndex, setSupIndex] = useState(0)
  // Set to a row id right after an explicit Esc-skip so focus parks on that row's
  // Skip-Mode selector. Cleared on any selection change, so merely navigating onto
  // an already-skipped row keeps focus on its Final Qty cell (navigation stays fast).
  const [skipFocusId, setSkipFocusId] = useState<string | null>(null)

  // Rows with an Esc-skip request already in flight. Guards the tiny window
  // between pressing Esc and the optimistic "skipped" status committing, so a
  // rapid double-press can never fire two skip save requests for the same row.
  const skipInFlight = useRef<Set<string>>(new Set())

  const allChecked =
    selectable && items.length > 0 && items.every((i) => checked?.has(i.order_item_id))

  // Everything stays editable until export locks it — a Skipped row can be
  // re-quantified (which un-skips it), so "skipped" no longer blocks editing.
  const editable = (item: WorkspaceItem) => !lockedIds.has(item.order_item_id)
  const skippedOf = (item: WorkspaceItem) => item.item_status === 'skipped'
  const deferredOf = (item: WorkspaceItem) => item.item_status === 'deferred'

  const qtyValue = (item: WorkspaceItem) =>
    edits[item.order_item_id] ?? String(item.final_qty ?? 0)

  // Positive integers only, max 5 digits — desktop-ERP data entry.
  const onQtyChange = (id: string, raw: string) =>
    onEditChange(id, raw.replace(/[^\d]/g, '').slice(0, 5))

  const focusQty = (index: number) => {
    const el = document.getElementById(`pm-qty-${index}`) as HTMLInputElement | null
    el?.focus()
    el?.select()
  }
  const focusSkip = (index: number) => {
    ;(document.getElementById(`pm-skip-${index}`) as HTMLElement | null)?.focus()
  }

  const selectedIndex = items.findIndex((i) => i.order_item_id === selectedId)
  // Status of the active row — included in the focus effect so that when a row
  // becomes Skipped (its Final Qty input unmounts) focus is re-parked on the
  // grid container instead of falling back to <body>.
  const selectedStatus = items[selectedIndex]?.item_status

  // A new active row always starts in the Final Qty zone (and drops any pending
  // Esc-skip focus, so navigating onto a skipped row lands on its qty cell).
  // Adjusted DURING RENDER, guarded by comparing against the previous selection
  // (React's documented pattern for "adjusting state when a prop changes" —
  // https://react.dev/learn/you-might-not-need-an-effect). Doing this in a
  // separate useEffect keyed on `selectedId` made it race the parent's own
  // selection-repair effect (below): a keyboard advance changes `selectedId`,
  // this effect resets zone/skipFocusId, the parent's effect can then also
  // reassign `selectedId`, re-arming this effect again — under the wrong timing
  // that cascade doesn't settle and React aborts with "Maximum update depth
  // exceeded". Resolving it in-render collapses the reset into the same pass
  // as the selection change, so there is nothing left for an effect to chase.
  const [prevSelectedId, setPrevSelectedId] = useState(selectedId)
  if (selectedId !== prevSelectedId) {
    setPrevSelectedId(selectedId)
    setZone('qty')
    setSupIndex(0)
    setSkipFocusId(null)
  }

  // Up to five ranked suppliers for a row, honouring the Supplier-Purchasing
  // collapse. Same shape the row renders, so keyboard and mouse agree.
  const recsFor = (item: WorkspaceItem): SupplierRow[] => {
    const recs = recommendations?.[item.order_item_id] ?? []
    const shown = collapseToSupplier ? recs.filter((s) => s.supplier_code === collapseToSupplier) : recs
    return shown.slice(0, 5)
  }

  // Land keyboard focus for the active row: the Final Qty cell in the qty zone
  // (editable rows) or the grid container otherwise — in the supplier zone the
  // container holds focus so Left/Right drive the supplier cursor and the number
  // caret never interferes. This effect only moves DOM focus — it never calls
  // setState, so it cannot itself re-trigger the render-time reset above.
  useEffect(() => {
    if (selectedIndex < 0) return
    if (zone === 'supplier') { wrapRef.current?.focus(); return }
    const cur = items[selectedIndex]
    // A just-Esc-skipped row parks focus on its Skip-Mode selector; otherwise the
    // Final Qty cell holds focus (so Down/Enter keep advancing, even over skipped
    // rows); locked rows fall back to the grid container.
    if (skippedOf(cur) && editable(cur) && skipFocusId === cur.order_item_id) focusSkip(selectedIndex)
    else if (editable(cur)) focusQty(selectedIndex)
    else wrapRef.current?.focus()
    // Re-run when the selection, row count, zone or the active row's status
    // changes (not on every edit).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, items.length, zone, selectedStatus, skipFocusId])

  // Tell the parent when the Supplier Recommendation zone is active, so the
  // external supplier panel can highlight itself.
  useEffect(() => {
    onSupplierFocusChange?.(zone === 'supplier')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zone])

  // Move the selection one row up/down. Adjacent rows of any status are
  // reachable (so a Reviewed row can be navigated to and skipped).
  const moveSelection = (dir: 1 | -1) => {
    if (items.length === 0) return
    const from = selectedIndex < 0 ? (dir === 1 ? -1 : items.length) : selectedIndex
    const next = from + dir
    if (next >= 0 && next < items.length) onSelect(items[next])
  }

  // Tab / Shift+Tab: jump to the next/previous *editable* Final Qty cell.
  const gotoEditableRow = (dir: 1 | -1) => {
    for (let i = (selectedIndex < 0 ? (dir === 1 ? -1 : items.length) : selectedIndex) + dir;
         i >= 0 && i < items.length; i += dir) {
      if (editable(items[i])) { onSelect(items[i]); return true }
    }
    return false
  }

  /* ---- Zone transitions & actions --------------------------------------- */

  // Right from Final Qty → Supplier Recommendation, starting on the currently
  // selected supplier, else the Preferred (latest-purchased) one, else the
  // top-ranked (cheapest) card — pre-selects visually only, never assigns (§3).
  const enterSupplierZone = () => {
    const cur = items[selectedIndex]
    if (!cur || !editable(cur)) return
    const recs = recsFor(cur)
    if (recs.length === 0) return
    const selCode = selectedSupplier?.[cur.order_item_id] ?? preferredSupplier(recs)
    const found = recs.findIndex((s) => s.supplier_code === selCode)
    const idx = found < 0 ? 0 : found
    setSupIndex(idx)
    setZone('supplier')
    onSelectSupplier?.(cur.order_item_id, recs[idx].supplier_code)
  }

  // Up/Down inside the (vertical) Supplier Recommendation panel. Up past the
  // first supplier returns to Final Qty.
  const moveSupplier = (dir: 1 | -1) => {
    const cur = items[selectedIndex]
    if (!cur) return
    const recs = recsFor(cur)
    if (recs.length === 0) { setZone('qty'); return }
    const next = supIndex + dir
    if (next < 0) { setZone('qty'); return }
    const idx = Math.min(next, recs.length - 1)
    setSupIndex(idx)
    onSelectSupplier?.(cur.order_item_id, recs[idx].supplier_code)
  }

  // Enter inside Supplier Recommendation: assign the highlighted supplier, then
  // advance to the next product.
  const commitSupplier = () => {
    const cur = items[selectedIndex]
    if (!cur) return
    const recs = recsFor(cur)
    const s = recs[supIndex]
    if (!s) return
    onCommitSupplier?.(cur, s.supplier_code)
    setZone('qty')
    moveSelection(1)
  }

  // Enter on Final Qty: save the row immediately, then advance. Qty > 0
  // finalises (green); qty 0 skips (grey). Never stops on the same row.
  const saveAndNext = () => {
    const cur = items[selectedIndex]
    if (!cur) return
    if (editable(cur)) {
      const v = Number(qtyValue(cur))
      if (!Number.isNaN(v) && v > 0) onSaveRow?.(cur)          // finalise / un-skip
      else if (!skippedOf(cur)) onSkip(cur, DEFAULT_SKIP_MODE) // qty 0 → skip
      // already skipped + qty 0 → keep the chosen mode, just advance
    }
    moveSelection(1)
  }

  // Once a row is no longer skipped (e.g. Restored), drop its in-flight guard so
  // Esc can skip it again.
  useEffect(() => {
    const g = skipInFlight.current
    for (const id of [...g]) {
      const it = items.find((x) => x.order_item_id === id)
      if (!it || it.item_status !== 'skipped') g.delete(id)
    }
  }, [items])

  // Esc on a Final Qty cell: skip the row outright in one action — quantity → 0,
  // status → Skipped (grey), saved immediately via the existing optimistic skip
  // API. No Status dropdown, no staged edit, no workspace reload. The row stays
  // selected and keyboard focus is re-parked on the grid (its input unmounts),
  // so a following Enter advances to the next row. A no-op on already-skipped or
  // locked rows, and guarded so a rapid double-press never double-saves.
  const skipCurrent = () => {
    const cur = items[selectedIndex]
    if (!cur || !editable(cur)) return
    if (skipInFlight.current.has(cur.order_item_id)) return
    skipInFlight.current.add(cur.order_item_id)
    onSkip(cur, DEFAULT_SKIP_MODE)
    setZone('qty')
    setSkipFocusId(cur.order_item_id) // park focus on this row's Skip-Mode selector
  }

  // Space Bar on the current row: toggle Assignment Deferred. A deferred row
  // keeps its Final Qty (unlike Skip) — it just excludes itself from Auto
  // Assign / Bulk / Assign Selected until either restored or manually
  // assigned (which auto-clears the flag). No-op on a skipped or locked row.
  const toggleDeferredCurrent = () => {
    const cur = items[selectedIndex]
    if (!cur || !editable(cur) || skippedOf(cur)) return
    if (deferredOf(cur)) onRestore(cur)
    else onDefer?.(cur)
  }

  // Grid-level keys. Caret editing keys inside the number input are handed back
  // to the browser; everything else drives spreadsheet-style navigation split
  // across the Final Qty and Supplier Recommendation zones.
  const onGridKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (isTextEditor(e.target) && CARET_KEYS.has(e.key)) return // never hijack text editing
    // The Skip-Mode combobox (SkipModeCell) stops propagation for the keys it
    // owns (Enter/Down open, Up/Down cycle, Enter confirm, Esc close), so those
    // never reach the grid while it holds focus.

    if (zone === 'supplier') {
      // Vertical panel: Up/Down cycle suppliers (Up past the first → Final Qty),
      // Enter assigns the whole Final Qty, Left returns to Final Qty.
      if (e.key === 'ArrowUp') { e.preventDefault(); moveSupplier(-1) }
      else if (e.key === 'ArrowDown') { e.preventDefault(); moveSupplier(1) }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); setZone('qty') }
      else if (e.key === 'Enter') { e.preventDefault(); commitSupplier() }
      else if (e.key === 'Tab') {
        // Next/previous editable product — same as the Final Qty zone (§8).
        if (gotoEditableRow(e.shiftKey ? -1 : 1)) e.preventDefault()
      } else if (e.key === 'Escape') {
        // §8 — Esc here only cancels the supplier highlight and returns to
        // Final Qty; nothing was committed yet, so there is nothing to skip.
        e.preventDefault()
        setZone('qty')
      }
      return
    }

    // Final Qty zone
    if (e.key === 'F2') {
      e.preventDefault()
      focusQty(selectedIndex) // F2 — (re)enter edit on the current cell
    } else if (e.key === 'Tab') {
      if (gotoEditableRow(e.shiftKey ? -1 : 1)) e.preventDefault()
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      enterSupplierZone()
    } else if (e.key === 'ArrowDown') {
      // DOWN behaves exactly like ENTER: save/finalise this row, then advance.
      e.preventDefault()
      saveAndNext()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      moveSelection(-1)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      saveAndNext()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      skipCurrent()
    } else if (e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault()
      toggleDeferredCurrent()
    }
  }

  // Auto-hide columns that carry no data for the whole list (§13 — never show a
  // column of only "—"). Unit/Pack now live in the detail panel; the grid keeps
  // Offer only when at least one row carries it.
  const hasOffer = items.some((i) => i.offer != null && i.offer !== '')

  return (
    <div className="pm-grid-wrap" ref={wrapRef} tabIndex={-1} onKeyDown={onGridKey}>
      <table className="pm-grid">
        <thead>
          <tr>
            {selectable && (
              <th className="pm-grid__check">
                <input
                  type="checkbox"
                  aria-label="Select all"
                  checked={allChecked}
                  onChange={(e) => onToggleAll?.(items.map((i) => i.order_item_id), e.target.checked)}
                />
              </th>
            )}
            <th className="pm-grid__sno">#</th>
            <th className="pm-grid__prod">Product</th>
            <th className="pm-grid__pack">Pack</th>
            <th className="pm-grid__unit">Unit</th>
            <th className="sx-num pm-col70">Stock</th>
            <th className="sx-num pm-col70">Sugg.</th>
            <th className="sx-num pm-grid__final">Final Qty</th>
            <th className="pm-grid__status">Planning State</th>
            {hasOffer && <th className="pm-grid__offer">Offer</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => {
            const skipped = item.item_status === 'skipped'
            const deferred = item.item_status === 'deferred'
            const locked = lockedIds.has(item.order_item_id)
            const isSel = selectedId === item.order_item_id
            const dirty = dirtyIds.has(item.order_item_id)
            const reviewed = REVIEWED_STATES.includes(item.item_status)
            const assigned = (item.assigned_qty ?? 0) > 0 && !skipped && !locked
            // Finalised = a reviewed row that carries a real quantity but no
            // supplier yet → purple. Once a supplier is assigned it turns green.
            const finalized = reviewed && (item.final_qty ?? 0) > 0 && !assigned && !skipped && !locked
            return (
              <tr
                key={item.order_item_id}
                className={`pm-row${isSel ? ' pm-row--sel' : ''}${assigned ? ' pm-row--assigned' : ''}${finalized ? ' pm-row--finalized' : ''}${skipped ? ' pm-row--skip' : ''}${deferred ? ' pm-row--deferred' : ''}${locked ? ' pm-row--locked' : ''}`}
                onClick={() => onSelect(item)}
              >
                {selectable && (
                  <td className="pm-grid__check" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label="Select row"
                      checked={checked?.has(item.order_item_id) ?? false}
                      onChange={() => onToggle?.(item.order_item_id)}
                      // A product already owned by a supplier can never be bulk
                      // re-assigned from here (§1/§2) — reassignment is explicit
                      // (Change Supplier). A deferred row (Space Bar) is excluded
                      // from bulk/Assign-Selected too — it's only assignable
                      // manually (Right-Arrow → Enter), which auto-clears defer.
                      disabled={skipped || locked || assigned || deferred}
                      title={
                        assigned ? 'Already assigned — use Change Supplier to reassign'
                          : deferred ? 'Assignment deferred — assign manually or press Space to restore'
                            : undefined
                      }
                    />
                  </td>
                )}
                <td className="pm-grid__sno sx-dim">{i + 1}</td>
                <td className="pm-grid__prod">
                  <span className="pm-prod__name" title={item.product_name ?? undefined}>{item.product_name ?? '—'}</span>
                  {item.is_manual && <span className="pm-tag pm-tag--manual">manual</span>}
                  {locked && <span className="pm-tag pm-tag--exported">exported</span>}
                </td>
                <td className="pm-grid__pack sx-dim">{item.pack || '—'}</td>
                <td className="pm-grid__unit sx-dim">{item.unit_description || '—'}</td>
                <td className="sx-num pm-col70">{num(item.current_stock_qty ?? 0)}</td>
                <td className="sx-num pm-col70 sx-dim">{num(item.suggested_qty ?? 0)}</td>
                <td className="sx-num pm-grid__final" onClick={(e) => e.stopPropagation()}>
                  {locked ? (
                    <span className="fw-semibold">{num(item.final_qty ?? 0)}</span>
                  ) : (
                    <input
                      id={`pm-qty-${i}`}
                      className={`pm-qty${dirty ? ' pm-qty--dirty' : ''}`}
                      inputMode="numeric"
                      maxLength={5}
                      value={qtyValue(item)}
                      onFocus={(e) => e.currentTarget.select()}
                      onDoubleClick={(e) => e.currentTarget.select()}
                      onChange={(e) => onQtyChange(item.order_item_id, e.target.value)}
                      onBlur={() => { if (dirty) onSaveRow?.(item) }}
                    />
                  )}
                </td>
                <td className="pm-grid__status">
                  {locked ? (
                    <span className="pm-status pm-status--reviewed"><i className="bi bi-lock-fill" /> Reviewed</span>
                  ) : skipped ? (
                    /* Planning state IS the skip mode — a keyboard-driven combo:
                       Enter/Down opens, Up/Down changes, Enter confirms + advances. */
                    <SkipModeCell
                      id={`pm-skip-${i}`}
                      value={item.skip_reason}
                      onChange={(code) => onSkip(item, code)}
                      onConfirm={() => { if (i + 1 < items.length) onSelect(items[i + 1]) }}
                      onRestore={() => onRestore(item)}
                    />
                  ) : assigned ? (
                    <span className="pm-status pm-status--assigned">Assigned</span>
                  ) : deferred ? (
                    <span className="pm-status-wrap">
                      <span className="pm-status pm-status--deferred" title="Excluded from Auto Assign / Assign Selected — assign manually or restore">
                        Assignment Deferred
                      </span>
                      <button
                        className="pm-linkbtn pm-linkbtn--icon"
                        title="Restore to review"
                        aria-label="Restore to review"
                        onClick={(e) => { e.stopPropagation(); onRestore(item) }}
                      >
                        <i className="bi bi-arrow-counterclockwise" aria-hidden="true" />
                      </button>
                    </span>
                  ) : (
                    <span className="pm-status-wrap">
                      {finalized ? (
                        <span className="pm-status pm-status--finalized">Finalized</span>
                      ) : (
                        <span className="pm-status pm-status--notrev">Not Reviewed</span>
                      )}
                      {/* Any un-exported row can be sent to Skipped, including a
                          Finalised one (before export). Icon-only (no "Skip"
                          text) to keep the Planning State column compact. */}
                      <button
                        className="pm-linkbtn pm-linkbtn--skip pm-linkbtn--icon"
                        title="Skip this product"
                        aria-label="Skip this product"
                        onClick={(e) => { e.stopPropagation(); onSkip(item, DEFAULT_SKIP_MODE) }}
                      >
                        <i className="bi bi-slash-circle" aria-hidden="true" />
                      </button>
                    </span>
                  )}
                </td>
                {hasOffer && (
                  <td className="pm-grid__offer">
                    {item.offer ? <span className="pm-offer">{item.offer}</span> : null}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
