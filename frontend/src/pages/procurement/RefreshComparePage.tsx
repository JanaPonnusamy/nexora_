import { useCallback, useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Cycle, CompareItem, CompareChange, Refresh } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { num } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'

type Banner = { kind: 'success' | 'danger'; text: string } | null

const PAGE_SIZE = 50
const ACTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All changes' },
  { value: 'Added', label: 'Added' },
  { value: 'Removed', label: 'Removed' },
  { value: 'Increased', label: 'Increased' },
  { value: 'Decreased', label: 'Decreased' },
  { value: 'NoChange', label: 'No change' },
]

const CHANGE_META: Record<CompareChange, { icon: string; cls: string }> = {
  Added: { icon: 'bi-plus-circle-fill', cls: 'pm-cmp--added' },
  Removed: { icon: 'bi-dash-circle-fill', cls: 'pm-cmp--removed' },
  Increased: { icon: 'bi-arrow-up-circle-fill', cls: 'pm-cmp--up' },
  Decreased: { icon: 'bi-arrow-down-circle-fill', cls: 'pm-cmp--down' },
  NoChange: { icon: 'bi-dash', cls: 'pm-cmp--same' },
}

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed')

/**
 * Refresh Compare (Procurement) — a read-only diff of two refreshes belonging to
 * the SAME cycle. Pure UI over the existing GET /vpl/compare endpoint; nothing
 * is persisted. Pairs naturally with "Close Refresh & New": compare Refresh N
 * against N+1 to see exactly what changed.
 */
