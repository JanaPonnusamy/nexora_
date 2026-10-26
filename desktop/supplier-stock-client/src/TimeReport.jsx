// Time Report (COSEC attendance) inside the Stock Client -- port of the web
// app's TimeReportPage over the same /api/time-report/* endpoints. Every
// download can go straight to WhatsApp; the Daily report sends ALL stores'
// images in ONE message with a single click (never a zip).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api/client.js';
import { WhatsAppShareButton, storeWhatsAppAvailable } from './storeWhatsApp.jsx';
import { unzipSync } from 'fflate';

// The API's light pastel status hexes -> theme tokens (readable in dark too).
const STATUS_HEX_TOKEN = {
  FFF3B0: { bg: 'var(--nx-warning-sunk)', ink: 'var(--nx-warning-ink)' }, // SHORT
  BBDEFB: { bg: 'var(--nx-info-sunk)', ink: 'var(--nx-info-ink)' }, // LOW
  F4A7A7: { bg: 'var(--nx-danger-sunk)', ink: 'var(--nx-danger-ink)' }, // MISS_PUNCH
  FFD9A0: { bg: 'var(--nx-warning-sunk)', ink: 'var(--nx-warning-ink)' }, // LATE
};
function statusStyle(hex) {
  if (!hex || hex.toUpperCase() === 'FFFFFF') return undefined;
  const token = STATUS_HEX_TOKEN[hex.toUpperCase()];
  return token ? { background: token.bg, color: token.ink } : { background: `#${hex}`, color: '#000000' };
}

const iso = (d) => d.toISOString().slice(0, 10);
const safeName = (name) => String(name || '').replace(/[^a-zA-Z0-9 _-]/g, '_');

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function Legend({ items = [] }) {
  return (
    <div className="trp-legend">
      <span className="trp-leg-label">Legend:</span>
      {items.map((it) => (
        <span key={it.code} className="trp-leg-item">
          <span className="trp-swatch" style={statusStyle(it.hex) || { background: `#${it.hex}` }} />
          {it.code} — {it.label}
        </span>
      ))}
    </div>
  );
}

