import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { SupplierRow, SupplierStockRow, WorkspaceItem } from '../../types/procurement'
import { num, date } from '../stock/format'
import { EmptyState } from '../common/EmptyState'
import { preferredSupplier } from './purchaseValue'

/** Stable row key: supplier product code, falling back to the mapped code. */
export const stockRowKey = (r: SupplierStockRow) => r.supplier_product_code ?? r.product_code ?? ''

/** Loose shape shared by both offer helpers — `scheme`/`free`/`discount` come
 *  back as either a real number (procurement.supplier_stock's actual live
 *  column types) or a string (the type this project's SupplierStockRow
 *  declares), so both are accepted and coerced via Number(). `discount` is a
 *  VARCHAR column that holds messy free-text in practice (e.g. "16% MICRO
 *  CARSYON 1"), not always a clean percentage — Number() safely yields NaN
 *  for those rows rather than a false reading. */
type OfferFields = { scheme?: number | string | null; free?: number | string | null; discount?: number | string | null }

/** Compact offer badge from the row's real scheme/free/discount (parsed at
 *  import from the supplier's own Excel scheme text, e.g. "10 F 1" -> scheme=10,
 *  free=1) — not the still-unpopulated WorkspaceItem.offer field used
 *  elsewhere in the grid. Buy-X-Get-Y wins display priority over a flat
 *  discount when both are present. */
export function formatOffer(r: OfferFields): string | null {
  const buy = r.scheme != null ? Number(r.scheme) : 0
  const free = r.free != null ? Number(r.free) : 0
  if (buy > 0 && free > 0) return `${buy}+${free}`
  if (r.discount != null && Number(r.discount) > 0) return `${num(Number(r.discount))}% OFF`
  return null
}

/** Non-blocking warning when a finalized Order Qty misses the Buy-X threshold
 *  of a Buy-X-Get-Y scheme (§ OFFER WARNING — informational only, never
 *  blocks Add/Save). */
export function offerWarning(r: OfferFields, qty: number): string | null {
  const buy = r.scheme != null ? Number(r.scheme) : 0
  const free = r.free != null ? Number(r.free) : 0
  if (buy > 0 && free > 0 && qty > 0 && qty < buy) {
    return `Qty does not qualify for supplier offer. Increase to ${buy} to receive ${free} free.`
  }
  return null
}

// Same caret-key exemption ProductGrid uses: while the text caret is live
// inside the Order Qty input, Backspace/Delete/Home/End must reach the
// browser untouched — everything else (Enter/Up/Down/Right/Left/Space) is
// owned by the grid's spreadsheet-style keyboard workflow, mirrored here for
// parity with Review All / Supplier Purchasing.
const CARET_KEYS = new Set(['Home', 'End', 'Backspace', 'Delete'])
function isTextEditor(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el || !el.tagName) return false
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable === true
}

type Zone = 'qty' | 'supplier'

/** Supplier Live Stock. Shows the supplier's live stock file (supplier_stock)
 *  already resolved to store ProductCodes via SupplierProductMatch and
 *  intersected with the current VPL. Selection + order qty are owned by the page
 *  so the persistent Product Details panel stays in sync with the focused row.
 *  Keyboard workflow (Up/Down/Enter/Right/Left/Esc/Space), checkbox bulk-select
 *  and the Supplier Recommendation zone all mirror ProductGrid exactly — same
 *  `checked`/`recommendations`/`selectedSupplier` state, same Assign Selected
 *  bar, no new selection model. */
