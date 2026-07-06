import { useEffect, useState } from 'react'
import type { TableStat } from '../../types/sync'
import { syncService } from '../../services/syncService'
import { formatDateTime } from '../../utils/format'
import { SyncTypeBadge } from './SyncBadges'
import { SxCard, SxCardHead, SxCardBody, SxStat, SxLive, SxTable } from './ui'

export function TableStatisticsTab() {
  const [stats, setStats] = useState<TableStat[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    const tick = async () => {
      try {
        const rows = await syncService.tableStats()
        if (!active) return
        setStats(rows)
        setLoaded(true)
      } catch { /* keep last good state */ }
    }
    void tick()
    const id = setInterval(tick, 5000)
    return () => { active = false; clearInterval(id) }
  }, [])

  const totals = stats.reduce(
    (a, s) => ({
      ho: a.ho + s.ho_rows,
      changed: a.changed + s.changed_today,
      uploaded: a.uploaded + s.uploaded_today,
      updated: a.updated + s.updated_today,
    }),
    { ho: 0, changed: 0, uploaded: 0, updated: 0 },
  )

  return (
    <div className="sx-stack">
      <div className="row row-cols-2 row-cols-md-4 g-3">
        <div className="col"><SxStat icon="bi-database" tone="info" value={totals.ho.toLocaleString()} label="HO Rows" /></div>
        <div className="col"><SxStat icon="bi-arrow-repeat" tone="violet" value={totals.changed.toLocaleString()} label="Changed Today" /></div>
        <div className="col"><SxStat icon="bi-cloud-upload" tone="success" value={totals.uploaded.toLocaleString()} label="Uploaded Today" /></div>
        <div className="col"><SxStat icon="bi-pencil-square" tone="indigo" value={totals.updated.toLocaleString()} label="Updated Today" /></div>
      </div>

      <SxCard>
        <SxCardHead title="Table Statistics" icon="bi-bar-chart-line"
          sub={`${stats.length} tables`} action={<SxLive label="5s" />} />
        <SxCardBody flush>
          <SxTable>
            <thead>
              <tr>
                <th>Table</th><th>Mode</th>
                <th className="sx-num">Source</th><th className="sx-num">HO</th>
                <th className="sx-num">Changed</th><th className="sx-num">Uploaded</th>
                <th className="sx-num">Inserted</th><th className="sx-num">Updated</th>
                <th className="sx-num">Skipped</th><th>Last Sync</th>
              </tr>
            </thead>
            <tbody>
              {stats.length === 0 ? (
                <tr><td colSpan={10} className="sx-table__empty">{loaded ? 'No tables configured.' : 'Loading…'}</td></tr>
              ) : stats.map((s) => (
                <tr key={s.table_name}>
                  <td className="sx-strong">{s.table_name}</td>
                  <td><SyncTypeBadge value={s.sync_mode} /></td>
                  <td className="sx-num">{s.source_rows != null ? s.source_rows.toLocaleString() : '—'}</td>
                  <td className="sx-num sx-strong">{s.ho_rows.toLocaleString()}</td>
                  <td className="sx-num">{s.changed_today.toLocaleString()}</td>
                  <td className="sx-num">{s.uploaded_today.toLocaleString()}</td>
                  <td className="sx-num" style={{ color: 'var(--sx-success)' }}>{s.inserted_today.toLocaleString()}</td>
                  <td className="sx-num" style={{ color: 'var(--sx-accent)' }}>{s.updated_today.toLocaleString()}</td>
                  <td className="sx-num sx-dim">{s.skipped_today.toLocaleString()}</td>
                  <td className="sx-dim" style={{ fontSize: '0.8rem' }}>{formatDateTime(s.last_sync)}</td>
                </tr>
              ))}
            </tbody>
          </SxTable>
        </SxCardBody>
      </SxCard>
    </div>
  )
}
