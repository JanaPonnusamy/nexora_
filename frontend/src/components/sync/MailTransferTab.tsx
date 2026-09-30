import { useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { mailTransferService } from '../../services/mailTransferService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { formatDateTime } from '../../utils/format'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxTable } from './ui'

// HO's EMAIL FILE_TRANSFER config is plain environment variables (see
// backend/modules/sync/file_transfer_config.py) -- there is deliberately no
// "Save" here, only a live view + real connection tests, matching that
// existing architecture decision. Actual receiving is done by the standalone
// NexoraHOMailReceiver service (Phase 2 extraction), not this HO process, so
// "status.receiver" below reflects the in-process receiver only and will
// read null/stale once a store's mode is EMAIL and the dedicated service has
// taken over polling.
export function MailTransferTab() {
  const statusQuery = useAsyncData(() => mailTransferService.status())
  const configQuery = useAsyncData(() => mailTransferService.mailConfig())
  const packagesQuery = useAsyncData(() => mailTransferService.packages(undefined, 50))
  const [testingSmtp, setTestingSmtp] = useState(false)
  const [testingImap, setTestingImap] = useState(false)
  const [smtpResult, setSmtpResult] = useState<string | null>(null)
  const [imapResult, setImapResult] = useState<string | null>(null)

  if (statusQuery.isLoading || configQuery.isLoading || packagesQuery.isLoading) {
    return <TableSkeleton rows={5} columns={6} />
  }
  if (statusQuery.error || !statusQuery.data) {
    return <ErrorState title="Mail Transfer unavailable" description={statusQuery.error ?? 'Failed to load status'} onRetry={statusQuery.reload} />
  }
  if (configQuery.error || !configQuery.data) {
    return <ErrorState title="Mail Transfer unavailable" description={configQuery.error ?? 'Failed to load mail config'} onRetry={configQuery.reload} />
  }

  const status = statusQuery.data
  const cfg = configQuery.data
  const packages = packagesQuery.data ?? []

  if (!status.enabled) {
    return (
      <EmptyState
        icon="bi-envelope"
        title="FILE_TRANSFER is not enabled at HO"
        description="Set NEXORA_FILE_TRANSFER_ENABLED=true (and NEXORA_FILE_TRANSFER_MODE=EMAIL for mail delivery) in the HO environment to use this."
        action={{ label: 'Refresh', icon: 'bi-arrow-clockwise', onClick: () => { void statusQuery.reload(); void configQuery.reload() } }}
      />
    )
  }

  const runTest = async (which: 'smtp' | 'imap') => {
    if (which === 'smtp') {
      setTestingSmtp(true)
      setSmtpResult(null)
      try {
        const result = await mailTransferService.testSmtp()
        setSmtpResult(result.ok ? `OK: ${result.detail}` : `FAILED: ${result.detail}`)
      } finally {
        setTestingSmtp(false)
      }
    } else {
      setTestingImap(true)
      setImapResult(null)
      try {
        const result = await mailTransferService.testImap()
        setImapResult(result.ok ? `OK: ${result.detail}` : `FAILED: ${result.detail}`)
      } finally {
        setTestingImap(false)
      }
    }
  }

  return (
    <div className="sx-stack">
      <SxCard>
        <SxCardHead
          title="Mail Transfer Status"
          sub={`Transport mode: ${status.transport_mode ?? '—'} · tick: ${status.tick_seconds}s`}
        />
        <SxCardBody>
          <p>
            In-process receiver last tick: {status.receiver?.at ? formatDateTime(status.receiver.at) : 'never'}
            {status.receiver?.error ? ` — error: ${status.receiver.error}` : ''}
          </p>
          {status.transport_mode === 'EMAIL' && (
            <p className="text-muted small">
              EMAIL mode: polling is owned by the standalone NexoraHOMailReceiver
              service (Phase 2 extraction), not this backend process — check that
              service's own logs/status for the authoritative last-poll time.
            </p>
          )}
        </SxCardBody>
      </SxCard>

      <SxCard>
        <SxCardHead title="Mail Configuration (read-only, environment-driven)" />
        <SxCardBody>
          <table className="table table-sm">
            <tbody>
              <tr><th>SMTP</th><td>{cfg.smtp_host ?? '—'}:{cfg.smtp_port ?? '—'}</td></tr>
              <tr><th>IMAP</th><td>{cfg.imap_host ?? '—'}:{cfg.imap_port ?? '—'} ({cfg.imap_folder ?? 'INBOX'})</td></tr>
              <tr><th>Username</th><td>{cfg.username ?? '—'}</td></tr>
              <tr>
                <th>Password</th>
                <td>
                  env var <code>{cfg.password_env ?? '—'}</code>{' '}
                  <SxChip tone={cfg.password_env_set ? 'success' : 'danger'}>
                    {cfg.password_env_set ? 'set' : 'not set'}
                  </SxChip>
                </td>
              </tr>
              <tr><th>Default store reply address</th><td>{cfg.default_store_address ?? '—'}</td></tr>
            </tbody>
          </table>
          <div className="d-flex gap-2 flex-wrap">
            <SxButton onClick={() => runTest('smtp')} disabled={testingSmtp || cfg.mode !== 'EMAIL'} busy={testingSmtp}>
              Test SMTP
            </SxButton>
            <SxButton onClick={() => runTest('imap')} disabled={testingImap || cfg.mode !== 'EMAIL'} busy={testingImap}>
              Test IMAP
            </SxButton>
          </div>
          {smtpResult && <p className={smtpResult.startsWith('OK') ? 'text-success mt-2' : 'text-danger mt-2'}>{smtpResult}</p>}
          {imapResult && <p className={imapResult.startsWith('OK') ? 'text-success mt-2' : 'text-danger mt-2'}>{imapResult}</p>}
        </SxCardBody>
      </SxCard>

      <SxCard>
        <SxCardHead title="Recent packages" sub={`${packages.length} shown`} />
        <SxCardBody>
          {packages.length === 0 ? (
            <EmptyState icon="bi-inbox" title="No packages yet" description="Packages will appear here once a store sends one." />
          ) : (
            <SxTable>
              <thead>
                <tr>
                  <th>Store</th><th>Status</th><th>Transport</th><th>Rows</th>
                  <th>Received</th><th>Tables imported/failed</th><th>Error</th>
                </tr>
              </thead>
              <tbody>
                {packages.map((pkg) => (
                  <tr key={pkg.package_id}>
                    <td>{pkg.store_id ?? '—'}</td>
                    <td><SxChip tone={pkg.status === 'IMPORTED' ? 'success' : pkg.status === 'REJECTED' || pkg.status === 'FAILED' ? 'danger' : 'muted'}>{pkg.status}</SxChip></td>
                    <td>{pkg.transport_mode ?? '—'}</td>
                    <td>{pkg.total_rows ?? '—'}</td>
                    <td>{formatDateTime(pkg.received_at)}</td>
                    <td>{pkg.tables_imported ?? 0} / {pkg.tables_failed ?? 0}</td>
                    <td>{pkg.error_message ?? ''}</td>
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
