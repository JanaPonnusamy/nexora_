import { useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Refresh } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import '../../components/procurement/purchase-manager.css'
import { FilterSelect } from '../../design-system/components/FilterBar'

type Row = { name: string; unit: string | null; product_code: string | null; category: string }

/**
 * Shelf Category Training — teaches the shelf-sort "agent" the categories it
 * can't infer. Lists an order's products that still resolve to Others, lets
 * Claude auto-suggest a category for each (optional, needs an API key on the
 * server), and saves the buyer's confirmed picks to the learned dictionary so
 * every future shelf-sort (order OR uploaded file, this store or another)
 * files them correctly.
 */
export default function ShelfCategoryTrainingPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [refreshes, setRefreshes] = useState<Refresh[]>([])
  const [refreshId, setRefreshId] = useState('')
  const [vocab, setVocab] = useState<{ category: string; code: string }[]>([])
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<'load' | 'ai' | 'save' | null>(null)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    tenantService.list().then((r) => {
      const active = r.filter((t) => t.is_active)
      setTenants(active)
      if (active.length) setTenantId((c) => c || active[0].tenant_id)
    })
    storeService.list().then(setStores).catch(() => setStores([]))
    procurementService.shelfCategoryVocab().then(setVocab).catch(() => setVocab([]))
  }, [])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )
  useEffect(() => {
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  useEffect(() => {
    setRows([]); setNote(null)
    if (!tenantId || !storeId) { setRefreshes([]); setRefreshId(''); return }
    setRefreshId('')
    setLoading(true)
    procurementService.refreshes(tenantId, storeId).then(setRefreshes).finally(() => setLoading(false))
  }, [tenantId, storeId])

  const loadUncategorised = async () => {
    if (!tenantId || !refreshId) return
    setBusy('load'); setNote(null)
    try {
      const products = await procurementService.shelfSortReview(tenantId, refreshId)
      setRows(products.map((p) => ({ name: p.name, unit: p.unit, product_code: p.product_code, category: 'Others' })))
      if (products.length === 0) setNote('Nothing to train — every product in this order already has a category.')
    } catch {
      setNote('Could not load the order.')
    } finally {
      setBusy(null)
    }
  }

  const aiSuggest = async () => {
    if (rows.length === 0) return
    setBusy('ai'); setNote(null)
    try {
      const { suggestions, llm_available } = await procurementService.shelfSortClassify(
        tenantId, rows.map((r) => r.name), rows.map((r) => r.unit),
      )
      if (!llm_available) {
        setNote('Claude auto-suggest is off on the server (no ANTHROPIC_API_KEY). Pick categories manually.')
        return
      }
      setRows((prev) => prev.map((r) => (suggestions[r.name] ? { ...r, category: suggestions[r.name] } : r)))
      setNote(`Claude suggested a category for ${Object.keys(suggestions).length} of ${rows.length} products — review and save.`)
    } catch {
      setNote('AI suggest failed.')
    } finally {
      setBusy(null)
    }
  }

  const save = async () => {
    const entries = rows.filter((r) => r.category && r.category !== 'Others').map((r) => ({ name: r.name, category: r.category }))
    if (entries.length === 0) { setNote('Set a category (other than Others) on at least one row first.'); return }
    setBusy('save'); setNote(null)
    try {
      const { saved } = await procurementService.shelfSortSaveCategories(tenantId, entries, null)
      setNote(`Saved ${saved} categories. They apply to every future shelf-sort.`)
      setRows((prev) => prev.filter((r) => r.category === 'Others'))
    } catch {
      setNote('Save failed.')
    } finally {
      setBusy(null)
    }
  }

  const setCategory = (idx: number, category: string) =>
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, category } : r)))

  const store = tenantStores.find((s) => s.store_id === storeId)

  return (
    <div className="pm-launch">
      <div className="pm-launch__card pm-launch__card--wide">
        <div className="pm-launch__brand"><i className="bi bi-mortarboard" /> Shelf Category Training</div>
        <p className="pm-launch__lead">
          Teach the shelf sorter the categories it can't guess. Load an order's un-categorised products,
          let Claude suggest categories, correct as needed, and save — remembered for every future sort.
        </p>

        <div className="pm-train__controls">
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
            <span>Order</span>
            <FilterSelect ariaLabel="Order" value={refreshId} onChange={setRefreshId} disabled={loading}>
              <option value="">{loading ? 'Loading…' : 'Select an order…'}</option>
              {refreshes.map((r) => <option key={r.refresh_id} value={r.refresh_id}>{r.snapshot_name} · {r.snapshot_status}</option>)}
            </FilterSelect>
          </label>
        </div>

        <div className="pm-train__actions">
          <button className="pm-btn pm-btn--primary" disabled={!refreshId || busy !== null} onClick={loadUncategorised}>
            <i className="bi bi-search" /> {busy === 'load' ? 'Loading…' : 'Load un-categorised'}
          </button>
          <button className="pm-btn pm-btn--ghost" disabled={rows.length === 0 || busy !== null} onClick={aiSuggest} title={store?.store_name}>
            <i className="bi bi-stars" /> {busy === 'ai' ? 'Asking Claude…' : 'AI Suggest (Claude)'}
          </button>
          <button className="pm-btn pm-btn--primary" disabled={rows.length === 0 || busy !== null} onClick={save}>
            <i className="bi bi-save" /> {busy === 'save' ? 'Saving…' : 'Save categories'}
          </button>
        </div>

        {note && <div className="pm-shelf__note"><i className="bi bi-info-circle" /> {note}</div>}

        {rows.length > 0 ? (
          <div className="pm-train__grid">
            <table>
              <thead>
                <tr><th>Product</th><th>Code</th><th>Category</th></tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.name}-${i}`}>
                    <td>{r.name}</td>
                    <td className="sx-dim">{r.product_code ?? '—'}</td>
                    <td>
                      <select className="sx-select sx-select--sm" value={r.category} onChange={(e) => setCategory(i, e.target.value)}>
                        {vocab.map((v) => <option key={v.category} value={v.category}>{v.category} ({v.code})</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !loading && refreshId && busy === null && !note && (
            <EmptyState icon="bi-inbox" title="Load an order" description="Pick an order and load its un-categorised products to begin." />
          )
        )}
      </div>
    </div>
  )
}
