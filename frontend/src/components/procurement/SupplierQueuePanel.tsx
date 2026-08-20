import { useMemo, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { PurchaseMode } from '../../types/procurement'
import { money, num, date } from '../stock/format'
import { ExportSettingsDialog } from './ExportSettingsDialog'
import { SupplierReplyImportDialog } from './SupplierReplyImportDialog'
import { FilterBar, FilterSearch, FilterSelect, FilterTabs } from '../../design-system/components/FilterBar'

/* ---- Data model (built by the workspace from draft assignments) ----------- */

export interface SupplierQueueProduct {
  assignment_id: string
  order_item_id: string
  product_name: string | null
  product_code: string | null
  ptr: number
  /** Landed cost (sync.PurchaseTrans.itemcost) for this supplier's last purchase. */
  cost: number | null
  mrp: number | null
  offer: string | null
  /** Flat discount % from the product's overall last purchase (any supplier) —
   *  always a separate figure from `offer`, never folded into it. */
  discount_pct: number | null
  /** Hover text for the offer/discount columns — who/when that overall last
   *  purchase actually came from, when it may differ from this line's supplier. */
  offer_source_label: string | null
  /** Quantity committed to this supplier — the maximum exportable for the line. */
  final_qty: number
  exported: boolean
}

export interface SupplierQueueGroup {
  supplier_code: string
  supplier_name: string | null
  product_count: number
  total_qty: number
  est_value: number
  /** est_value restricted to not-yet-exported lines — the CURRENT purchase
   *  value still to be sent, as opposed to est_value's lifetime total. */
  live_value: number
  offer_count: number
  exported_count: number
  status: 'ready' | 'partial' | 'exported'
  exported_at: string | null
  exported_by: string | null
  export_batch_number: string | null
  /** Assignment ids still eligible for export (not yet exported). */
  assignment_ids: string[]
  lines: SupplierQueueProduct[]
}

type Filter = 'all' | 'ready' | 'exported' | 'pending'
type SortKey = 'value' | 'count'

const FILTERS: { label: string; value: Filter }[] = [
  { label: 'All', value: 'all' },
  { label: 'Ready', value: 'ready' },
  { label: 'Pending', value: 'pending' },
  { label: 'Exported', value: 'exported' },
]

const STATUS_META: Record<SupplierQueueGroup['status'], { label: string; cls: string }> = {
  ready: { label: 'Ready', cls: 'pm-sqstat--ready' },
  partial: { label: 'Pending', cls: 'pm-sqstat--pending' },
  exported: { label: 'Exported', cls: 'pm-sqstat--exported' },
}

/**
 * Supplier Queue — the buyer's final review before creating purchase orders.
 * Compact desktop cards (products / qty / value / offers / status), one
 * inline-expandable supplier at a time, editable Export Qty, client-side
 * PDF/Excel, and mode-aware scoping. No dialogs; no backend changes.
 */
export function SupplierQueuePanel({
  tenantId,
  storeId,
  refreshId,
  actingUser,
  notify,
  groups,
  loading,
  error,
  mode,
  focusSupplierCode,
  onLoad,
  onExport,
  onExportSupplier,
  onExportAll,
  onExportSelected,
  exportingSelected,
  busySupplier,
  exportingAll,
}: {
  tenantId: string
  storeId: string
  refreshId: string
  actingUser: string
  notify: (kind: 'success' | 'danger', text: string) => void
  groups: SupplierQueueGroup[]
  loading: boolean
  error?: string | null
  mode: PurchaseMode
  focusSupplierCode: string | null
  onLoad: () => void
  onExport: (group: SupplierQueueGroup, assignmentIds: string[]) => void
  /** Plain per-supplier Export (collapsed card) — resolves the CURRENT live
   *  assignment set on the backend at request time instead of the possibly a
   *  few-hundred-ms-stale client `groups` snapshot (§14). The expanded Review
   *  export (below) still passes explicit assignment ids, since that path
   *  respects deliberate per-line Export-Qty hold-backs. */
  onExportSupplier: (supplierCode: string) => void
  onExportAll: () => void
  /** Export Selected Suppliers (§12) — a buyer-checked subset, exported one
   *  call per supplier (same per-supplier export `onExportSupplier` already
   *  uses under the hood). */
  onExportSelected: (supplierCodes: string[]) => void
  exportingSelected?: boolean
  busySupplier: string | null
  exportingAll: boolean
}) {
  // Whole-queue open state: auto-opens once suppliers load; manual toggle wins.
  const [openChoice, setOpenChoice] = useState<boolean | null>(null)
  const open = openChoice ?? groups.length > 0

  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<SortKey>('value')
  const [search, setSearch] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  // Per-assignment Export Qty overrides (default = line.final_qty).
  const [exportQty, setExportQty] = useState<Record<string, number>>({})
  const [errorsByCode, setErrorsByCode] = useState<Record<string, string[]>>({})
  const listRef = useRef<HTMLDivElement>(null)
  // Export Selected Suppliers (§12) — a buyer-checked subset of exportable cards.
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set())
  // Import Supplier Reply — file picked via a hidden input, then handed to
  // the preview/confirm dialog.
  const [replyFile, setReplyFile] = useState<File | null>(null)
  const replyInputRef = useRef<HTMLInputElement>(null)

  // Expanded supplier: auto-focus the selected supplier in non-review modes.
  const [expandChoice, setExpandChoice] = useState<string | null>(null)
  const autoExpand = mode !== 'review' ? focusSupplierCode : null
  const expandedCode =
    expandChoice === null ? autoExpand : expandChoice === '' ? null : expandChoice
  const toggleExpand = (code: string) =>
    setExpandChoice((prev) => {
      const current = prev === null ? autoExpand : prev === '' ? null : prev
      return current === code ? '' : code
    })
  const collapse = () => setExpandChoice('')

  // Never render ₹0.00 unless it is the real calculated value: while totals are
  // being computed show "Calculating…", and when a line/group has quantity but no
  // known rate yet (value === 0) show a dash instead of a false ₹0.00.
  const fmtValue = (value: number, qty: number) =>
    loading ? 'Calculating…' : value > 0 ? money(value) : qty > 0 ? '—' : money(value)

  const eq = (line: SupplierQueueProduct) => exportQty[line.assignment_id] ?? line.final_qty
  const setEq = (line: SupplierQueueProduct, raw: string) => {
    const clean = Math.min(line.final_qty, Number(raw.replace(/[^\d]/g, '') || 0))
    setExportQty((d) => ({ ...d, [line.assignment_id]: clean }))
  }

  // Mode scoping + filter + search + sort.
  const visible = useMemo(() => {
    let rows = groups
    if (mode !== 'review' && focusSupplierCode) rows = rows.filter((g) => g.supplier_code === focusSupplierCode)
    if (filter !== 'all') {
      rows = rows.filter((g) =>
        filter === 'ready' ? g.status === 'ready'
          : filter === 'exported' ? g.status === 'exported'
            : g.status === 'partial',
      )
    }
    const q = search.trim().toLowerCase()
    if (q) rows = rows.filter((g) => (g.supplier_name ?? g.supplier_code).toLowerCase().includes(q))
    return [...rows].sort((a, b) =>
      sort === 'value' ? b.est_value - a.est_value : b.product_count - a.product_count,
    )
  }, [groups, mode, focusSupplierCode, filter, search, sort])

  const totals = useMemo(
    () => ({
      suppliers: visible.length,
      products: visible.reduce((a, g) => a + g.product_count, 0),
      qty: visible.reduce((a, g) => a + g.total_qty, 0),
      value: visible.reduce((a, g) => a + g.est_value, 0),
    }),
    [visible],
  )

  const activeGroup = visible[Math.min(activeIndex, visible.length - 1)] ?? null

  // Export Selected Suppliers (§12) — only not-fully-exported cards are
  // selectable (an already-exported supplier has nothing left to send).
  const exportableVisible = useMemo(() => visible.filter((g) => g.status !== 'exported'), [visible])
  const allVisibleSelected =
    exportableVisible.length > 0 && exportableVisible.every((g) => selectedCodes.has(g.supplier_code))
  const toggleSelected = (code: string) =>
    setSelectedCodes((prev) => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  const toggleSelectAllVisible = () =>
    setSelectedCodes((prev) => {
      if (allVisibleSelected) {
        const next = new Set(prev)
        exportableVisible.forEach((g) => next.delete(g.supplier_code))
        return next
      }
      const next = new Set(prev)
      exportableVisible.forEach((g) => next.add(g.supplier_code))
      return next
    })

  /* ---- Effective (Export-Qty aware) supplier summary ---------------------- */
  const summary = (g: SupplierQueueGroup) => {
    const live = g.lines.filter((l) => !l.exported)
    const qty = live.reduce((a, l) => a + eq(l), 0)
    const value = live.reduce((a, l) => a + eq(l) * l.ptr, 0)
    const margin = live.reduce((a, l) => a + eq(l) * ((l.mrp ?? 0) - l.ptr), 0)
    const offers = live.filter((l) => l.offer).length
    return { products: live.length, qty, value, margin, offers }
  }

  const validate = (g: SupplierQueueGroup): string[] => {
    const errs: string[] = []
    const live = g.lines.filter((l) => !l.exported)
    if (live.length === 0) errs.push('No products left to export for this supplier.')
    if (live.reduce((a, l) => a + eq(l), 0) <= 0) errs.push('Set at least one Export Qty greater than 0.')
    const over = live.find((l) => eq(l) > l.final_qty)
    if (over) errs.push(`${over.product_name ?? over.product_code}: Export Qty cannot exceed Final Qty.`)
    return errs
  }

  const runExport = (g: SupplierQueueGroup | null) => {
    if (!g) return
    const errs = validate(g)
    if (errs.length) {
      setErrorsByCode((e) => ({ ...e, [g.supplier_code]: errs }))
      return
    }
    setErrorsByCode((e) => ({ ...e, [g.supplier_code]: [] }))
    const ids = g.lines.filter((l) => !l.exported && eq(l) > 0).map((l) => l.assignment_id)
    onExport(g, ids)
  }

  /* ---- Keyboard: ↑/↓ move · Enter expand · Esc collapse · Ctrl+E export --- */
  const onKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const inField = (e.target as HTMLElement).tagName === 'INPUT'
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'e') {
      e.preventDefault()
      runExport(expandedCode ? visible.find((g) => g.supplier_code === expandedCode) ?? activeGroup : activeGroup)
      return
    }
    if (e.key === 'Escape') { e.preventDefault(); collapse(); return }
    if (inField) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex((i) => Math.min(visible.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex((i) => Math.max(0, i - 1)) }
    else if (e.key === 'Enter' && activeGroup) { e.preventDefault(); toggleExpand(activeGroup.supplier_code) }
  }

  const loaded = groups.length > 0

  return (
    <section
      className="pm-sq"
      tabIndex={0}
      onKeyDown={onKey}
      aria-label="Supplier Queue"
    >
      <header className="pm-sq__head">
        <button className="pm-sq__toggle" onClick={() => setOpenChoice(!open)} aria-expanded={open}>
          <i className={`bi ${open ? 'bi-chevron-down' : 'bi-chevron-right'}`} />
          <i className="bi bi-collection" /> Supplier Queue
          {loaded && (
            <span className="pm-sq__sum">
              {totals.suppliers} suppliers · {totals.products} products · {num(totals.qty)} units · {fmtValue(totals.value, totals.qty)}
            </span>
          )}
        </button>
        <div className="pm-sq__actions">
          <button className="pm-btn pm-btn--ghost" onClick={onLoad} disabled={loading}>
            <i className="bi bi-arrow-repeat" /> {loading ? 'Loading…' : loaded ? 'Reload Queue' : 'Load Suppliers'}
          </button>
          <input
            ref={replyInputRef}
            type="file"
            accept=".xlsx"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) setReplyFile(f)
              e.target.value = ''
            }}
          />
          <button className="pm-btn pm-btn--ghost" onClick={() => replyInputRef.current?.click()}>
            <i className="bi bi-envelope-arrow-down" /> Import Supplier Reply
          </button>
          {loaded && (
            <>
              <button
                className="pm-btn pm-btn--ghost"
                onClick={() => { onExportSelected([...selectedCodes]); setSelectedCodes(new Set()) }}
                disabled={selectedCodes.size === 0 || Boolean(exportingSelected)}
                title="Export every checked supplier's current assignments"
              >
                <i className="bi bi-box-arrow-up" /> {exportingSelected ? 'Exporting…' : `Export Selected${selectedCodes.size > 0 ? ` (${selectedCodes.size})` : ''}`}
              </button>
              <button className="pm-btn pm-btn--primary" onClick={onExportAll} disabled={exportingAll}>
                <i className="bi bi-box-arrow-up" /> {exportingAll ? 'Exporting…' : 'Export All Purchase Orders'}
              </button>
            </>
          )}
        </div>
      </header>

      {open && (
        <div className="pm-sq__body">
          {loading ? (
            <div className="pm-sq__hint">Recalculating supplier totals…</div>
          ) : error ? (
            <div className="pm-sq__hint pm-sq__hint--error">
              <i className="bi bi-exclamation-triangle" /> {error}
              <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={onLoad}>
                <i className="bi bi-arrow-repeat" /> Retry
              </button>
            </div>
          ) : !loaded ? (
            <div className="pm-sq__hint">No suppliers available. Assign suppliers to products, then Load Suppliers.</div>
          ) : (
            <>
              <FilterBar compact className="pm-sq__toolbar" ariaLabel="Supplier queue filters">
                <FilterTabs value={filter} ariaLabel="Supplier status" options={FILTERS} onChange={setFilter} />
                <FilterSearch className="pm-sq__search" value={search} placeholder="Search supplier…" ariaLabel="Search supplier" onChange={setSearch} />
                <FilterSelect ariaLabel="Sort suppliers" value={sort} onChange={setSort}>
                  <option value="value">Sort: Highest Value</option>
                  <option value="count">Sort: Most Products</option>
                </FilterSelect>
                {exportableVisible.length > 0 && (
                  <label className="pm-chk pm-sq__selectall">
                    <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} />
                    Select all visible
                  </label>
                )}
              </FilterBar>

              {visible.length === 0 ? (
                <div className="pm-sq__hint">No suppliers match the current filter.</div>
              ) : (
                <div className="pm-sq__split">
                  <div className="pm-sq__list" ref={listRef}>
                    {visible.map((g, i) => {
                      const st = STATUS_META[g.status]
                      const isActive = i === activeIndex
                      const isOpen = expandedCode === g.supplier_code
                      const busy = busySupplier === g.supplier_code
                      return (
                        <div key={g.supplier_code} className={`pm-sqrow${isOpen ? ' pm-sqrow--open' : ''}`}>
                          <div
                            className={`pm-sqcard${isActive ? ' pm-sqcard--active' : ''}`}
                            onClick={() => { setActiveIndex(i); if (expandedCode !== g.supplier_code) toggleExpand(g.supplier_code) }}
                          >
                            {g.status !== 'exported' && (
                              <input
                                type="checkbox"
                                className="pm-sqcard__chk"
                                aria-label={`Select ${g.supplier_name ?? g.supplier_code} for export`}
                                checked={selectedCodes.has(g.supplier_code)}
                                onChange={() => toggleSelected(g.supplier_code)}
                                onClick={(e) => e.stopPropagation()}
                              />
                            )}
                            <span className="pm-sqcard__name">{g.supplier_name ?? g.supplier_code}</span>
                            <span className="pm-sqcard__stat"><b>{num(g.product_count)}</b>Products</span>
                            <span className="pm-sqcard__stat"><b>{num(g.total_qty)}</b>Qty</span>
                            <span className="pm-sqcard__stat"><b>{fmtValue(g.est_value, g.total_qty)}</b>Value</span>
                            <span className="pm-sqcard__stat"><b>{num(g.offer_count)}</b>Offers</span>
                            <span className={`pm-sqstat ${st.cls}`}>{st.label}</span>
                            <span className="pm-sqcard__cta">
                              <button
                                className="pm-btn pm-btn--ghost pm-btn--sm"
                                onClick={(e) => { e.stopPropagation(); toggleExpand(g.supplier_code) }}
                              >
                                {isOpen ? 'Close' : 'Review'}
                              </button>
                              <button
                                className="pm-btn pm-btn--success pm-btn--sm"
                                onClick={(e) => { e.stopPropagation(); onExportSupplier(g.supplier_code) }}
                                disabled={busy || g.status === 'exported' || g.product_count === 0}
                                title="Export every current assignment for this supplier"
                              >
                                <i className="bi bi-box-arrow-up" /> {busy ? 'Exporting…' : 'Export'}
                              </button>
                            </span>
                          </div>

                          {g.status === 'exported' && (
                            <div className="pm-sqcard__exported">
                              <i className="bi bi-check2-circle" /> Exported {date(g.exported_at)}
                              {g.exported_at && <> · {new Date(g.exported_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</>}
                              {g.exported_by && <> · by {g.exported_by}</>}
                              {g.export_batch_number && <> · {g.export_batch_number}</>}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>

                  {/* Right panel — the selected supplier's product detail:
                      PTR / MRP / Offer per line and the running order total,
                      persistent (not inline-per-row) so it reads as a real
                      left-list / right-detail split. */}
                  <div className="pm-sq__detail">
                    {(() => {
                      const g = visible.find((x) => x.supplier_code === expandedCode)
                      if (!g) {
                        return (
                          <div className="pm-sq__hint pm-sq__detailempty">
                            <i className="bi bi-hand-index" /> Select a supplier to review its products.
                          </div>
                        )
                      }
                      const busy = busySupplier === g.supplier_code
                      return (
                        <SupplierReview
                          tenantId={tenantId}
                          storeId={storeId}
                          refreshId={refreshId}
                          notify={notify}
                          group={g}
                          summary={summary(g)}
                          fmtValue={fmtValue}
                          eq={eq}
                          setEq={setEq}
                          errors={errorsByCode[g.supplier_code] ?? []}
                          busy={busy}
                          onExport={() => runExport(g)}
                        />
                      )
                    })()}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {replyFile && (
        <SupplierReplyImportDialog
          tenantId={tenantId}
          refreshId={refreshId}
          file={replyFile}
          actingUser={actingUser}
          notify={notify}
          onClose={() => setReplyFile(null)}
          onImported={() => onLoad()}
        />
      )}
    </section>
  )
}

/* ---- Expanded supplier review (inline, no dialog) ------------------------- */

function SupplierReview({
  tenantId,
  storeId,
  refreshId,
  notify,
  group,
  summary,
  fmtValue,
  eq,
  setEq,
  errors,
  busy,
  onExport,
}: {
  tenantId: string
  storeId: string
  refreshId: string
  notify: (kind: 'success' | 'danger', text: string) => void
  group: SupplierQueueGroup
  summary: { products: number; qty: number; value: number; margin: number; offers: number }
  fmtValue: (value: number, qty: number) => string
  eq: (l: SupplierQueueProduct) => number
  setEq: (l: SupplierQueueProduct, raw: string) => void
  errors: string[]
  busy: boolean
  onExport: () => void
}) {
  const [showExportSettings, setShowExportSettings] = useState(false)
  const exportedAll = group.status === 'exported'
  return (
    <div className="pm-sqexp">
      <div className="pm-sqexp__totalbar">
        <span className="pm-sqexp__totalname">{group.supplier_name ?? group.supplier_code}</span>
        <span className="pm-sqexp__totalval">
          <span className="pm-sqexp__totallbl">Total Order Value</span>
          <b>{fmtValue(summary.value, summary.qty)}</b>
        </span>
      </div>
      <div className="pm-sqexp__summary">
        <Stat label="Products" value={num(summary.products)} />
        <Stat label="Qty" value={num(summary.qty)} />
        <Stat label="Value" value={fmtValue(summary.value, summary.qty)} />
        <Stat label="Offers" value={num(summary.offers)} />
        <Stat label="Est. Margin" value={money(summary.margin)} />
      </div>

      <div className="pm-sqexp__tablewrap">
        <table className="pm-sqexp__table">
          <thead>
            <tr>
              <th>Product</th>
              <th className="sx-num">PTR</th>
              <th className="sx-num">Cost</th>
              <th className="sx-num">MRP</th>
              <th>Offer</th>
              <th className="sx-num">Dis %</th>
              <th className="sx-num">Final Qty</th>
              <th className="sx-num">Export Qty</th>
            </tr>
          </thead>
          <tbody>
            {group.lines.map((l) => (
              <tr key={l.assignment_id} className={l.exported ? 'pm-sqexp__row--done' : ''}>
                <td>{l.product_name ?? l.product_code ?? '—'}</td>
                <td className="sx-num">{l.ptr > 0 ? money(l.ptr) : '—'}</td>
                <td className="sx-num">{l.cost != null && l.cost > 0 ? money(l.cost) : '—'}</td>
                <td className="sx-num">{l.mrp != null && l.mrp > 0 ? money(l.mrp) : '—'}</td>
                <td title={l.offer_source_label ?? undefined}>
                  {l.offer ? <span className="pm-offer">{l.offer}</span> : <span className="sx-dim">—</span>}
                </td>
                <td className="sx-num" title={l.offer_source_label ?? undefined}>
                  {l.discount_pct != null && l.discount_pct > 0 ? `${num(l.discount_pct)}%` : <span className="sx-dim">—</span>}
                </td>
                <td className="sx-num">{num(l.final_qty)}</td>
                <td className="sx-num">
                  {l.exported ? (
                    <span className="sx-dim">{num(l.final_qty)}</span>
                  ) : (
                    <input
                      className="pm-qty"
                      inputMode="numeric"
                      maxLength={5}
                      value={String(eq(l))}
                      onFocus={(e) => e.currentTarget.select()}
                      onChange={(e) => setEq(l, e.target.value)}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {errors.length > 0 && (
        <div className="pm-sqexp__errors">
          <i className="bi bi-exclamation-triangle" />
          {errors.map((msg, i) => <span key={i}>{msg}</span>)}
        </div>
      )}

      <div className="pm-sqexp__foot">
        <span className="pm-sqexp__note">Export sends assigned quantities; set a line to 0 to hold it back.</span>
        <div className="pm-sqexp__btns">
          <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => setShowExportSettings(true)}>
            <i className="bi bi-file-earmark-arrow-down" /> Export Document…
          </button>
          <button className="pm-btn pm-btn--success pm-btn--sm" onClick={onExport} disabled={busy || exportedAll || group.assignment_ids.length === 0}>
            <i className="bi bi-box-arrow-up" /> {busy ? 'Exporting…' : 'Export'}
          </button>
        </div>
      </div>

      {showExportSettings && (
        <ExportSettingsDialog
          tenantId={tenantId}
          storeId={storeId}
          refreshId={refreshId}
          group={group}
          eq={eq}
          notify={notify}
          onClose={() => setShowExportSettings(false)}
        />
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="pm-sqexp__stat">
      <span className="pm-sqexp__stat-val">{value}</span>
      <span className="pm-sqexp__stat-lbl">{label}</span>
    </div>
  )
}
