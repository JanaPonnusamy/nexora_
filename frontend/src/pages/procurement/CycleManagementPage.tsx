import { useCallback, useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Cycle } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { date } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'

type Banner = { kind: 'success' | 'danger'; text: string } | null

/** Cycle Management (Procurement Admin) — open, review and close Business
 *  Cycles. Reuses the existing lifecycle endpoints; no engine logic here. */
export default function CycleManagementPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [cycles, setCycles] = useState<Cycle[]>([])
  const [loading, setLoading] = useState(false)
  const actingUser = useActingUser()
  const [banner, setBanner] = useState<Banner>(null)

  // Open-cycle form
  const [name, setName] = useState('')
  const [storeId, setStoreId] = useState('')
  const [startGrn, setStartGrn] = useState('')
  const [startBill, setStartBill] = useState('')
  const [opening, setOpening] = useState(false)

  // Close flow. End GRN / End Sale Bill are read from synced data on the server
  // (no manual entry). `closing` = the cycle a request is in flight for;
  // `confirm` holds the pending-confirmation prompt when pending items remain.
  const [closing, setClosing] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<{ cycle: Cycle; message: string } | null>(null)

  const say = useCallback((kind: 'success' | 'danger', text: string) => {
    setBanner({ kind, text })
    window.setTimeout(() => setBanner(null), 4000)
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

  const load = useCallback(() => {
    if (!tenantId || !storeId) { setCycles([]); return }
    setLoading(true)
    procurementService.cycles(tenantId, storeId)
      .then(setCycles)
      .catch(fail)
      .finally(() => setLoading(false))
  }, [tenantId, storeId, fail])

  useEffect(() => { load() }, [load])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )

  // Procurement is store-based: default to the first store and keep the
  // selection valid when the tenant changes.
  useEffect(() => {
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  const openCycle = async () => {
    if (!storeId) return say('danger', 'Select a store first')
    if (!name.trim()) return say('danger', 'Enter a cycle name')
    setOpening(true)
    try {
      await procurementService.openCycle({
        tenant_id: tenantId,
        name: name.trim(),
        store_id: storeId,
        start_grn_number: startGrn.trim() || undefined,
        start_sale_bill_number: startBill.trim() || undefined,
        created_by: actingUser,
      })
      say('success', `Opened cycle “${name.trim()}”`)
      setName(''); setStartGrn(''); setStartBill('')
      load()
    } catch (e) {
      fail(e)
    } finally {
      setOpening(false)
    }
  }

  // Close reconciles from synced purchases, auto-stamps End GRN / End Sale Bill,
  // then closes and auto-opens a fresh cycle. When pending items remain the API
  // returns `pending_confirm`; we prompt, and re-call with force=true on OK.
  const runClose = async (cycle: Cycle, force: boolean) => {
    setClosing(cycle.cycle_id)
    try {
      const res = await procurementService.closeCycle(tenantId, cycle.cycle_id, actingUser, force)
      if (res.status === 'pending_confirm') {
        setConfirm({ cycle, message: res.message })
        return
      }
      setConfirm(null)
      const grn = res.end_grn_number ?? '—'
      const bill = res.end_sale_bill_number ?? '—'
      say(
        'success',
        `Closed “${cycle.name}” · End GRN ${grn} · End Bill ${bill}. ` +
        `Fresh cycle “${res.new_cycle.name}” opened.`,
      )
      load()
    } catch (e) {
      fail(e)
    } finally {
      setClosing(null)
    }
  }

  const storeName = (id: string | null) =>
    id ? stores.find((s) => s.store_id === id)?.store_name ?? id : 'All stores'

  return (
    <div className="pm-admin">
      <header className="pm-admin__head">
        <div className="pm-admin__title"><i className="bi bi-diagram-3" /> Cycle Management</div>
        <div className="pm-admin__ctx">
          <select className="sx-select" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
          <select className="sx-select" aria-label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            <option value="">Select store…</option>
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </select>
          <button className="pm-btn pm-btn--ghost" onClick={load} title="Refresh"><i className="bi bi-arrow-repeat" /></button>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">Open a new cycle</div>
        <div className="pm-admin__form">
          <input className="pm-input" placeholder="Cycle name" value={name} onChange={(e) => setName(e.target.value)} />
          <input className="pm-input" placeholder="Start GRN #" value={startGrn} onChange={(e) => setStartGrn(e.target.value)} />
          <input className="pm-input" placeholder="Start Sale Bill #" value={startBill} onChange={(e) => setStartBill(e.target.value)} />
          <button className="pm-btn pm-btn--primary" disabled={opening} onClick={openCycle}>
            <i className="bi bi-plus-lg" /> {opening ? 'Opening…' : 'Open Cycle'}
          </button>
        </div>
      </section>

      {cycles.length === 0 && !loading ? (
        <EmptyState icon="bi-diagram-3" title="No cycles" description="Open a cycle to begin a procurement lifecycle." />
      ) : (
        <table className="pm-grid pm-admin__table">
          <thead>
            <tr>
              <th>Cycle</th><th>Status</th><th>Store</th>
              <th>Start Date</th><th>End Date</th><th>Active Refresh</th>
              <th className="pm-grid__act">Actions</th>
            </tr>
          </thead>
          <tbody>
            {cycles.map((c) => {
              const active = (c.status ?? '').toUpperCase() === 'ACTIVE'
              return (
                <tr key={c.cycle_id}>
                  <td>
                    <div className="pm-prod__name">{c.name}</div>
                    {c.description && <div className="pm-prod__meta">{c.description}</div>}
                  </td>
                  <td><span className={`pm-badge ${active ? 'pm-badge--ok' : 'pm-badge--muted'}`}>{c.status}</span></td>
                  <td>{storeName(c.store_id ?? null)}</td>
                  <td className="sx-dim">{date(c.start_date)}</td>
                  <td className="sx-dim">{date(c.end_date)}</td>
                  <td className="sx-dim">{c.active_refresh_id ? c.active_refresh_id.slice(0, 8) : '—'}</td>
                  <td className="pm-grid__act">
                    {active && (
                      <button
                        className="pm-btn pm-btn--ghost pm-btn--sm"
                        disabled={closing === c.cycle_id}
                        onClick={() => runClose(c, false)}
                      >
                        {closing === c.cycle_id ? 'Closing…' : 'Close'}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {confirm && (
        <div className="pm-drawer__backdrop" style={{ zIndex: 1060 }} onClick={() => setConfirm(null)}>
          <div className="pm-confirm" role="dialog" aria-label="Pending items" onClick={(e) => e.stopPropagation()}>
            <h5 className="mb-1"><i className="bi bi-exclamation-triangle me-1" /> Pending items still available</h5>
            <p className="text-muted small mb-3">{confirm.message}</p>
            <div className="pm-confirm__actions">
              <button className="pm-btn pm-btn--ghost" onClick={() => setConfirm(null)}>Cancel</button>
              <button
                className="pm-btn pm-btn--primary"
                disabled={closing === confirm.cycle.cycle_id}
                onClick={() => runClose(confirm.cycle, true)}
              >
                {closing === confirm.cycle.cycle_id ? 'Closing…' : 'Close anyway'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
