import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../components/common/PageHeader'
import { EmptyState } from '../components/common/EmptyState'
import { ErrorState } from '../components/common/ErrorState'
import { api, ApiError } from '../services/apiClient'
import { timeReportService } from '../services/timeReportService'
import type {
  DailyReport,
  DayRecord,
  InactiveReport,
  LegendItem,
  MissPunchReport,
  MonthlyReport,
  TimeReportMeta,
  TimeReportParams,
  UserReport,
  UserSummaryRow,
} from '../types/timeReport'
import './timeReport.css'

const WHITE = 'FFFFFF'

/** Status colours carry meaning (miss punch = red, etc.), so they are applied
 *  inline. The neutral "full/absent" white is left to the theme instead of
 *  forcing a white row in dark mode — full vs. absent stays legible by content
 *  (absent rows have blank punches and hours). */
function statusStyle(hex?: string, text?: string): React.CSSProperties | undefined {
  if (!hex || hex.toUpperCase() === WHITE) return undefined
  return { background: `#${hex}`, color: `#${text ?? '000000'}` }
}

function Legend({ items }: { items: LegendItem[] }) {
  return (
    <div className="trp-legend">
      <span className="trp-leg-label">Legend:</span>
      {items.map((it) => (
        <span key={it.code} className="trp-leg-item">
          <span className="trp-swatch" style={{ background: `#${it.hex}` }} />
          {it.code} — {it.label}
        </span>
      ))}
    </div>
  )
}

type Result =
  | { kind: 'daily'; data: DailyReport }
  | { kind: 'monthly'; data: MonthlyReport }
  | { kind: 'misspunch'; data: MissPunchReport }
  | { kind: 'user'; data: UserReport }
  | { kind: 'inactive'; data: InactiveReport }

const iso = (d: Date) => d.toISOString().slice(0, 10)

