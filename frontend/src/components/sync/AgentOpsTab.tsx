import { useEffect, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { agentOpsService } from '../../services/agentOpsService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { formatDateTime } from '../../utils/format'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxSelect, SxTable } from './ui'

// Remote start/stop/update for the store agent, via the watchdog service
// installed alongside NexoraStoreAgent on each store PC. "Desired" is what HO
// wants; the watchdog polls /agent/watchdog/state and reconciles reality to
// match within one cycle (60s) - it is NOT instantaneous like a local sc stop.
export function AgentOpsTab() {
  const storesQuery = useAsyncData(() => agentOpsService.list())
  const releasesQuery = useAsyncData(() => agentOpsService.releases())
  const logsQuery = useAsyncData(() => agentOpsService.logs())
  const [busyStoreId, setBusyStoreId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkBusy, setBulkBusy] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState('')

  useEffect(() => {
    if (selectedVersion || !releasesQuery.data?.length) return
    const current = releasesQuery.data.find((row) => row.is_current) ?? releasesQuery.data[0]
    setSelectedVersion(current.version)
  }, [releasesQuery.data, selectedVersion])

  const coreUnavailable = [storesQuery.error, releasesQuery.error, logsQuery.error]
    .some((message) => /internal server error|request failed|not found/i.test(message ?? ''))

  if (storesQuery.isLoading || releasesQuery.isLoading || logsQuery.isLoading) {
    return <TableSkeleton rows={5} columns={8} />
  }
  if (coreUnavailable) {
    return (
      <EmptyState
        icon="bi-router"
        title="Agent Ops not available"
        description="This HO does not have Agent Ops configured yet, or the backend module is not ready. Sync can still run normally without it."
        action={{ label: 'Try again', icon: 'bi-arrow-clockwise', onClick: () => { void storesQuery.reload(); void releasesQuery.reload(); void logsQuery.reload() } }}
      />
    )
  }
  if (storesQuery.error || !storesQuery.data) {
    return <ErrorState title="Agent Ops unavailable" description={storesQuery.error ?? 'Failed to load agent status'} onRetry={storesQuery.reload} />
  }
  if (releasesQuery.error || !releasesQuery.data) {
    return <ErrorState title="Agent Ops unavailable" description={releasesQuery.error ?? 'Failed to load releases'} onRetry={releasesQuery.reload} />
  }
  if (logsQuery.error || !logsQuery.data) {
    return <ErrorState title="Agent Ops unavailable" description={logsQuery.error ?? 'Failed to load agent logs'} onRetry={logsQuery.reload} />
  }

  const rows = storesQuery.data
  const releases = releasesQuery.data
  const logs = logsQuery.data
  const currentRelease = releases.find((row) => row.is_current) ?? null
  const watchdogsSeen = rows.filter((row) => row.watchdog_last_heartbeat).length

  const refreshAll = async () => {
    await Promise.all([storesQuery.reload(), logsQuery.reload(), releasesQuery.reload()])
  }

  const toggleSelected = (storeId: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(storeId)) next.delete(storeId)
      else next.add(storeId)
      return next
    })
  }

  const setOne = async (storeId: string, state: 'RUNNING' | 'STOPPED') => {
    setBusyStoreId(storeId)
    try {
      await agentOpsService.setState(storeId, state)
      await Promise.all([storesQuery.reload(), logsQuery.reload()])
    } finally {
      setBusyStoreId(null)
    }
  }

  const setBulk = async (state: 'RUNNING' | 'STOPPED') => {
    if (selected.size === 0) return
    setBulkBusy(true)
    try {
      await agentOpsService.setStateBulk(Array.from(selected), state)
      await Promise.all([storesQuery.reload(), logsQuery.reload()])
    } finally {
      setBulkBusy(false)
    }
  }

  const pushVersion = async (desiredVersion: string | null) => {
    if (selected.size === 0) return
    setBulkBusy(true)
    try {
      await agentOpsService.setVersionBulk(Array.from(selected), desiredVersion)
      await Promise.all([storesQuery.reload(), logsQuery.reload()])
    } finally {
      setBulkBusy(false)
    }
  }

  return (
    <div className="sx-stack">
      <SxCard className="sx-pane">
        <SxCardHead
          title="Agent Remote Control"
          icon="bi-router"
          sub={`${rows.length} stores · ${watchdogsSeen} watchdog${watchdogsSeen === 1 ? '' : 's'} reporting`}
          action={<SxButton sm variant="ghost" icon="bi-arrow-clockwise" onClick={() => void refreshAll()}>Refresh</SxButton>}
        />
        <SxCardBody>
          <p className="sx-dim small mb-3">
            <i className="bi bi-info-circle me-1" aria-hidden="true" />
            Start, stop, and version changes apply on the store&apos;s next watchdog cycle, usually within about 60 seconds.
            Stores without the watchdog installed will stay visible but won&apos;t react until the new installer is deployed there.
          </p>
          <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
            <span className="sx-dim small">Current release</span>
            <SxChip tone="indigo" compact>{currentRelease?.version ?? 'none'}</SxChip>
            <SxSelect value={selectedVersion} onChange={setSelectedVersion} ariaLabel="Select agent release">
              {releases.map((release) => (
                <option key={release.version} value={release.version}>
                  {release.version}{release.is_current ? ' (current)' : ''}
                </option>
              ))}
            </SxSelect>
            <span className="sx-dim small">
              {currentRelease?.notes || 'Select a release to pin selected stores, or clear pins so they follow the current release.'}
            </span>
          </div>
          {selected.size > 0 && (
            <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
              <span className="sx-dim small">{selected.size} selected</span>
              <SxButton sm variant="danger" icon="bi-stop-circle" busy={bulkBusy} onClick={() => void setBulk('STOPPED')}>
                Stop selected
              </SxButton>
              <SxButton sm variant="primary" icon="bi-play-circle" busy={bulkBusy} onClick={() => void setBulk('RUNNING')}>
                Start selected
              </SxButton>
              <SxButton sm variant="warning" icon="bi-arrow-repeat" busy={bulkBusy} onClick={() => void pushVersion(selectedVersion || null)}>
                Push release
              </SxButton>
              <SxButton sm variant="ghost" icon="bi-stars" busy={bulkBusy} onClick={() => void pushVersion(null)}>
                Follow current
              </SxButton>
            </div>
          )}
        </SxCardBody>
        <SxCardBody flush>
          {rows.length === 0 ? (
            <EmptyState icon="bi-router" title="No stores" description="Active stores will appear here." />
          ) : (
            <SxTable>
              <thead>
                <tr>
                  <th style={{ width: 32 }} />
                  <th>Store</th>
                  <th>Installed</th>
                  <th>Target</th>
                  <th>Watchdog</th>
                  <th>Desired State</th>
                  <th>Last Action</th>
                  <th className="sx-num">Controls</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const hasWatchdog = Boolean(row.watchdog_last_heartbeat)
                  return (
                    <tr key={row.store_id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selected.has(row.store_id)}
                          onChange={() => toggleSelected(row.store_id)}
                          aria-label={`Select ${row.store_code}`}
                        />
                      </td>
                      <td>
                        <div className="sx-rowlabel">
                          <span className="sx-rowlabel__main">{row.store_code}</span>
                          <span className="sx-rowlabel__sub">{row.store_name}</span>
                        </div>
                      </td>
                      <td className="sx-dim" style={{ fontSize: '0.82rem' }}>
                        {row.installed_agent_version ?? row.agent_version ?? '—'}
                      </td>
                      <td className="sx-dim" style={{ fontSize: '0.82rem' }}>
                        {row.desired_version ?? 'Follow current'}
                      </td>
                      <td>
                        {hasWatchdog ? (
                          <span className="sx-dim" style={{ fontSize: '0.82rem' }}>
                            {row.service_state ?? 'unknown'} · {formatDateTime(row.watchdog_last_heartbeat)}
                          </span>
                        ) : (
                          <span className="sx-dim">— not installed —</span>
                        )}
                      </td>
                      <td>
                        <SxChip tone={row.desired_state === 'RUNNING' ? 'success' : 'muted'}>
                          {row.desired_state}
                        </SxChip>
                      </td>
                      <td className="sx-dim" style={{ fontSize: '0.78rem', maxWidth: 220 }}>
                        {row.last_action ?? '—'}
                      </td>
                      <td className="sx-num">
                        <div className="d-flex gap-1 justify-content-end">
                          <SxButton
                            sm
                            variant="danger"
                            icon="bi-stop-circle"
                            busy={busyStoreId === row.store_id}
                            disabled={row.desired_state === 'STOPPED'}
                            onClick={() => void setOne(row.store_id, 'STOPPED')}
                          >
                            Stop
                          </SxButton>
                          <SxButton
                            sm
                            variant="primary"
                            icon="bi-play-circle"
                            busy={busyStoreId === row.store_id}
                            disabled={row.desired_state === 'RUNNING'}
                            onClick={() => void setOne(row.store_id, 'RUNNING')}
                          >
                            Start
                          </SxButton>
                          <SxButton
                            sm
                            variant="warning"
                            icon="bi-arrow-repeat"
                            busy={busyStoreId === row.store_id}
                            disabled={!selectedVersion}
                            onClick={async () => {
                              setBusyStoreId(row.store_id)
                              try {
                                await agentOpsService.setVersion(row.store_id, selectedVersion || null)
                                await Promise.all([storesQuery.reload(), logsQuery.reload()])
                              } finally {
                                setBusyStoreId(null)
                              }
                            }}
                          >
                            Update
                          </SxButton>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </SxTable>
          )}
        </SxCardBody>
      </SxCard>

      <SxCard className="sx-pane">
        <SxCardHead
          title="Recent Agent Activity"
          icon="bi-journal-text"
          sub="Desired-state changes, version targets, and watchdog-applied updates"
          action={<SxButton sm variant="ghost" icon="bi-arrow-clockwise" onClick={() => void logsQuery.reload()}>Refresh</SxButton>}
        />
        <SxCardBody flush>
          {logs.length === 0 ? (
            <EmptyState icon="bi-journal-text" title="No agent activity yet" description="Version pushes and watchdog actions will appear here." />
          ) : (
            <SxTable>
              <thead>
                <tr>
                  <th>Store</th>
                  <th>Event</th>
                  <th>Detail</th>
                  <th>Version</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((row) => (
                  <tr key={row.audit_id}>
                    <td>
                      <div className="sx-rowlabel">
                        <span className="sx-rowlabel__main">{row.store_code ?? '—'}</span>
                        <span className="sx-rowlabel__sub">{row.store_name ?? 'Unknown store'}</span>
                      </div>
                    </td>
                    <td><SxChip tone="teal">{row.event_type}</SxChip></td>
                    <td className="sx-dim">{row.detail ?? '—'}</td>
                    <td className="sx-dim">{row.target_version ?? '—'}</td>
                    <td className="sx-dim">{formatDateTime(row.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          )}
        </SxCardBody>
      </SxCard>
    </div>
  )
}
