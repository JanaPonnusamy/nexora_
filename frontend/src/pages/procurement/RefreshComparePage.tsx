import { useCallback, useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Cycle, CompareChange, Refresh, WorkspaceItem } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { num } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'

type Banner = { kind: 'success' | 'danger'; text: string } | null

const ACTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All changes' },
  { value: 'Added', label: 'Added' },
  { value: 'Removed', label: 'Removed' },
  { value: 'Increased', label: 'Increased' },
  { value: 'Decreased', label: 'Decreased' },
  { value: 'NoChange', label: 'No change' },
]

const CHANGE_META: Record<CompareChange, { icon: string; cls: string; label: string }> = {
  Added: { icon: 'bi-plus-circle-fill', cls: 'pm-cmp--added', label: 'Added' },
  Removed: { icon: 'bi-dash-circle-fill', cls: 'pm-cmp--removed', label: 'Removed' },
  Increased: { icon: 'bi-arrow-up-circle-fill', cls: 'pm-cmp--up', label: 'Increased' },
  Decreased: { icon: 'bi-arrow-down-circle-fill', cls: 'pm-cmp--down', label: 'Decreased' },
  NoChange: { icon: 'bi-dash', cls: 'pm-cmp--same', label: 'No change' },
}

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed')

/** One side (From / To) of a product's order state in a refresh. */
type Side = { present: boolean; qty: number; skipped: boolean }
/** A product's full diff between the two refreshes. `qty` is the FINAL ORDER
 *  quantity (what the buyer decided to order), not the raw VPL suggestion. */
type Row = {
  code: string
  name: string | null
  from: Side
  to: Side
  diff: number
  change: CompareChange
  suppliers: string[]
}

const blankSide = (): Side => ({ present: false, qty: 0, skipped: false })

function classify(from: Side, to: Side): CompareChange {
  if (!from.present && to.present) return 'Added'
  if (from.present && !to.present) return 'Removed'
  if (to.qty > from.qty) return 'Increased'
  if (to.qty < from.qty) return 'Decreased'
  return 'NoChange'
}

