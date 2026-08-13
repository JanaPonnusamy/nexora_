import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Refresh } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import '../../components/procurement/purchase-manager.css'
import { FilterSelect } from '../../design-system/components/FilterBar'

/** Refresh launcher — the only job of this screen is to pick a Refresh and open
 *  the Purchase Manager workspace for it. All procurement work happens there. */
export default function RefreshLauncherPage() {
  const navigate = useNavigate()
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [refreshes, setRefreshes] = useState<Refresh[]>([])
  const [refreshId, setRefreshId] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    tenantService.list().then((rows) => {
      const active = rows.filter((t) => t.is_active)
      setTenants(active)
      if (active.length) setTenantId((c) => c || active[0].tenant_id)
    })
    storeService.list().then(setStores).catch(() => setStores([]))
  }, [])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )

  // Procurement is store-based: default the store, keep it valid on tenant change.
  useEffect(() => {
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  useEffect(() => {
    if (!tenantId || !storeId) { setRefreshes([]); setRefreshId(''); return }
    setRefreshId('')
    setLoading(true)
    procurementService.refreshes(tenantId, storeId)
      .then(setRefreshes)
      .finally(() => setLoading(false))
  }, [tenantId, storeId])

  const open = () => {
    if (!tenantId || !refreshId) return
    navigate(`/procurement/workspace?tenant=${encodeURIComponent(tenantId)}&refresh=${encodeURIComponent(refreshId)}`)
  }

  return (
    <div className="pm-launch">
      <div className="pm-launch__card">
        <div className="pm-launch__brand"><i className="bi bi-cart-check" /> Purchase Manager</div>
        <p className="pm-launch__lead">Select a refresh to open the workspace. All review, assignment and export happen inside.</p>

        <label className="pm-launch__field">
          <span>Tenant</span>
          <FilterSelect ariaLabel="Tenant" value={tenantId} onChange={setTenantId}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </FilterSelect>
        </label>

        <label className="pm-launch__field">
          <span>Store</span>
          <FilterSelect ariaLabel="Store" value={storeId} onChange={setStoreId}>
            <option value="">Select store…</option>
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </FilterSelect>
        </label>

        <label className="pm-launch__field">
          <span>Refresh</span>
          <FilterSelect ariaLabel="Refresh" value={refreshId} onChange={setRefreshId} disabled={loading}>
            <option value="">{loading ? 'Loading…' : 'Select a refresh…'}</option>
            {refreshes.map((r) => <option key={r.refresh_id} value={r.refresh_id}>{r.snapshot_name} · {r.snapshot_status}</option>)}
          </FilterSelect>
        </label>

        {!loading && refreshes.length === 0 && tenantId && (
          <EmptyState icon="bi-inbox" title="No refreshes" description="Generate a refresh for this tenant first." />
        )}

        <button className="pm-btn pm-btn--primary pm-launch__go" disabled={!refreshId} onClick={open}>
          Submit &amp; Open Purchase Manager <i className="bi bi-arrow-right" />
        </button>
      </div>
    </div>
  )
}
