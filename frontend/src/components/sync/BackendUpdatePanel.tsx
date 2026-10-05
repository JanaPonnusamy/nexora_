import { useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { hoOpsService } from '../../services/hoOpsService'
import type { HoNodeStatus } from '../../types/hoOps'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { formatDateTime } from '../../utils/format'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxTable, type Tone } from './ui'

const nodeKey = (n: HoNodeStatus) => (n.is_self ? 'self' : n.url ?? '')
const xs: React.CSSProperties = { fontSize: 11, color: 'var(--sx-dim, #8a94a6)' }
const rowGap: React.CSSProperties = { display: 'flex', gap: 8, alignItems: 'center' }

function versionTone(n: HoNodeStatus): Tone {
  if (!n.reachable) return 'danger'
  if (n.up_to_date === true) return 'success'
  if (n.behind_main && n.behind_main > 0) return 'warning'
  return 'muted'
}

function versionLabel(n: HoNodeStatus): string {
  if (!n.reachable) return 'UNREACHABLE'
  if (n.up_to_date === true) return 'UP TO DATE'
  if (n.behind_main && n.behind_main > 0) return `${n.behind_main} BEHIND`
  return 'UNKNOWN'
}

// Remote HO backend updates: show every HO node's running code version and
// trigger a git-pull + reinstall + restart from here. Self-update is detached
// server-side so a node survives restarting itself.
export function BackendUpdatePanel() {
  const nodesQuery = useAsyncData(() => hoOpsService.nodes())
  const [busy, setBusy] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<HoNodeStatus | null>(null)
  const [flash, setFlash] = useState<string | null>(null)

  const nodes = nodesQuery.data?.nodes ?? []
  const outOfDate = nodes.filter(
    (n) => n.reachable && n.can_self_update && !!n.behind_main && n.behind_main > 0,
  )

  async function runUpdate(targets: HoNodeStatus[]) {
    if (!targets.length) return
    setBusy(targets.length === 1 ? nodeKey(targets[0]) : 'all')
    setFlash(null)
    try {
      const res = await hoOpsService.update(
        targets.map((t) => ({ url: t.is_self ? null : t.url, is_self: t.is_self })),
      )
      const ok = res.results.filter((r) => r.ok).length
      const failed = res.results.filter((r) => !r.ok)
      setFlash(
        `Update triggered on ${ok} node${ok === 1 ? '' : 's'}. ` +
          (failed.length ? `Failed: ${failed.map((f) => f.url ?? 'this node').join(', ')}. ` : '') +
          'Nodes restart shortly — refresh in ~30–60s.',
      )
      setConfirm(null)
      setTimeout(() => nodesQuery.reload(), 8000)
    } catch (e) {
      setFlash(`Update failed: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  if (nodesQuery.isLoading && !nodesQuery.data) return <TableSkeleton rows={3} />
  if (nodesQuery.error && !nodesQuery.data) {
    return <ErrorState title="Nodes unavailable" description={nodesQuery.error ?? 'Failed to load HO nodes'} onRetry={nodesQuery.reload} />
  }

  return (
    <div className="sx-stack">
      <SxCard>
        <SxCardHead
          title="HO Backend Nodes"
          sub="Running code version per node, and remote git-pull + restart."
          action={
            <div style={rowGap}>
              <SxButton variant="ghost" onClick={() => nodesQuery.reload()} disabled={!!busy}>
                Refresh
              </SxButton>
              <SxButton
                variant="primary"
                disabled={!!busy || outOfDate.length === 0}
                busy={busy === 'all'}
                onClick={() => runUpdate(outOfDate)}
              >
                {`Update all out-of-date (${outOfDate.length})`}
              </SxButton>
            </div>
          }
        />
        <SxCardBody>
          {flash && (
            <div
              style={{
                marginBottom: 12,
                padding: '8px 12px',
                borderRadius: 8,
                background: 'rgba(79,120,255,0.12)',
                fontSize: 13,
              }}
            >
              {flash}
            </div>
          )}
          <SxTable>
            <thead>
              <tr>
                <th>Node</th>
                <th>Host</th>
                <th>Branch</th>
                <th>Running commit</th>
                <th>Fleet routes</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((n) => (
                <tr key={nodeKey(n)}>
                  <td>
                    {n.is_self ? <SxChip tone="indigo">This node</SxChip> : n.label || n.url}
                    {!n.is_self && n.label && <div style={xs}>{n.url}</div>}
                  </td>
                  <td>{n.hostname ?? '—'}</td>
                  <td>{n.branch ?? '—'}</td>
                  <td>
                    {n.head ? (
                      <>
                        <code>{n.head}</code>
                        {n.subject && <div style={xs} title={n.subject}>{n.subject.slice(0, 48)}</div>}
                        {n.committed_at && <div style={xs}>{formatDateTime(n.committed_at)}</div>}
                      </>
                    ) : n.error ? (
                      <span style={xs}>{n.error.slice(0, 40)}</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{n.reachable ? n.fleet_routes ?? 0 : '—'}</td>
                  <td>
                    <div style={rowGap}>
                      <SxChip tone={versionTone(n)}>{versionLabel(n)}</SxChip>
                      {n.dirty && <SxChip tone="warning">local edits</SxChip>}
                    </div>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <SxButton
                      variant="ghost"
                      disabled={!!busy || !n.reachable || !n.can_self_update}
                      busy={busy === nodeKey(n)}
                      title={
                        !n.can_self_update
                          ? 'This node cannot self-update (not a Windows git checkout, or deploy script missing)'
                          : undefined
                      }
                      onClick={() => setConfirm(n)}
                    >
                      Update
                    </SxButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </SxTable>
        </SxCardBody>
      </SxCard>

      {confirm && (
        <SxCard>
          <SxCardHead title="Confirm backend update" />
          <SxCardBody>
            <p>
              Pull <code>origin/main</code>, reinstall dependencies, and restart the backend on{' '}
              <strong>{confirm.is_self ? 'this node' : confirm.label || confirm.url}</strong>
              {confirm.hostname ? ` (${confirm.hostname})` : ''}?
            </p>
            <p style={xs}>
              The backend will be briefly unavailable (~20–40s) while it restarts.
              {confirm.behind_main != null && confirm.behind_main > 0
                ? ` This node is ${confirm.behind_main} commit(s) behind main.`
                : ' This node is already up to date — updating will simply restart it.'}
            </p>
            <div style={{ ...rowGap, marginTop: 12 }}>
              <SxButton variant="primary" busy={!!busy} disabled={!!busy} onClick={() => runUpdate([confirm])}>
                Update now
              </SxButton>
              <SxButton variant="ghost" disabled={!!busy} onClick={() => setConfirm(null)}>
                Cancel
              </SxButton>
            </div>
          </SxCardBody>
        </SxCard>
      )}
    </div>
  )
}
