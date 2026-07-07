import { useCallback, useEffect, useRef, useState } from 'react'
import type { TableStat } from '../../types/sync'
import { syncService } from '../../services/syncService'
import { formatDateTime } from '../../utils/format'
import { SyncTypeBadge } from './SyncBadges'
import { SxCard, SxCardHead, SxCardBody, SxStat, SxLive, SxTable, SxButton } from './ui'

export function TableStatisticsTab() {
  const [stats, setStats] = useState<TableStat[]>([])
  const [loaded, setLoaded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [live, setLive] = useState(true)
  const activeRef = useRef(true)

  const tick = useCallback(async () => {
    try {
      setRefreshing(true)
      const rows = await syncService.tableStats()
      if (!activeRef.current) return
      setStats(rows)
      setLoaded(true)
    } catch { /* keep last good state */ } finally {
      if (activeRef.current) setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    activeRef.current = true
    void tick()
    if (!live) return () => { activeRef.current = false }
    const id = setInterval(tick, 5000)
    return () => { activeRef.current = false; clearInterval(id) }
  }, [tick, live])

  const totals = stats.reduce(
    (a, s) => ({
      ho: a.ho + s.ho_rows,
      changed: a.changed + s.changed_today,
      uploaded: a.uploaded + s.uploaded_today,
      updated: a.updated + s.updated_today,
    }),
    { ho: 0, changed: 0, uploaded: 0, updated: 0 },
  )

  // Most recent sync across every configured table.
  const lastSyncOverall = stats.reduce<string | null>(
    (max, s) => (s.last_sync && (!max || s.last_sync > max) ? s.last_sync : max),
    null,
  )
  const trackedTables = stats.filter((s) => s.watermark_column).length

  return (
    <div className="sx-stack">
      <div className="row row-cols-2 row-cols-md-3 row-cols-xl-5 g-3">
        <div className="col"><SxStat icon="bi-database" tone="info" value={totals.ho.toLocaleString()} label="HO Rows" /></div>
        <div className="col"><SxStat icon="bi-arrow-repeat" tone="violet" value={totals.changed.toLocaleString()} label="Changed Today" /></div>
        <div className="col"><SxStat icon="bi-cloud-upload" tone="success" value={totals.uploaded.toLocaleString()} label="Uploaded Today" /></div>
        <div className="col"><SxStat icon="bi-pencil-square" tone="indigo" value={totals.updated.toLocaleString()} label="Updated Today" /></div>
        <div className="col">
          <SxStat icon="bi-clock-history" tone="teal"
            value={lastSyncOverall ? formatDateTime(lastSyncOverall) : '—'}
            label="Last Sync" sub={`${trackedTables} tracked table${trackedTables === 1 ? '' : 's'}`} />
        </div>
      </div>

      <SxCard>
        <SxCardHead title="Last Sync & Business Details" icon="bi-bar-chart-line"
          sub={`${stats.length} tables`}
          action={
            <div className="d-flex align-items-center gap-2">
              {live && <SxLive label="5s" />}
              <SxButton sm variant={live ? 'warning' : 'ghost'}
                icon={live ? 'bi-pause-fill' : 'bi-play-fill'}
                onClick={() => setLive((v) => !v)}>
                {live ? 'Pause' : 'Live'}
              </SxButton>
              <SxButton sm variant="primary" icon="bi-arrow-clockwise"
                busy={refreshing} onClick={() => void tick()}>
                Refresh
              </SxButton>
            </div>
          } />
        <SxCardBody flush>
          <SxTable>
            <thead>
              <tr>
                <th>Table</th><th>Mode</th>
                <th className="sx-num">Source</th><th className="sx-num">HO</th>
                <th className="sx-num">Changed</th><th className="sx-num">Uploaded</th>
                <th className="sx-num">Inserted</th><th className="sx-num">Updated</th>
                <th className="sx-num">Skipped</th><th>Last Sync</th>
                <th>Last Trans Business Value</th>
              </tr>
            </thead>
            <tbody>
              {stats.length === 0 ? (
                <tr><td colSpan={11} className="sx-table__empty">{loaded ? 'No tables configured.' : 'Loading…'}</td></tr>
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
                  <td>
                    {s.watermark_column ? (
                      <>
                        <div className="sx-strong" style={{ fontSize: '0.85rem' }}>
                          {s.last_business_value ?? '—'}
                        </div>
                        <div className="sx-dim" style={{ fontSize: '0.72rem' }}>
                          <i className="bi bi-water" aria-hidden="true" /> {s.watermark_column}
                        </div>
                      </>
                    ) : <span className="sx-dim">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </SxTable>
        </SxCardBody>
      </SxCard>
    </div>
  )
}
