import { useCallback, useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { procurementService } from '../../services/procurementService'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { DistributionConfigRow, DistributionRunSummary } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { date } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'

type Banner = { kind: 'success' | 'danger'; text: string } | null

/** Supplier Stock Distribution (Procurement Admin) — one click generates the
 *  source ("HO") store's own stock out to every other store: an Excel file
 *  per store + an automatic replace of that store's procurement.supplier_stock
 *  feed (source = 'internal_distribution'), plus a WhatsApp send queue. See
 *  backend/modules/procurement/distribution_service.py. */
export default function SupplierStockDistributionPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [sourceStoreCode, setSourceStoreCode] = useState('NMW')
  const [provider, setProvider] = useState<'legacy' | 'nexora'>('legacy')
  const [config, setConfig] = useState<DistributionConfigRow[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [runs, setRuns] = useState<DistributionRunSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const actingUser = useActingUser()
  const [banner, setBanner] = useState<Banner>(null)

  const say = useCallback((kind: 'success' | 'danger', text: string) => {
    setBanner({ kind, text })
    window.setTimeout(() => setBanner(null), 6000)
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
  }, [fail])

  const load = useCallback(() => {
    if (!tenantId) { setConfig([]); setRuns([]); return }
    setLoading(true)
    Promise.all([
      procurementService.distributionConfig(tenantId, sourceStoreCode),
      procurementService.distributionRuns(tenantId, 15),
    ])
      .then(([c, r]) => { setConfig(c); setRuns(r) })
      .catch(fail)
      .finally(() => setLoading(false))
  }, [tenantId, sourceStoreCode, fail])

  const importLegacyMap = async () => {
    try {
      const res = await procurementService.importLegacySupplierMap(tenantId, sourceStoreCode)
      say('success', `Mapped ${res.imported.length} store(s) from legacy Ho_code${res.skipped.length ? `, skipped ${res.skipped.join(', ')}` : ''}`)
      load()
    } catch (e) { fail(e) }
  }

  useEffect(() => { load() }, [load])

  const targets = useMemo(
    () => config.filter((c) => c.store_code !== sourceStoreCode),
    [config, sourceStoreCode],
  )

  const toggle = (storeId: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(storeId)) next.delete(storeId); else next.add(storeId)
      return next
    })
  }

  const run = async (opts: { excelOnly?: boolean; supplierUpdateOnly?: boolean; onlySelected?: boolean }) => {
    if (!tenantId || !sourceStoreCode) return say('danger', 'Select a tenant and source store')
    const storeIds = opts.onlySelected ? Array.from(selected) : undefined
    if (opts.onlySelected && (!storeIds || storeIds.length === 0)) return say('danger', 'Select at least one store')
    setGenerating(true)
    try {
      const res = await procurementService.generateDistribution(tenantId, sourceStoreCode, provider, {
        storeIds,
        excelOnly: opts.excelOnly,
        supplierUpdateOnly: opts.supplierUpdateOnly,
        startedBy: actingUser,
      })
      if (res.error) throw new Error(res.error)
      say('success', `Done — ${res.stores_succeeded ?? 0} succeeded, ${res.stores_failed ?? 0} failed`)
      load()
    } catch (e) {
      fail(e)
    } finally {
      setGenerating(false)
    }
  }

  const retryFailed = async (runId: string) => {
    try {
      const res = await procurementService.retryDistribution(runId, provider, actingUser)
      say('success', `Retried — ${res.stores_succeeded ?? 0} succeeded, ${res.stores_failed ?? 0} failed`)
      load()
    } catch (e) { fail(e) }
  }

  const saveConfig = async (row: DistributionConfigRow, patch: Partial<DistributionConfigRow>) => {
    const next = { ...row, ...patch }
    setConfig((prev) => prev.map((c) => (c.store_id === row.store_id ? next : c)))
    try {
      await procurementService.saveDistributionConfig(tenantId, row.store_id, {
        whatsapp_group: next.whatsapp_group ?? undefined,
        phone_number: next.phone_number ?? undefined,
        enabled: next.enabled,
      })
    } catch (e) { fail(e); load() }
  }

  return (
    <div className="pm-admin">
      <header className="pm-admin__head">
        <div className="pm-admin__title"><i className="bi bi-broadcast" /> Supplier Stock Distribution</div>
        <div className="pm-admin__ctx">
          <select className="sx-select" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
          <input
            className="pm-input pm-input--sm" placeholder="Source store code (e.g. NMW)"
            value={sourceStoreCode} onChange={(e) => setSourceStoreCode(e.target.value.trim().toUpperCase())}
          />
          <select className="sx-select" aria-label="Source" value={provider} onChange={(e) => setProvider(e.target.value as 'legacy' | 'nexora')}>
            <option value="legacy">Legacy (OrderNMC)</option>
            <option value="nexora">Nexora (synced)</option>
          </select>
          <button className="pm-btn pm-btn--ghost" onClick={load} title="Refresh"><i className="bi bi-arrow-repeat" /></button>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">Generate</div>
        <div className="pm-admin__form">
          <button className="pm-btn pm-btn--primary" disabled={generating} onClick={() => run({})}>
            <i className="bi bi-play-fill" /> {generating ? 'Working…' : 'Generate All'}
          </button>
          <button className="pm-btn" disabled={generating} onClick={() => run({ onlySelected: true })}>
            Generate Selected ({selected.size})
          </button>
          <button className="pm-btn" disabled={generating} onClick={() => run({ excelOnly: true })}>
            Generate Excel Only
          </button>
          <button className="pm-btn" disabled={generating} onClick={() => run({ supplierUpdateOnly: true })}>
            Update Supplier Stock Only
          </button>
        </div>
      </section>

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">
          Target stores, supplier code mapping &amp; WhatsApp distribution config
          <button className="pm-btn pm-btn--ghost" style={{ marginLeft: 12 }} onClick={importLegacyMap} title="Copy each store's own supplier code for this source from the legacy OrderNMC Ho_code column">
            <i className="bi bi-download" /> Import from Legacy Ho_code
          </button>
        </div>
        {targets.length === 0 && !loading ? (
          <EmptyState icon="bi-shop" title="No target stores" description="Every store in this tenant is either missing or matches the source store code." />
        ) : (
          <table className="pm-grid pm-admin__table">
            <thead>
              <tr>
                <th></th><th>Store</th><th>Local Supplier Code</th><th>WhatsApp Group</th><th>Phone Number</th><th>Enabled</th>
              </tr>
            </thead>
            <tbody>
              {targets.map((c) => (
                <tr key={c.store_id}>
                  <td><input type="checkbox" checked={selected.has(c.store_id)} onChange={() => toggle(c.store_id)} /></td>
                  <td className="pm-prod__name">{c.store_name} <span className="sx-dim">({c.store_code})</span></td>
                  <td>
                    <input
                      className="pm-input pm-input--sm" placeholder={sourceStoreCode}
                      defaultValue={c.local_supplier_code ?? ''}
                      title="What this store's own systems call the source store as a supplier (defaults to the source store code if left blank)"
                      onBlur={(e) => {
                        const code = e.target.value.trim() || sourceStoreCode
                        procurementService.saveDistributionSupplierMap(tenantId, c.store_id, sourceStoreCode, code)
                          .then(() => load()).catch(fail)
                      }}
                    />
                  </td>
                  <td>
                    <input
                      className="pm-input pm-input--sm" defaultValue={c.whatsapp_group ?? ''}
                      onBlur={(e) => saveConfig(c, { whatsapp_group: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className="pm-input pm-input--sm" defaultValue={c.phone_number ?? ''}
                      onBlur={(e) => saveConfig(c, { phone_number: e.target.value })}
                    />
                  </td>
                  <td>
                    <input type="checkbox" checked={c.enabled} onChange={(e) => saveConfig(c, { enabled: e.target.checked })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">Run history</div>
        {runs.length === 0 && !loading ? (
          <EmptyState icon="bi-clock-history" title="No runs yet" description="Generated runs will show up here." />
        ) : (
          <table className="pm-grid pm-admin__table">
            <thead>
              <tr>
                <th>Started</th><th>Source</th><th>Provider</th><th>Status</th>
                <th className="sx-num">Stores</th><th className="sx-num">OK</th><th className="sx-num">Failed</th><th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="sx-dim">{date(r.started_at)}</td>
                  <td>{r.source_store_code}</td>
                  <td><span className="pm-badge pm-badge--muted">{r.provider}</span></td>
                  <td><span className={`pm-badge ${r.status === 'completed' ? 'pm-badge--success' : r.status === 'failed' ? 'pm-badge--danger' : 'pm-badge--muted'}`}>{r.status}</span></td>
                  <td className="sx-num">{r.stores_total}</td>
                  <td className="sx-num">{r.stores_succeeded}</td>
                  <td className="sx-num">{r.stores_failed}</td>
                  <td>
                    {r.stores_failed > 0 && (
                      <button className="pm-btn pm-btn--ghost" onClick={() => retryFailed(r.run_id)}>Retry Failed</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
