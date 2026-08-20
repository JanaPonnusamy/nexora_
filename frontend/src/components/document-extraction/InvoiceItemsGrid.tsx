import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { DocImportItem, ItemPatch } from '../../types/documentExtraction'
import { isInvalidBatch, isInvalidExpiry, isLowConfidence, isMissingProduct } from './reviewChecks'

interface InvoiceItemsGridProps {
  items: DocImportItem[]
  onSaveItem: (itemId: number, patch: ItemPatch) => Promise<void> | void
  onExcludeItem: (itemId: number) => Promise<void> | void
  saving?: boolean
}

interface ColDef {
  key: keyof ItemPatch
  label: string
  width: string
  numeric?: boolean
}

const COLS: ColDef[] = [
  { key: 'normalized_product_name', label: 'Product', width: '13rem' },
  { key: 'pack', label: 'Pack', width: '4.5rem' },
  { key: 'hsn_code', label: 'HSN', width: '4.5rem' },
  { key: 'batch_number', label: 'Batch', width: '5.5rem' },
  { key: 'expiry_date', label: 'Expiry', width: '5.5rem' },
  { key: 'quantity', label: 'Qty', width: '4rem', numeric: true },
  { key: 'free_quantity', label: 'Free', width: '4rem', numeric: true },
  { key: 'purchase_rate', label: 'Rate', width: '5.5rem', numeric: true },
  { key: 'mrp', label: 'MRP', width: '5.5rem', numeric: true },
  { key: 'gst_percent', label: 'GST %', width: '4.5rem', numeric: true },
  { key: 'discount_percent', label: 'Disc %', width: '4.5rem', numeric: true },
  { key: 'amount', label: 'Amount', width: '6rem', numeric: true },
]

function isTextEditor(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return !!el?.tagName && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')
}

function toStr(v: unknown): string {
  return v == null ? '' : String(v)
}

function buildForm(item: DocImportItem): Record<string, string> {
  const next: Record<string, string> = {}
  for (const { key } of COLS) next[key] = toStr((item as unknown as Record<string, unknown>)[key])
  return next
}

/** Row-active inline editing, spreadsheet-style — the active row's cells
 *  become inputs, everything else stays plain text for scan speed. Mirrors
 *  the Purchase Manager grid's Up/Down/Enter conventions so operators who
 *  already know that workflow transfer straight over: Up/Down moves the
 *  active row (saving any dirty edit first), Enter/Down both save-and-advance,
 *  Tab moves across fields and rolls onto the next row at the last one, Esc
 *  reverts the row's in-flight edits without saving. */