export function SupplierStockTable({
  rows,
  loading,
  error,
  onOrder,
  busy,
  storeStockByCode,
  statusByCode,
  selectedKey,
  onSelect,
  draft,
  onDraftChange,
  checkableByCode,
  checked,
  onToggle,
  onToggleAll,
  itemByCode,
  recommendations,
  selectedSupplier,
  onSelectSupplier,
  onCommitSupplier,
  onSupplierFocusChange,
}: {
  rows: SupplierStockRow[]
  loading: boolean
  error: string | null
  onOrder: (row: SupplierStockRow, qty: number) => void
  busy: boolean
  /** Current store stock keyed by mapped store ProductCode (from the workspace
   *  items already loaded for this refresh — no extra fetch). */
  storeStockByCode: Map<string, number>
  /** Assigned / Skipped state keyed by mapped ProductCode (nothing shown for
   *  rows still in the Review workflow). */
  statusByCode: Map<string, 'assigned' | 'skipped'>
  selectedKey: string | null
  onSelect: (row: SupplierStockRow) => void
  draft: Record<string, string>
  onDraftChange: (key: string, value: string) => void
  /** order_item_id keyed by ProductCode, only for rows eligible for bulk
   *  checkbox selection (mapped to a workspace item, not skipped/locked/
   *  already assigned). Rows without an entry render a disabled checkbox. */
  checkableByCode: Map<string, string>
  checked: Set<string>
  onToggle: (id: string) => void
  onToggleAll: (ids: string[], on: boolean) => void
  /** Every workspace item keyed by ProductCode — resolves a row to the
   *  order-item id the Supplier Recommendation panel/API operate on. */
  itemByCode: Map<string, WorkspaceItem>
  /** Supplier recommendations keyed by order_item_id (same shape ProductGrid
   *  and SupplierRecPanel consume). */
  recommendations: Record<string, SupplierRow[]>
  /** Locally-selected supplier per row (not yet committed). */
  selectedSupplier: Record<string, string>
  onSelectSupplier: (orderItemId: string, supplierCode: string) => void
  onCommitSupplier: (item: WorkspaceItem, supplierCode: string) => void
  /** Fires when the keyboard enters/leaves the Supplier Recommendation zone, so
   *  the external supplier panel can show itself as active. */
  onSupplierFocusChange?: (active: boolean) => void
}) {
  // Order-qty inputs, keyed by row, so keyboard nav can (re)focus a row's cell.
  const inputs = useRef<Record<string, HTMLInputElement | null>>({})
  const wrapRef = useRef<HTMLDivElement>(null)

  const [zone, setZone] = useState<Zone>('qty')
  const [supIndex, setSupIndex] = useState(0)

  const selectedIndex = rows.findIndex((r) => stockRowKey(r) === selectedKey)

  // A new active row always starts in the Order Qty zone — same in-render
  // adjustment pattern ProductGrid uses (avoids an effect race between this
  // reset and the page's own selection-repair effect).
  const [prevSelectedKey, setPrevSelectedKey] = useState(selectedKey)
  if (selectedKey !== prevSelectedKey) {
    setPrevSelectedKey(selectedKey)
    setZone('qty')
    setSupIndex(0)
  }

  // Land keyboard focus: the Order Qty cell in the qty zone, or the wrapper
  // (so Up/Down/Enter/Left drive the supplier cursor) in the supplier zone —
  // mirrors ProductGrid's own focus effect.
  useEffect(() => {
    // Same fix as ProductGrid: with no row focus target yet (index transiently
    // -1), park focus on the container so it — not the native page — owns
    // arrow-key navigation.
    if (selectedIndex < 0) { if (rows.length > 0) wrapRef.current?.focus(); return }
    if (zone === 'supplier') { wrapRef.current?.focus(); return }
    const key = stockRowKey(rows[selectedIndex])
    inputs.current[key]?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey, rows.length, zone])

  useEffect(() => {
    onSupplierFocusChange?.(zone === 'supplier')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zone])

  if (loading) return <div className="pm-queue__hint">Loading supplier live stock…</div>
  if (error) {
    return <EmptyState icon="bi-cloud-slash" title="Supplier stock unavailable" description={error} />
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        icon="bi-inboxes"
        title="No matched stock"
        description="Import supplier stock and map SupplierProductMatch, then reopen this supplier to see products available in the current VPL."
      />
    )
  }

  const add = (r: SupplierStockRow) => {
    // Mirror ManualProductModal's guard: the Enter-to-advance keyboard path
    // bypasses the button's `disabled={busy}`, so a rapid double-Enter could
    // otherwise fire two POSTs before `busy` re-renders in.
    if (busy) return
    const n = Number(draft[stockRowKey(r)])
    if (!Number.isNaN(n) && n > 0) onOrder(r, n)
  }

  const itemFor = (r: SupplierStockRow | undefined) => (r?.product_code ? itemByCode.get(r.product_code) ?? null : null)
  const recsFor = (item: WorkspaceItem | null) => (item ? (recommendations[item.order_item_id] ?? []).slice(0, 8) : [])

  const moveSelection = (dir: 1 | -1) => {
    if (rows.length === 0) return
    const from = selectedIndex < 0 ? (dir === 1 ? -1 : rows.length) : selectedIndex
    const next = from + dir
    if (next >= 0 && next < rows.length) onSelect(rows[next])
  }

  // Enter / Down: finalize (save order qty), then move to the next row —
  // same "save + advance" contract as the main grid's Final Qty cell.
  const saveAndNext = () => {
    const cur = rows[selectedIndex]
    if (cur) add(cur)
    moveSelection(1)
  }

  const toggleCheckedCurrent = () => {
    const cur = rows[selectedIndex]
    if (!cur || !cur.product_code) return
    const id = checkableByCode.get(cur.product_code)
    if (id) onToggle(id)
  }

  // Right from Order Qty → Supplier Recommendation, starting on the currently
  // selected supplier, else the Preferred one, else the top-ranked card —
  // same rule ProductGrid uses. Any pending order-qty edit is saved first.
  const enterSupplierZone = () => {
    const cur = rows[selectedIndex]
    if (!cur) return
    add(cur)
    const item = itemFor(cur)
    const recs = recsFor(item)
    if (!item || recs.length === 0) return
    const selCode = selectedSupplier[item.order_item_id] ?? preferredSupplier(recs)
    const found = recs.findIndex((s) => s.supplier_code === selCode)
    const idx = found < 0 ? 0 : found
    setSupIndex(idx)
    setZone('supplier')
    onSelectSupplier(item.order_item_id, recs[idx].supplier_code)
  }

  // Up/Down inside the supplier panel — clamps at the first/last card; focus
  // stays inside the panel until an explicit Left or Esc (same as ProductGrid).
  const moveSupplier = (dir: 1 | -1) => {
    const item = itemFor(rows[selectedIndex])
    const recs = recsFor(item)
    if (!item || recs.length === 0) return
    const idx = Math.min(Math.max(supIndex + dir, 0), recs.length - 1)
    setSupIndex(idx)
    onSelectSupplier(item.order_item_id, recs[idx].supplier_code)
  }

  // Enter inside Supplier Recommendation: assign the highlighted supplier,
  // then advance to the next row.
  const commitSupplier = () => {
    const item = itemFor(rows[selectedIndex])
    const recs = recsFor(item)
    const s = recs[supIndex]
    if (!item || !s) return
    onCommitSupplier(item, s.supplier_code)
    setZone('qty')
    moveSelection(1)
  }

  const onGridKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (isTextEditor(e.target) && CARET_KEYS.has(e.key)) return // never hijack text editing

    if (zone === 'supplier') {
      if (e.key === 'ArrowUp') { e.preventDefault(); moveSupplier(-1) }
      else if (e.key === 'ArrowDown') { e.preventDefault(); moveSupplier(1) }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); setZone('qty') }
      else if (e.key === 'Enter') { e.preventDefault(); commitSupplier() }
      else if (e.key === 'Escape') { e.preventDefault(); setZone('qty') }
      return
    }

    if (e.key === 'ArrowRight') { e.preventDefault(); enterSupplierZone() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); saveAndNext() }
    else if (e.key === 'ArrowUp') { e.preventDefault(); moveSelection(-1) }
    else if (e.key === 'Enter') { e.preventDefault(); saveAndNext() }
    else if (e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); toggleCheckedCurrent() }
  }

  const checkableIds = rows
    .map((r) => (r.product_code ? checkableByCode.get(r.product_code) : undefined))
    .filter((id): id is string => Boolean(id))
  const allChecked = checkableIds.length > 0 && checkableIds.every((id) => checked.has(id))

  return (
    <div className="pm-grid-wrap" ref={wrapRef} tabIndex={-1} onKeyDown={onGridKey}>
      <table className="pm-grid pm-grid--stock">
        <thead>
          <tr>
            <th className="pm-grid__check">
              <input
                type="checkbox"
                aria-label="Select all"
                checked={allChecked}
                onChange={(e) => onToggleAll(checkableIds, e.target.checked)}
              />
            </th>
            <th>Supplier Product</th>
            <th>Mapped Product</th>
            <th>Offer</th>
            <th className="sx-num">Supplier Stock</th>
            <th className="sx-num">Store Stock</th>
            <th className="sx-num">Sugg.</th>
            <th className="sx-num">Disc%</th>
            <th className="sx-num">Free</th>
            <th>Scheme</th>
            <th className="sx-num">Last Sync</th>
            <th>Status</th>
            <th className="sx-num pm-grid__final">Order Qty</th>
            <th className="pm-grid__act" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const key = stockRowKey(r)
            const storeStock = r.product_code != null ? storeStockByCode.get(r.product_code) : undefined
            const status = r.product_code != null ? statusByCode.get(r.product_code) : undefined
            const checkId = r.product_code ? checkableByCode.get(r.product_code) : undefined
            return (
              <tr
                key={key}
                className={key === selectedKey ? 'pm-row--sel' : undefined}
                onClick={() => onSelect(r)}
              >
                <td className="pm-grid__check" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label="Select row"
                    checked={checkId ? checked.has(checkId) : false}
                    onChange={() => checkId && onToggle(checkId)}
                    disabled={!checkId}
                    title={!checkId ? 'Not eligible for bulk assign (unmapped, skipped, or already assigned)' : undefined}
                  />
                </td>
                <td>
                  <div className="pm-prod__name">{r.supplier_product_name ?? '—'}</div>
                  <div className="pm-prod__meta">{r.supplier_product_code}</div>
                </td>
                <td>
                  <div className="pm-prod__name">{r.product_name ?? '—'}</div>
                  <div className="pm-prod__meta">{r.product_code ?? '—'}</div>
                </td>
                <td>{formatOffer(r) ? <span className="pm-offer">{formatOffer(r)}</span> : <span className="sx-dim">—</span>}</td>
                <td className="sx-num pm-sx__supp">{num(r.available_stock ?? 0)}</td>
                <td className="sx-num pm-sx__store">{storeStock != null ? num(storeStock) : '—'}</td>
                <td className="sx-num sx-dim">{num(r.suggested_qty ?? 0)}</td>
                <td className="sx-num">{r.discount != null ? `${num(r.discount)}%` : '—'}</td>
                <td className="sx-num">{num(r.free ?? 0)}</td>
                <td className="sx-dim">{r.scheme ?? '—'}</td>
                <td className="sx-num sx-dim">{date(r.transaction_date)}</td>
                <td>
                  {status && (
                    <span className={`pm-sxchip pm-sxchip--${status}`}>
                      {status === 'assigned' ? 'Assigned' : 'Skipped'}
                    </span>
                  )}
                </td>
                <td className="sx-num pm-grid__final">
                  <span className="pm-qty-wrap">
                    <input
                      ref={(el) => { inputs.current[key] = el }}
                      className="pm-qty pm-qty--sm"
                      inputMode="numeric"
                      value={draft[key] ?? ''}
                      onFocus={(e) => { onSelect(r); e.currentTarget.select() }}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => onDraftChange(key, e.target.value)}
                    />
                    {/* § OFFER WARNING — informational only, never blocks Add/Save. */}
                    {(() => {
                      const warn = offerWarning(r, Number(draft[key]))
                      return warn ? <i className="bi bi-exclamation-triangle-fill pm-offer-warn" title={warn} /> : null
                    })()}
                  </span>
                </td>
                <td className="pm-grid__act">
                  <button
                    className="pm-btn pm-btn--add"
                    disabled={busy}
                    onClick={(e) => { e.stopPropagation(); add(r) }}
                    title="Add to order"
                  >
                    <i className="bi bi-plus-lg" /> Add
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
