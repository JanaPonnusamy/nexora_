import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { procurementService } from '../../services/procurementService'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type {
  DistributionConfigRow,
  DistributionRunSummary,
  DistributionRunItemRow,
} from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { WhatsAppSendCard } from '../../components/common/WhatsAppSendCard'
import { whatsappService } from '../../services/whatsappService'
import { buildDistributionImage } from '../../components/procurement/distributionImage'
import { date } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'
import { FilterSelect } from '../../design-system/components/FilterBar'

function stageBadge(status: string | null | undefined) {
  const s = status || 'skipped'
  const kind = s === 'success' || s === 'sent' ? 'success' : s === 'failed' ? 'danger' : 'muted'
  return <span className={`pm-badge pm-badge--${kind}`}>{s}</span>
}

function statusBadge(status: string) {
  const kind = status === 'completed' ? 'success' : status === 'failed' ? 'danger' : status === 'partial' ? 'warn' : 'muted'
  return <span className={`pm-badge pm-badge--${kind}`}>{status.toUpperCase()}</span>
}

function waStatusLine(status: string | null | undefined) {
  const s = status || 'not_queued'
  if (s === 'sent') return { icon: <span style={{ color: 'var(--nx-success-ink)' }}>✓</span>, label: 'Sent' }
  if (s === 'failed') return { icon: <span style={{ color: 'var(--nx-danger-ink)' }}>✕</span>, label: 'Failed' }
  if (s === 'queued') return { icon: <span className="sx-dim">…</span>, label: 'Queued' }
  return { icon: <span className="sx-dim">–</span>, label: 'Not sent' }
}

type Banner = { kind: 'success' | 'danger'; text: string } | null
type ActiveAction = 'all' | 'selected' | 'excel' | 'stock' | null

/** NEXORA Platform — Supplier Stock Distribution. One click generates the
 *  source store's ("NMW") own stock out to every other store: an Excel file
 *  per store + an automatic replace of that store's procurement.supplier_stock
 *  feed, plus a WhatsApp image send. See
 *  backend/modules/procurement/distribution_service.py. Frontend presents
 *  this purely as a NEXORA workflow — no implementation/legacy terminology. */
