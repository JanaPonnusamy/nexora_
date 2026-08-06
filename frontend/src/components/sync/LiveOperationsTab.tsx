import { useEffect, useState } from 'react'
import type { LiveStore } from '../../types/sync'
import { syncService } from '../../services/syncService'
import { SyncStatusBadge } from './SyncBadges'
import { SxCard, SxCardHead, SxCardBody, SxChip, SxButton, SxLive, SxTable } from './ui'

function fmtEta(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return '—'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

export function LiveOperationsTab() {
  const [live, setLive] = useState<LiveStore[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    const tick = async () => {
      try {
        const rows = await syncService.live()
        if (!active) return
        setLive(rows)
        setLoaded(true)
      } catch { /* keep last good state */ }
    }
    void tick()
    const id = setInterval(tick, 2000)
    return () => { active = false; clearInterval(id) }
  }, [])

  const allSelected = live.length > 0 && live.every((l) => selected.has(l.store_id))
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(live.map((l) => l.store_id)))
  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })

  async function control(action: 'PAUSE' | 'STOP') {
    if (selected.size === 0) return
    setBusy(true)
    try {
      await syncService.control([...selected], action)
      setSelected(new Set())
    } finally { setBusy(false) }
  }

  return (
    <SxCard className="sx-pane">
      <SxCardHead title="Live Operations" icon="bi-broadcast-pin"
        sub={<SxChip tone="indigo" running dot compact>{live.length} active</SxChip>}
        action={
          <div className="d-flex align-items-center gap-2">
            <SxLive label="2s" />
            <SxButton sm variant="warning" icon="bi-pause-fill" disabled={busy || selected.size === 0} onClick={() => control('PAUSE')}>Pause</SxButton>
            <SxButton sm variant="danger" icon="bi-stop-fill" disabled={busy || selected.size === 0} onClick={() => control('STOP')}>Stop</SxButton>
          </div>
        } />
      <SxCardBody flush>
        <SxTable>
          <thead>
            <tr>
              <th><input type="checkbox" className="form-check-input" checked={allSelected} onChange={toggleAll} aria-label="Select all" /></th>
              <th>Store</th><th>Current Table</th>
              <th className="sx-num">Changed</th><th className="sx-num">Uploaded</th>
              <th className="sx-num">Inserted</th><th className="sx-num">Updated</th>
              <th>Chunk</th><th className="sx-num">Speed</th><th>ETA</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {live.length === 0 ? (
              <tr><td colSpan={11} className="sx-table__empty">{loaded ? 'No active syncs right now.' : 'Loading…'}</td></tr>
            ) : live.map((l) => (
              <tr key={l.execution_id}>
                <td><input type="checkbox" className="form-check-input" checked={selected.has(l.store_id)} onChange={() => toggleOne(l.store_id)} aria-label={`Select ${l.store_code}`} /></td>
                <td>
                  <span className={`sx-sdot sx-sdot--${l.status === 'PAUSED' ? 'paused' : 'running'}`} />
                  <span className="sx-rowlabel d-inline-flex align-middle">
                    <span className="sx-rowlabel__main">{l.store_code}</span>
                    <span className="sx-rowlabel__sub">{l.store_name}</span>
                  </span>
                </td>
                <td className="sx-strong">{l.current_table ?? '—'}</td>
                <td className="sx-num">{l.rows_changed.toLocaleString()}</td>
                <td className="sx-num">{l.rows_uploaded.toLocaleString()}</td>
                <td className="sx-num" style={{ color: 'var(--sx-success)' }}>{l.rows_inserted.toLocaleString()}</td>
                <td className="sx-num" style={{ color: 'var(--sx-accent)' }}>{l.rows_updated.toLocaleString()}</td>
                <td>{l.chunk_no != null ? `${l.chunk_no}${l.total_chunks ? ` / ${l.total_chunks}` : ''}` : '—'}</td>
                <td className="sx-num">{l.speed_rows_sec > 0 ? <span style={{ color: 'var(--sx-success)', fontWeight: 650 }}>{l.speed_rows_sec.toLocaleString()}/s</span> : '—'}</td>
                <td>{fmtEta(l.eta_seconds)}</td>
                <td><SyncStatusBadge status={l.status === 'PAUSED' ? 'QUEUED' : 'Syncing'} compact /></td>
              </tr>
            ))}
          </tbody>
        </SxTable>
      </SxCardBody>
    </SxCard>
  )
}
