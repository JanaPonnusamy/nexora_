import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAsyncData } from '../../hooks/useAsyncData'
import { deviceControllerService as dc } from '../../services/deviceControllerService'
import type {
  DcAppKey, DcAppStatus, DcCommand, DcDevice, DcDeviceDetail, DcPackage,
} from '../../types/deviceController'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import {
  SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxSearch, SxSelect, SxStat, SxTable, type Tone,
} from './ui'
import './device-controller.css'

const APP_ORDER: DcAppKey[] = ['store_agent', 'stock_client', 'ho_backend', 'mail_transfer', 'controller']
const APP_LABEL: Record<DcAppKey, string> = {
  store_agent: 'Store Agent', stock_client: 'Stock Client', ho_backend: 'HO Backend',
  mail_transfer: 'Mail Transfer', controller: 'Controller',
}
const APP_ACTIONS: Record<DcAppKey, string[]> = {
  store_agent: ['start', 'stop', 'restart', 'pause', 'resume', 'update'],
  stock_client: ['start', 'stop', 'restart', 'pause', 'resume', 'update'],
  ho_backend: ['start', 'stop', 'restart', 'pause', 'resume', 'update'],
  mail_transfer: ['start', 'stop', 'restart', 'pause', 'resume'],
  controller: ['update', 'restart', 'retire_legacy_watchdogs'],
}
const ACTION_ICON: Record<string, string> = {
  start: 'bi-play-fill', stop: 'bi-stop-fill', restart: 'bi-arrow-clockwise',
  pause: 'bi-pause-fill', resume: 'bi-skip-forward-fill', update: 'bi-cloud-arrow-down',
  retire_legacy_watchdogs: 'bi-shield-x',
}
const ACTION_LABEL: Record<string, string> = { retire_legacy_watchdogs: 'Retire old watchdogs' }

// Backend datetimes are naive UTC (SYSUTCDATETIME).
function fmt(value: string | null | undefined) {
  if (!value) return '—'
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString()
}

const statusTone = (s: string | null | undefined): Tone =>
  s === 'running' ? 'success' : s === 'stopped' ? 'danger' : s === 'pending' ? 'warning' : 'muted'
const commandTone = (s: DcCommand['status']): Tone =>
  ({ SUCCEEDED: 'success', FAILED: 'danger', RUNNING: 'info', DELIVERED: 'indigo', QUEUED: 'warning' } as Record<string, Tone>)[s] ?? 'muted'

// The Stock Client is a desktop app people open and close, so "not running"
// is normal for it -- shown neutral as "closed", never as a failure.
const isGui = (app: DcAppStatus) => app.app_key === 'stock_client'
function appTone(app: DcAppStatus): Tone {
  if (appNeedsAttention(app)) return 'danger'
  if (isGui(app) && app.status !== 'running') return 'muted'
  return statusTone(app.status)
}
function appStatusLabel(app: DcAppStatus) {
  if (isGui(app)) return app.status === 'running' ? 'open' : 'closed'
  return app.status ?? 'unknown'
}

function appNeedsAttention(app: DcAppStatus) {
  return app.installed && app.desired_state === 'RUNNING' && app.status !== 'running' && app.app_key !== 'stock_client'
}

