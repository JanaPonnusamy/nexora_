import { useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Refresh } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import '../../components/procurement/purchase-manager.css'

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Shelf Sorting & Excel Split — picks a Store + Order (Refresh) and generates
 * the existing Purchase Order export, re-sorted by shelf category ->
 * SubLocation -> ProductName and split into pick-sized files (max 16 products
 * each). Single file downloads as .xlsx; multiple come back as a .zip. The
 * export format, columns and engine are unchanged — only the row order and the
 * split boundaries. Summary shows Store / Order / Total Products / Generated
 * Files, nothing else.
 */
type Source = 'order' | 'file'

export default function ShelfSortingPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [refreshes, setRefreshes] = useState<Refresh[]>([])
  const [refreshId, setRefreshId] = useState('')
  const [source, setSource] = useState<Source>('order')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{
    storeName: string
    orderName: string
    totalProducts: number
    fileCount: number
  } | null>(null)

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

  useEffect(() => {
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : (tenantStores[0]?.store_id ?? '')))
  }, [tenantStores])

  useEffect(() => {
    setResult(null)
    if (!tenantId || !storeId) { setRefreshes([]); setRefreshId(''); return }
    setRefreshId('')
    setLoading(true)
    procurementService.refreshes(tenantId, storeId)
      .then(setRefreshes)
      .finally(() => setLoading(false))
  }, [tenantId, storeId])

  const store = tenantStores.find((s) => s.store_id === storeId)
  const refresh = refreshes.find((r) => r.refresh_id === refreshId)

  const canGenerate = !!store && (source === 'order' ? !!refreshId : !!file)

  const generate = async () => {
    if (!tenantId || !store || !canGenerate) return
    setBusy(true)
    try {
      const out =
        source === 'order'
          ? await procurementService.shelfSort(tenantId, refreshId, { store_name: store.store_name })
          : await procurementService.shelfSortFile(tenantId, store.store_id, store.store_name, file!)
      downloadBlob(out.blob, out.filename)
      setResult({
        storeName: store.store_name,
        orderName: source === 'order' ? (refresh?.snapshot_name ?? refreshId) : (file?.name ?? 'Excel file'),
        totalProducts: out.totalProducts,
        fileCount: out.fileCount,
      })
    } catch {
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pm-launch">
      <div className="pm-launch__card">
        <div className="pm-launch__brand"><i className="bi bi-signpost-split" /> Shelf Sorting &amp; Excel Split</div>
        <p className="pm-launch__lead">
          Generate the order sorted by shelf category and location, split into pick-sized Excel files.
        </p>

        <label className="pm-launch__field">
          <span>Tenant</span>
          <select className="sx-select" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
        </label>

        <label className="pm-launch__field">
          <span>Store</span>
          <select className="sx-select" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            <option value="">Select store…</option>
            {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </select>
        </label>

        <div className="pm-launch__field">
          <span>Source</span>
          <div className="pm-shelf__source">
            {(['order', 'file'] as Source[]).map((s) => (
              <label key={s} className={`pm-shelf__srcopt${source === s ? ' pm-shelf__srcopt--on' : ''}`}>
                <input
                  type="radio"
                  name="pm-shelf-source"
                  checked={source === s}
                  onChange={() => { setSource(s); setResult(null) }}
                />
                {s === 'order' ? 'From Order' : 'From Excel File'}
              </label>
            ))}
          </div>
        </div>

        {source === 'order' ? (
          <>
            <label className="pm-launch__field">
              <span>Order</span>
              <select className="sx-select" value={refreshId} onChange={(e) => setRefreshId(e.target.value)} disabled={loading}>
                <option value="">{loading ? 'Loading…' : 'Select an order…'}</option>
                {refreshes.map((r) => <option key={r.refresh_id} value={r.refresh_id}>{r.snapshot_name} · {r.snapshot_status}</option>)}
              </select>
            </label>

            {!loading && refreshes.length === 0 && tenantId && storeId && (
              <EmptyState icon="bi-inbox" title="No orders" description="This store has no refreshes to sort yet." />
            )}
          </>
        ) : (
          <label className="pm-launch__field">
            <span>Excel File</span>
            <input
              className="pm-input"
              type="file"
              accept=".xlsx"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null) }}
            />
          </label>
        )}

        <button className="pm-btn pm-btn--primary pm-launch__go" disabled={!canGenerate || busy} onClick={generate}>
          <i className="bi bi-file-earmark-excel" /> {busy ? 'Generating…' : 'Generate Sorted Excel'}
        </button>

        {result && (
          <dl className="pm-shelf__summary">
            <div><dt>Store</dt><dd>{result.storeName}</dd></div>
            <div><dt>Order</dt><dd>{result.orderName}</dd></div>
            <div><dt>Total Products</dt><dd>{result.totalProducts}</dd></div>
            <div><dt>Generated Files</dt><dd>{result.fileCount}</dd></div>
          </dl>
        )}
      </div>
    </div>
  )
}