export default function TimeReportPage() {
  const [meta, setMeta] = useState<TimeReportMeta | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [reportKey, setReportKey] = useState('daily')

  const today = useMemo(() => new Date(), [])
  const [date, setDate] = useState(iso(today))
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth() + 1)
  const [start, setStart] = useState(iso(new Date(today.getFullYear(), today.getMonth(), 1)))
  const [end, setEnd] = useState(iso(today))
  const [deptId, setDeptId] = useState('')
  const [userId, setUserId] = useState('')
  const [mode, setMode] = useState<'detail' | 'summary'>('detail')
  const [search, setSearch] = useState('')
  const [days, setDays] = useState('30')

  const [result, setResult] = useState<Result | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    timeReportService
      .meta()
      .then((m) => {
        setMeta(m)
        setDate((c) => c || m.bounds.max)
      })
      .catch((e) => setMetaError(e instanceof Error ? e.message : 'Failed to load Time Report metadata'))
  }, [])

  // Params for the currently-selected report (also used to build the export URL).
  const params = useCallback((): TimeReportParams => {
    switch (reportKey) {
      case 'daily':
        return { date, dept_id: deptId }
      case 'monthly':
        return { year, month, dept_id: deptId }
      case 'misspunch':
        return { start, end, dept_id: deptId, user_id: userId }
      case 'user':
        return { start, end, dept_id: deptId, user_id: userId, mode, search }
      case 'inactive':
        return { days: Number(days), dept_id: deptId }
      default:
        return {}
    }
  }, [reportKey, date, year, month, start, end, deptId, userId, mode, search, days])

  const run = useCallback(() => {
    setLoading(true)
    setError(null)
    const p = params()
    const call = () => {
      switch (reportKey) {
        case 'daily':
          return timeReportService.daily(p).then((data) => ({ kind: 'daily', data }) as Result)
        case 'monthly':
          return timeReportService.monthly(p).then((data) => ({ kind: 'monthly', data }) as Result)
        case 'misspunch':
          return timeReportService.misspunch(p).then((data) => ({ kind: 'misspunch', data }) as Result)
        case 'user':
          return timeReportService.user(p).then((data) => ({ kind: 'user', data }) as Result)
        case 'inactive':
          return timeReportService.inactive(p).then((data) => ({ kind: 'inactive', data }) as Result)
        default:
          return Promise.reject(new Error('Unknown report'))
      }
    }
    call()
      .then(setResult)
      .catch((e) => {
        setResult(null)
        setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Failed to run report')
      })
      .finally(() => setLoading(false))
  }, [reportKey, params])

  const exportXlsx = useCallback(async () => {
    setDownloading(true)
    try {
      const path = timeReportService.exportPath(reportKey, params())
      const blob = await api.blob(path)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${reportKey}_${iso(today)}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setDownloading(false)
    }
  }, [reportKey, params, today])

  const def = useMemo(
    () => meta?.reports.find((r) => r.key === reportKey) ?? null,
    [meta, reportKey],
  )

  const yearOptions = useMemo(() => {
    const minY = meta ? Number(meta.bounds.min.slice(0, 4)) : today.getFullYear() - 8
    const maxY = today.getFullYear()
    const out: number[] = []
    for (let y = maxY; y >= minY; y--) out.push(y)
    return out
  }, [meta, today])

  if (metaError) {
    return (
      <div className="container-fluid px-0">
        <PageHeader title="Time Report" breadcrumb={['Time Report']} />
        <ErrorState title="Time Report unavailable" description={metaError} onRetry={() => window.location.reload()} />
      </div>
    )
  }

  const bounds = meta?.bounds
  const hasExport = Boolean(result)

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Time Report" breadcrumb={['Time Report']} />

      <div className="trp-bar">
        <label className="trp-field">
          <span>Report</span>
          <select
            className="form-select form-select-sm"
            value={reportKey}
            onChange={(e) => {
              setReportKey(e.target.value)
              setResult(null)
              setError(null)
            }}
          >
            {(meta?.reports ?? []).map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
        </label>

        {reportKey === 'daily' && (
          <label className="trp-field">
            <span>Date</span>
            <input
              type="date"
              className="form-control form-control-sm"
              value={date}
              min={bounds?.min}
              max={bounds?.max}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>
        )}

        {reportKey === 'monthly' && (
          <>
            <label className="trp-field">
              <span>Month</span>
              <select className="form-select form-select-sm" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>
                    {String(m).padStart(2, '0')}
                  </option>
                ))}
              </select>
            </label>
            <label className="trp-field">
              <span>Year</span>
              <select className="form-select form-select-sm" value={year} onChange={(e) => setYear(Number(e.target.value))}>
                {yearOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}

        {(reportKey === 'misspunch' || reportKey === 'user') && (
          <>
            <label className="trp-field">
              <span>From</span>
              <input type="date" className="form-control form-control-sm" value={start} min={bounds?.min} max={bounds?.max} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label className="trp-field">
              <span>To</span>
              <input type="date" className="form-control form-control-sm" value={end} min={bounds?.min} max={bounds?.max} onChange={(e) => setEnd(e.target.value)} />
            </label>
          </>
        )}

        {reportKey === 'user' && (
          <>
            <label className="trp-field">
              <span>Search user (name or ID)</span>
              <input
                className="form-control form-control-sm"
                placeholder="e.g. 470 or BALAJI"
                value={search}
                autoComplete="off"
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label className="trp-field">
              <span>Mode</span>
              <select className="form-select form-select-sm" value={mode} onChange={(e) => setMode(e.target.value as 'detail' | 'summary')}>
                <option value="detail">Detail (day by day)</option>
                <option value="summary">Summary (totals)</option>
              </select>
            </label>
          </>
        )}

        {reportKey === 'inactive' && (
          <label className="trp-field">
            <span>No punch for (days)</span>
            <input type="number" min={1} max={3650} className="form-control form-control-sm trp-num" value={days} onChange={(e) => setDays(e.target.value)} />
          </label>
        )}

        {reportKey === 'misspunch' && (
          <label className="trp-field">
            <span>User</span>
            <select className="form-select form-select-sm" value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">All Users</option>
              {(meta?.users ?? []).map((u) => (
                <option key={u.UserID} value={u.UserID}>
                  {u.UserID} - {u.Name}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="trp-field">
          <span>Department</span>
          <select className="form-select form-select-sm" value={deptId} onChange={(e) => setDeptId(e.target.value)}>
            <option value="">All Departments</option>
            {(meta?.departments ?? []).map((d) => (
              <option key={d.DPTID} value={String(d.DPTID)}>
                {d.Name}
              </option>
            ))}
          </select>
        </label>

        <button className="btn btn-primary btn-sm" disabled={!meta || loading} onClick={run}>
          <i className="bi bi-play-fill" /> {loading ? 'Running…' : 'Show'}
        </button>
        <button className="btn btn-outline-secondary btn-sm" disabled={!hasExport || downloading} onClick={exportXlsx}>
          <i className="bi bi-download" /> {downloading ? 'Exporting…' : 'Excel'}
        </button>
      </div>

      {def?.description && <div className="trp-desc">{def.description}</div>}

      {error ? (
        <ErrorState description={error} onRetry={run} />
      ) : !result ? (
        <EmptyState icon="bi-clock-history" title="Run a report" description="Choose a report and its options, then press Show." />
      ) : (
        <ResultView result={result} />
      )}
    </div>
  )
}

function ResultView({ result }: { result: Result }) {
  switch (result.kind) {
    case 'daily':
      return <DailyView data={result.data} />
    case 'monthly':
      return <MonthlyView data={result.data} />
    case 'misspunch':
      return <MissPunchView data={result.data} />
    case 'user':
      return <UserView data={result.data} />
    case 'inactive':
      return <InactiveView data={result.data} />
    default:
      return null
  }
}

function PunchCells({ punches, n = 8 }: { punches: string[]; n?: number }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <td key={i} className="trp-center">
          {punches[i] ?? ''}
        </td>
      ))}
    </>
  )
}

