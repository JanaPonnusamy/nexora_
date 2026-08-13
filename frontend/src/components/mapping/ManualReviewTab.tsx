import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useActingUser } from '../../hooks/useActingUser'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { productMappingService } from '../../services/productMappingService'
import type { Mapping, ProductSearchResult, ReviewCursor, ReviewProgress } from '../../types/productMapping'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxProgress, SxSearch, SxStat, SxTable } from '../sync/ui'
import { ConfidenceChip, RequireStorePair, type MappingCtx } from './shared'
import { ProductSearchDialog } from './ProductSearchDialog'
import { MatchLogicDrawer } from './MatchLogicDrawer'
import { FilterBar } from '../../design-system/components/FilterBar'

const BATCH_SIZE = 100

interface Override { code: string; name: string }

interface RowProps {
  m: Mapping
  checked: boolean
  ov: Override | undefined
  active: boolean
  onFocus: () => void
  onToggle: (id: string) => void
  onSearch: (m: Mapping) => void
  onInspect: (m: Mapping) => void
  onApprove: (m: Mapping) => void
  onClearOverride: (id: string) => void
}

/** One-line "Name  |  Code" cell — replaces the old two-line ProductCell in
 *  this grid only, to fit the 38px compact row target. */
function ProductLine({ name, code }: { name: string | null; code: string | null }) {
  if (!name && !code) return <span className="sx-dim">—</span>
  return (
    <span className="pmx-pline">
      <span className="pmx-pline__name">{name || '—'}</span>
      {code && <span className="pmx-pline__code">{code}</span>}
    </span>
  )
}

/** Memoized row — with batches of 100 this keeps a bulk selection toggle from
 *  re-rendering every other row. */
const ReviewRow = memo(function ReviewRow({ m, checked, ov, active, onFocus, onToggle, onSearch, onInspect, onApprove, onClearOverride }: RowProps) {
  return (
    <tr
      className={`${active ? 'sx-row--active' : ''}${checked ? '' : ' pmx-row--off'}`}
      onMouseDown={onFocus}
    >
      <td className="pmx-check">
        <input type="checkbox" checked={checked} onChange={() => onToggle(m.mapping_id)} aria-label={`Select ${m.source_product_name}`} />
      </td>
      <td className="pmx-col-source"><ProductLine name={m.source_product_name} code={m.source_product_code} /></td>
      <td className="pmx-col-correct">
        {ov ? (
          <span className="pmx-pline">
            <span className="pmx-pline__name">{ov.name}</span>
            <span className="pmx-pline__code">{ov.code}</span>
            <SxChip tone="violet">Manual</SxChip>
            <button type="button" className="pmx-linkbtn" onClick={() => onClearOverride(m.mapping_id)} title="Undo override"><i className="bi bi-arrow-counterclockwise" /></button>
          </span>
        ) : m.target_product_name ? (
          <ProductLine name={m.target_product_name} code={m.target_product_code} />
        ) : (
          <span className="sx-dim">No suggestion</span>
        )}
      </td>
      <td className="pmx-col-match"><ConfidenceChip value={m.confidence} dot /></td>
      <td className="pmx-col-actions">
        <button type="button" className="pmx-iconbtn" onClick={() => onSearch(m)} title="Search Product (Alt+S)" aria-label="Search Product">
          <i className="bi bi-search" aria-hidden="true" />
        </button>
        <button type="button" className="pmx-iconbtn" onClick={() => onInspect(m)} title="How Matched (Alt+M)" aria-label="How Matched">
          <i className="bi bi-cpu" aria-hidden="true" />
        </button>
        <button type="button" className="pmx-iconbtn pmx-iconbtn--success" onClick={() => onApprove(m)} title="Approve (Enter)" aria-label="Approve">
          <i className="bi bi-check2" aria-hidden="true" />
        </button>
      </td>
    </tr>
  )
})

/** Manual Review v2 — a select-by-default review grid: every PENDING row in the
 *  batch starts checked, the reviewer only unchecks bad matches (or picks a
 *  correct product), then approves/rejects the whole selection in one
 *  transaction. Loads PENDING mappings in keyset-paginated batches of 100 (flat
 *  ~15ms per batch server-side regardless of queue depth — see
 *  repository.list_review_batch) rather than OFFSET pages, and lazy-loads match
 *  details only when "How Matched" is opened. */