/**
 * Refresh Compare (Procurement) — a read-only diff of the FINAL ORDER between
 * two refreshes of the SAME cycle. Compares the whole refresh in one view
 * (skipped items included), optionally scoped to one supplier. Built client-side
 * over the existing workspace + assignments feeds — nothing is persisted. Runs
 * only when the buyer presses Compare.
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
  const [supplierNames, setSupplierNames] = useState<Record<string, string>>({})

  // Client-side view filters (applied over the computed diff).
  const [changedOnly, setChangedOnly] = useState(true)
  const [includeSkipped, setIncludeSkipped] = useState(true)
  const [supplierFilter, setSupplierFilter] = useState('')
  const [action, setAction] = useState('')
  const [search, setSearch] = useState('')

  const [rows, setRows] = useState<Row[] | null>(null)
  const [comparedLabel, setComparedLabel] = useState<{ from: string; to: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [banner, setBanner] = useState<Banner>(null)

  const fail = useCallback((e: unknown) => {
    setBanner({ kind: 'danger', text: errMsg(e) })
    window.setTimeout(() => setBanner(null), 6000)
  }, [])

  useEffect(() => {
    tenantService.list().then((r) => {
      const active = r.filter((t) => t.is_active)
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

  // Cycles + refreshes for the store; default to the current open cycle. Also
  // load supplier code→name for the supplier filter.
  useEffect(() => {
    setRows(null); setComparedLabel(null)
    if (!tenantId || !storeId) { setCycles([]); setRefreshes([]); setCycleId(''); setSupplierNames({}); return }
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
    procurementService.supplierSettings(tenantId, storeId)
      .then((rowsS) => { if (live) setSupplierNames(Object.fromEntries(rowsS.map((s) => [s.supplier_code, s.supplier_name ?? s.supplier_code]))) })
      .catch(() => { if (live) setSupplierNames({}) })
    return () => { live = false }
  }, [tenantId, storeId, fail])

  const refreshesInCycle = useMemo(
    () => refreshes
      .filter((r) => r.cycle_id === cycleId)
      .sort((a, b) => (b.refresh_no ?? 0) - (a.refresh_no ?? 0)),
    [refreshes, cycleId],
  )

  // Default From = the refresh before the latest, To = the latest. A picker
  // change invalidates the shown diff (must press Compare again).
  useEffect(() => {
    setRows(null); setComparedLabel(null)
    const latest = refreshesInCycle[0]
    const prev = refreshesInCycle[1]
    setToId((cur) => (cur && refreshesInCycle.some((r) => r.refresh_id === cur) ? cur : (latest?.refresh_id ?? '')))
    setFromId((cur) => (cur && refreshesInCycle.some((r) => r.refresh_id === cur) ? cur : (prev?.refresh_id ?? '')))
  }, [refreshesInCycle])

  const canCompare = Boolean(tenantId && fromId && toId && fromId !== toId)
  const labelOf = useCallback(
    (id: string) => {
      const r = refreshesInCycle.find((x) => x.refresh_id === id)
      return r ? (r.refresh_no != null ? `Refresh ${r.refresh_no}` : (r.snapshot_name ?? '—')) : '—'
    },
    [refreshesInCycle],
  )

  // Build one refresh's product→order state, plus product→supplier codes, from
  // the workspace items (final qty / skip) and the assignments feed (supplier).
  const loadSide = useCallback(async (refreshId: string) => {
    const [page, assignments] = await Promise.all([
      procurementService.workspace(tenantId, refreshId, { page_size: 5000 }),
      procurementService.refreshAssignments(tenantId, refreshId).catch(() => []),
    ])
    const byCode = new Map<string, { item: WorkspaceItem; suppliers: Set<string> }>()
    const codeByItem = new Map<string, string>()
    for (const it of page.items) {
      if (!it.product_code) continue
      byCode.set(it.product_code, { item: it, suppliers: new Set() })
      codeByItem.set(it.order_item_id, it.product_code)
    }
    for (const a of assignments) {
      const code = codeByItem.get(a.order_item_id) ?? a.product_code ?? undefined
      if (!code || !a.supplier_code) continue
      byCode.get(code)?.suppliers.add(a.supplier_code)
    }
    return byCode
  }, [tenantId])

  const runCompare = useCallback(async () => {
    if (!canCompare) return
    setLoading(true)
    try {
      const [fromMap, toMap] = await Promise.all([loadSide(fromId), loadSide(toId)])
      const codes = new Set<string>([...fromMap.keys(), ...toMap.keys()])
      const out: Row[] = []
      for (const code of codes) {
        const f = fromMap.get(code)
        const t = toMap.get(code)
        const from: Side = f
          ? { present: true, qty: f.item.final_qty ?? 0, skipped: f.item.item_status === 'skipped' }
          : blankSide()
        const to: Side = t
          ? { present: true, qty: t.item.final_qty ?? 0, skipped: t.item.item_status === 'skipped' }
          : blankSide()
        const suppliers = new Set<string>([...(f?.suppliers ?? []), ...(t?.suppliers ?? [])])
        out.push({
          code,
          name: (t?.item.product_name ?? f?.item.product_name) ?? code,
          from,
          to,
          diff: to.qty - from.qty,
          change: classify(from, to),
          suppliers: [...suppliers],
        })
      }
      out.sort((a, b) => (a.name ?? a.code).localeCompare(b.name ?? b.code))
      setRows(out)
      setComparedLabel({ from: labelOf(fromId), to: labelOf(toId) })
    } catch (e) {
      fail(e)
      setRows(null)
    } finally {
      setLoading(false)
    }
  }, [canCompare, loadSide, fromId, toId, labelOf, fail])

  // Supplier options — only suppliers that actually appear in the compared data.
  const supplierOptions = useMemo(() => {
    if (!rows) return []
    const codes = new Set<string>()
    rows.forEach((r) => r.suppliers.forEach((c) => codes.add(c)))
    return [...codes].map((c) => ({ code: c, name: supplierNames[c] ?? c })).sort((a, b) => a.name.localeCompare(b.name))
  }, [rows, supplierNames])

  // Client-side view filters over the computed diff.
  const visible = useMemo(() => {
    if (!rows) return []
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (!includeSkipped && (r.from.skipped || r.to.skipped) && r.change === 'NoChange') return false
      if (changedOnly && r.change === 'NoChange') return false
      if (action && r.change !== action) return false
      if (supplierFilter && !r.suppliers.includes(supplierFilter)) return false
      if (q && !(`${r.name ?? ''} ${r.code}`.toLowerCase().includes(q))) return false
      return true
    })
  }, [rows, changedOnly, includeSkipped, action, supplierFilter, search])

  const tally = useMemo(() => {
    const t = { Added: 0, Removed: 0, Increased: 0, Decreased: 0, NoChange: 0 } as Record<CompareChange, number>
    visible.forEach((r) => { t[r.change] += 1 })
    return t
  }, [visible])

  const stale = rows != null && comparedLabel != null &&
    (comparedLabel.from !== labelOf(fromId) || comparedLabel.to !== labelOf(toId))

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
        <label className="pm-admin__field">
          <span>Supplier</span>
          <select className="sx-select sx-select--sm" value={supplierFilter} onChange={(e) => setSupplierFilter(e.target.value)} disabled={!rows}>
            <option value="">All suppliers</option>
            {supplierOptions.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
          </select>
        </label>
        <button className="pm-btn pm-btn--primary pm-cmp__run" disabled={!canCompare || loading} onClick={runCompare}>
          <i className="bi bi-arrow-left-right" /> {loading ? 'Comparing…' : 'Compare'}
        </button>
      </section>

      {rows && (
        <section className="pm-admin__panel pm-cmp__filters">
          <label className="pm-console__opt" title="Hide products whose order quantity did not change">
            <input type="checkbox" checked={changedOnly} onChange={(e) => setChangedOnly(e.target.checked)} />
            <span>Changed only</span>
          </label>
          <label className="pm-console__opt" title="Include products skipped in either refresh">
            <input type="checkbox" checked={includeSkipped} onChange={(e) => setIncludeSkipped(e.target.checked)} />
            <span>Include skipped</span>
          </label>
          <select className="sx-select sx-select--sm" aria-label="Change filter" value={action} onChange={(e) => setAction(e.target.value)}>
            {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
          </select>
          <span className="sx-search">
            <i className="bi bi-search" aria-hidden="true" />
            <input type="search" value={search} placeholder="Search product…" aria-label="Search product" onChange={(e) => setSearch(e.target.value)} />
          </span>
          <div className="pm-cmp__tally">
            <span className="pm-cmp-badge pm-cmp--added">+{tally.Added} added</span>
            <span className="pm-cmp-badge pm-cmp--removed">−{tally.Removed} removed</span>
            <span className="pm-cmp-badge pm-cmp--up">↑{tally.Increased}</span>
            <span className="pm-cmp-badge pm-cmp--down">↓{tally.Decreased}</span>
            <span className="pm-cmp__count">{num(visible.length)} shown</span>
          </div>
        </section>
      )}

      {stale && (
        <div className="pm-banner pm-banner--info">Selection changed — press <b>Compare</b> to refresh the results.</div>
      )}

      {!rows ? (
        <EmptyState
          icon="bi-arrow-left-right"
          title={canCompare ? 'Ready to compare' : 'Pick two refreshes'}
          description={!canCompare
            ? (refreshesInCycle.length < 2 ? 'This cycle needs at least two refreshes to compare.' : 'Choose a base (From) and a comparison (To) refresh in the same cycle.')
            : 'Press Compare to diff the entire order between the two refreshes.'}
        />
      ) : (
        <table className="pm-grid pm-admin__table pm-cmp__grid">
          <thead>
            <tr>
              <th>Product</th>
              <th className="pm-cmp__numcol">{comparedLabel?.from}</th>
              <th className="pm-cmp__numcol">{comparedLabel?.to}</th>
              <th className="pm-cmp__numcol">Δ</th>
              <th className="pm-cmp__chgcol">Change</th>
              <th className="pm-cmp__supcol">Supplier</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr><td colSpan={6} className="pm-cmp__empty">No products match these filters.</td></tr>
            ) : (
              visible.map((r) => {
                const meta = CHANGE_META[r.change]
                return (
                  <tr key={r.code}>
                    <td>
                      <div className="pm-prod__name">{r.name}</div>
                      <div className="pm-prod__meta">{r.code}</div>
                    </td>
                    <td className="pm-cmp__numcol sx-num">
                      {r.from.present ? num(r.from.qty) : '—'}
                      {r.from.skipped && <span className="pm-cmp__skip" title="Skipped in this refresh">skip</span>}
                    </td>
                    <td className="pm-cmp__numcol sx-num">
                      {r.to.present ? num(r.to.qty) : '—'}
                      {r.to.skipped && <span className="pm-cmp__skip" title="Skipped in this refresh">skip</span>}
                    </td>
                    <td className={`pm-cmp__numcol sx-num ${r.diff > 0 ? 'pm-cmp--up' : r.diff < 0 ? 'pm-cmp--down' : ''}`}>
                      {r.diff > 0 ? `+${num(r.diff)}` : r.diff < 0 ? num(r.diff) : '—'}
                    </td>
                    <td className="pm-cmp__chgcol">
                      <span className={`pm-cmp-badge ${meta.cls}`}><i className={`bi ${meta.icon}`} /> {meta.label}</span>
                    </td>
                    <td className="pm-cmp__supcol">
                      {r.suppliers.length === 0
                        ? <span className="sx-dim">—</span>
                        : r.suppliers.map((c) => supplierNames[c] ?? c).join(', ')}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}
