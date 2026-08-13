import { useCallback, useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Cycle, Refresh } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { num, date } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'
import { FilterSelect } from '../../design-system/components/FilterBar'

type Banner = { kind: 'success' | 'danger'; text: string } | null

/** Refresh Management (Procurement Admin) — generate and review Refreshes for an
 *  ACTIVE cycle. Generation runs the existing engine pipeline; a published
 *  Refresh is what the Purchase Manager then works on. No engine logic here. */
export default function RefreshManagementPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [cycles, setCycles] = useState<Cycle[]>([])
  const [cycleId, setCycleId] = useState('')
  const [refreshes, setRefreshes] = useState<Refresh[]>([])
  const [loading, setLoading] = useState(false)
  const actingUser = useActingUser()
  const [banner, setBanner] = useState<Banner>(null)

  // Generate-refresh form
  const [snapshotName, setSnapshotName] = useState('')
  const [rollingDays, setRollingDays] = useState('90')
  const [minDays, setMinDays] = useState('7')
  const [maxDays, setMaxDays] = useState('21')
  const [generating, setGenerating] = useState(false)

  const say = useCallback((kind: 'success' | 'danger', text: string) => {
    setBanner({ kind, text })
    window.setTimeout(() => setBanner(null), 5000)
  }, [])
  const fail = useCallback(
    (e: unknown) => say('danger', e instanceof Error ? e.message : 'Request failed'),
    [say],
  )

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

  // Procurement is store-based: default to the first store, keep it valid on
  // tenant change.
  useEffect(() => {
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  useEffect(() => {
    if (!tenantId || !storeId) { setCycles([]); setCycleId(''); return }
    setCycleId('')
    procurementService.cycles(tenantId, storeId).then((rows) => {
      setCycles(rows)
      const activeCycle = rows.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE')
      if (activeCycle) setCycleId(activeCycle.cycle_id)
    }).catch(fail)
  }, [tenantId, storeId, fail])

  const load = useCallback(() => {
    if (!tenantId || !cycleId) { setRefreshes([]); return }
    setLoading(true)
    procurementService.refreshesForCycle(tenantId, cycleId)
      .then(setRefreshes)
      .catch(fail)
      .finally(() => setLoading(false))
  }, [tenantId, cycleId, fail])

  useEffect(() => { load() }, [load])

  const selectedCycle = useMemo(
    () => cycles.find((c) => c.cycle_id === cycleId) ?? null,
    [cycles, cycleId],
  )
  const cycleActive = (selectedCycle?.status ?? '').toUpperCase() === 'ACTIVE'

  const generate = async () => {
    if (!cycleId) return say('danger', 'Select an ACTIVE cycle')
    if (!cycleActive) return say('danger', 'Refreshes can only be generated for an ACTIVE cycle')
    const min = Number(minDays), max = Number(maxDays), roll = Number(rollingDays)
    if (Number.isNaN(min) || Number.isNaN(max) || min >= max) return say('danger', 'Min days must be less than Max days')
    setGenerating(true)
    try {
      const res = await procurementService.generateRefresh(tenantId, cycleId, {
        snapshot_name: snapshotName.trim() || undefined,
        rolling_days: Number.isNaN(roll) ? undefined : roll,
        min_days: min,
        max_days: max,
        created_by: actingUser,
      })
      say('success', `Refresh generated — ${num(res.generated_product_count)} products to procure, ${num(res.working_item_count)} working items`)
      setSnapshotName('')
      load()
    } catch (e) {
      fail(e)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="pm-admin">
      <header className="pm-admin__head">
        <div className="pm-admin__title"><i className="bi bi-arrow-repeat" /> Refresh Management</div>
        <div className="pm-admin__ctx">
          <FilterSelect ariaLabel="Tenant" value={tenantId} onChange={setTenantId}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </FilterSelect>
          <FilterSelect ariaLabel="Store" value={storeId} onChange={setStoreId}>
            <option value="">Select store…</option>
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </FilterSelect>
          <FilterSelect ariaLabel="Cycle" value={cycleId} onChange={setCycleId}>
            <option value="">Select cycle…</option>
            {cycles.map((c) => <option key={c.cycle_id} value={c.cycle_id}>{c.name} · {c.status}</option>)}
          </FilterSelect>
          <button className="pm-btn pm-btn--ghost" onClick={load} title="Refresh"><i className="bi bi-arrow-repeat" /></button>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">
          Generate a refresh
          {selectedCycle && !cycleActive && <span className="pm-admin__hint"> — cycle is {selectedCycle.status}, generation disabled</span>}
        </div>
        <div className="pm-admin__form">
          <input className="pm-input" placeholder="Snapshot name (optional)" value={snapshotName} onChange={(e) => setSnapshotName(e.target.value)} />
          <label className="pm-admin__field"><span>Rolling days</span><input className="pm-input pm-input--sm" value={rollingDays} onChange={(e) => setRollingDays(e.target.value)} /></label>
          <label className="pm-admin__field"><span>Min days</span><input className="pm-input pm-input--sm" value={minDays} onChange={(e) => setMinDays(e.target.value)} /></label>
          <label className="pm-admin__field"><span>Max days</span><input className="pm-input pm-input--sm" value={maxDays} onChange={(e) => setMaxDays(e.target.value)} /></label>
          <button className="pm-btn pm-btn--primary" disabled={generating || !cycleActive} onClick={generate}>
            <i className="bi bi-play-fill" /> {generating ? 'Generating…' : 'Generate Refresh'}
          </button>
        </div>
      </section>

      {refreshes.length === 0 && !loading ? (
        <EmptyState icon="bi-inbox" title="No refreshes" description="Generate a refresh for this cycle to publish it to the Purchase Manager." />
      ) : (
        <table className="pm-grid pm-admin__table">
          <thead>
            <tr>
              <th>Refresh</th><th className="sx-num">#</th><th>Status</th>
              <th className="sx-num">Rolling</th><th className="sx-num">Products</th><th>Created</th>
            </tr>
          </thead>
          <tbody>
            {refreshes.map((r) => (
              <tr key={r.refresh_id}>
                <td className="pm-prod__name">{r.snapshot_name}</td>
                <td className="sx-num sx-dim">{r.refresh_no ?? '—'}</td>
                <td><span className="pm-badge pm-badge--muted">{r.snapshot_status}</span></td>
                <td className="sx-num">{r.rolling_days ?? '—'}</td>
                <td className="sx-num">{num(r.generated_product_count ?? 0)}</td>
                <td className="sx-dim">{date(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
