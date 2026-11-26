import { useRef, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { legacyOrderService, type OrderCacheMonitorRow } from '../../services/legacyOrderService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { formatDateTime } from '../../utils/format'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxTable, type Tone } from './ui'

const connectionTone = (status?: string): Tone => (status === 'ok' ? 'success' : 'danger')
const writebackTone = (status?: string | null): Tone =>
  status === 'ok' ? 'success' : status === 'failed' ? 'danger' : 'muted'

function ageLabel(seconds?: number) {
  if (seconds === undefined || seconds === null) return '—'
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

// Order cache monitor (Sync > Order Cache Monitor): one row per store's local
// SQLite order cache -- file age, last write-back status/time, how many
// order_lines rows have a local edit not yet synced (updated_at > synced_at),
// and connection status. Force actions (pull/push/export/send/import) all
// reuse the same backend endpoints the automatic Order Process path uses, so
// there is one behavior whether a drain happens automatically or by hand.
export function OrderCacheMonitor() {
  const monitorQuery = useAsyncData(() => legacyOrderService.orderCacheMonitorAll())
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [importTarget, setImportTarget] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const rows: OrderCacheMonitorRow[] = monitorQuery.data?.stores ?? []

  async function withBusy(key: string, fn: () => Promise<string>) {
    setBusy(key)
    setMessage(null)
    setError(null)
    try {
      setMessage(await fn())
      await monitorQuery.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(null)
    }
  }

  const forcePull = (storeName: string) =>
    withBusy(`pull:${storeName}`, async () => {
      await legacyOrderService.orderCacheForcePull(storeName)
      return `${storeName}: cache rebuilt from central.`
    })

  const forcePush = (storeName: string) =>
    withBusy(`push:${storeName}`, async () => {
      const result = await legacyOrderService.orderCacheForcePush(storeName)
      if (!result.ok) throw new Error(result.error || 'Write-back did not drain.')
      return `${storeName}: ${result.applied} edit(s) pushed to HO.`
    })

  const exportFile = (storeName: string) =>
    withBusy(`export:${storeName}`, async () => {
      const blob = await legacyOrderService.orderCacheExport(storeName)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `order_cache_${storeName}.sqlite`
      link.click()
      URL.revokeObjectURL(url)
      return `${storeName}: cache file downloaded.`
    })

  const sendFile = (storeName: string, channel: 'whatsapp' | 'email') =>
    withBusy(`send:${storeName}`, async () => {
      const result = await legacyOrderService.orderCacheSend(storeName, channel)
      if (!result.ok) throw new Error(result.error || `Send via ${channel} failed.`)
      return `${storeName}: cache file sent via ${channel}.`
    })

  function openImportPicker(storeName: string) {
    setImportTarget(storeName)
    fileInputRef.current?.click()
  }

  async function onImportFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !importTarget) return
    const storeName = importTarget
    setImportTarget(null)
    await withBusy(`import:${storeName}`, async () => {
      const result = await legacyOrderService.orderCacheImport(storeName, file)
      if (!result.writeback.ok) throw new Error(result.writeback.error || 'Imported, but write-back did not drain.')
      return `${storeName}: imported and ${result.writeback.applied} edit(s) pushed to HO.`
    })
  }

  if (monitorQuery.isLoading) return <TableSkeleton rows={6} columns={7} />
  if (monitorQuery.error) {
    return (
      <ErrorState
        icon="bi-exclamation-triangle"
        title="Could not load order cache status"
        description={monitorQuery.error}
        action={{ label: 'Try again', icon: 'bi-arrow-clockwise', onClick: () => { void monitorQuery.reload() } }}
      />
    )
  }
  if (!rows.length) {
    return (
      <EmptyState
        icon="bi-sd-card"
        title="No active stores"
        description="No active stores were found, or the local order cache feature is disabled (LEGACY_ORDER_CACHE_ENABLED)."
      />
    )
  }

  return (
    <SxCard>
      <SxCardHead
        title="Order Cache Monitor"
        icon="bi-sd-card"
        sub={<span className="sx-card__sub">Per-store local SQLite order cache: file age, last write-back, unsynced rows</span>}
      />
      <SxCardBody flush>
        <input ref={fileInputRef} type="file" accept=".sqlite,.db" hidden onChange={(e) => { void onImportFileChosen(e) }} />
        {message && <div className="alert alert-success py-2 px-3 mb-0" role="alert">{message}</div>}
        {error && <div className="alert alert-danger py-2 px-3 mb-0" role="alert">{error}</div>}
        <SxTable>
          <thead>
            <tr>
              <th>Store</th>
              <th>File created</th>
              <th>Rows</th>
              <th>Unsynced</th>
              <th>Last write-back</th>
              <th>Connection</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.store_name}>
                <td className="fw-semibold">{row.store_name}</td>
                <td>
                  {row.exists
                    ? <span title={row.file_created_at}>{ageLabel(row.file_age_seconds)}</span>
                    : <SxChip tone="muted">no cache file</SxChip>}
                </td>
                <td>{row.exists ? row.row_count ?? 0 : '—'}</td>
                <td>
                  {row.exists ? (
                    <SxChip tone={(row.unsynced_row_count ?? 0) > 0 ? 'warning' : 'success'}>
                      {row.unsynced_row_count ?? 0} pending
                    </SxChip>
                  ) : '—'}
                </td>
                <td>
                  {row.exists ? (
                    <div className="d-flex align-items-center gap-2">
                      <SxChip tone={writebackTone(row.last_writeback_status)}>
                        {row.last_writeback_status ?? 'never'}
                      </SxChip>
                      <span className="sx-card__sub">{formatDateTime(row.last_writeback_at ?? undefined)}</span>
                    </div>
                  ) : '—'}
                  {row.last_writeback_error && <div className="sx-card__sub text-danger">{row.last_writeback_error}</div>}
                </td>
                <td>
                  <SxChip tone={connectionTone(row.connection_status)} dot>
                    {row.connection_status ?? 'ok'}
                  </SxChip>
                </td>
                <td>
                  <div className="d-flex flex-wrap gap-1">
                    <SxButton sm icon="bi-cloud-download" title="Force pull: rebuild cache from central now"
                      busy={busy === `pull:${row.store_name}`} onClick={() => { void forcePull(row.store_name) }}>
                      Pull
                    </SxButton>
                    <SxButton sm icon="bi-cloud-upload" title="Force push: drain pending write-back to HO now"
                      busy={busy === `push:${row.store_name}`} onClick={() => { void forcePush(row.store_name) }}>
                      Push
                    </SxButton>
                    <SxButton sm icon="bi-download" title="Download the raw .sqlite cache file"
                      busy={busy === `export:${row.store_name}`} onClick={() => { void exportFile(row.store_name) }} />
                    <SxButton sm icon="bi-whatsapp" title="Send cache file via WhatsApp (offline fallback)"
                      busy={busy === `send:${row.store_name}`} onClick={() => { void sendFile(row.store_name, 'whatsapp') }} />
                    <SxButton sm icon="bi-upload" title="Import a cache file received by mail/WhatsApp"
                      busy={busy === `import:${row.store_name}`} onClick={() => openImportPicker(row.store_name)} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </SxTable>
      </SxCardBody>
    </SxCard>
  )
}