export default function RefreshComparePage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [cycles, setCycles] = useState<Cycle[]>([])
  const [cycleId, setCycleId] = useState('')
  const [refreshes, setRefreshes] = useState<Refresh[]>([])
  const [fromId, setFromId] = useState('')
  const [toId, setToId] = useState('')

  const [changedOnly, setChangedOnly] = useState(true)
  const [action, setAction] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const [items, setItems] = useState<CompareItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [banner, setBanner] = useState<Banner>(null)

  const fail = useCallback((e: unknown) => {
    setBanner({ kind: 'danger', text: errMsg(e) })
    window.setTimeout(() => setBanner(null), 5000)
  }, [])

  useEffect(() => {
    tenantService.list().then((rows) => {
      const active = rows.filter((t) => t.is_active)
      setTenants(active)
      if (active.length) setTenantId((c) => c || active[0].tenant_id)
    }).catch(fail)
    storeService.list().then(setStores).catch(() => setStores([]))
  }, [fail])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )
  useEffect(() => {
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  // Cycles + refreshes for the store; default to the current open cycle.
  useEffect(() => {
    if (!tenantId || !storeId) { setCycles([]); setRefreshes([]); setCycleId(''); return }
    let live = true
    Promise.all([
      procurementService.cycles(tenantId, storeId),
      procurementService.refreshes(tenantId, storeId),
    ]).then(([cyc, refs]) => {
      if (!live) return
      setCycles(cyc)
      setRefreshes(refs)
      const open = cyc.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE')
      const latest = [...cyc].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))[0]
      setCycleId((cur) => (cur && cyc.some((c) => c.cycle_id === cur) ? cur : (open?.cycle_id ?? latest?.cycle_id ?? '')))
    }).catch(fail)
    return () => { live = false }
  }, [tenantId, storeId, fail])

  const refreshesInCycle = useMemo(
    () => refreshes
      .filter((r) => r.cycle_id === cycleId)
      .sort((a, b) => (b.refresh_no ?? 0) - (a.refresh_no ?? 0)),
    [refreshes, cycleId],
  )

  // Default From = the refresh before the latest, To = the latest.
  useEffect(() => {
    const latest = refreshesInCycle[0]
    const prev = refreshesInCycle[1]
    setToId((cur) => (cur && refreshesInCycle.some((r) => r.refresh_id === cur) ? cur : (latest?.refresh_id ?? '')))
    setFromId((cur) => (cur && refreshesInCycle.some((r) => r.refresh_id === cur) ? cur : (prev?.refresh_id ?? '')))
  }, [refreshesInCycle])

  const canCompare = Boolean(tenantId && fromId && toId && fromId !== toId)
  const labelOf = useCallback(
    (id: string) => {
      const r = refreshesInCycle.find((x) => x.refresh_id === id)
      return r ? (r.refresh_no != null ? `Refresh ${r.refresh_no}` : r.snapshot_name) : '—'
    },
    [refreshesInCycle],
  )

  // Reset to the first page whenever the query changes.
  useEffect(() => { setPage(1) }, [fromId, toId, changedOnly, action, search])

  // Load the comparison (debounced for search).
  useEffect(() => {
    if (!canCompare) { setItems([]); setTotal(0); return }
    let live = true
    const t = window.setTimeout(() => {
      setLoading(true)
      procurementService
        .compareVpls(tenantId, fromId, toId, {
          changedOnly, action: action || undefined, search: search || undefined,
          page, pageSize: PAGE_SIZE,
        })
        .then((res) => { if (live) { setItems(res.items); setTotal(res.total) } })
        .catch((e) => { if (live) { fail(e); setItems([]); setTotal(0) } })
        .finally(() => { if (live) setLoading(false) })
    }, 250)
    return () => { live = false; window.clearTimeout(t) }
  }, [canCompare, tenantId, fromId, toId, changedOnly, action, search, page, fail])

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="pm-admin pm-cmp">
      <header className="pm-admin__head">
        <div className="pm-admin__title"><i className="bi bi-arrow-left-right" /> Refresh Compare</div>
        <div className="pm-admin__ctx">
          <select className="sx-select" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
          <select className="sx-select" aria-label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            <option value="">Select store…</option>
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </select>
          <select className="sx-select" aria-label="Cycle" value={cycleId} onChange={(e) => setCycleId(e.target.value)}>
            <option value="">Select cycle…</option>
            {cycles.map((c) => (
              <option key={c.cycle_id} value={c.cycle_id}>
                {c.name}{(c.status ?? '').toUpperCase() === 'ACTIVE' ? '' : ' · Closed'}
              </option>
            ))}
          </select>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      <section className="pm-admin__panel pm-cmp__bar">
        <label className="pm-admin__field">
          <span>From (base)</span>
          <select className="sx-select sx-select--sm" value={fromId} onChange={(e) => setFromId(e.target.value)}>
            <option value="">—</option>
            {refreshesInCycle.map((r) => (
              <option key={r.refresh_id} value={r.refresh_id} disabled={r.refresh_id === toId}>
                {r.refresh_no != null ? `Refresh ${r.refresh_no}` : r.snapshot_name} · {r.snapshot_status}
              </option>
            ))}
          </select>
        </label>
        <i className="bi bi-arrow-right pm-cmp__arrow" aria-hidden="true" />
        <label className="pm-admin__field">
          <span>To (compare)</span>
          <select className="sx-select sx-select--sm" value={toId} onChange={(e) => setToId(e.target.value)}>
            <option value="">—</option>
            {refreshesInCycle.map((r) => (
              <option key={r.refresh_id} value={r.refresh_id} disabled={r.refresh_id === fromId}>
                {r.refresh_no != null ? `Refresh ${r.refresh_no}` : r.snapshot_name} · {r.snapshot_status}
              </option>
            ))}
          </select>
        </label>
        <label className="pm-console__opt" title="Hide products whose quantity did not change">
          <input type="checkbox" checked={changedOnly} onChange={(e) => setChangedOnly(e.target.checked)} />
          <span>Changed only</span>
        </label>
        <select className="sx-select sx-select--sm" aria-label="Change filter" value={action} onChange={(e) => setAction(e.target.value)}>
          {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
        <span className="sx-search">
          <i className="bi bi-search" aria-hidden="true" />
          <input type="search" value={search} placeholder="Search product…" aria-label="Search product" onChange={(e) => setSearch(e.target.value)} />
        </span>
        <span className="pm-cmp__count">{loading ? 'Loading…' : `${num(total)} product${total === 1 ? '' : 's'}`}</span>
      </section>

      {!canCompare ? (
        <EmptyState
          icon="bi-arrow-left-right"
          title="Pick two refreshes"
          description={refreshesInCycle.length < 2
            ? 'This cycle needs at least two refreshes to compare.'
            : 'Choose a base (From) and a comparison (To) refresh in the same cycle.'}
        />
      ) : (
        <>
          <table className="pm-grid pm-admin__table pm-cmp__grid">
            <thead>
              <tr>
                <th>Product</th>
                <th className="pm-cmp__numcol">{labelOf(fromId)}</th>
                <th className="pm-cmp__numcol">{labelOf(toId)}</th>
                <th className="pm-cmp__numcol">Δ</th>
                <th className="pm-cmp__chgcol">Change</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && !loading ? (
                <tr><td colSpan={5} className="pm-cmp__empty">No products match these filters.</td></tr>
              ) : (
                items.map((it) => {
                  const meta = CHANGE_META[it.change_type]
                  const diff = it.qty_difference ?? 0
                  return (
                    <tr key={it.product_id ?? `${it.product_code}`}>
                      <td>
                        <div className="pm-prod__name">{it.product_name ?? it.product_code ?? '—'}</div>
                        <div className="pm-prod__meta">{it.product_code}</div>
                      </td>
                      <td className="pm-cmp__numcol sx-num">{it.source_qty != null ? num(it.source_qty) : '—'}</td>
                      <td className="pm-cmp__numcol sx-num">{it.target_qty != null ? num(it.target_qty) : '—'}</td>
                      <td className={`pm-cmp__numcol sx-num ${diff > 0 ? 'pm-cmp--up' : diff < 0 ? 'pm-cmp--down' : ''}`}>
                        {diff > 0 ? `+${num(diff)}` : diff < 0 ? num(diff) : '—'}
                      </td>
                      <td className="pm-cmp__chgcol">
                        <span className={`pm-cmp-badge ${meta.cls}`}>
                          <i className={`bi ${meta.icon}`} /> {it.change_type === 'NoChange' ? 'No change' : it.change_type}
                        </span>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>

          {pages > 1 && (
            <div className="pm-cmp__pager">
              <button className="pm-btn pm-btn--ghost pm-btn--sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                <i className="bi bi-chevron-left" /> Prev
              </button>
              <span className="sx-dim">Page {page} of {pages}</span>
              <button className="pm-btn pm-btn--ghost pm-btn--sm" disabled={page >= pages} onClick={() => setPage((p) => Math.min(pages, p + 1))}>
                Next <i className="bi bi-chevron-right" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
