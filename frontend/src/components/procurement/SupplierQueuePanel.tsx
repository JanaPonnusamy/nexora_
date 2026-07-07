import { useMemo, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { PurchaseMode } from '../../types/procurement'
import { money, num, date } from '../stock/format'

/* ---- Data model (built by the workspace from draft assignments) ----------- */

export interface SupplierQueueProduct {
  assignment_id: string
  order_item_id: string
  product_name: string | null
  product_code: string | null
  ptr: number
  mrp: number | null
  offer: string | null
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
  groups,
  loading,
  mode,
  focusSupplierCode,
  onLoad,
  onExport,
  onExportAll,
  busySupplier,
  exportingAll,
}: {
  groups: SupplierQueueGroup[]
  loading: boolean
  mode: PurchaseMode
  focusSupplierCode: string | null
  onLoad: () => void
  onExport: (group: SupplierQueueGroup, assignmentIds: string[]) => void
  onExportAll: () => void
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
          {loaded && (
            <button className="pm-btn pm-btn--primary" onClick={onExportAll} disabled={exportingAll}>
              <i className="bi bi-box-arrow-up" /> Export All
            </button>
          )}
        </div>
      </header>

      {open && (
        <div className="pm-sq__body">
          {loading ? (
            <div className="pm-sq__hint">Recalculating supplier totals…</div>
          ) : !loaded ? (
            <div className="pm-sq__hint">No draft assignments yet. Assign suppliers to products, then Load Suppliers.</div>
          ) : (
            <>
              <div className="pm-sq__toolbar">
                <div className="pm-sq__filters">
                  {FILTERS.map((f) => (
                    <button
                      key={f.value}
                      className={`pm-sq__filter${filter === f.value ? ' pm-sq__filter--on' : ''}`}
                      onClick={() => setFilter(f.value)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
                <span className="sx-search pm-sq__search">
                  <i className="bi bi-search" aria-hidden="true" />
                  <input type="search" value={search} placeholder="Search supplier…" aria-label="Search supplier" onChange={(e) => setSearch(e.target.value)} />
                </span>
                <select className="sx-select" aria-label="Sort suppliers" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                  <option value="value">Sort: Highest Value</option>
                  <option value="count">Sort: Most Products</option>
                </select>
              </div>

              {visible.length === 0 ? (
                <div className="pm-sq__hint">No suppliers match the current filter.</div>
              ) : (
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
                          onClick={() => setActiveIndex(i)}
                        >
                          <span className="pm-sqcard__name">{g.supplier_name ?? g.supplier_code}</span>
                          <span className="pm-sqcard__stat"><b>{num(g.product_count)}</b>Products</span>
                          <span className="pm-sqcard__stat"><b>{num(g.total_qty)}</b>Qty</span>
                          <span className="pm-sqcard__stat"><b>{fmtValue(g.est_value, g.total_qty)}</b>Value</span>
                          <span className="pm-sqcard__stat"><b>{num(g.offer_count)}</b>Offers</span>
                          <span className={`pm-sqstat ${st.cls}`}>{st.label}</span>
                          <span className="pm-sqcard__cta">
                            <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => toggleExpand(g.supplier_code)}>
                              {isOpen ? 'Close' : 'Review'}
                            </button>
                            <button
                              className="pm-btn pm-btn--success pm-btn--sm"
                              onClick={() => runExport(g)}
                              disabled={busy || g.status === 'exported' || g.assignment_ids.length === 0}
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

                        {isOpen && (
                          <SupplierReview
                            group={g}
                            summary={summary(g)}
                            eq={eq}
                            setEq={setEq}
                            errors={errorsByCode[g.supplier_code] ?? []}
                            busy={busy}
                            onExport={() => runExport(g)}
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  )
}

/* ---- Expanded supplier review (inline, no dialog) ------------------------- */

function SupplierReview({
  group,
  summary,
  eq,
  setEq,
  errors,
  busy,
  onExport,
}: {
  group: SupplierQueueGroup
  summary: { products: number; qty: number; value: number; margin: number; offers: number }
  eq: (l: SupplierQueueProduct) => number
  setEq: (l: SupplierQueueProduct, raw: string) => void
  errors: string[]
  busy: boolean
  onExport: () => void
}) {
  const exportedAll = group.status === 'exported'
  return (
    <div className="pm-sqexp">
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
              <th>Offer</th>
              <th className="sx-num">Final Qty</th>
              <th className="sx-num">Export Qty</th>
            </tr>
          </thead>
          <tbody>
            {group.lines.map((l) => (
              <tr key={l.assignment_id} className={l.exported ? 'pm-sqexp__row--done' : ''}>
                <td>{l.product_name ?? l.product_code ?? '—'}</td>
                <td className="sx-num">{l.ptr > 0 ? money(l.ptr) : '—'}</td>
                <td>{l.offer ? <span className="pm-offer">{l.offer}</span> : <span className="sx-dim">—</span>}</td>
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
          <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => downloadCsv(group, eq)}>
            <i className="bi bi-file-earmark-excel" /> Export Excel
          </button>
          <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => printPdf(group, eq)}>
            <i className="bi bi-file-earmark-pdf" /> Export PDF
          </button>
          <button className="pm-btn pm-btn--success pm-btn--sm" onClick={onExport} disabled={busy || exportedAll || group.assignment_ids.length === 0}>
            <i className="bi bi-box-arrow-up" /> {busy ? 'Exporting…' : 'Export'}
          </button>
        </div>
      </div>
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

/* ---- Client-side document export (no backend) ----------------------------- */

function exportRows(group: SupplierQueueGroup, eq: (l: SupplierQueueProduct) => number) {
  return group.lines
    .filter((l) => l.exported || eq(l) > 0)
    .map((l) => ({
      product: l.product_name ?? l.product_code ?? '',
      ptr: l.ptr,
      offer: l.offer ?? '',
      finalQty: l.final_qty,
      exportQty: l.exported ? l.final_qty : eq(l),
    }))
}

function downloadCsv(group: SupplierQueueGroup, eq: (l: SupplierQueueProduct) => number) {
  const rows = exportRows(group, eq)
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`
  const lines = [
    ['Product', 'PTR', 'Offer', 'Final Qty', 'Export Qty'].join(','),
    ...rows.map((r) => [r.product, r.ptr, r.offer, r.finalQty, r.exportQty].map(esc).join(',')),
  ]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `PO_${group.supplier_code}_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function printPdf(group: SupplierQueueGroup, eq: (l: SupplierQueueProduct) => number) {
  const rows = exportRows(group, eq)
  const esc = (v: string) => v.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c] as string))
  const body = rows
    .map((r) => `<tr><td>${esc(r.product)}</td><td class="n">${r.ptr.toFixed(2)}</td><td>${esc(r.offer)}</td><td class="n">${r.finalQty}</td><td class="n">${r.exportQty}</td></tr>`)
    .join('')
  const w = window.open('', '_blank', 'width=800,height=900')
  if (!w) return
  w.document.write(`<!doctype html><html><head><title>PO ${esc(group.supplier_code)}</title><style>
    body{font-family:Segoe UI,Arial,sans-serif;padding:24px;color:#0f172a}
    h1{font-size:18px;margin:0 0 4px} .meta{color:#64748b;font-size:12px;margin-bottom:16px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left} th{background:#f8fafc}
    td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
  </style></head><body>
    <h1>Purchase Order — ${esc(group.supplier_name ?? group.supplier_code)}</h1>
    <div class="meta">Supplier ${esc(group.supplier_code)} · ${rows.length} products · Generated ${new Date().toLocaleString('en-IN')}</div>
    <table><thead><tr><th>Product</th><th class="n">PTR</th><th>Offer</th><th class="n">Final Qty</th><th class="n">Export Qty</th></tr></thead><tbody>${body}</tbody></table>
  </body></html>`)
  w.document.close()
  w.focus()
  w.print()
}