export function InvoiceItemsGrid({ items, onSaveItem, onExcludeItem, saving }: InvoiceItemsGridProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [activeId, setActiveId] = useState<number | null>(items[0]?.item_id ?? null)
  const fieldRefs = useRef<Map<string, HTMLInputElement>>(new Map())

  // Never persist an id that no longer exists (row excluded/list refreshed
  // out from under it) — recomputed every render instead of clamped via an
  // effect, so there's no invalid intermediate state to guard against.
  const resolvedActiveId = items.some((i) => i.item_id === activeId) ? activeId : (items[0]?.item_id ?? null)
  const activeIndex = items.findIndex((i) => i.item_id === resolvedActiveId)
  const active = activeIndex >= 0 ? items[activeIndex] : null

  const [form, setForm] = useState<Record<string, string>>(() => (active ? buildForm(active) : {}))

  // Re-seed the edit buffer when the resolved active row actually changes
  // (row switch, or the previous one disappeared) — adjusted during render,
  // matching the codebase's own "reset local state on prop change" idiom
  // (see ProductGrid's prevSelectedId comparison) instead of an effect.
  const [prevActiveId, setPrevActiveId] = useState(resolvedActiveId)
  if (resolvedActiveId !== prevActiveId) {
    setPrevActiveId(resolvedActiveId)
    setForm(active ? buildForm(active) : {})
  }

  // Land keyboard focus on the new active row's first field whenever the
  // selection changes (mouse click or keyboard nav) — this is what makes
  // Up/Down/Enter/Tab feel continuous instead of dropping focus each time.
  // A genuine DOM side effect (not derived state), so this stays an effect.
  useEffect(() => {
    if (active && !active.is_excluded) fieldRefs.current.get(COLS[0].key)?.focus()
    else wrapRef.current?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedActiveId])

  function buildPatch(item: DocImportItem): ItemPatch | null {
    const patch: Record<string, unknown> = {}
    let changed = false
    for (const { key, numeric } of COLS) {
      const raw = form[key] ?? ''
      const current = toStr((item as unknown as Record<string, unknown>)[key])
      if (raw === current) continue
      changed = true
      patch[key] = raw === '' ? null : numeric ? Number(raw) : raw
    }
    return changed ? (patch as ItemPatch) : null
  }

  async function commitActive() {
    if (!active) return
    const patch = buildPatch(active)
    if (patch) await onSaveItem(active.item_id, patch)
  }

  async function selectRow(item: DocImportItem) {
    if (active && active.item_id !== item.item_id) await commitActive()
    setActiveId(item.item_id)
  }

  async function moveSelection(dir: 1 | -1) {
    if (items.length === 0) return
    await commitActive()
    const from = activeIndex < 0 ? (dir === 1 ? -1 : items.length) : activeIndex
    const next = from + dir
    if (next >= 0 && next < items.length) setActiveId(items[next].item_id)
  }

  function revertActive() {
    if (active) setForm(buildForm(active))
    wrapRef.current?.focus()
  }

  const onGridKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'Enter') {
      e.preventDefault()
      void moveSelection(1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      void moveSelection(-1)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      revertActive()
    } else if (e.key === 'Tab' && isTextEditor(e.target)) {
      const el = e.target as HTMLInputElement
      const colIndex = COLS.findIndex((c) => c.key === el.dataset.col)
      // Tab off the last field (or Shift+Tab off the first) rolls onto the
      // next/previous row instead of leaving the grid entirely — the
      // useEffect above lands focus on the new row's first field, matching
      // Up/Down/Enter's behavior.
      if (!e.shiftKey && colIndex === COLS.length - 1) {
        e.preventDefault()
        void moveSelection(1)
      } else if (e.shiftKey && colIndex === 0) {
        e.preventDefault()
        void moveSelection(-1)
      }
      // otherwise let native Tab move within the row
    }
  }

  return (
    <div className="dx-grid-wrap" ref={wrapRef} tabIndex={-1} onKeyDown={onGridKey}>
      <table className="dx-grid">
        <thead>
          <tr>
            <th className="dx-grid__sno">#</th>
            {COLS.map((c) => (
              <th key={c.key} style={{ width: c.width, textAlign: c.numeric ? 'right' : 'left' }}>{c.label}</th>
            ))}
            <th className="dx-grid__flags">Flags</th>
            <th className="dx-grid__act" />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const isActive = item.item_id === resolvedActiveId
            const missing = isMissingProduct(item)
            const lowConf = isLowConfidence(item.confidence)
            const badBatch = isInvalidBatch(item)
            const badExpiry = isInvalidExpiry(item)
            const flagged = missing || lowConf || badBatch || badExpiry
            return (
              <tr
                key={item.item_id}
                className={[
                  'dx-row',
                  isActive ? 'dx-row--active' : '',
                  item.is_excluded ? 'dx-row--excluded' : '',
                  !item.is_excluded && flagged ? 'dx-row--flagged' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => void selectRow(item)}
              >
                <td className="dx-grid__sno sx-dim">{item.line_number}</td>
                {COLS.map((c) => (
                  <td key={c.key} style={{ textAlign: c.numeric ? 'right' : 'left' }} onClick={(e) => e.stopPropagation()}>
                    {isActive && !item.is_excluded ? (
                      <input
                        ref={(el) => { if (el) fieldRefs.current.set(c.key, el); else fieldRefs.current.delete(c.key) }}
                        className="dx-cell-input"
                        data-col={c.key}
                        type="text"
                        inputMode={c.numeric ? 'decimal' : undefined}
                        style={{ textAlign: c.numeric ? 'right' : 'left' }}
                        value={form[c.key] ?? ''}
                        onFocus={(e) => e.currentTarget.select()}
                        onChange={(e) => setForm((prev) => ({ ...prev, [c.key]: e.target.value }))}
                      />
                    ) : (
                      <span className={c.key === 'normalized_product_name' && missing ? 'text-danger' : undefined}>
                        {displayValue(item, c.key)}
                      </span>
                    )}
                  </td>
                ))}
                <td className="dx-grid__flags">
                  {item.is_excluded ? (
                    <span className="badge text-bg-secondary">Excluded</span>
                  ) : (
                    <>
                      {missing && <span className="badge text-bg-danger me-1">Unknown Product</span>}
                      {lowConf && <span className="badge text-bg-warning me-1">Low Confidence</span>}
                      {badBatch && <span className="badge text-bg-warning me-1">Bad Batch</span>}
                      {badExpiry && <span className="badge text-bg-warning me-1">Check Expiry</span>}
                    </>
                  )}
                </td>
                <td className="dx-grid__act" onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button" className="dx-iconbtn" disabled={saving || item.is_excluded}
                    title="Exclude this line" aria-label="Exclude this line"
                    onClick={() => void onExcludeItem(item.item_id)}
                  >
                    <i className="bi bi-x-lg" />
                  </button>
                </td>
              </tr>
            )
          })}
          {items.length === 0 && (
            <tr><td colSpan={COLS.length + 3} className="text-center text-muted small py-4">No product lines extracted.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function displayValue(item: DocImportItem, key: keyof ItemPatch): string {
  if (key === 'normalized_product_name') return item.normalized_product_name || item.ocr_product_name
  const v = (item as unknown as Record<string, unknown>)[key]
  return v == null || v === '' ? '—' : String(v)
}