export default function TimeReport({ session }) {
  const [meta, setMeta] = useState(null);
  const [metaError, setMetaError] = useState('');
  const [reportKey, setReportKey] = useState('daily');
  const today = useMemo(() => new Date(), []);
  const yesterday = useMemo(() => iso(new Date(today.getTime() - 86400000)), [today]);
  const [date, setDate] = useState(iso(today));
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [start, setStart] = useState(yesterday);
  const [end, setEnd] = useState(yesterday);
  const [deptId, setDeptId] = useState('');
  const [userId, setUserId] = useState('');
  const [mode, setMode] = useState('detail');
  const [search, setSearch] = useState('');
  const [days, setDays] = useState('30');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.timeReportMeta(session)
      .then((payload) => { setMeta(payload); setDate((cur) => cur || payload.bounds.max); })
      .catch((e) => setMetaError(e.message || 'Time Report is unavailable.'));
  }, [session]);

  const params = useCallback(() => {
    switch (reportKey) {
      case 'daily': return { date, dept_id: deptId };
      case 'monthly': return { year, month, dept_id: deptId };
      case 'misspunch': return { start, end, dept_id: deptId, user_id: userId };
      case 'user': return { start, end, dept_id: deptId, user_id: userId, mode, search };
      case 'inactive': return { days: Number(days), dept_id: deptId };
      default: return {};
    }
  }, [reportKey, date, year, month, start, end, deptId, userId, mode, search, days]);

  const run = useCallback(() => {
    setLoading(true); setError('');
    api.timeReport(reportKey, params(), session)
      .then((data) => setResult({ kind: reportKey, data }))
      .catch((e) => { setResult(null); setError(e.message || 'Failed to run report.'); })
      .finally(() => setLoading(false));
  }, [reportKey, params, session]);

  const def = meta?.reports?.find((r) => r.key === reportKey) || null;
  const caption = `Time Report | ${def?.label || reportKey}`;
  const stamp = reportKey === 'daily' ? date : iso(today);

  const excelBlob = () => api.getBlob(api.timeReportPath(reportKey, { ...params(), export: 'xlsx' }), session);
  const imageBlob = () => api.getBlob(api.timeReportPath(reportKey, { ...params(), export: 'image' }), session);
  const deptImageBlob = (id) => api.getBlob(api.timeReportPath('daily/image', { date, dept_id: id }), session);
  // Every store's PNG, unpacked from the server's zip -- sent as images.
  const allStoreImages = async () => {
    const zip = await api.getBlob(api.timeReportPath('daily/images', params()), session);
    const parts = unzipSync(new Uint8Array(await zip.arrayBuffer()));
    return Object.entries(parts).filter(([name]) => /\.png$/i.test(name))
      .map(([name, bytes]) => ({ name: name.split('/').pop(), blob: new Blob([bytes], { type: 'image/png' }) }));
  };

  const download = async (build, filename) => {
    setBusy(true);
    try { saveBlob(await build(), filename); } catch (e) { setError(e.message || 'Download failed.'); } finally { setBusy(false); }
  };

  const yearOptions = useMemo(() => {
    const minY = meta ? Number(meta.bounds.min.slice(0, 4)) : today.getFullYear() - 8;
    const out = [];
    for (let y = today.getFullYear(); y >= minY; y--) out.push(y);
    return out;
  }, [meta, today]);

  if (metaError) {
    return (
      <section className="screen-panel trp-screen">
        <header className="screen-header"><div><h2>Time Report</h2></div></header>
        <div className="status-line error">{metaError}</div>
      </section>
    );
  }

  const bounds = meta?.bounds;
  const hasResult = Boolean(result);
  const daily = result?.kind === 'daily' ? result.data : null;

  return (
    <section className="screen-panel trp-screen">
      <header className="screen-header">
        <div>
          <h2>Time Report</h2>
          <p>{def?.description || 'Staff attendance from the COSEC punch machines.'}</p>
        </div>
      </header>

      <div className="trp-bar" role="search" aria-label="Time report filters">
        <label className="trp-field">Report
          <select value={reportKey} onChange={(e) => {
            const next = e.target.value;
            setReportKey(next);
            if (next === 'misspunch') { setStart(yesterday); setEnd(yesterday); }
            setResult(null); setError('');
          }}>
            {(meta?.reports || []).map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
        </label>
        {reportKey === 'daily' && (
          <label className="trp-field">Date
            <input type="date" value={date} min={bounds?.min} max={bounds?.max} onChange={(e) => setDate(e.target.value)} />
          </label>
        )}
        {reportKey === 'monthly' && (
          <>
            <label className="trp-field">Month
              <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{String(m).padStart(2, '0')}</option>)}
              </select>
            </label>
            <label className="trp-field">Year
              <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
                {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
          </>
        )}
        {(reportKey === 'misspunch' || reportKey === 'user') && (
          <>
            <label className="trp-field">From
              <input type="date" value={start} min={bounds?.min} max={bounds?.max} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label className="trp-field">To
              <input type="date" value={end} min={bounds?.min} max={bounds?.max} onChange={(e) => setEnd(e.target.value)} />
            </label>
          </>
        )}
        {reportKey === 'user' && (
          <>
            <label className="trp-field">Search user
              <input placeholder="e.g. 470 or BALAJI" value={search} autoComplete="off" onChange={(e) => setSearch(e.target.value)} />
            </label>
            <label className="trp-field">Mode
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="detail">Detail (day by day)</option>
                <option value="summary">Summary (totals)</option>
              </select>
            </label>
          </>
        )}
        {reportKey === 'inactive' && (
          <label className="trp-field">No punch for (days)
            <input type="number" min={1} max={3650} className="trp-num" value={days} onChange={(e) => setDays(e.target.value)} />
          </label>
        )}
        {reportKey === 'misspunch' && (
          <label className="trp-field">User
            <select value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">All Users</option>
              {(meta?.users || []).map((u) => <option key={u.UserID} value={u.UserID}>{u.UserID} - {u.Name}</option>)}
            </select>
          </label>
        )}
        <label className="trp-field">Department
          <select value={deptId} onChange={(e) => setDeptId(e.target.value)}>
            <option value="">All Departments</option>
            {(meta?.departments || []).map((d) => <option key={d.DPTID} value={String(d.DPTID)}>{d.Name}</option>)}
          </select>
        </label>

        <div className="trp-actions">
          <button type="button" className="primary-button" disabled={!meta || loading} onClick={run}>{loading ? 'Running…' : 'Show'}</button>
          <button type="button" className="secondary-button" disabled={!hasResult || busy}
            onClick={() => download(excelBlob, `${reportKey}_${stamp}.xlsx`)}>Excel</button>
          {reportKey !== 'daily' && (
            <button type="button" className="secondary-button" disabled={!hasResult || busy}
              onClick={() => download(imageBlob, `${reportKey}_${stamp}.png`)}>Image</button>
          )}
          {storeWhatsAppAvailable() && (
            <span className="trp-wa">
              {reportKey === 'daily' ? (
                <WhatsAppShareButton label="WhatsApp · all stores" className="primary-button trp-wa-main"
                  title="Every store's image in one WhatsApp message" caption={`${caption} | ${daily?.period || date}`}
                  source="Time Report" disabled={!daily?.departments?.length} buildFiles={allStoreImages} />
              ) : (
                <WhatsAppShareButton label="WhatsApp · image" title="Send the report image" caption={caption}
                  source="Time Report" disabled={!hasResult}
                  buildFiles={async () => [{ name: `${reportKey}_${stamp}.png`, blob: await imageBlob() }]} />
              )}
              <WhatsAppShareButton label="WhatsApp · Excel" title="Send the Excel file" caption={caption}
                source="Time Report" disabled={!hasResult}
                buildFiles={async () => [{ name: `${reportKey}_${stamp}.xlsx`, blob: await excelBlob() }]} />
            </span>
          )}
        </div>
      </div>

      {error ? (
        <div className="status-line error">{error}</div>
      ) : !result ? (
        <div className="empty-state">Choose a report and its options, then press Show.</div>
      ) : (
        <div className="trp-result">
          {result.kind === 'daily' && <DailyView data={result.data} busy={busy}
            onImage={(d) => download(() => deptImageBlob(d.dpt_id), `${safeName(d.name)}_${date}.png`)}
            buildImage={async (d) => [{ name: `${safeName(d.name)}_${date}.png`, blob: await deptImageBlob(d.dpt_id) }]} />}
          {result.kind === 'monthly' && <MonthlyView data={result.data} />}
          {result.kind === 'misspunch' && <MissPunchView data={result.data} />}
          {result.kind === 'user' && <UserView data={result.data} />}
          {result.kind === 'inactive' && <InactiveView data={result.data} />}
        </div>
      )}
    </section>
  );
}

