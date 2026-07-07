import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useActingUser } from '../../hooks/useActingUser'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { productMappingService } from '../../services/productMappingService'
import type { Mapping, ProductSearchResult, ReviewProgress } from '../../types/productMapping'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxProgress, SxSearch, SxStat, SxTable } from '../sync/ui'
import { AttrCell, ConfidenceChip, ProductCell, RequireStorePair, type MappingCtx } from './shared'
import { ProductSearchDialog } from './ProductSearchDialog'

const PAGE_SIZE = 50

interface Override { code: string; name: string }

/** Manual Review v2 — a select-by-default review grid: every PENDING row on the
 *  page starts checked, the reviewer only unchecks bad matches (or picks a
 *  correct product), then approves/rejects the whole selection in one
 *  transaction. Auto-loads the next page and tracks live progress. */
export function ManualReviewTab({ ctx }: { ctx: MappingCtx }) {
  const actingUser = useActingUser()
  const [rows, setRows] = useState<Mapping[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [overrides, setOverrides] = useState<Record<string, Override>>({})
  const [progress, setProgress] = useState<ReviewProgress>({ remaining: 0, approved_today: 0 })
  const [focused, setFocused] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [picking, setPicking] = useState<Mapping | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const selectAllRef = useRef<HTMLInputElement>(null)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const load = useCallback((toPage: number, opts?: { keepToast?: boolean }) => {
    // Guard mirrors <RequireStorePair>: both store ids are required by the
    // backend (tenant_id/source_store_id/target_store_id are non-optional
    // Query(...) params), so an incomplete pair must not fetch at all rather
    // than send a request the API is guaranteed to reject with 422.
    if (!ctx.sourceStoreId || !ctx.targetStoreId) {
      setLoading(false)
      return
    }
    // Hoisted inner so the empty-page fallback can re-fetch the front of the
    // queue without self-referencing the memoised `load`.
    function fetchPage(page: number) {
      setLoading(true)
      setError(null)
      Promise.all([
        productMappingService.mappings(ctx.tenantId, {
          status: 'PENDING',
          source_store_id: ctx.sourceStoreId,
          target_store_id: ctx.targetStoreId,
          search: debouncedSearch || undefined,
          page,
          page_size: PAGE_SIZE,
        }),
        productMappingService.reviewProgress(ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId),
      ])
        .then(([res, prog]) => {
          // Safety net: if this page came back empty but work still exists (offset
          // drift after deletions, or a filter narrowing the set), fall back to
          // the front of the queue instead of showing a spurious blank page.
          if (res.items.length === 0 && res.total > 0 && res.page > 1) {
            fetchPage(1)
            return
          }
          setRows(res.items)
          setTotal(res.total)
          setPage(res.page)
          setProgress(prog)
          setSelected(new Set(res.items.map((m) => m.mapping_id))) // all selected by default
          setOverrides({})
          setFocused(0)
          setLoading(false)
          if (!opts?.keepToast) setToast(null)
        })
        .catch((e) => { setError(e instanceof Error ? e.message : 'Failed to load review queue'); setLoading(false) })
    }
    fetchPage(toPage)
  }, [ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId, debouncedSearch])

  // (re)load whenever the store pair or search changes
  useEffect(() => { load(1) }, [load])

  useEffect(() => {
    if (!toast) return
    const t = window.setTimeout(() => setToast(null), 4000)
    return () => window.clearTimeout(t)
  }, [toast])

  // header select-all: indeterminate when only some rows are checked
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selected.size > 0 && selected.size < rows.length
    }
  }, [selected, rows.length])

  const allChecked = rows.length > 0 && selected.size === rows.length

  const toggleRow = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  const toggleAll = () => {
    setSelected((prev) => (prev.size === rows.length ? new Set() : new Set(rows.map((m) => m.mapping_id))))
  }

  // Return keyboard focus to the grid whenever the picker dialog closes.
  const focusGrid = () => window.requestAnimationFrame(() => gridRef.current?.focus())
  const closePicker = () => { setPicking(null); focusGrid() }

  const applyOverride = (mappingId: string, product: ProductSearchResult) => {
    setOverrides((prev) => ({ ...prev, [mappingId]: { code: product.product_code, name: product.product_name } }))
    setSelected((prev) => new Set(prev).add(mappingId)) // an overridden row is implicitly kept
    setPicking(null)
    focusGrid()
  }

  const clearOverride = (mappingId: string) => {
    setOverrides((prev) => {
      const next = { ...prev }
      delete next[mappingId]
      return next
    })
  }

  const runBulk = async (action: 'APPROVE' | 'REJECT') => {
    if (selected.size === 0) return
    setBusy(true)
    try {
      const items = [...selected].map((id) => {
        const ov = overrides[id]
        return ov ? { mapping_id: id, target_product_code: ov.code, target_product_name: ov.name } : { mapping_id: id }
      })
      const res = await productMappingService.bulkReview(ctx.tenantId, {
        action,
        items,
        source_store_id: ctx.sourceStoreId,
        target_store_id: ctx.targetStoreId,
        page,
        page_size: PAGE_SIZE,
        actor: actingUser || null,
      })
      const n = action === 'APPROVE' ? res.approved : res.rejected
      const verb = action === 'APPROVE' ? 'Approved' : 'Rejected'
      const bits = [`${verb} ${n} product${n === 1 ? '' : 's'}.`]
      if (res.skipped > 0) bits.push(`${res.skipped} skipped.`)
      if (res.failed.length > 0) bits.push(`${res.failed.length} could not be applied — ${res.failed[0].reason}`)
      bits.push(res.has_next ? 'Loading next review page…' : res.remaining > 0 ? 'Loading remaining…' : 'Review queue is clear 🎉')
      setToast(bits.join(' '))
      load(res.current_page, { keepToast: true }) // trust the server's paging
    } catch (e) {
      setToast(e instanceof Error ? e.message : 'Bulk action failed. Nothing was changed.')
    } finally {
      setBusy(false)
    }
  }

  const skipSelected = () => {
    const n = selected.size
    if (n === 0) return
    if (page < totalPages) {
      setToast(`Skipped ${n} for now. Loading next page…`)
      load(page + 1, { keepToast: true })
    } else {
      setToast(`Skipped ${n}. No more pages — reloading remaining.`)
      load(1, { keepToast: true })
    }
  }

  // keyboard productivity (ignored while typing in an input/textarea)
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (picking) return
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    const row = rows[focused]
    if (e.key === 'ArrowDown') { e.preventDefault(); setFocused((f) => Math.min(rows.length - 1, f + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setFocused((f) => Math.max(0, f - 1)) }
    else if (e.key === ' ') { e.preventDefault(); if (row) toggleRow(row.mapping_id) }
    else if (e.key === 'a' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); setSelected(new Set(rows.map((m) => m.mapping_id))) }
    else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!busy) runBulk('APPROVE') }
    else if (e.key === 'Enter') { e.preventDefault(); if (row) setPicking(row) }
    else if (e.key === 'PageDown') { e.preventDefault(); if (page < totalPages) load(page + 1) }
    else if (e.key === 'PageUp') { e.preventDefault(); if (page > 1) load(page - 1) }
  }

  const progressPct = useMemo(() => {
    const done = progress.approved_today
    const denom = done + progress.remaining
    return denom > 0 ? Math.round((done / denom) * 100) : 0
  }, [progress])

  if (loading && rows.length === 0) {
    return <RequireStorePair ctx={ctx}><TableSkeleton rows={8} columns={6} /></RequireStorePair>
  }

  return (
    <RequireStorePair ctx={ctx}>
      {error ? <ErrorState description={error} onRetry={() => load(page)} /> : (
        <>
          {/* Progress dashboard */}
          <div className="pmx-stats">
            <SxStat icon="bi-inboxes" tone="warning" value={progress.remaining.toLocaleString()} label="Remaining reviews" />
            <SxStat icon="bi-file-earmark-text" tone="indigo" value={`${page} / ${totalPages}`} label="Current page" />
            <SxStat icon="bi-check2-square" tone="teal" value={selected.size.toLocaleString()} label="Selected rows"
              sub={Object.keys(overrides).length ? `${Object.keys(overrides).length} overridden` : undefined} />
            <SxStat icon="bi-calendar-check" tone="success" value={progress.approved_today.toLocaleString()} label="Approved today" />
            <div className="pmx-stat-progress sx-stat sx-tone-violet">
              <span className="sx-stat__icon"><i className="bi bi-graph-up-arrow" aria-hidden="true" /></span>
              <div className="min-w-0 w-100">
                <div className="sx-stat__value">{progressPct}%</div>
                <div className="sx-stat__label">Progress today</div>
                <SxProgress value={progressPct} />
              </div>
            </div>
          </div>

          <SxCard>
            <SxCardHead
              title="Manual Review"
              icon="bi-diagram-3"
              sub={`${total.toLocaleString()} pending · ${selected.size} selected`}
              action={
                <div className="pmx-toolbar">
                  <SxSearch value={search} onChange={setSearch} placeholder="Filter source product…" />
                  <SxButton variant="success" sm icon="bi-check2-all" busy={busy} disabled={selected.size === 0} onClick={() => runBulk('APPROVE')}>
                    Approve Selected
                  </SxButton>
                  <SxButton variant="danger" sm icon="bi-x-circle" busy={busy} disabled={selected.size === 0} onClick={() => runBulk('REJECT')}>
                    Reject Selected
                  </SxButton>
                  <SxButton variant="ghost" sm icon="bi-skip-forward" disabled={busy || selected.size === 0} onClick={skipSelected}>
                    Skip Selected
                  </SxButton>
                </div>
              }
            />
            <SxCardBody flush>
              {rows.length === 0 ? (
                <EmptyState icon="bi-check2-all" title="Nothing to review" description="Every product for this store pair is matched or already decided." />
              ) : (
                <div ref={gridRef} tabIndex={0} onKeyDown={onKeyDown} className="pmx-grid" role="grid" aria-label="Review queue">
                  <SxTable>
                    <thead>
                      <tr>
                        <th className="pmx-check">
                          <input ref={selectAllRef} type="checkbox" checked={allChecked} onChange={toggleAll} aria-label="Select all rows on this page" />
                        </th>
                        <th>Source Product</th>
                        <th>Attributes</th>
                        <th>Correct Product</th>
                        <th className="sx-num">Best</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((m, i) => {
                        const ov = overrides[m.mapping_id]
                        const checked = selected.has(m.mapping_id)
                        return (
                          <tr
                            key={m.mapping_id}
                            className={`${i === focused ? 'sx-row--active' : ''}${checked ? '' : ' pmx-row--off'}`}
                            onMouseDown={() => setFocused(i)}
                          >
                            <td className="pmx-check">
                              <input type="checkbox" checked={checked} onChange={() => toggleRow(m.mapping_id)} aria-label={`Select ${m.source_product_name}`} />
                            </td>
                            <td><ProductCell code={m.source_product_code} name={m.source_product_name} /></td>
                            <td><AttrCell m={m} /></td>
                            <td>
                              {ov ? (
                                <div className="pmx-correct">
                                  <div className="sx-rowlabel">
                                    <span className="sx-rowlabel__main">{ov.name}</span>
                                    <span className="sx-rowlabel__sub">Code {ov.code}</span>
                                  </div>
                                  <div className="pmx-correct__actions">
                                    <SxChip tone="violet">Manual override</SxChip>
                                    <button type="button" className="pmx-linkbtn" onClick={() => setPicking(m)} title="Change product"><i className="bi bi-pencil" /></button>
                                    <button type="button" className="pmx-linkbtn" onClick={() => clearOverride(m.mapping_id)} title="Undo override"><i className="bi bi-arrow-counterclockwise" /></button>
                                  </div>
                                </div>
                              ) : (
                                <div className="pmx-correct">
                                  {m.target_product_name
                                    ? <ProductCell code={m.target_product_code} name={m.target_product_name} />
                                    : <span className="sx-dim">No suggestion</span>}
                                  <button type="button" className="pmx-searchbtn" onClick={() => setPicking(m)} title="Search for the correct product">
                                    <i className="bi bi-search" aria-hidden="true" />Search
                                  </button>
                                </div>
                              )}
                            </td>
                            <td className="sx-num"><ConfidenceChip value={m.confidence} /></td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </SxTable>
                </div>
              )}
            </SxCardBody>
            {rows.length > 0 && (
              <div className="pmx-foot">
                <span className="sx-dim">
                  Page {page} of {totalPages} · showing {rows.length} of {total.toLocaleString()} pending
                </span>
                <div className="pmx-foot__keys sx-dim">
                  <kbd>Space</kbd> toggle · <kbd>Ctrl</kbd>+<kbd>A</kbd> all · <kbd>Enter</kbd> search · <kbd>Ctrl</kbd>+<kbd>Enter</kbd> approve · <kbd>PgUp</kbd>/<kbd>PgDn</kbd> page
                </div>
                <div className="pmx-foot__pager">
                  <button type="button" className="sx-pager__btn" disabled={page <= 1 || busy} onClick={() => load(page - 1)} aria-label="Previous page"><i className="bi bi-chevron-left" /></button>
                  <span className="sx-pager__page">{page} / {totalPages}</span>
                  <button type="button" className="sx-pager__btn" disabled={page >= totalPages || busy} onClick={() => load(page + 1)} aria-label="Next page"><i className="bi bi-chevron-right" /></button>
                </div>
              </div>
            )}
          </SxCard>

          {toast && (
            <div className="pmx-toast" role="status">
              <i className="bi bi-info-circle" aria-hidden="true" />
              <span>{toast}</span>
              <button type="button" className="pmx-toast__close" aria-label="Dismiss" onClick={() => setToast(null)}><i className="bi bi-x" /></button>
            </div>
          )}

          {picking && (
            <ProductSearchDialog
              tenantId={ctx.tenantId}
              targetStoreId={ctx.targetStoreId}
              targetLabel={ctx.targetLabel}
              sourceName={picking.source_product_name}
              onPick={(p) => applyOverride(picking.mapping_id, p)}
              onClose={closePicker}
            />
          )}
        </>
      )}
    </RequireStorePair>
  )
}
