import { useCallback, useEffect, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { Skeleton } from '../../components/common/Skeleton'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { auditService } from '../../services/auditService'
import type { AuditFilterOptions, AuditFilterParams, AuditLogEntry } from '../../types/audit'
import './audit-logs.css'

function getCategoryBadge(category: string) {
  const cat = (category || 'system').toLowerCase()
  const validCat = [
    'auth', 'user', 'role', 'tenant', 'store', 'sync',
    'procurement', 'inventory', 'audit', 'system'
  ].includes(cat) ? cat : 'system'

  return <span className={`audit-badge-cat audit-cat-${validCat}`}>{category}</span>
}

function formatUtcTimestamp(iso: string): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
  } catch {
    return iso
  }
}

export default function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filter options
  const [options, setOptions] = useState<AuditFilterOptions | null>(null)

  // Active filters
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [action, setAction] = useState('')
  const [category, setCategory] = useState('')
  const [actorId, setActorId] = useState('')
  const [actorRole, setActorRole] = useState('')
  const [targetType, setTargetType] = useState('')
  const [status, setStatus] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [preset, setPreset] = useState<string>('7d')

  // Selected row for detail drawer
  const [selectedEntry, setSelectedEntry] = useState<AuditLogEntry | null>(null)
  const [exporting, setExporting] = useState(false)

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  // Load filter options on mount
  useEffect(() => {
    auditService
      .filterOptions()
      .then((opts) => setOptions(opts))
      .catch(() => {})
  }, [])

  // Apply default 7d preset on first load if unset
  useEffect(() => {
    const now = new Date()
    const past = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
    setFromDate(past.toISOString().substring(0, 10))
    setToDate(now.toISOString().substring(0, 10))
  }, [])

  // Apply date preset
  const handlePreset = (presetKey: string) => {
    setPreset(presetKey)
    setPage(1)
    const now = new Date()

    if (presetKey === 'today') {
      const todayStr = now.toISOString().substring(0, 10)
      setFromDate(todayStr)
      setToDate(todayStr)
    } else if (presetKey === '7d') {
      const past = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
      setFromDate(past.toISOString().substring(0, 10))
      setToDate(now.toISOString().substring(0, 10))
    } else if (presetKey === '30d') {
      const past = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      setFromDate(past.toISOString().substring(0, 10))
      setToDate(now.toISOString().substring(0, 10))
    } else {
      setFromDate('')
      setToDate('')
    }
  }

  // Fetch logs
  const fetchLogs = useCallback(
    (signal?: AbortSignal) => {
      setLoading(true)
      setError(null)

      const params: AuditFilterParams = {
        search: debouncedSearch || undefined,
        action: action || undefined,
        category: category || undefined,
        actor_id: actorId || undefined,
        actor_role: actorRole || undefined,
        target_type: targetType || undefined,
        status: status || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        page,
        page_size: pageSize,
      }

      auditService
        .list(params, signal)
        .then((res) => {
          setLogs(res.items || [])
          setTotal(res.total || 0)
          setTotalPages(res.total_pages || 1)
        })
        .catch((err) => {
          if (err.name === 'AbortError') return
          setError(err instanceof Error ? err.message : 'Failed to fetch audit logs')
        })
        .finally(() => {
          setLoading(false)
        })
    },
    [debouncedSearch, action, category, actorId, actorRole, targetType, status, fromDate, toDate, page, pageSize]
  )

  useEffect(() => {
    const controller = new AbortController()
    fetchLogs(controller.signal)
    return () => controller.abort()
  }, [fetchLogs])

  const clearAllFilters = () => {
    setSearch('')
    setDebouncedSearch('')
    setAction('')
    setCategory('')
    setActorId('')
    setActorRole('')
    setTargetType('')
    setStatus('')
    setFromDate('')
    setToDate('')
    setPreset('all')
    setPage(1)
  }

  const hasActiveFilters = Boolean(
    debouncedSearch || action || category || actorId || actorRole || targetType || status || fromDate || toDate
  )

  const handleExport = async () => {
    if (exporting) return
    setExporting(true)
    try {
      const params: AuditFilterParams = {
        search: debouncedSearch || undefined,
        action: action || undefined,
        category: category || undefined,
        actor_id: actorId || undefined,
        actor_role: actorRole || undefined,
        target_type: targetType || undefined,
        status: status || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
      }
      const blob = await auditService.exportCsv(params)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `audit-logs-${new Date().toISOString().substring(0, 10)}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="container-fluid py-3 audit-page-container">
      {/* Header */}
      <div className="d-flex justify-content-between align-items-start mb-3 flex-wrap gap-2">
        <PageHeader
          title="Audit Trail"
          breadcrumb={['Administration', 'Audit Logs']}
          description="Immutable, append-only record of all administrative operations, authentication events, and system mutations."
        />
        <button
          type="button"
          className="btn btn-outline-primary btn-sm d-flex align-items-center gap-2 mt-2"
          onClick={handleExport}
          disabled={exporting || total === 0}
        >
          {exporting ? (
            <span className="spinner-border spinner-border-sm" aria-hidden="true" />
          ) : (
            <i className="bi bi-download" />
          )}
          Export CSV ({total.toLocaleString()} rows)
        </button>
      </div>

      {/* Filter Card */}
      <div className="audit-card p-3 mb-3">
        {/* Row 1: Search & Quick Presets */}
        <div className="row g-2 align-items-center mb-3">
          <div className="col-12 col-md-5 col-lg-4">
            <div className="input-group input-group-sm">
              <span className="input-group-text audit-search-addon border-end-0">
                <i className="bi bi-search" />
              </span>
              <input
                type="search"
                className="form-control form-control-sm audit-control border-start-0"
                placeholder="Search actor, action, target, IP, reason..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button
                  type="button"
                  className="btn btn-outline-secondary audit-control"
                  onClick={() => setSearch('')}
                >
                  ✕
                </button>
              )}
            </div>
          </div>

          <div className="col-12 col-md-7 col-lg-8 d-flex gap-2 flex-wrap justify-content-md-end align-items-center">
            <span className="small text-muted fw-bold text-uppercase">Time Range:</span>
            <div className="btn-group btn-group-sm" role="group">
              <button
                type="button"
                className={`btn audit-btn-preset ${preset === 'today' ? 'active' : ''}`}
                onClick={() => handlePreset('today')}
              >
                Today
              </button>
              <button
                type="button"
                className={`btn audit-btn-preset ${preset === '7d' ? 'active' : ''}`}
                onClick={() => handlePreset('7d')}
              >
                7 Days
              </button>
              <button
                type="button"
                className={`btn audit-btn-preset ${preset === '30d' ? 'active' : ''}`}
                onClick={() => handlePreset('30d')}
              >
                30 Days
              </button>
              <button
                type="button"
                className={`btn audit-btn-preset ${preset === 'all' ? 'active' : ''}`}
                onClick={() => handlePreset('all')}
              >
                All Time
              </button>
            </div>

            <div className="d-flex align-items-center gap-1">
              <input
                type="date"
                className="form-control form-control-sm audit-control"
                style={{ width: '140px' }}
                value={fromDate}
                onChange={(e) => {
                  setFromDate(e.target.value)
                  setPreset('custom')
                  setPage(1)
                }}
                title="From UTC Date"
              />
              <span className="text-muted">–</span>
              <input
                type="date"
                className="form-control form-control-sm audit-control"
                style={{ width: '140px' }}
                value={toDate}
                onChange={(e) => {
                  setToDate(e.target.value)
                  setPreset('custom')
                  setPage(1)
                }}
                title="To UTC Date"
              />
            </div>
          </div>
        </div>

        {/* Row 2: Categorical Dropdowns */}
        <div className="row g-2">
          <div className="col-6 col-md-3 col-lg-2">
            <label className="form-label small text-muted mb-1 fw-semibold">Category</label>
            <select
              className="form-select form-select-sm audit-control"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Categories</option>
              {options?.categories.map((c) => (
                <option key={c} value={c}>
                  {c.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          <div className="col-6 col-md-3 col-lg-2">
            <label className="form-label small text-muted mb-1 fw-semibold">Action</label>
            <select
              className="form-select form-select-sm audit-control"
              value={action}
              onChange={(e) => {
                setAction(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Actions</option>
              {options?.actions.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>

          <div className="col-6 col-md-3 col-lg-2">
            <label className="form-label small text-muted mb-1 fw-semibold">Actor</label>
            <select
              className="form-select form-select-sm audit-control"
              value={actorId}
              onChange={(e) => {
                setActorId(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Actors</option>
              {options?.actors.map((act) => (
                <option key={act.actor_id} value={act.actor_id}>
                  {act.actor_name || act.actor_email || act.actor_id}
                </option>
              ))}
            </select>
          </div>

          <div className="col-6 col-md-3 col-lg-2">
            <label className="form-label small text-muted mb-1 fw-semibold">Actor Role</label>
            <select
              className="form-select form-select-sm audit-control"
              value={actorRole}
              onChange={(e) => {
                setActorRole(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Roles</option>
              {options?.actor_roles.map((r) => (
                <option key={r} value={r}>
                  {r.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          <div className="col-6 col-md-3 col-lg-2">
            <label className="form-label small text-muted mb-1 fw-semibold">Target Type</label>
            <select
              className="form-select form-select-sm audit-control"
              value={targetType}
              onChange={(e) => {
                setTargetType(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Targets</option>
              {options?.target_types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div className="col-6 col-md-3 col-lg-2">
            <label className="form-label small text-muted mb-1 fw-semibold">Status</label>
            <select
              className="form-select form-select-sm audit-control"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Statuses</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
            </select>
          </div>
        </div>

        {/* Active Filter Chips */}
        {hasActiveFilters && (
          <div className="d-flex align-items-center gap-2 flex-wrap mt-3 pt-2 border-top">
            <span className="small text-muted fw-bold">Active Filters:</span>
            {debouncedSearch && (
              <span className="audit-chip">
                Search: {debouncedSearch}
                <button type="button" className="audit-chip-close" onClick={() => setSearch('')}>✕</button>
              </span>
            )}
            {category && (
              <span className="audit-chip">
                Category: {category}
                <button type="button" className="audit-chip-close" onClick={() => setCategory('')}>✕</button>
              </span>
            )}
            {action && (
              <span className="audit-chip">
                Action: {action}
                <button type="button" className="audit-chip-close" onClick={() => setAction('')}>✕</button>
              </span>
            )}
            {actorId && (
              <span className="audit-chip">
                Actor: {options?.actors.find((a) => a.actor_id === actorId)?.actor_name || actorId}
                <button type="button" className="audit-chip-close" onClick={() => setActorId('')}>✕</button>
              </span>
            )}
            {status && (
              <span className="audit-chip">
                Status: {status}
                <button type="button" className="audit-chip-close" onClick={() => setStatus('')}>✕</button>
              </span>
            )}
            {fromDate && (
              <span className="audit-chip">
                From: {fromDate}
                <button type="button" className="audit-chip-close" onClick={() => setFromDate('')}>✕</button>
              </span>
            )}
            {toDate && (
              <span className="audit-chip">
                To: {toDate}
                <button type="button" className="audit-chip-close" onClick={() => setToDate('')}>✕</button>
              </span>
            )}
            <button
              type="button"
              className="btn btn-link btn-sm text-danger text-decoration-none p-0 ms-auto fw-semibold"
              onClick={clearAllFilters}
            >
              Clear all filters
            </button>
          </div>
        )}
      </div>

      {/* Main Table Card */}
      <div className="audit-table-card">
        <div className="table-responsive" style={{ minHeight: '380px' }}>
          {loading ? (
            <div className="p-4">
              <Skeleton height="20rem" />
            </div>
          ) : error ? (
            <div className="p-4">
              <ErrorState description={error} onRetry={() => fetchLogs()} />
            </div>
          ) : logs.length === 0 ? (
            <div className="p-5">
              <EmptyState
                icon="bi-journal-text"
                title="No Audit Logs Found"
                description={
                  hasActiveFilters
                    ? 'No log entries match your active filters. Try adjusting or clearing search filters.'
                    : 'No administrative mutations or audit events have been recorded yet.'
                }
              />
            </div>
          ) : (
            <table className="audit-table">
              <thead>
                <tr>
                  <th style={{ width: '175px' }}>Timestamp (UTC)</th>
                  <th style={{ width: '95px' }}>Status</th>
                  <th style={{ width: '110px' }}>Category</th>
                  <th>Action</th>
                  <th>Actor (Snapshot)</th>
                  <th>Target</th>
                  <th>Reason / Summary</th>
                  <th style={{ width: '60px', textAlign: 'center' }}>Details</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((entry) => {
                  const isFail = entry.status === 'failure'
                  return (
                    <tr
                      key={entry.log_id}
                      className={isFail ? 'audit-row-failure' : ''}
                      onClick={() => setSelectedEntry(entry)}
                    >
                      <td className="font-monospace text-muted small">
                        {formatUtcTimestamp(entry.timestamp)}
                      </td>
                      <td>
                        {entry.status === 'success' ? (
                          <span className="audit-badge-success">
                            <i className="bi bi-check-circle-fill" />
                            Success
                          </span>
                        ) : (
                          <span className="audit-badge-failure">
                            <i className="bi bi-x-circle-fill" />
                            Failure
                          </span>
                        )}
                      </td>
                      <td>{getCategoryBadge(entry.category)}</td>
                      <td className="fw-semibold font-monospace">{entry.action}</td>
                      <td>
                        <div>
                          <span className="fw-semibold d-block">{entry.actor_name || 'System'}</span>
                          {entry.actor_email && (
                            <span className="text-muted small d-block">{entry.actor_email}</span>
                          )}
                          <span className="badge bg-secondary-subtle text-secondary border small px-1 py-0 text-uppercase">
                            {entry.actor_role}
                          </span>
                        </div>
                      </td>
                      <td>
                        {entry.target_label || entry.target_id ? (
                          <div>
                            <span className="fw-semibold d-block">{entry.target_label || entry.target_id}</span>
                            {entry.target_type && (
                              <span className="text-muted small d-block font-monospace">
                                {entry.target_type}: {entry.target_id}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td>
                        <div
                          className="text-truncate"
                          style={{ maxWidth: '320px' }}
                          title={entry.reason || entry.error_message || ''}
                        >
                          {entry.reason || entry.error_message || '—'}
                        </div>
                      </td>
                      <td className="text-center" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="btn btn-outline-secondary btn-sm p-1"
                          title="View full audit record"
                          onClick={() => setSelectedEntry(entry)}
                        >
                          <i className="bi bi-eye" />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pager Footer */}
        <div className="audit-pager-footer">
          <span>
            Showing {(page - 1) * pageSize + (logs.length > 0 ? 1 : 0)}–
            {Math.min(page * pageSize, total)} of {total.toLocaleString()} records
          </span>

          <div className="d-flex align-items-center gap-3">
            <div className="d-flex align-items-center gap-1">
              <span>Rows per page:</span>
              <select
                className="form-select form-select-sm audit-control"
                style={{ width: '75px' }}
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setPage(1)
                }}
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>

            <div className="btn-group btn-group-sm">
              <button
                type="button"
                className="audit-pager-btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <i className="bi bi-chevron-left" />
              </button>
              <span className="audit-pager-indicator">
                {page} / {totalPages}
              </span>
              <button
                type="button"
                className="audit-pager-btn"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                <i className="bi bi-chevron-right" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Row Detail Modal / Slide-over */}
      {selectedEntry && (
        <div
          className="modal fade show d-block"
          tabIndex={-1}
          style={{ backgroundColor: 'rgba(0,0,0,0.65)' }}
          onClick={() => setSelectedEntry(null)}
        >
          <div
            className="modal-dialog modal-lg modal-dialog-scrollable"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-content audit-modal-content">
              <div className="modal-header audit-modal-header d-flex justify-content-between align-items-center">
                <div>
                  <h5 className="modal-title d-flex align-items-center gap-2 mb-1">
                    <i className="bi bi-journal-text text-primary" />
                    Audit Record Details
                  </h5>
                  <span className="font-monospace text-muted small">{selectedEntry.log_id}</span>
                </div>
                <button
                  type="button"
                  className="btn-close btn-close-white"
                  onClick={() => setSelectedEntry(null)}
                  aria-label="Close"
                />
              </div>

              <div className="modal-body audit-modal-body">
                <div className="row g-3">
                  <div className="col-md-6">
                    <label className="text-muted small fw-bold">TIMESTAMP (UTC)</label>
                    <div className="font-monospace fw-semibold">{formatUtcTimestamp(selectedEntry.timestamp)}</div>
                  </div>
                  <div className="col-md-6">
                    <label className="text-muted small fw-bold">STATUS</label>
                    <div>
                      {selectedEntry.status === 'success' ? (
                        <span className="audit-badge-success">
                          <i className="bi bi-check-circle-fill" /> Success
                        </span>
                      ) : (
                        <span className="audit-badge-failure">
                          <i className="bi bi-x-circle-fill" /> Failure
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="col-md-6">
                    <label className="text-muted small fw-bold">ACTION</label>
                    <div className="font-monospace fw-bold">{selectedEntry.action}</div>
                  </div>
                  <div className="col-md-6">
                    <label className="text-muted small fw-bold">CATEGORY</label>
                    <div>{getCategoryBadge(selectedEntry.category)}</div>
                  </div>

                  <div className="col-md-6">
                    <label className="text-muted small fw-bold">ACTOR (SNAPSHOT)</label>
                    <div className="fw-semibold">{selectedEntry.actor_name || 'System'}</div>
                    <div className="text-muted small">{selectedEntry.actor_email || '—'}</div>
                    <div className="text-muted small">Role: {selectedEntry.actor_role} | ID: {selectedEntry.actor_id || '—'}</div>
                  </div>
                  <div className="col-md-6">
                    <label className="text-muted small fw-bold">TARGET ENTITY</label>
                    <div className="fw-semibold">{selectedEntry.target_label || '—'}</div>
                    <div className="text-muted small">
                      Type: {selectedEntry.target_type || '—'} | ID: {selectedEntry.target_id || '—'}
                    </div>
                  </div>

                  <div className="col-12">
                    <label className="text-muted small fw-bold">REASON / SUMMARY</label>
                    <div className="audit-detail-box">
                      {selectedEntry.reason || '—'}
                    </div>
                  </div>

                  {selectedEntry.error_message && (
                    <div className="col-12">
                      <label className="text-danger small fw-bold">ERROR MESSAGE</label>
                      <div className="audit-detail-error">
                        {selectedEntry.error_message}
                      </div>
                    </div>
                  )}

                  <div className="col-md-4">
                    <label className="text-muted small fw-bold">CLIENT IP</label>
                    <div className="font-monospace small">{selectedEntry.ip || '—'}</div>
                  </div>
                  <div className="col-md-4">
                    <label className="text-muted small fw-bold">DEVICE / OS</label>
                    <div className="small">{selectedEntry.device || '—'}</div>
                  </div>
                  <div className="col-md-4">
                    <label className="text-muted small fw-bold">COUNTRY</label>
                    <div className="small">{selectedEntry.country || '—'}</div>
                  </div>

                  <div className="col-12">
                    <label className="text-muted small fw-bold">USER AGENT</label>
                    <div className="audit-detail-box font-monospace small text-break">
                      {selectedEntry.user_agent || '—'}
                    </div>
                  </div>

                  <div className="col-12">
                    <label className="text-muted small fw-bold">METADATA (REDACTED JSON)</label>
                    <pre className="audit-json-viewer mb-0">
                      {selectedEntry.metadata
                        ? JSON.stringify(JSON.parse(selectedEntry.metadata), null, 2)
                        : '// No metadata attached'}
                    </pre>
                  </div>
                </div>
              </div>

              <div className="modal-footer audit-modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSelectedEntry(null)}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