function MtdCell({ value, tone, first }) {
  const n = value ?? 0;
  return (
    <td className={`trp-mtd${first ? ' trp-mtd-sep' : ''}`}>
      {n > 0 ? <span className={`trp-pill trp-pill-${tone}`}>{n}</span> : <span className="trp-zero">–</span>}
    </td>
  );
}

function DailyView({ data, busy, onImage, buildImage }) {
  if (!data.departments.length) return <div className="empty-state">No attendance for that date.</div>;
  return (
    <div>
      <div className="trp-period">{data.period}</div>
      <div className="trp-subnote">
        Month-to-date for <b>{data.month_name}</b>: <b>MP Days</b> = miss-punch days · <b>&lt;8:30</b> = 8:00–8:29 days · <b>&lt;8:00</b> = under 8h.
      </div>
      {data.departments.map((dept) => (
        <div key={`${dept.dpt_id}-${dept.name}`}>
          <div className="trp-dept-head">
            <h3>{dept.name}</h3>
            <div className="trp-dept-actions">
              <button type="button" className="secondary-button" disabled={busy || dept.dpt_id === null} onClick={() => onImage(dept)}>Image</button>
              <WhatsAppShareButton label="WhatsApp" disabled={dept.dpt_id === null} title={`Send ${dept.name} image`}
                caption={`Time Report | ${dept.name} | ${data.period}`} source="Time Report" buildFiles={() => buildImage(dept)} />
            </div>
          </div>
          <div className="trp-tablewrap">
            <table className="trp-table trp-daily">
              <thead>
                <tr>
                  <th className="trp-left" rowSpan={2}>ID</th>
                  <th className="trp-left" rowSpan={2}>Name</th>
                  <th className="trp-center trp-grp" colSpan={8}>Punches</th>
                  <th className="trp-center" rowSpan={2}>Hrs</th>
                  <th className="trp-center trp-grp trp-mtd-sep" colSpan={3}>This month · to date</th>
                </tr>
                <tr>
                  {Array.from({ length: 8 }, (_, i) => <th key={i} className="trp-center">{i + 1}</th>)}
                  <th className="trp-center trp-mtd-sep" title="Miss-punch days this month">MP Days</th>
                  <th className="trp-center" title="Days worked 8:00–8:29 this month">&lt;8:30</th>
                  <th className="trp-center" title="Days worked under 8h this month">&lt;8:00</th>
                </tr>
              </thead>
              <tbody>
                {dept.rows.map((row, index) => (
                  <tr key={`${row.user_id}-${index}`} style={statusStyle(row.status_hex)}>
                    <td>{row.user_id}</td>
                    <td className="trp-left">{row.name.slice(0, 30)}{row.is_late && <span className="trp-badge">LATE</span>}</td>
                    {Array.from({ length: 8 }, (_, i) => <td key={i} className="trp-center">{row.punches[i] ?? ''}</td>)}
                    <td className="trp-center">{row.work_hm}</td>
                    <MtdCell value={row.mp_month} tone="mp" first />
                    <MtdCell value={row.below_830} tone="w830" />
                    <MtdCell value={row.below_800} tone="w800" />
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="trp-foot">
                  <td colSpan={14} className="trp-left">
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
  );
}

function MonthlyView({ data }) {
  if (!data.rows.length) return <div className="empty-state">No attendance for that month.</div>;
  return (
    <div>
      <div className="trp-period">{data.month_name}</div>
      <div className="trp-tablewrap">
        <table className="trp-table trp-muster">
          <thead>
            <tr>
              <th className="trp-left trp-fixed">Name</th>
              {data.days.map((d) => <th key={d} className="trp-center">{d}</th>)}
              {['P', 'Abs', 'Miss', 'Late', 'Total'].map((h) => <th key={h} className="trp-center">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, index) => (
              <tr key={`${row.user_id}-${index}`}>
                <td className="trp-left trp-fixed" title={`${row.user_id} · ${row.department}`}>{row.name}</td>
                {row.cells.map((cell, i) => <td key={i} className="trp-day" style={statusStyle(cell.hex)} title={cell.work_hm}>{cell.code}</td>)}
                <td className="trp-center">{row.present}</td>
                <td className="trp-center">{row.absent}</td>
                <td className="trp-center">{row.miss_punch}</td>
                <td className="trp-center">{row.late}</td>
                <td className="trp-center">{row.total_hm}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend items={data.legend} />
    </div>
  );
}

function FlatTable({ headers, rows, empty, render }) {
  return (
    <div className="trp-tablewrap">
      <table className="trp-table">
        <thead><tr>{headers.map(([label, cls]) => <th key={label} className={cls}>{label}</th>)}</tr></thead>
        <tbody>
          {rows.length ? rows.map(render) : <tr><td colSpan={headers.length} className="trp-center trp-zero">{empty}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function MissPunchView({ data }) {
  return (
    <div>
      <div className="trp-summary-line">Total miss-punch days: <b>{data.count}</b></div>
      <FlatTable
        headers={[['Date', 'trp-left'], ['UserID', 'trp-left'], ['Name', 'trp-left'], ['Department', 'trp-left'], ['Punches', 'trp-left'], ['#', 'trp-center'], ['Work', 'trp-center']]}
        rows={data.rows} empty="No miss-punch days in this range."
        render={(row, index) => (
          <tr key={`${row.user_id}-${index}`} style={statusStyle(row.status_hex)}>
            <td>{row.pdate_str}</td><td>{row.user_id}</td><td className="trp-left">{row.name}</td>
            <td className="trp-left">{row.department}</td><td className="trp-left">{row.punches.join(' | ')}</td>
            <td className="trp-center">{row.punch_count}</td><td className="trp-center">{row.work_hm}</td>
          </tr>
        )}
      />
      <Legend items={data.legend} />
    </div>
  );
}

function UserView({ data }) {
  if (data.mode === 'summary') {
    return (
      <div>
        <FlatTable
          headers={[['UserID', 'trp-left'], ['Name', 'trp-left'], ['Department', 'trp-left'], ...['Present', 'Full', 'Short', 'Low', 'Miss', 'Absent', 'Late', 'Total Hrs'].map((h) => [h, 'trp-center'])]}
          rows={data.rows} empty="No data for this selection."
          render={(row, index) => (
            <tr key={`${row.user_id}-${index}`}>
              <td>{row.user_id}</td><td className="trp-left">{row.name}</td><td className="trp-left">{row.department}</td>
              {[row.present, row.full, row.short, row.low, row.miss_punch, row.absent, row.late, row.total_hm].map((v, i) => <td key={i} className="trp-center">{v}</td>)}
            </tr>
          )}
        />
        <Legend items={data.legend} />
      </div>
    );
  }
  return (
    <div>
      <FlatTable
        headers={[['Date', 'trp-left'], ['UserID', 'trp-left'], ['Name', 'trp-left'], ['Punches', 'trp-left'], ['Work', 'trp-center'], ['Late', 'trp-center']]}
        rows={data.rows} empty="No data for this selection."
        render={(row, index) => (
          <tr key={`${row.user_id}-${index}`} style={statusStyle(row.status_hex)}>
            <td>{row.pdate_str}</td><td>{row.user_id}</td><td className="trp-left">{row.name}</td>
            <td className="trp-left">{row.punches.join(' | ')}</td><td className="trp-center">{row.work_hm}</td>
            <td className="trp-center">{row.late_in || ''}</td>
          </tr>
        )}
      />
      <Legend items={data.legend} />
    </div>
  );
}

function InactiveView({ data }) {
  return (
    <div>
      <div className="trp-summary-line">Inactive users found: <b>{data.count}</b></div>
      <FlatTable
        headers={[['UserID', 'trp-left'], ['Name', 'trp-left'], ['Department', 'trp-left'], ['Join Date', 'trp-center'], ['Last Punch', 'trp-center'], ['Days Since', 'trp-center']]}
        rows={data.rows} empty="No inactive users."
        render={(row, index) => (
          <tr key={`${row.user_id}-${index}`} style={row.last_seen === 'Never' ? { background: 'var(--nx-danger-sunk)', color: 'var(--nx-danger-ink)' } : undefined}>
            <td>{row.user_id}</td><td className="trp-left">{row.name}</td><td className="trp-left">{row.department}</td>
            <td className="trp-center">{row.join_dt}</td><td className="trp-center">{row.last_seen}</td><td className="trp-center">{row.days_since}</td>
          </tr>
        )}
      />
    </div>
  );
}
