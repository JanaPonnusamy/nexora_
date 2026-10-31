// Rate Analysis -- supplier purchase-rate tools over /api/rate-analysis/*:
//   * Quote Compare & Order: paste a supplier's quoted list (Product, MRP, PTR),
//     confirm the product match, then compare with every store's last PTR and
//     get a 1-month order in strips (sales / days x 30, stock not deducted).
//   * Fast Movers: fast-moving products of chosen suppliers with the least
//     rate every supplier billed recently.
//   * Rate Difference: each bill vs the chain least rate (extra paid).
// Every result comes back as {title, notes, sheets}; one grid renders it and
// the same request with ?format=xlsx downloads it as Excel.
import { useEffect, useMemo, useState } from 'react';
import { api } from './api/client.js';
import { fmtCell, parseQuoteLine, toNum } from './rateAnalysisView.js';

const TABS = [
  { id: 'quote', label: 'Quote Compare & Order' },
  { id: 'fast', label: 'Fast Movers - Least Rate' },
  { id: 'diff', label: 'Rate Difference' },
];
const MAX_ROWS = 1000;
const iso = (d) => d.toISOString().slice(0, 10);

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

const num = toNum;

function ResultView({ result, onExcel, busy }) {
  const [sheetIdx, setSheetIdx] = useState(0);
  const [filter, setFilter] = useState('');
  useEffect(() => { setSheetIdx(0); setFilter(''); }, [result]);
  const sheet = result.sheets[sheetIdx] || result.sheets[0];
  const rows = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return sheet.rows;
    return sheet.rows.filter((r) => r._total || sheet.columns.some((c) => String(r[c.key] ?? '').toLowerCase().includes(q)));
  }, [sheet, filter]);
  const cols = sheet.columns;
  const grouped = cols.some((c) => c.group);
  const groupRow = [];
  if (grouped) {
    for (let i = 0; i < cols.length;) {
      const g = cols[i].group;
      let n = 1;
      while (g && i + n < cols.length && cols[i + n].group === g) n += 1;
      groupRow.push({ g, n, col: cols[i] });
      i += n;
    }
  }
  const right = (c) => ['money', 'int', 'num1', 'pct'].includes(c.format);
  return (
    <div className="trp-result">
      <div className="rta-result-head">
        <div>
          <div className="trp-period">{result.title}</div>
          {(result.notes || []).map((n) => <div key={n} className="trp-subnote rta-note">{n}</div>)}
        </div>
        <button type="button" className="primary-button" disabled={busy} onClick={onExcel}>{busy ? 'Preparing…' : 'Download Excel'}</button>
      </div>
      <div className="rta-sheetbar">
        {result.sheets.length > 1 && result.sheets.map((s, i) => (
          <button key={s.name} type="button" className={`rta-chip${i === sheetIdx ? ' active' : ''}`} onClick={() => setSheetIdx(i)}>
            {s.name} <span className="rta-count">{s.rows.length}</span>
          </button>
        ))}
        <input className="rta-filter" placeholder="Filter rows…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        {rows.length > MAX_ROWS && <span className="trp-subnote">Showing {MAX_ROWS} of {rows.length} rows - Excel has all.</span>}
      </div>
      <div className="trp-tablewrap">
        <table className="trp-table rta-table">
          <thead>
            {grouped && (
              <tr>
                {groupRow.map(({ g, n, col }) => (g
                  ? <th key={`g-${col.key}`} colSpan={n} className="trp-center rta-group">{g}</th>
                  : <th key={`g-${col.key}`} rowSpan={2} className={right(col) ? 'rta-num' : 'trp-left'}>{col.label}</th>))}
              </tr>
            )}
            <tr>
              {cols.filter((c) => !grouped || c.group).map((c) => (
                <th key={c.key} className={right(c) ? 'rta-num' : 'trp-left'}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, MAX_ROWS).map((r, i) => (
              <tr key={i} className={r._total ? 'trp-foot' : undefined}>
                {cols.map((c) => {
                  const flag = r._flags?.[c.key];
                  return (
                    <td key={c.key} className={`${right(c) ? 'rta-num' : 'trp-left'}${flag ? ` rta-${flag}` : ''}`} title={c.width > 30 ? String(r[c.key] ?? '') : undefined}>
                      {fmtCell(r[c.key], c.format)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SupplierPicker({ suppliers, selected, onChange, loading, emptyMeansAll }) {
  const [q, setQ] = useState('');
  const list = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? suppliers.filter((s) => s.name.toLowerCase().includes(t) || (s.gst || '').toLowerCase().includes(t)) : suppliers;
  }, [suppliers, q]);
  const toggle = (key) => onChange(selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key]);
  const byKey = useMemo(() => Object.fromEntries(suppliers.map((s) => [s.key, s])), [suppliers]);
  return (
    <div className="rta-picker">
      <div className="rta-picker-head">
        <strong>Suppliers</strong>
        <span className="trp-subnote">{selected.length ? `${selected.length} chosen` : (emptyMeansAll ? 'none chosen = all suppliers' : 'choose one or more')}</span>
        {selected.length > 0 && <button type="button" className="secondary-button" onClick={() => onChange([])}>Clear</button>}
      </div>
      {selected.length > 0 && (
        <div className="rta-chips">
          {selected.map((k) => (
            <button key={k} type="button" className="rta-chip active" title="Remove" onClick={() => toggle(k)}>{byKey[k]?.name || k} ✕</button>
          ))}
        </div>
      )}
      <input className="rta-filter" placeholder={loading ? 'Loading suppliers…' : 'Search supplier or GST…'} value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="rta-picker-list">
        {list.slice(0, 200).map((s) => (
          <label key={s.key} className="rta-picker-row">
            <input type="checkbox" checked={selected.includes(s.key)} onChange={() => toggle(s.key)} />
            <span className="rta-picker-name">{s.name}</span>
            <span className="rta-picker-meta">{s.bills} bills · {s.stores.join(' ')}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function NumField({ label, value, onChange, min = 1, max = 730 }) {
  return (
    <label className="trp-field">{label}
      <input type="number" className="trp-num" min={min} max={max} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export default function RateAnalysis({ session, settings }) {
  const tenantId = settings?.tenantId || session?.user?.tenant_id || '';
  const [tab, setTab] = useState('quote');
  const [suppliers, setSuppliers] = useState([]);
  const [supLoading, setSupLoading] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [results, setResults] = useState({});
  const [lastRequest, setLastRequest] = useState({});

  // quote tab
  const [quoteText, setQuoteText] = useState('');
  const [quoteLines, setQuoteLines] = useState([]);
  const [compareDays, setCompareDays] = useState(90);
  const [salesDays, setSalesDays] = useState(90);
  const [orderDays, setOrderDays] = useState(30);
  // fast movers tab
  const [fastSup, setFastSup] = useState([]);
  const [rateDays, setRateDays] = useState(30);
  const [minStores, setMinStores] = useState(3);
  const [fastSalesDays, setFastSalesDays] = useState(90);
  const [excludeText, setExcludeText] = useState('');
  // rate difference tab
  const [diffSup, setDiffSup] = useState([]);
  const today = useMemo(() => new Date(), []);
  const [dateFrom, setDateFrom] = useState(iso(new Date(today.getFullYear(), today.getMonth() - 2, 1)));
  const [dateTo, setDateTo] = useState(iso(today));
  const [gapPct, setGapPct] = useState(20);

  const [supRequested, setSupRequested] = useState(false);
  useEffect(() => {
    if (!tenantId || tab === 'quote' || supRequested) return;
    setSupRequested(true);
    setSupLoading(true);
    api.rateSuppliers(tenantId, 90, session)
      .then((res) => setSuppliers(res?.suppliers || []))
      .catch((err) => setError(err.message || 'Could not load suppliers'))
      .finally(() => setSupLoading(false));
  }, [tab, tenantId, session, supRequested]);

  const run = async (kind, body) => {
    setError('');
    setLoading(true);
    try {
      const res = await api.rateReport(kind, body, session);
      setResults((r) => ({ ...r, [tab]: res }));
      setLastRequest((r) => ({ ...r, [tab]: { kind, body } }));
    } catch (err) {
      setError(err.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  const exportExcel = async () => {
    const req = lastRequest[tab];
    if (!req) return;
    setExporting(true);
    try {
      const { blob, filename } = await api.rateReportExcel(req.kind, req.body, session);
      saveBlob(blob, filename);
    } catch (err) {
      setError(err.message || 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  const matchQuote = async () => {
    const parsed = quoteText.split(/\r?\n/).map(parseQuoteLine).filter(Boolean);
    if (!parsed.length) { setError('Paste the quoted products first (Product, MRP, PTR - one per line).'); return; }
    setError('');
    setLoading(true);
    try {
      const res = await api.rateQuoteMatch({ tenant_id: tenantId, lines: parsed.map((p) => ({ text: p.text, mrp: p.mrp })) }, session);
      setQuoteLines(parsed.map((p, i) => {
        const cands = res.lines?.[i]?.candidates || [];
        return { ...p, candidates: cands, key: cands[0]?.key || '' };
      }));
    } catch (err) {
      setError(err.message || 'Match failed');
    } finally {
      setLoading(false);
    }
  };

  const updateLine = (i, patch) => setQuoteLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  const result = results[tab];
  const days = (v, d) => Math.max(1, Number(v) || d);

  if (!tenantId) {
    return (
      <section className="screen-panel trp-screen">
        <header className="screen-header"><div><h2>Rate Analysis</h2></div></header>
        <div className="status-line error">No tenant selected for this login.</div>
      </section>
    );
  }

  return (
    <section className="screen-panel trp-screen rta-screen">
      <header className="screen-header">
        <div><h2>Rate Analysis</h2><p>Supplier rates across all stores - quotes, least rates and extra paid.</p></div>
      </header>
      <div className="rta-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={`rta-chip${tab === t.id ? ' active' : ''}`}
            onClick={() => { setTab(t.id); setError(''); }}>{t.label}</button>
        ))}
      </div>

      {tab === 'quote' && (
        <div className="trp-bar rta-bar">
          <label className="trp-field rta-grow">Quoted products - one per line: Product, MRP, PTR (paste straight from Excel)
            <textarea className="rta-text" rows={6} value={quoteText} onChange={(e) => setQuoteText(e.target.value)}
              placeholder={'SPASMONIL\t33.00\t11.65\nBETAMOX LB\t177.00\t25.50\nOKACET 20.16 5.05'} />
          </label>
          <NumField label="Compare rates (days)" value={compareDays} onChange={setCompareDays} />
          <NumField label="Sales basis (days)" value={salesDays} onChange={setSalesDays} />
          <NumField label="Order for (days)" value={orderDays} onChange={setOrderDays} max={365} />
          <div className="trp-actions">
            <button type="button" className="secondary-button" disabled={loading} onClick={matchQuote}>{loading && !quoteLines.length ? 'Matching…' : '1. Match products'}</button>
            <button type="button" className="primary-button" disabled={loading || !quoteLines.some((l) => l.key)}
              onClick={() => run('quote/compare', {
                tenant_id: tenantId,
                compare_days: days(compareDays, 90), sales_days: days(salesDays, 90), order_days: days(orderDays, 30),
                lines: quoteLines.filter((l) => l.key).map((l) => ({ label: l.text, key: l.key, mrp: l.mrp, ptr: l.ptr })),
              })}>{loading && quoteLines.length ? 'Working…' : '2. Compare & order'}</button>
          </div>
        </div>
      )}
      {tab === 'quote' && quoteLines.length > 0 && (
        <div className="trp-tablewrap rta-match">
          <table className="trp-table">
            <thead><tr><th>#</th><th className="trp-left">Quoted</th><th className="rta-num">MRP</th><th className="rta-num">PTR</th><th className="trp-left">Matched product (check / change)</th></tr></thead>
            <tbody>
              {quoteLines.map((l, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td className="trp-left">{l.text}</td>
                  <td className="rta-num"><input className="rta-cell" value={l.mrp ?? ''} onChange={(e) => updateLine(i, { mrp: num(e.target.value) })} /></td>
                  <td className="rta-num"><input className="rta-cell" value={l.ptr ?? ''} onChange={(e) => updateLine(i, { ptr: num(e.target.value) })} /></td>
                  <td className={`trp-left${l.key ? '' : ' rta-warn'}`}>
                    <select value={l.key} onChange={(e) => updateLine(i, { key: e.target.value })}>
                      <option value="">- not matched / skip -</option>
                      {l.candidates.map((c) => (
                        <option key={c.key} value={c.key}>{c.label} · MRP {c.mrp ?? '-'} · pack {c.packs} · {c.stores.length} stores</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'fast' && (
        <div className="trp-bar rta-bar">
          <SupplierPicker suppliers={suppliers} selected={fastSup} onChange={setFastSup} loading={supLoading} />
          <div className="rta-side">
            <NumField label="Sales basis (days)" value={fastSalesDays} onChange={setFastSalesDays} />
            <NumField label="Least rate within (days)" value={rateDays} onChange={setRateDays} max={365} />
            <NumField label="Sold in at least (stores)" value={minStores} onChange={setMinStores} max={50} />
            <label className="trp-field">Skip products (one per line, optional)
              <textarea className="rta-text rta-small" rows={3} value={excludeText} onChange={(e) => setExcludeText(e.target.value)} />
            </label>
            <button type="button" className="primary-button" disabled={loading || !fastSup.length}
              onClick={() => run('fast-movers', {
                tenant_id: tenantId, supplier_keys: fastSup, sales_days: days(fastSalesDays, 90), rate_days: days(rateDays, 30),
                min_stores: days(minStores, 3), exclude_names: excludeText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
              })}>{loading ? 'Working… (about 30s)' : 'Show fast movers'}</button>
          </div>
        </div>
      )}

      {tab === 'diff' && (
        <div className="trp-bar rta-bar">
          <SupplierPicker suppliers={suppliers} selected={diffSup} onChange={setDiffSup} loading={supLoading} emptyMeansAll />
          <div className="rta-side">
            <label className="trp-field">From<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
            <label className="trp-field">To<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
            <NumField label="To verify above (% gap)" value={gapPct} onChange={setGapPct} max={500} />
            <button type="button" className="primary-button" disabled={loading}
              onClick={() => run('rate-difference', {
                tenant_id: tenantId, supplier_keys: diffSup, date_from: dateFrom, date_to: dateTo, check_gap_pct: Number(gapPct) || 20,
              })}>{loading ? 'Working…' : 'Show rate difference'}</button>
          </div>
        </div>
      )}

      {error && <div className="status-line error">{error}</div>}
      {result ? <ResultView result={result} onExcel={exportExcel} busy={exporting} />
        : !loading && <div className="empty-state">{tab === 'quote'
          ? 'Paste the quoted list, press "Match products", check the matches, then "Compare & order".'
          : 'Choose suppliers and press Show.'}</div>}
    </section>
  );
}
