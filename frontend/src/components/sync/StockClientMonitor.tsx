import { useEffect, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { stockClientOpsService } from '../../services/stockClientOpsService'
import type {
  StockClientDeploymentDetail,
  StockClientInstallationDetail,
} from '../../types/stockClient'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { formatDateTime } from '../../utils/format'
import {
  SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxProgress, SxSegmented,
  SxSelect, SxStat, SxTable, type Tone,
} from './ui'

const connectivityTone = (c?: string): Tone =>
  c === 'ONLINE' ? 'success' : c === 'STALE' ? 'warning' : 'muted'
const clientTone = (c?: string): Tone =>
  c === 'RUNNING' ? 'success' : c === 'STOPPED' ? 'danger' : 'muted'
const versionTone = (v?: string): Tone =>
  v === 'UP TO DATE' ? 'success' : v === 'UPDATE AVAILABLE' ? 'indigo' : 'muted'
const releaseTone = (s: string): Tone =>
  ({ DRAFT: 'muted', TESTING: 'warning', APPROVED: 'success', ROLLED_OUT: 'indigo', RETIRED: 'muted' } as Record<string, Tone>)[s] ?? 'muted'
const deployTone = (s: string): Tone =>
  ({ DRAFT: 'muted', PENDING: 'warning', IN_PROGRESS: 'info', COMPLETED: 'success', CANCELLED: 'muted' } as Record<string, Tone>)[s] ?? 'muted'
const targetTone = (s: string): Tone => {
  if (s === 'SUCCESS') return 'success'
  if (s === 'FAILED') return 'danger'
  if (s === 'ROLLED_BACK') return 'warning'
  if (['DOWNLOADING', 'VERIFYING', 'INSTALLING', 'RESTARTING'].includes(s)) return 'info'
  return 'muted'
}

// Store Client fleet monitor + authorized per-store rollout. Watchdog-vs-client
// status are DISTINCT: client shows UNKNOWN whenever its watchdog isn't ONLINE.
export function StockClientMonitor() {
  const installQuery = useAsyncData(() => stockClientOpsService.installations())
  const releasesQuery = useAsyncData(() => stockClientOpsService.releases())
  const deploymentsQuery = useAsyncData(() => stockClientOpsService.deployments())

  const [detail, setDetail] = useState<StockClientInstallationDetail | null>(null)
  const [expanded, setExpanded] = useState<StockClientDeploymentDetail | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  // deploy builder
  const [releaseId, setReleaseId] = useState('')
  const [scope, setScope] = useState<'ALL' | 'SELECTED'>('ALL')
  const [picked, setPicked] = useState<Set<string>>(new Set())

  const deployable = (releasesQuery.data?.releases ?? []).filter(
    (r) => r.status === 'APPROVED' || r.status === 'ROLLED_OUT',
  )
  useEffect(() => {
    if (!releaseId && deployable.length) setReleaseId(deployable[0].id)
  }, [deployable, releaseId])

  const coreUnavailable = [installQuery.error, releasesQuery.error, deploymentsQuery.error]
    .some((m) => /internal server error|request failed|not found|forbidden|403/i.test(m ?? ''))

  if (installQuery.isLoading || releasesQuery.isLoading || deploymentsQuery.isLoading) {
    return <TableSkeleton rows={6} columns={8} />
  }
  if (coreUnavailable) {
    return (
      <EmptyState
        icon="bi-pc-display"
        title="Stock Client fleet not available"
        description="This HO has no Stock Client installations registered yet, or you lack super-admin access. Publish + approve a release and register a client to begin."
        action={{ label: 'Try again', icon: 'bi-arrow-clockwise', onClick: () => { void reloadAll() } }}
      />
    )
  }
  if (installQuery.error || !installQuery.data) {
    return <ErrorState title="Fleet unavailable" description={installQuery.error ?? 'Failed to load installations'} onRetry={installQuery.reload} />
  }
  if (releasesQuery.error || !releasesQuery.data) {
    return <ErrorState title="Fleet unavailable" description={releasesQuery.error ?? 'Failed to load releases'} onRetry={releasesQuery.reload} />
  }
  if (deploymentsQuery.error || !deploymentsQuery.data) {
    return <ErrorState title="Fleet unavailable" description={deploymentsQuery.error ?? 'Failed to load deployments'} onRetry={deploymentsQuery.reload} />
  }

  const installations = installQuery.data.installations
  const releases = releasesQuery.data.releases
  const deployments = deploymentsQuery.data.deployments

  function reloadAll() {
    return Promise.all([installQuery.reload(), releasesQuery.reload(), deploymentsQuery.reload()])
  }

  const online = installations.filter((i) => i.connectivity === 'ONLINE').length
  const needUpdate = installations.filter((i) => i.version_status === 'UPDATE AVAILABLE').length
  const offline = installations.filter((i) => i.connectivity === 'OFFLINE').length

  const togglePick = (storeId: string) => setPicked((prev) => {
    const next = new Set(prev)
    if (next.has(storeId)) next.delete(storeId); else next.add(storeId)
    return next
  })

  const openDetail = async (id: string | null) => {
    if (!id) return
    setDetail(await stockClientOpsService.installation(id))
  }

  const approve = async (id: string) => { setBusy(id); try { await stockClientOpsService.approveRelease(id); await releasesQuery.reload() } finally { setBusy(null) } }
  const retire = async (id: string) => { setBusy(id); try { await stockClientOpsService.retireRelease(id); await releasesQuery.reload() } finally { setBusy(null) } }

  const createDeployment = async () => {
    if (!releaseId) return
    const storeIds = scope === 'SELECTED' ? Array.from(picked) : []
    if (scope === 'SELECTED' && storeIds.length === 0) { window.alert('Select at least one store.'); return }
    setBusy('create')
    try {
      await stockClientOpsService.createDeployment({ release_id: releaseId, scope, store_ids: storeIds })
      setPicked(new Set())
      await deploymentsQuery.reload()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Failed to create deployment')
    } finally { setBusy(null) }
  }

  const authorize = async (id: string, count: number) => {
    if (!window.confirm(`Authorize this rollout? It will update ${count} store(s). This cannot be undone.`)) return
    setBusy(id)
    try { await stockClientOpsService.authorizeDeployment(id); await Promise.all([deploymentsQuery.reload(), installQuery.reload()]) }
    catch (e) { window.alert(e instanceof Error ? e.message : 'Failed to authorize') }
    finally { setBusy(null) }
  }
  const cancel = async (id: string) => { if (!window.confirm('Cancel this rollout?')) return; setBusy(id); try { await stockClientOpsService.cancelDeployment(id); await deploymentsQuery.reload() } finally { setBusy(null) } }
  const toggleExpand = async (id: string) => {
    if (expanded?.id === id) { setExpanded(null); return }
    setExpanded(await stockClientOpsService.deployment(id))
  }
  const retry = async (depId: string, targetId: string) => {
    setBusy(targetId)
    try { const d = await stockClientOpsService.retryTarget(depId, targetId); setExpanded(d); await deploymentsQuery.reload() }
    finally { setBusy(null) }
  }

  return (
    <div className="sx-stack">
      {/* ---- Monitor ---- */}
      <SxCard className="sx-pane">
        <SxCardHead
          title="Store Client Monitor"
          icon="bi-pc-display"
          sub={`${installations.length} stores`}
          action={<SxButton sm variant="ghost" icon="bi-arrow-clockwise" onClick={() => void reloadAll()}>Refresh</SxButton>}
        />
        <SxCardBody>
          <div className="d-flex flex-wrap gap-3 mb-1">
            <SxStat icon="bi-reception-4" tone="success" value={online} label="Online" />
            <SxStat icon="bi-arrow-up-circle" tone="indigo" value={needUpdate} label="Update available" />
            <SxStat icon="bi-reception-0" tone="muted" value={offline} label="Offline" />
          </div>
        </SxCardBody>
        <SxCardBody flush>
          {installations.length === 0 ? (
            <EmptyState icon="bi-pc-display" title="No stores" description="Active stores will appear here once registered." />
          ) : (
            <SxTable>
              <thead>
                <tr>
                  <th>Store</th>
                  <th>Current</th>
                  <th>Target</th>
                  <th>Client</th>
                  <th>Watchdog</th>
                  <th>Last heartbeat</th>
                  <th>IP</th>
                  <th className="sx-num" />
                </tr>
              </thead>
              <tbody>
                {installations.map((row) => (
                  <tr key={row.store_id}>
                    <td>
                      <div className="sx-rowlabel">
                        <span className="sx-rowlabel__main">{row.store_code ?? '—'}</span>
                        <span className="sx-rowlabel__sub">{row.store_name ?? ''}</span>
                      </div>
                    </td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{row.client_version ?? '—'}</td>
                    <td>
                      {row.target_version
                        ? <SxChip tone={versionTone(row.version_status)} compact>{row.target_version}</SxChip>
                        : <span className="sx-dim">—</span>}
                    </td>
                    <td><SxChip tone={clientTone(row.client)} compact>{row.client}</SxChip></td>
                    <td><SxChip tone={connectivityTone(row.connectivity)} compact>{row.connectivity}</SxChip></td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>
                      {row.last_heartbeat_at ? formatDateTime(row.last_heartbeat_at) : 'never'}
                    </td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{row.local_ip ?? row.observed_ip ?? '—'}</td>
                    <td className="sx-num">
                      <SxButton sm variant="ghost" icon="bi-info-circle" disabled={!row.installation_id} onClick={() => void openDetail(row.installation_id)}>Details</SxButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          )}
        </SxCardBody>
      </SxCard>

      {/* ---- Installation detail ---- */}
      {detail && (
        <SxCard className="sx-pane">
          <SxCardHead
            title={`${detail.store_code ?? 'Store'} — ${detail.store_name ?? ''}`}
            icon="bi-pc-display-horizontal"
            sub={detail.installation_status ?? ''}
            action={<SxButton sm variant="ghost" icon="bi-x-lg" onClick={() => setDetail(null)}>Close</SxButton>}
          />
          <SxCardBody>
            <div className="row g-2 small">
              <Field label="Client version" value={detail.client_version} />
              <Field label="Watchdog version" value={detail.watchdog_version} />
              <Field label="Installation ID" value={detail.installation_id} mono />
              <Field label="System fingerprint" value={detail.fingerprint_hash} mono />
              <Field label="Local IP" value={detail.local_ip} />
              <Field label="Observed IP" value={detail.observed_ip} />
              <Field label="OS" value={detail.os_version} />
              <Field label="Hostname" value={detail.hostname} />
              <Field label="Last heartbeat" value={detail.last_heartbeat_at ? formatDateTime(detail.last_heartbeat_at) : 'never'} />
              <Field label="Last update result" value={detail.last_update_status} />
              <Field label="Last error" value={detail.last_error ?? 'None'} />
              <Field label="Registered" value={detail.registered_at ? formatDateTime(detail.registered_at) : '—'} />
            </div>
          </SxCardBody>
          <SxCardBody flush>
            {detail.events.length === 0 ? (
              <EmptyState icon="bi-journal-text" title="No events" description="Update + registration events appear here." />
            ) : (
              <SxTable>
                <thead><tr><th>Event</th><th>Detail</th><th>Version</th><th>Result</th><th>Time</th></tr></thead>
                <tbody>
                  {detail.events.map((e, i) => (
                    <tr key={i}>
                      <td><SxChip tone="teal" compact>{e.event_type}</SxChip></td>
                      <td className="sx-dim">{e.detail ?? '—'}</td>
                      <td className="sx-dim">{e.target_version ?? '—'}</td>
                      <td className="sx-dim">{e.result ?? '—'}</td>
                      <td className="sx-dim">{e.created_at ? formatDateTime(e.created_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </SxTable>
            )}
          </SxCardBody>
        </SxCard>
      )}

      {/* ---- Releases + Deploy ---- */}
      <SxCard className="sx-pane">
        <SxCardHead
          title="Releases & Deploy"
          icon="bi-box-seam"
          sub="Publish a build with publish_stock_release.py, then approve + deploy here"
          action={<SxButton sm variant="ghost" icon="bi-arrow-clockwise" onClick={() => void releasesQuery.reload()}>Refresh</SxButton>}
        />
        <SxCardBody flush>
          {releases.length === 0 ? (
            <EmptyState icon="bi-box-seam" title="No releases" description="Run publish_stock_release.py <version> to create a DRAFT release." />
          ) : (
            <SxTable>
              <thead>
                <tr><th>Version</th><th>Release ID</th><th>Status</th><th>Notes</th><th>Created</th><th>Approved</th><th className="sx-num" /></tr>
              </thead>
              <tbody>
                {releases.map((r) => (
                  <tr key={r.id}>
                    <td className="sx-rowlabel__main">{r.version}</td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{r.release_id}</td>
                    <td><SxChip tone={releaseTone(r.status)} compact>{r.status}</SxChip></td>
                    <td className="sx-dim" style={{ maxWidth: 240 }}>{r.release_notes ?? '—'}</td>
                    <td className="sx-dim" style={{ fontSize: '0.8rem' }}>{r.created_at ? formatDateTime(r.created_at) : '—'}</td>
                    <td className="sx-dim" style={{ fontSize: '0.8rem' }}>{r.approved_by ? `${r.approved_by}` : '—'}</td>
                    <td className="sx-num">
                      <div className="d-flex gap-1 justify-content-end">
                        {(r.status === 'DRAFT' || r.status === 'TESTING') && (
                          <SxButton sm variant="success" icon="bi-check2-circle" busy={busy === r.id} onClick={() => void approve(r.id)}>Approve</SxButton>
                        )}
                        {r.status !== 'RETIRED' && (
                          <SxButton sm variant="ghost" icon="bi-archive" busy={busy === r.id} onClick={() => void retire(r.id)}>Retire</SxButton>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          )}
        </SxCardBody>
        <SxCardBody>
          <div className="d-flex flex-wrap align-items-center gap-2">
            <span className="sx-dim small">Deploy release</span>
            <SxSelect value={releaseId} onChange={setReleaseId} ariaLabel="Select release to deploy">
              <option value="">— select approved release —</option>
              {deployable.map((r) => <option key={r.id} value={r.id}>{r.version} ({r.status})</option>)}
            </SxSelect>
            <SxSegmented<'ALL' | 'SELECTED'>
              ariaLabel="Deployment scope"
              value={scope}
              onChange={setScope}
              options={[{ label: 'All stores', value: 'ALL' }, { label: 'Select stores', value: 'SELECTED' }]}
            />
            <SxButton sm variant="warning" icon="bi-rocket-takeoff" busy={busy === 'create'} disabled={!releaseId} onClick={() => void createDeployment()}>
              Create deployment
            </SxButton>
            <span className="sx-dim small">
              {scope === 'ALL' ? 'Targets every active store.' : `${picked.size} store(s) selected.`}
            </span>
          </div>
          {scope === 'SELECTED' && (
            <div className="d-flex flex-wrap gap-3 mt-2">
              {installations.map((i) => (
                <label key={i.store_id} className="d-inline-flex align-items-center gap-1 small">
                  <input type="checkbox" checked={picked.has(i.store_id)} onChange={() => togglePick(i.store_id)} />
                  {i.store_code}
                </label>
              ))}
            </div>
          )}
          <p className="sx-dim small mt-2 mb-0">
            <i className="bi bi-info-circle me-1" aria-hidden="true" />
            A deployment is created as DRAFT. It only reaches store watchdogs after you <strong>Authorize</strong> it below.
          </p>
        </SxCardBody>
      </SxCard>

      {/* ---- Deployments ---- */}
      <SxCard className="sx-pane">
        <SxCardHead
          title="Rollouts"
          icon="bi-diagram-2"
          sub="Authorize, track per-store progress, retry failures"
          action={<SxButton sm variant="ghost" icon="bi-arrow-clockwise" onClick={() => void deploymentsQuery.reload()}>Refresh</SxButton>}
        />
        <SxCardBody flush>
          {deployments.length === 0 ? (
            <EmptyState icon="bi-diagram-2" title="No rollouts yet" description="Create and authorize a deployment above." />
          ) : (
            <SxTable>
              <thead>
                <tr><th>Rollout</th><th>Version</th><th>Scope</th><th>Status</th><th>Progress</th><th>Authorized by</th><th className="sx-num" /></tr>
              </thead>
              <tbody>
                {deployments.map((d) => (
                  <tr key={d.id}>
                    <td className="sx-rowlabel__main">{d.rollout_id}</td>
                    <td className="sx-dim">{d.release_version}</td>
                    <td className="sx-dim">{d.scope}</td>
                    <td><SxChip tone={deployTone(d.status)} compact>{d.status}</SxChip></td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>
                      {d.success_count}/{d.target_count} ok{d.failed_count ? ` · ${d.failed_count} failed` : ''}
                    </td>
                    <td className="sx-dim" style={{ fontSize: '0.8rem' }}>{d.authorized_by ?? '—'}</td>
                    <td className="sx-num">
                      <div className="d-flex gap-1 justify-content-end">
                        {d.status === 'DRAFT' && (
                          <SxButton sm variant="primary" icon="bi-shield-check" busy={busy === d.id} onClick={() => void authorize(d.id, d.target_count)}>Authorize</SxButton>
                        )}
                        {(d.status === 'DRAFT' || d.status === 'PENDING' || d.status === 'IN_PROGRESS') && (
                          <SxButton sm variant="danger" icon="bi-x-circle" busy={busy === d.id} onClick={() => void cancel(d.id)}>Cancel</SxButton>
                        )}
                        <SxButton sm variant="ghost" icon={expanded?.id === d.id ? 'bi-chevron-up' : 'bi-chevron-down'} onClick={() => void toggleExpand(d.id)}>Targets</SxButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          )}
        </SxCardBody>
        {expanded && (
          <SxCardBody flush>
            <SxTable>
              <thead>
                <tr><th>Store</th><th>Current</th><th>Target</th><th>Status</th><th>Progress</th><th>Error</th><th className="sx-num" /></tr>
              </thead>
              <tbody>
                {expanded.targets.map((t) => (
                  <tr key={t.id}>
                    <td className="sx-rowlabel__main">{t.store_code ?? '—'}</td>
                    <td className="sx-dim">{t.current_version ?? '—'}</td>
                    <td className="sx-dim">{t.target_version}</td>
                    <td><SxChip tone={targetTone(t.status)} compact>{t.status}</SxChip></td>
                    <td style={{ minWidth: 120 }}><SxProgress value={t.progress} /></td>
                    <td className="sx-dim" style={{ maxWidth: 220, fontSize: '0.8rem' }}>{t.error ?? '—'}</td>
                    <td className="sx-num">
                      {t.status === 'FAILED' && (
                        <SxButton sm variant="warning" icon="bi-arrow-repeat" busy={busy === t.id} onClick={() => void retry(expanded.id, t.id)}>Retry</SxButton>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          </SxCardBody>
        )}
      </SxCard>
    </div>
  )
}

function Field({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div className="col-6 col-md-4 col-lg-3">
      <div className="sx-dim" style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
      <div style={{ fontFamily: mono ? 'var(--bs-font-monospace, monospace)' : undefined, wordBreak: 'break-word' }}>
        {value ?? '—'}
      </div>
    </div>
  )
}