export function ManualReviewTab({ ctx }: { ctx: MappingCtx }) {
  const actingUser = useActingUser()
  const [rows, setRows] = useState<Mapping[]>([])
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
  const [inspecting, setInspecting] = useState<Mapping | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const selectAllRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  // The cursor of the batch currently on screen. Every reload — approve,
  // reject, or skip — continues forward from here rather than resetting to
  // the front of the queue: a row left unchecked (reviewed but not approved)
  // must not resurface at the top of the very next batch, it should just be
  // passed over like anything else already seen.
  const nextCursorRef = useRef<ReviewCursor | null>(null)

  const load = useCallback((cursor: ReviewCursor | null, opts?: { keepToast?: boolean }) => {
    // Guard mirrors <RequireStorePair>: both store ids are required by the
    // backend, so an incomplete pair must not fetch at all.
    if (!ctx.sourceStoreId || !ctx.targetStoreId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    Promise.all([
      productMappingService.reviewBatch(ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId, {
        search: debouncedSearch || undefined,
        afterConfidence: cursor?.confidence,
        afterMappingId: cursor?.mapping_id,
        limit: BATCH_SIZE,
      }),
      productMappingService.reviewProgress(ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId),
    ])
      .then(([batch, prog]) => {
        setRows(batch.items)
        nextCursorRef.current = batch.next_cursor
        setProgress(prog)
        setSelected(new Set(batch.items.map((m) => m.mapping_id))) // all selected by default
        setOverrides({})
        setFocused(0)
        setLoading(false)
        if (!opts?.keepToast) setToast(null)
        window.requestAnimationFrame(() => gridRef.current?.focus())
      })
      .catch((e) => { setError(e instanceof Error ? e.message : 'Failed to load review queue'); setLoading(false) })
  }, [ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId, debouncedSearch])

  // (re)load whenever the store pair or search changes — always from the front.
  useEffect(() => { load(null) }, [load])

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

  // Return keyboard focus to the grid whenever a dialog closes.
  const focusGrid = () => window.requestAnimationFrame(() => gridRef.current?.focus())
  const closePicker = () => { setPicking(null); focusGrid() }
  const closeInspector = () => { setInspecting(null); focusGrid() }

  const applyOverride = useCallback((mappingId: string, product: ProductSearchResult) => {
    setOverrides((prev) => ({ ...prev, [mappingId]: { code: product.product_code, name: product.product_name } }))
    setSelected((prev) => new Set(prev).add(mappingId)) // an overridden row is implicitly kept
    setPicking(null)
    focusGrid()
  }, [])

  const clearOverride = useCallback((mappingId: string) => {
    setOverrides((prev) => {
      const next = { ...prev }
      delete next[mappingId]
      return next
    })
  }, [])

  const runBulk = async (action: 'APPROVE' | 'REJECT', ids?: Set<string>) => {
    const idSet = ids ?? selected
    if (idSet.size === 0) return
    setBusy(true)
    try {
      const items = [...idSet].map((id) => {
        const ov = overrides[id]
        return ov ? { mapping_id: id, target_product_code: ov.code, target_product_name: ov.name } : { mapping_id: id }
      })
      const res = await productMappingService.bulkReview(ctx.tenantId, {
        action,
        items,
        source_store_id: ctx.sourceStoreId,
        target_store_id: ctx.targetStoreId,
        page: 1,
        page_size: BATCH_SIZE,
        actor: actingUser || null,
      })
      const n = action === 'APPROVE' ? res.approved : res.rejected
      const verb = action === 'APPROVE' ? 'Approved' : 'Rejected'
      const bits = [`${verb} ${n} product${n === 1 ? '' : 's'}.`]
      if (res.skipped > 0) bits.push(`${res.skipped} skipped.`)
      if (res.failed.length > 0) bits.push(`${res.failed.length} could not be applied — ${res.failed[0].reason}`)
      bits.push(res.remaining > 0 ? 'Loading next batch…' : 'Review queue is clear 🎉')
      setToast(bits.join(' '))
      // Continue forward from this batch's cursor — any row left unchecked
      // (reviewed, not approved) stays behind instead of reappearing at the top.
      load(nextCursorRef.current, { keepToast: true })
    } catch (e) {
      setToast(e instanceof Error ? e.message : 'Bulk action failed. Nothing was changed.')
    } finally {
      setBusy(false)
    }
  }

  const skipSelected = () => {
    const n = selected.size
    if (n === 0) return
    setToast(`Skipped ${n} for now. Loading next batch…`)
    load(nextCursorRef.current, { keepToast: true })
  }

  // keyboard-first workflow (ignored while typing in an input/textarea, except / and Ctrl+F)
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (picking || inspecting) return
    const tag = (e.target as HTMLElement).tagName
    const typing = tag === 'INPUT' || tag === 'TEXTAREA'
    const row = rows[focused]

    if (e.key === '/' && !typing) { e.preventDefault(); searchRef.current?.focus(); return }
    if ((e.key === 'f' || e.key === 'F') && (e.ctrlKey || e.metaKey)) { e.preventDefault(); searchRef.current?.focus(); return }
    if (typing) return

    if (e.key === 'ArrowDown') { e.preventDefault(); setFocused((f) => Math.min(rows.length - 1, f + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setFocused((f) => Math.max(0, f - 1)) }
    else if (e.key === ' ') { e.preventDefault(); if (row) toggleRow(row.mapping_id) }
    else if (e.key === 'a' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); setSelected(new Set(rows.map((m) => m.mapping_id))) }
    else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!busy) runBulk('APPROVE') }
    else if (e.key === 'Enter') { e.preventDefault(); if (row && !busy) runBulk('APPROVE', new Set([row.mapping_id])) }
    else if (e.key === 'm' && e.altKey) { e.preventDefault(); if (row) setInspecting(row) }
    else if (e.key === 's' && e.altKey) { e.preventDefault(); if (row) setPicking(row) }
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
      {error ? <ErrorState description={error} onRetry={() => load(null)} /> : (
        <>
          {/* Progress dashboard — stays visible through loads/errors, never freezes */}
          <div className="pmx-stats">
            <SxStat icon="bi-inboxes" tone="warning" value={progress.remaining.toLocaleString()} label="Remaining reviews" />
            <SxStat icon="bi-stack" tone="indigo" value={rows.length.toLocaleString()} label="Loaded this batch" />
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
              sub={`${progress.remaining.toLocaleString()} pending · ${selected.size} selected`}
              action={
                <FilterBar compact className="pmx-toolbar" ariaLabel="Manual review filters and actions">
                  <SxSearch ref={searchRef} value={search} onChange={setSearch} placeholder="Filter source product… ( / )" />
                  <SxButton variant="success" sm icon="bi-check2-all" busy={busy} disabled={selected.size === 0} onClick={() => runBulk('APPROVE')}>
                    Approve Selected
                  </SxButton>
                  <SxButton variant="danger" sm icon="bi-x-circle" busy={busy} disabled={selected.size === 0} onClick={() => runBulk('REJECT')}>
                    Reject Selected
                  </SxButton>
                  <SxButton variant="ghost" sm icon="bi-skip-forward" disabled={busy || selected.size === 0} onClick={skipSelected}>
                    Skip Selected
                  </SxButton>
                </FilterBar>
              }
            />
            <SxCardBody flush>
              {loading ? (
                <TableSkeleton rows={8} columns={5} />
              ) : rows.length === 0 ? (
                <EmptyState icon="bi-check2-all" title="Nothing to review" description="Every product for this store pair is matched or already decided." />
              ) : (
                <div ref={gridRef} tabIndex={0} onKeyDown={onKeyDown} className="pmx-grid pmx-grid--compact" role="grid" aria-label="Review queue">
                  <SxTable>
                    <colgroup>
                      <col className="pmx-col-check" />
                      <col className="pmx-col-source" />
                      <col className="pmx-col-correct" />
                      <col className="pmx-col-match" />
                      <col className="pmx-col-actions" />
                    </colgroup>
                    <thead className="pmx-thead-sticky">
                      <tr>
                        <th className="pmx-check">
                          <input ref={selectAllRef} type="checkbox" checked={allChecked} onChange={toggleAll} aria-label="Select all rows in this batch" />
                        </th>
                        <th>Source Product</th>
                        <th>Correct Product</th>
                        <th className="pmx-col-match">Match</th>
                        <th className="pmx-col-actions">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((m, i) => (
                        <ReviewRow
                          key={m.mapping_id}
                          m={m}
                          checked={selected.has(m.mapping_id)}
                          ov={overrides[m.mapping_id]}
                          active={i === focused}
                          onFocus={() => setFocused(i)}
                          onToggle={toggleRow}
                          onSearch={setPicking}
                          onInspect={setInspecting}
                          onApprove={(row) => { if (!busy) runBulk('APPROVE', new Set([row.mapping_id])) }}
                          onClearOverride={clearOverride}
                        />
                      ))}
                    </tbody>
                  </SxTable>
                </div>
              )}
            </SxCardBody>
            {rows.length > 0 && (
              <div className="pmx-foot">
                <span className="sx-dim">
                  Batch of {rows.length} · {progress.remaining.toLocaleString()} pending total
                </span>
                <div className="pmx-foot__keys sx-dim">
                  <kbd>Space</kbd> select · <kbd>Enter</kbd> approve row · <kbd>Ctrl</kbd>+<kbd>Enter</kbd> approve selected ·{' '}
                  <kbd>Alt</kbd>+<kbd>S</kbd> pick product · <kbd>Alt</kbd>+<kbd>M</kbd> how matched · <kbd>/</kbd> search
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

          {inspecting && (
            <MatchLogicDrawer
              tenantId={ctx.tenantId}
              mapping={inspecting}
              onUseCandidate={(p) => { applyOverride(inspecting.mapping_id, p); setInspecting(null) }}
              onClose={closeInspector}
            />
          )}
        </>
      )}
    </RequireStorePair>
  )
}