function DailyView({ data }: { data: DailyReport }) {
  const empty = data.departments.length === 0
  if (empty) return <EmptyState icon="bi-inbox" title="No data" description="No attendance for that date." />
  return (
    <div>
      <div className="trp-period">{data.period}</div>
      {data.departments.map((dept) => (
        <div key={`${dept.dpt_id}-${dept.name}`}>
          <div className="trp-dept-head">
            <h2>{dept.name}</h2>
          </div>
          <div className="trp-tablewrap">
            <table className="trp-table">
              <thead>
                <tr>
                  <th className="trp-left">ID</th>
                  <th className="trp-left">Name</th>
                  {Array.from({ length: 8 }, (_, i) => (
                    <th key={i} className="trp-center">
                      {i + 1}
                    </th>
                  ))}
                  <th className="trp-center">Hrs</th>
                </tr>
              </thead>
              <tbody>
                {dept.rows.map((d, i) => (
                  <tr key={`${d.user_id}-${i}`} style={statusStyle(d.status_hex, d.status_text)}>
                    <td>{d.user_id}</td>
                    <td className="trp-left">
                      {d.name.slice(0, 30)}
                      {d.is_late && <span className="trp-badge">LATE</span>}
                    </td>
                    <PunchCells punches={d.punches} />
                    <td className="trp-center">{d.work_hm}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="trp-foot">
                  <td colSpan={11} className="trp-left">
                    Present {dept.totals.present} | Absent {dept.totals.absent} | Miss Punch {dept.totals.miss_punch} | Late {dept.totals.late}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      ))}
      <Legend items={data.legend} />
    </div>
  )
}

function MonthlyView({ data }: { data: MonthlyReport }) {
  if (data.rows.length === 0) return <EmptyState icon="bi-inbox" title="No data" description="No attendance for that month." />
  return (
    <div>
      <div className="trp-period">{data.month_name}</div>
      <div className="trp-tablewrap">
        <table className="trp-table trp-muster">
          <thead>
            <tr>
              <th className="trp-left trp-fixed">Name</th>
              {data.days.map((d) => (
                <th key={d} className="trp-center">
                  {d}
                </th>
              ))}
              <th className="trp-center">P</th>
              <th className="trp-center">Abs</th>
              <th className="trp-center">Miss</th>
              <th className="trp-center">Late</th>
              <th className="trp-center">Total</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((u, i) => (
              <tr key={`${u.user_id}-${i}`}>
                <td className="trp-left trp-fixed" title={`${u.user_id} · ${u.department}`}>
                  {u.name}
                </td>
                {u.cells.map((c, j) => (
                  <td key={j} className="trp-day" style={statusStyle(c.hex)} title={c.work_hm}>
                    {c.code}
                  </td>
                ))}
                <td className="trp-center">{u.present}</td>
                <td className="trp-center">{u.absent}</td>
                <td className="trp-center">{u.miss_punch}</td>
                <td className="trp-center">{u.late}</td>
                <td className="trp-center">{u.total_hm}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend items={data.legend} />
    </div>
  )
}

function MissPunchView({ data }: { data: MissPunchReport }) {
  return (
    <div>
      <div className="trp-summary-line">
        Total miss-punch days: <b>{data.count}</b>
      </div>
      <div className="trp-tablewrap">
        <table className="trp-table">
          <thead>
            <tr>
              <th className="trp-left">Date</th>
              <th className="trp-left">UserID</th>
              <th className="trp-left">Name</th>
              <th className="trp-left">Department</th>
              <th className="trp-left">Punches</th>
              <th className="trp-center">#</th>
              <th className="trp-center">Work</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="trp-center text-muted">
                  No miss-punch days in this range. 🎉
                </td>
              </tr>
            ) : (
              data.rows.map((d, i) => (
                <tr key={`${d.user_id}-${i}`} style={statusStyle(d.status_hex, d.status_text)}>
                  <td>{d.pdate_str}</td>
                  <td>{d.user_id}</td>
                  <td className="trp-left">{d.name}</td>
                  <td className="trp-left">{d.department}</td>
                  <td className="trp-left">{d.punches.join(' | ')}</td>
                  <td className="trp-center">{d.punch_count}</td>
                  <td className="trp-center">{d.work_hm}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <Legend items={data.legend} />
    </div>
  )
}

function UserView({ data }: { data: UserReport }) {
  if (data.mode === 'summary') {
    const rows = data.rows as UserSummaryRow[]
    return (
      <div>
        <div className="trp-tablewrap">
          <table className="trp-table">
            <thead>
              <tr>
                <th className="trp-left">UserID</th>
                <th className="trp-left">Name</th>
                <th className="trp-left">Department</th>
                <th className="trp-center">Present</th>
                <th className="trp-center">Full</th>
                <th className="trp-center">Short</th>
                <th className="trp-center">Low</th>
                <th className="trp-center">Miss</th>
                <th className="trp-center">Absent</th>
                <th className="trp-center">Late</th>
                <th className="trp-center">Total Hrs</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={11} className="trp-center text-muted">
                    No data for this selection.
                  </td>
                </tr>
              ) : (
                rows.map((d, i) => (
                  <tr key={`${d.user_id}-${i}`}>
                    <td>{d.user_id}</td>
                    <td className="trp-left">{d.name}</td>
                    <td className="trp-left">{d.department}</td>
                    <td className="trp-center">{d.present}</td>
                    <td className="trp-center">{d.full}</td>
                    <td className="trp-center">{d.short}</td>
                    <td className="trp-center">{d.low}</td>
                    <td className="trp-center">{d.miss_punch}</td>
                    <td className="trp-center">{d.absent}</td>
                    <td className="trp-center">{d.late}</td>
                    <td className="trp-center">{d.total_hm}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <Legend items={data.legend} />
      </div>
    )
  }

  const rows = data.rows as DayRecord[]
  return (
    <div>
      <div className="trp-tablewrap">
        <table className="trp-table">
          <thead>
            <tr>
              <th className="trp-left">Date</th>
              <th className="trp-left">UserID</th>
              <th className="trp-left">Name</th>
              <th className="trp-left">Punches</th>
              <th className="trp-center">Work</th>
              <th className="trp-center">Late</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="trp-center text-muted">
                  No data for this selection.
                </td>
              </tr>
            ) : (
              rows.map((d, i) => (
                <tr key={`${d.user_id}-${i}`} style={statusStyle(d.status_hex, d.status_text)}>
                  <td>{d.pdate_str}</td>
                  <td>{d.user_id}</td>
                  <td className="trp-left">{d.name}</td>
                  <td className="trp-left">{d.punches.join(' | ')}</td>
                  <td className="trp-center">{d.work_hm}</td>
                  <td className="trp-center">{d.late_in || ''}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <Legend items={data.legend} />
    </div>
  )
}

function InactiveView({ data }: { data: InactiveReport }) {
  return (
    <div>
      <div className="trp-summary-line">
        Inactive users found: <b>{data.count}</b>
      </div>
      <div className="trp-tablewrap">
        <table className="trp-table">
          <thead>
            <tr>
              <th className="trp-left">UserID</th>
              <th className="trp-left">Name</th>
              <th className="trp-left">Department</th>
              <th className="trp-center">Join Date</th>
              <th className="trp-center">Last Punch</th>
              <th className="trp-center">Days Since</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="trp-center text-muted">
                  No inactive users. 🎉
                </td>
              </tr>
            ) : (
              data.rows.map((d, i) => (
                <tr key={`${d.user_id}-${i}`} style={d.last_seen === 'Never' ? { background: '#F4A7A7', color: '#000' } : undefined}>
                  <td>{d.user_id}</td>
                  <td className="trp-left">{d.name}</td>
                  <td className="trp-left">{d.department}</td>
                  <td className="trp-center">{d.join_dt}</td>
                  <td className="trp-center">{d.last_seen}</td>
                  <td className="trp-center">{d.days_since}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