export default function SupplierStockDistributionPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [sourceStoreCode, setSourceStoreCode] = useState('NMW')
  const provider = 'legacy' as const
  const [config, setConfig] = useState<DistributionConfigRow[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [runs, setRuns] = useState<DistributionRunSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [activeAction, setActiveAction] = useState<ActiveAction>(null)
  const actingUser = useActingUser()
  const [banner, setBanner] = useState<Banner>(null)
  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [runItems, setRunItems] = useState<DistributionRunItemRow[]>([])
  const [runItemsLoading, setRunItemsLoading] = useState(false)

  const [lastRun, setLastRun] = useState<DistributionRunSummary | null>(null)
  const [lastRunItems, setLastRunItems] = useState<DistributionRunItemRow[]>([])
  const [copiedPath, setCopiedPath] = useState<string | null>(null)
  const [waErrorOpen, setWaErrorOpen] = useState<string | null>(null)
  const [waLaunching, setWaLaunching] = useState(false)
  const [waLaunchStatus, setWaLaunchStatus] = useState('')

  const launchWhatsAppLogin = async () => {
    setWaLaunching(true)
    setWaLaunchStatus('')
    try {
      const state = await whatsappService.getState()
      const profileId = state.capabilities.default_profile_id
      if (!profileId) {
        setWaLaunchStatus('No WhatsApp profile configured to launch.')
        return
      }
      const result = await whatsappService.launchProfile(profileId)
      setWaLaunchStatus(result.message || 'WhatsApp opened — scan the QR code, then retry the failed store.')
    } catch (e) {
      setWaLaunchStatus(e instanceof Error ? e.message : 'Unable to launch WhatsApp.')
    } finally {
      setWaLaunching(false)
    }
  }

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

  const run = async (
    action: Exclude<ActiveAction, null>,
    opts: { excelOnly?: boolean; supplierUpdateOnly?: boolean; onlySelected?: boolean },
  ) => {
    if (!tenantId || !sourceStoreCode) return say('danger', 'Select a tenant and source store')
    const storeIds = opts.onlySelected ? Array.from(selected) : undefined
    if (opts.onlySelected && (!storeIds || storeIds.length === 0)) return say('danger', 'Select at least one target store')
    setActiveAction(action)
    try {
      const res = await procurementService.generateDistribution(tenantId, sourceStoreCode, provider, {
        storeIds,
        excelOnly: opts.excelOnly,
        supplierUpdateOnly: opts.supplierUpdateOnly,
        startedBy: actingUser,
      })
      if (res.error) throw new Error(res.error)
      say('success', `Done — ${res.stores_succeeded ?? 0} succeeded, ${res.stores_failed ?? 0} failed`)
      if (res.run_id) {
        const detail = await procurementService.distributionRunDetail(res.run_id)
        setLastRun(detail.run)
        setLastRunItems(detail.items)
      }
      load()
    } catch (e) {
      fail(e)
    } finally {
      setActiveAction(null)
    }
  }

  const toggleRunDetail = async (runId: string) => {
    if (expandedRun === runId) { setExpandedRun(null); return }
    setExpandedRun(runId)
    setRunItemsLoading(true)
    try {
      const detail = await procurementService.distributionRunDetail(runId)
      setRunItems(detail.items)
    } catch (e) {
      fail(e)
    } finally {
      setRunItemsLoading(false)
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

  const copyPath = (path: string) => {
    navigator.clipboard.writeText(path).then(() => {
      setCopiedPath(path)
      window.setTimeout(() => setCopiedPath((c) => (c === path ? null : c)), 2000)
    }).catch(() => fail(new Error('Could not copy path')))
  }

  const exportedItems = lastRunItems.filter((it) => it.excel_status === 'success' && it.excel_path)

  return (
    <div className="pm-admin">
      <header className="pm-admin__head">
        <div className="pm-admin__title">
          <i className="bi bi-broadcast" />
          <div>
            <div className="sx-dim" style={{ fontSize: 12, letterSpacing: '0.06em' }}>NEXORA PLATFORM</div>
            <div>Supplier Stock Distribution</div>
          </div>
        </div>
        <div className="pm-admin__ctx">
          <FilterSelect ariaLabel="Tenant" value={tenantId} onChange={setTenantId}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </FilterSelect>
          <input
            className="pm-input pm-input--sm" placeholder="Source store (e.g. NMW)"
            value={sourceStoreCode} onChange={(e) => setSourceStoreCode(e.target.value.trim().toUpperCase())}
            title="Source store"
          />
          <button className="pm-btn pm-btn--ghost" onClick={load} title="Refresh"><i className="bi bi-arrow-repeat" /></button>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">Generate</div>
        <div className="pm-admin__form">
          <button className="pm-btn pm-btn--primary" disabled={activeAction !== null} onClick={() => run('all', {})}>
            <i className="bi bi-play-fill" /> {activeAction === 'all' ? 'Generating…' : 'Generate All'}
          </button>
          <button className="pm-btn" disabled={activeAction !== null} onClick={() => run('selected', { onlySelected: true })}>
            {activeAction === 'selected' ? 'Generating…' : `Generate Selected (${selected.size})`}
          </button>
          <button className="pm-btn" disabled={activeAction !== null} onClick={() => run('excel', { excelOnly: true })}>
            {activeAction === 'excel' ? 'Exporting…' : 'Export Excel'}
          </button>
          <button className="pm-btn" disabled={activeAction !== null} onClick={() => run('stock', { supplierUpdateOnly: true })}>
            {activeAction === 'stock' ? 'Updating…' : 'Update Supplier Stock'}
          </button>
        </div>
      </section>

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">Target stores</div>
        {targets.length === 0 && !loading ? (
          <EmptyState icon="bi-shop" title="No target stores" description="Every store in this tenant is either missing or matches the source store code." />
        ) : (
          <table className="pm-grid pm-admin__table">
            <thead>
              <tr>
                <th></th><th>Store</th><th>Supplier Code</th><th>WhatsApp Group</th><th>Phone Number</th><th>Enabled</th>
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

      {exportedItems.length > 0 && (
        <section className="pm-admin__panel">
          <div className="pm-admin__panel-title">Export</div>
          <div className="pm-banner pm-banner--success" style={{ marginBottom: 12 }}>
            <i className="bi bi-check-circle" /> Excel exported successfully
          </div>
          <table className="pm-grid pm-admin__table">
            <thead>
              <tr>
                <th>Store</th><th>File</th><th>WhatsApp</th><th></th>
              </tr>
            </thead>
            <tbody>
              {exportedItems.map((it) => {
                const targetCfg = targets.find((t) => t.store_code === it.store_code)
                const runDateText = date(lastRun?.started_at)
                return (
                  <tr key={it.run_item_id}>
                    <td className="pm-prod__name">{it.store_code}</td>
                    <td>
                      <code style={{ fontSize: 12 }}>{it.excel_path}</code>{' '}
                      <button className="pm-btn pm-btn--ghost" onClick={() => copyPath(it.excel_path as string)}>
                        {copiedPath === it.excel_path ? 'Copied!' : 'Copy Path'}
                      </button>
                    </td>
                    <td>{waStatusLine(it.whatsapp_status).icon} {waStatusLine(it.whatsapp_status).label}</td>
                    <td>
                      <WhatsAppSendCard
                        title={`Send ${it.store_code} distribution image`}
                        buttonLabel="Send WhatsApp Image"
                        defaultCaption={`NEXORA PLATFORM\nSUPPLIER STOCK DISTRIBUTION\n\nSource: ${sourceStoreCode}\nTarget: ${it.store_code}\nDate: ${runDateText}`}
                        preferredTargetName={targetCfg?.whatsapp_group ?? undefined}
                        preferredPhone={targetCfg?.phone_number ?? undefined}
                        buildFile={async () => {
                          const products = await procurementService.distributionRunItemProducts(it.run_item_id)
                          return buildDistributionImage({
                            sourceStoreCode,
                            targetStoreCode: it.store_code,
                            targetStoreName: targetCfg?.store_name ?? it.store_code,
                            runDate: runDateText,
                            rows: products.rows,
                          })
                        }}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      )}

      {lastRunItems.length > 0 && (
        <section className="pm-admin__panel">
          <div className="pm-admin__panel-title">WhatsApp Distribution</div>
          {waLaunchStatus && (
            <div className="pm-banner pm-banner--success" style={{ marginBottom: 12 }}>{waLaunchStatus}</div>
          )}
          <table className="pm-grid pm-admin__table">
            <tbody>
              {lastRunItems.map((it) => {
                const wa = waStatusLine(it.whatsapp_status)
                const errorText = it.whatsapp_error
                const needsQrLogin = it.whatsapp_status === 'failed' && !!errorText && /not logged in/i.test(errorText)
                return (
                  <tr key={it.run_item_id}>
                    <td className="pm-prod__name" style={{ width: 100 }}>{it.store_code}</td>
                    <td>{wa.icon} {wa.label}</td>
                    <td>
                      {it.whatsapp_status === 'failed' && errorText && (
                        <button className="pm-btn pm-btn--ghost" onClick={() => setWaErrorOpen((c) => (c === it.run_item_id ? null : it.run_item_id))}>
                          {waErrorOpen === it.run_item_id ? 'Hide error' : 'View error'}
                        </button>
                      )}
                      {needsQrLogin && (
                        <button className="pm-btn pm-btn--ghost" disabled={waLaunching} onClick={() => void launchWhatsAppLogin()} style={{ marginLeft: 8 }}>
                          {waLaunching ? 'Launching…' : 'Launch WhatsApp (Scan QR)'}
                        </button>
                      )}
                      {waErrorOpen === it.run_item_id && <span className="sx-dim" style={{ marginLeft: 8 }}>{errorText}</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      )}

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">Run history</div>
        {runs.length === 0 && !loading ? (
          <EmptyState icon="bi-clock-history" title="No runs yet" description="Generated runs will show up here." />
        ) : (
          <table className="pm-grid pm-admin__table">
            <thead>
              <tr>
                <th>Run Date</th><th>Operation</th><th>Status</th>
                <th className="sx-num">Stores</th><th className="sx-num">Success</th><th className="sx-num">Failed</th>
                <th className="sx-num">Products</th><th className="sx-num">Total Qty</th><th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <Fragment key={r.run_id}>
                  <tr>
                    <td className="sx-dim">{date(r.started_at)}</td>
                    <td>{r.source_store_code} Distribution</td>
                    <td>{statusBadge(r.status)}</td>
                    <td className="sx-num">{r.stores_total}</td>
                    <td className="sx-num">{r.stores_succeeded}</td>
                    <td className="sx-num">{r.stores_failed}</td>
                    <td className="sx-num">{r.total_products ?? '—'}</td>
                    <td className="sx-num">{r.total_stock_qty ?? '—'}</td>
                    <td>
                      <button className="pm-btn pm-btn--ghost" onClick={() => toggleRunDetail(r.run_id)}>
                        {expandedRun === r.run_id ? 'Hide' : 'View'}
                      </button>
                      {r.stores_failed > 0 && (
                        <button className="pm-btn pm-btn--ghost" onClick={() => retryFailed(r.run_id)}>Retry Failed</button>
                      )}
                    </td>
                  </tr>
                  {expandedRun === r.run_id && (
                    <tr>
                      <td colSpan={9}>
                        <div className="sx-dim" style={{ marginBottom: 8 }}>
                          <strong>NEXORA PLATFORM</strong> — Distribution Run Details · Source Store: {r.source_store_code} · Run Date: {date(r.started_at)} · Status: {r.status.toUpperCase()}
                        </div>
                        {r.error_summary && <div className="pm-banner pm-banner--danger" style={{ marginBottom: 8 }}>{r.error_summary}</div>}
                        {runItemsLoading ? (
                          <div className="sx-dim">Loading…</div>
                        ) : (
                          <table className="pm-grid pm-admin__table">
                            <thead>
                              <tr>
                                <th>Store</th><th className="sx-num">Rows</th>
                                <th>Stock Update</th><th>Excel</th><th>WhatsApp</th><th>Error</th>
                              </tr>
                            </thead>
                            <tbody>
                              {runItems.map((it) => (
                                <tr key={it.run_item_id}>
                                  <td>{it.store_code}</td>
                                  <td className="sx-num">{it.rows_imported ?? it.rows_exported ?? '—'}</td>
                                  <td>{stageBadge(it.stock_status)}</td>
                                  <td>{stageBadge(it.excel_status)}</td>
                                  <td>{stageBadge(it.whatsapp_status)}</td>
                                  <td className="sx-dim">{it.stock_error || it.excel_error || it.whatsapp_error || it.error_message || ''}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