export function DeviceController() {
  const navigate = useNavigate()
  const devicesQuery = useAsyncData(() => dc.devices())
  const packagesQuery = useAsyncData(() => dc.packages())
  const [search, setSearch] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState<{ tone: Tone; text: string } | null>(null)
  const [showEnroll, setShowEnroll] = useState(false)

  const reloadDevices = devicesQuery.reload
  useEffect(() => {
    const t = window.setInterval(() => { void reloadDevices() }, 15000)
    return () => window.clearInterval(t)
  }, [reloadDevices])

  const devices = useMemo(() => devicesQuery.data?.devices ?? [], [devicesQuery.data])
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return devices
    return devices.filter((d) => [d.hostname, d.machine_name, d.local_ip, d.observed_ip,
      ...d.stores.map((s) => `${s.store_code} ${s.store_name}`)]
      .some((v) => (v ?? '').toLowerCase().includes(q)))
  }, [devices, search])

  const packages = packagesQuery.data?.packages ?? {}
  const online = devices.filter((d) => d.online).length
  const attention = devices.reduce((n, d) => n + d.apps.filter(appNeedsAttention).length, 0)
  const pending = devices.reduce((n, d) => n + d.pending_commands, 0)

  const toggle = (id: string) => setSelected((cur) => {
    const next = new Set(cur)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  if (devicesQuery.error) {
    return <ErrorState description={devicesQuery.error} onRetry={() => void devicesQuery.reload()} />
  }

  return (
    <div className="dc">
      <div className="dc-stats">
        <SxStat icon="bi-pc-display" tone="indigo" value={devices.length} label="Controlled PCs" />
        <SxStat icon="bi-wifi" tone="success" value={online} label="Online" sub={`${devices.length - online} offline`} />
        <SxStat icon="bi-exclamation-triangle" tone={attention ? 'danger' : 'muted'} value={attention} label="Apps down" sub="desired running, not running" />
        <SxStat icon="bi-hourglass-split" tone={pending ? 'warning' : 'muted'} value={pending} label="Commands in flight" />
      </div>

      {packagesQuery.data && !packagesQuery.data.has_command_key && (
        <div className="dc-banner dc-banner--danger">
          <i className="bi bi-key" /> This HO node has no device-controller command key, so it cannot send commands.
          Copy <code>device_controller_command_key.pem</code> into the HO config folder.
        </div>
      )}
      {message && (
        <div className={`dc-banner dc-banner--${message.tone}`}>
          {message.text}
          <button type="button" className="dc-banner__close" onClick={() => setMessage(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      <SxCard>
        <SxCardHead
          title="Devices"
          icon="bi-hdd-network"
          sub={`${filtered.length} of ${devices.length}`}
          action={(
            <div className="d-flex gap-2 align-items-center flex-wrap">
              <SxSearch value={search} onChange={setSearch} placeholder="Host, IP or store…" />
              <SxButton sm icon="bi-terminal" onClick={() => navigate('/sync/terminal')}>Terminal</SxButton>
              <SxButton sm icon="bi-key" onClick={() => setShowEnroll((v) => !v)}>Enroll a PC</SxButton>
              <SxButton sm icon="bi-arrow-clockwise" onClick={() => { void devicesQuery.reload(); void packagesQuery.reload() }}>Refresh</SxButton>
            </div>
          )}
        />
        {showEnroll && <EnrollPanel onClose={() => setShowEnroll(false)} />}
        {selected.size > 0 && (
          <BulkBar
            deviceIds={[...selected]}
            packages={packages}
            onDone={(text, tone) => { setMessage({ text, tone }); setSelected(new Set()); void devicesQuery.reload() }}
          />
        )}
        <SxCardBody flush>
          {devicesQuery.isLoading && !devicesQuery.data ? <TableSkeleton rows={5} columns={6} /> : filtered.length === 0 ? (
            <EmptyState
              icon="bi-hdd-network"
              title="No controlled PCs yet"
              description="Install the Device Controller on a PC (it ships with the Stock Client installer, or run NexoraDeviceController.exe setup with an enrollment code)."
            />
          ) : (
            <SxTable>
              <thead>
                <tr>
                  <th style={{ width: 32 }} />
                  <th>PC</th>
                  <th>Store</th>
                  <th>Apps</th>
                  <th>Updates available</th>
                  <th>Controller</th>
                  <th>Last seen</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.map((d) => (
                  <DeviceRow
                    key={d.device_id}
                    device={d}
                    open={openId === d.device_id}
                    selected={selected.has(d.device_id)}
                    onToggleSelect={() => toggle(d.device_id)}
                    onToggleOpen={() => setOpenId(openId === d.device_id ? null : d.device_id)}
                    onTerminal={() => navigate(`/sync/terminal?device=${d.device_id}`)}
                    packages={packages}
                    onChanged={() => void devicesQuery.reload()}
                  />
                ))}
              </tbody>
            </SxTable>
          )}
        </SxCardBody>
      </SxCard>
    </div>
  )
}

function DeviceRow({
  device, open, selected, onToggleSelect, onToggleOpen, onTerminal, packages, onChanged,
}: {
  device: DcDevice; open: boolean; selected: boolean
  onToggleSelect: () => void; onToggleOpen: () => void; onTerminal: () => void
  packages: Partial<Record<string, DcPackage[]>>; onChanged: () => void
}) {
  const apps = APP_ORDER.map((k) => device.apps.find((a) => a.app_key === k)).filter(
    (a): a is DcAppStatus => !!a && a.installed && a.app_key !== 'controller',
  )
  return (
    <>
      <tr className={open ? 'dc-row--open' : ''}>
        <td><input type="checkbox" checked={selected} onChange={onToggleSelect} aria-label="Select PC" /></td>
        <td>
          <button type="button" className="dc-link" onClick={onToggleOpen}>
            <i className={`bi ${open ? 'bi-chevron-down' : 'bi-chevron-right'}`} /> {device.hostname || device.machine_name || device.device_id}
          </button>
          <div className="dc-muted">{device.local_ip || '—'}{device.observed_ip && device.observed_ip !== device.local_ip ? ` · seen ${device.observed_ip}` : ''}</div>
        </td>
        <td>{device.stores.length ? device.stores.map((s) => s.store_code).join(', ') : <span className="dc-muted">—</span>}</td>
        <td>
          <div className="dc-appchips">
            {apps.length === 0 && <span className="dc-muted">none found</span>}
            {apps.map((a) => (
              <span key={a.app_key} title={`${APP_LABEL[a.app_key]}: ${appStatusLabel(a)}`}>
                <SxChip compact dot tone={appTone(a)}>
                  {APP_LABEL[a.app_key]} {a.version ? `v${a.version}` : ''}
                </SxChip>
              </span>
            ))}
          </div>
        </td>
        <td><UpdatesCell device={device} packages={packages} onChanged={onChanged} /></td>
        <td>{device.controller_version ?? '—'}</td>
        <td>
          <SxChip compact dot tone={device.online ? 'success' : 'muted'}>{device.online ? 'Online' : 'Offline'}</SxChip>
          <div className="dc-muted">{fmt(device.last_heartbeat_at)}</div>
        </td>
        <td className="text-end">
          <SxButton sm icon="bi-terminal" onClick={onTerminal} title="Open a PowerShell terminal on this PC" />
        </td>
      </tr>
      {open && (
        <tr className="dc-detailrow">
          <td colSpan={8}><DevicePanel deviceId={device.device_id} packages={packages} onChanged={onChanged} /></td>
        </tr>
      )}
    </>
  )
}

function DevicePanel({
  deviceId, packages, onChanged,
}: { deviceId: string; packages: Partial<Record<string, DcPackage[]>>; onChanged: () => void }) {
  const [detail, setDetail] = useState<DcDeviceDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(() => {
    dc.device(deviceId).then(setDetail).catch((e: Error) => setError(e.message))
  }, [deviceId])

  useEffect(() => { load() }, [load])
  const inFlight = detail?.commands.some((c) => ['QUEUED', 'DELIVERED', 'RUNNING'].includes(c.status))
  useEffect(() => {
    const t = window.setInterval(load, inFlight ? 3000 : 15000)
    return () => window.clearInterval(t)
  }, [load, inFlight])

  const send = async (app: DcAppKey, action: string, args: Record<string, unknown> = {}) => {
    if (['stop', 'pause', 'update', 'restart'].includes(action) && app === 'ho_backend'
        && !window.confirm(`${action} the HO backend on this PC? Users of this HO node will be disconnected briefly.`)) return
    setBusy(`${app}:${action}`)
    setError(null)
    try {
      await dc.command(deviceId, app, action, args)
      load()
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  if (!detail) return error ? <div className="dc-banner dc-banner--danger">{error}</div> : <TableSkeleton rows={3} columns={4} />

  return (
    <div className="dc-panel">
      {error && <div className="dc-banner dc-banner--danger">{error}</div>}
      <div className="dc-panel__meta">
        <span><b>OS</b> {detail.os_version ?? '—'}</span>
        <span><b>Reaches HO via</b> {detail.ho_url ?? '—'}</span>
        <span><b>Enrolled by</b> {detail.registered_by_username ?? '—'} · {fmt(detail.registered_at)}</span>
      </div>
      <div className="dc-apps">
        {APP_ORDER.map((key) => {
          const app = detail.apps.find((a) => a.app_key === key)
          if (!app || (!app.installed && key !== 'stock_client')) return null
          return (
            <AppCard
              key={key}
              app={app}
              desired={detail.desired[key]?.desired_state ?? app.desired_state}
              pausedUntil={detail.desired[key]?.paused_until ?? null}
              versions={packages[key] ?? []}
              busy={busy}
              onAction={(action, args) => void send(key, action, args)}
            />
          )
        })}
      </div>
      <CommandHistory commands={detail.commands} onCancel={async (id) => { await dc.cancelCommand(id); load() }} />
    </div>
  )
}

function AppCard({
  app, desired, pausedUntil, versions, busy, onAction,
}: {
  app: DcAppStatus; desired: string | null; pausedUntil: string | null; versions: DcPackage[]
  busy: string | null; onAction: (action: string, args?: Record<string, unknown>) => void
}) {
  const [version, setVersion] = useState('')
  const [editingLinks, setEditingLinks] = useState(false)
  const [links, setLinks] = useState('')
  const key = app.app_key
  const maintenance = Boolean(app.details?.maintenance)

  useEffect(() => {
    if (!version && versions.length) setVersion(versions[0].version)
  }, [versions, version])

  const run = (action: string) => {
    if (action === 'pause') {
      const minutes = window.prompt('Pause for how many minutes? (it resumes automatically)', '30')
      if (minutes === null) return
      onAction('pause', { minutes: Number(minutes) || 30 })
    } else if (action === 'update') {
      if (!version) return
      if (!window.confirm(`Update ${APP_LABEL[key]} to ${version}?`)) return
      onAction('update', { version })
    } else {
      onAction(action)
    }
  }

  return (
    <div className="dc-app">
      <div className="dc-app__head">
        <span className="dc-app__name">{APP_LABEL[key]}</span>
        {app.installed ? (
          <SxChip compact dot tone={appTone(app)}>{appStatusLabel(app)}</SxChip>
        ) : <SxChip compact tone="muted">not installed</SxChip>}
        {maintenance && <SxChip compact tone="warning">updating…</SxChip>}
      </div>
      <div className="dc-app__facts">
        <span>Version <b>{app.version ?? '—'}</b></span>
        {desired && <span>Desired <b>{desired}</b>{desired === 'PAUSED' && pausedUntil ? ` until ${fmt(pausedUntil)}` : ''}</span>}
        {key === 'ho_backend' && <span>Health <b>{app.details?.healthy ? 'OK' : 'down'}</b></span>}
        {app.details?.kind === 'git' && <span>Checkout <b>{String(app.details.commit ?? app.details.repo ?? '')}</b></span>}
        {key === 'stock_client' && app.details?.user_session && <span>User <b>{String(app.details.user_session)}</b></span>}
      </div>
      {key === 'store_agent' && (
        <div className="dc-links">
          <div className="dc-links__head">
            <span>HO links</span>
            {!editingLinks && (
              <button type="button" className="dc-link" onClick={() => { setLinks((app.details.ho_urls ?? []).join('\n')); setEditingLinks(true) }}>
                <i className="bi bi-pencil" /> Edit
              </button>
            )}
          </div>
          {editingLinks ? (
            <>
              <textarea className="dc-links__edit" rows={4} value={links} onChange={(e) => setLinks(e.target.value)}
                placeholder="One HO URL per line, preferred first" />
              <div className="d-flex gap-2 mt-1">
                <SxButton sm variant="primary" icon="bi-check2" busy={busy === 'store_agent:set_ho_urls'}
                  onClick={() => {
                    const urls = links.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)
                    if (!urls.length) return
                    onAction('set_ho_urls', { urls, restart: true })
                    setEditingLinks(false)
                  }}>Save &amp; restart agent</SxButton>
                <SxButton sm onClick={() => setEditingLinks(false)}>Cancel</SxButton>
              </div>
            </>
          ) : (
            <ol className="dc-links__list">
              {(app.details.ho_urls ?? []).map((u) => <li key={u}>{u}</li>)}
              {!(app.details.ho_urls ?? []).length && <li className="dc-muted">none configured</li>}
            </ol>
          )}
          {app.details.ho_override && <div className="dc-muted">Override file: {app.details.ho_override}</div>}
        </div>
      )}
      {key === 'controller' && app.details.legacy_watchdogs && (
        <div className="dc-muted">
          Old watchdogs: {Object.entries(app.details.legacy_watchdogs).map(([k, v]) => `${k} ${v}`).join(' · ')}
        </div>
      )}
      <div className="dc-app__actions">
        {APP_ACTIONS[key].filter((a) => a !== 'update').map((action) => (
          <SxButton key={action} sm icon={ACTION_ICON[action]} busy={busy === `${key}:${action}`}
            disabled={!app.installed && key !== 'controller'} onClick={() => run(action)}
            variant={action === 'stop' ? 'danger' : action === 'start' || action === 'resume' ? 'success' : 'ghost'}>
            {ACTION_LABEL[action] ?? action[0].toUpperCase() + action.slice(1)}
          </SxButton>
        ))}
        {APP_ACTIONS[key].includes('update') && app.details?.kind !== 'git' && (
          <span className="dc-update">
            <SxSelect value={version} onChange={setVersion} ariaLabel={`${APP_LABEL[key]} version`}>
              {versions.length === 0 && <option value="">no packages</option>}
              {versions.map((p) => <option key={p.version} value={p.version}>{p.version}{p.version === app.version ? ' (installed)' : ''}</option>)}
            </SxSelect>
            <SxButton sm variant="warning" icon={ACTION_ICON.update} busy={busy === `${key}:update`}
              disabled={!version} onClick={() => run('update')}>
              {app.installed ? 'Update' : 'Install'}
            </SxButton>
          </span>
        )}
      </div>
    </div>
  )
}

// Numeric-aware version compare: 2026.10.22.1 > 2026.7.22.1, 0.1.47 > 0.1.9.
function compareVersions(a: string, b: string) {
  const pa = a.split(/[.-]/)
  const pb = b.split(/[.-]/)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] ?? '0'
    const y = pb[i] ?? '0'
    const nx = Number(x)
    const ny = Number(y)
    const d = Number.isNaN(nx) || Number.isNaN(ny) ? x.localeCompare(y) : nx - ny
    if (d !== 0) return d
  }
  return 0
}

const UPDATABLE: DcAppKey[] = ['store_agent', 'stock_client', 'ho_backend', 'controller']

/** Published versions newer than what each app on this PC runs, newest first. */
function newerVersions(device: DcDevice, packages: Partial<Record<string, DcPackage[]>>) {
  return UPDATABLE.map((key) => {
    const app = device.apps.find((a) => a.app_key === key)
    if (!app?.installed || app.details?.kind === 'git') return null
    const installed = app.version ?? ''
    const versions = (packages[key] ?? [])
      .map((p) => p.version)
      .filter((v) => !installed || compareVersions(v, installed) > 0)
      .sort((a, b) => compareVersions(b, a))
    return versions.length ? { key, installed, versions } : null
  }).filter((x): x is { key: DcAppKey; installed: string; versions: string[] } => x !== null)
}

function UpdatesCell({
  device, packages, onChanged,
}: { device: DcDevice; packages: Partial<Record<string, DcPackage[]>>; onChanged: () => void }) {
  const updates = newerVersions(device, packages)
  if (!updates.length) return <span className="dc-muted">Up to date</span>
  return (
    <div className="dc-updates">
      {updates.map((u) => <UpdateRow key={u.key} deviceId={device.device_id} update={u} disabled={!device.online} onChanged={onChanged} />)}
    </div>
  )
}

function UpdateRow({
  deviceId, update, disabled, onChanged,
}: {
  deviceId: string; update: { key: DcAppKey; installed: string; versions: string[] }
  disabled: boolean; onChanged: () => void
}) {
  const [version, setVersion] = useState(update.versions[0])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  useEffect(() => { setVersion(update.versions[0]) }, [update.versions])

  const go = async () => {
    const label = APP_LABEL[update.key]
    const warn = update.key === 'ho_backend' ? ' This HO node restarts during the update.' : ''
    if (!window.confirm(`Update ${label} ${update.installed || ''} -> ${version}?${warn}`)) return
    setBusy(true)
    setNote(null)
    try {
      await dc.command(deviceId, update.key, 'update', { version })
      setNote('queued')
      onChanged()
    } catch (e) {
      setNote((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="dc-updates__row" title={disabled ? 'PC is offline' : undefined}>
      <span className="dc-updates__app">{APP_LABEL[update.key]}</span>
      <span className="dc-muted">{update.installed || '?'} →</span>
      <select className="dc-updates__select" value={version} onChange={(e) => setVersion(e.target.value)}
        aria-label={`${APP_LABEL[update.key]} version`}>
        {update.versions.map((v, i) => <option key={v} value={v}>{v}{i === 0 ? ' (latest)' : ''}</option>)}
      </select>
      <SxButton sm variant="warning" icon="bi-cloud-arrow-down" busy={busy} disabled={disabled} onClick={() => void go()}
        title={`Update ${APP_LABEL[update.key]}`} />
      {note && <span className="dc-muted">{note}</span>}
    </div>
  )
}

function CommandHistory({ commands, onCancel }: { commands: DcCommand[]; onCancel: (id: string) => void }) {
  const [openId, setOpenId] = useState<string | null>(null)
  if (!commands.length) return <div className="dc-muted mt-2">No commands sent to this PC yet.</div>
  return (
    <div className="dc-history">
      <div className="dc-history__title">Command history</div>
      <SxTable>
        <thead>
          <tr><th>When</th><th>App</th><th>Action</th><th>By</th><th>Status</th><th /></tr>
        </thead>
        <tbody>
          {commands.map((c) => (
            <Fragment key={c.command_id}>
              <tr>
                <td>{fmt(c.requested_at)}</td>
                <td>{APP_LABEL[c.app_key] ?? c.app_key}</td>
                <td>
                  {ACTION_LABEL[c.action] ?? c.action}
                  {c.action === 'update' && c.args?.package ? ` ${(c.args.package as { version: string }).version}` : ''}
                  {c.action === 'pause' && c.args?.minutes ? ` ${String(c.args.minutes)} min` : ''}
                </td>
                <td>{c.requested_by ?? '—'}</td>
                <td><SxChip compact tone={commandTone(c.status)} running={c.status === 'RUNNING'}>{c.status}</SxChip></td>
                <td className="text-end">
                  {c.status === 'QUEUED' && <SxButton sm icon="bi-x" onClick={() => onCancel(c.command_id)} title="Cancel" />}
                  {c.result_text && (
                    <SxButton sm icon={openId === c.command_id ? 'bi-chevron-up' : 'bi-card-text'}
                      onClick={() => setOpenId(openId === c.command_id ? null : c.command_id)} title="Output" />
                  )}
                </td>
              </tr>
              {openId === c.command_id && (
                <tr><td colSpan={6}><pre className="dc-output">{c.result_text}</pre></td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </SxTable>
    </div>
  )
}

function BulkBar({
  deviceIds, packages, onDone,
}: { deviceIds: string[]; packages: Partial<Record<string, DcPackage[]>>; onDone: (text: string, tone: Tone) => void }) {
  const [app, setApp] = useState<DcAppKey>('store_agent')
  const [action, setAction] = useState('restart')
  const [version, setVersion] = useState('')
  const [busy, setBusy] = useState(false)
  const versions = packages[app] ?? []

  useEffect(() => {
    if (!APP_ACTIONS[app].includes(action)) setAction(APP_ACTIONS[app][0])
  }, [app, action])
  useEffect(() => { setVersion(versions[0]?.version ?? '') }, [app]) // eslint-disable-line react-hooks/exhaustive-deps

  const go = async () => {
    let args: Record<string, unknown> = {}
    if (action === 'update') {
      if (!version) return
      args = { version }
    }
    if (action === 'pause') {
      const minutes = window.prompt('Pause for how many minutes?', '30')
      if (minutes === null) return
      args = { minutes: Number(minutes) || 30 }
    }
    if (!window.confirm(`${action} ${APP_LABEL[app]} on ${deviceIds.length} PC(s)?`)) return
    setBusy(true)
    try {
      const { results } = await dc.bulkCommand(deviceIds, app, action, args)
      const failed = results.filter((r) => !r.ok)
      onDone(failed.length
        ? `${results.length - failed.length} queued, ${failed.length} failed: ${failed.map((f) => f.error).join('; ')}`
        : `${action} queued for ${results.length} PC(s).`, failed.length ? 'warning' : 'success')
    } catch (e) {
      onDone((e as Error).message, 'danger')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="dc-bulk">
      <span><b>{deviceIds.length}</b> selected</span>
      <SxSelect value={app} onChange={(v) => setApp(v as DcAppKey)} ariaLabel="App">
        {APP_ORDER.map((k) => <option key={k} value={k}>{APP_LABEL[k]}</option>)}
      </SxSelect>
      <SxSelect value={action} onChange={setAction} ariaLabel="Action">
        {APP_ACTIONS[app].map((a) => <option key={a} value={a}>{ACTION_LABEL[a] ?? a}</option>)}
      </SxSelect>
      {action === 'update' && (
        <SxSelect value={version} onChange={setVersion} ariaLabel="Version">
          {versions.length === 0 && <option value="">no packages</option>}
          {versions.map((p) => <option key={p.version} value={p.version}>{p.version}</option>)}
        </SxSelect>
      )}
      <SxButton sm variant="primary" icon="bi-send" busy={busy} onClick={() => void go()}>Run</SxButton>
    </div>
  )
}

function EnrollPanel({ onClose }: { onClose: () => void }) {
  const codesQuery = useAsyncData(() => dc.enrollCodes())
  const [note, setNote] = useState('')
  const [hours, setHours] = useState('24')
  const [uses, setUses] = useState('1')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const hoUrl = window.location.origin

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      await dc.createEnrollCode(note, Number(hours) || 24, Number(uses) || 1)
      setNote('')
      void codesQuery.reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const codes = codesQuery.data?.codes ?? []
  return (
    <div className="dc-enroll">
      <div className="dc-enroll__head">
        <b>Enroll a PC</b>
        <button type="button" className="dc-banner__close" onClick={onClose} aria-label="Close">×</button>
      </div>
      <p className="dc-muted">
        PCs with the Stock Client enroll themselves when a user signs in. For an HO node or a Store-Agent-only PC,
        create a code and run this once in an elevated prompt on that PC:
      </p>
      <div className="dc-enroll__form">
        <input className="form-control form-control-sm" placeholder="Note (e.g. NMS billing PC)" value={note} onChange={(e) => setNote(e.target.value)} />
        <input className="form-control form-control-sm" type="number" min={1} value={hours} onChange={(e) => setHours(e.target.value)} title="Valid for (hours)" />
        <input className="form-control form-control-sm" type="number" min={1} value={uses} onChange={(e) => setUses(e.target.value)} title="How many PCs may use it" />
        <SxButton sm variant="primary" icon="bi-plus" busy={busy} onClick={() => void create()}>Create code</SxButton>
      </div>
      {error && <div className="dc-banner dc-banner--danger">{error}</div>}
      {codes.filter((c) => c.usable).slice(0, 5).map((c) => (
        <div key={c.code} className="dc-enroll__code">
          <div><b className="dc-code">{c.code}</b> <span className="dc-muted">{c.note} · {c.use_count}/{c.max_uses} used · expires {fmt(c.expires_at)}</span></div>
          <pre className="dc-output">{`NexoraDeviceController.exe setup --ho ${hoUrl} --code ${c.code}`}</pre>
        </div>
      ))}
    </div>
  )
}
