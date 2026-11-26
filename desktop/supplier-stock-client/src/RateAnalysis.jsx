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
  { id: 'nmw', label: 'NMW vs SMS/Success (Super Admin)' },
  { id: 'nmwActivity', label: 'NMW 90-Day Activity (Super Admin)' },
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

// NMW vs SMS/Success variance -- step 1: upload a reference Excel of product
// names, review every stored NMW variant (name/MRP/unit) per name and pick the
// ones that are really the product meant (never auto-merged - the NAN PRO
// false-match lesson), step 2: pick ONE tenant and generate its own report.
function NmwVarianceTab({ session }) {
  const [source, setSource] = useState('upload'); // 'upload' | 'nmw'
  const [file, setFile] = useState(null);
  const [searchText, setSearchText] = useState('');
  const [days, setDays] = useState(90);
  const [tenant, setTenant] = useState('SMS');
  const [picking, setPicking] = useState(false);
  const [picker, setPicker] = useState(null); // {window_days, results:[{query, variants}]}
  const [selected, setSelected] = useState({}); // `${query}|${idx}` -> variant
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [result, setResult] = useState(null);

  const autoSelect = (results) => {
    const sel = {};
    (results || []).forEach((r) => { if (r.variants.length === 1) sel[`${r.query}|0`] = r.variants[0]; });
    return sel;
  };

  const upload = async () => {
    if (!file) { setError('Choose a reference Excel file first (needs a "Product Name" column).'); return; }
    setError(''); setPicking(true); setResult(null);
    try {
      const res = await api.rateEngineVariantsUpload(file, days || 90, session);
      setPicker(res);
      setSelected(autoSelect(res.results));
    } catch (err) {
      setError(err.message || 'Upload failed');
    } finally {
      setPicking(false);
    }
  };

  // Source the reference list straight from NMW's own purchase history
  // instead of an external file: build up a list of product names first
  // (add as many as needed), then submit the whole list in one go, the same
  // way an uploaded file's rows would have produced it.
  const [pendingNames, setPendingNames] = useState([]);
  const addPendingName = (name) => {
    const q = (name ?? searchText).trim();
    if (!q) return;
    setPendingNames((ns) => (ns.includes(q) ? ns : [...ns, q]));
    setSearchText('');
    setSuggestions([]);
  };
  const removePendingName = (q) => setPendingNames((ns) => ns.filter((n) => n !== q));

  // Live typeahead: as the user types, show real NMW product names (not a
  // blind free-text box) so they pick an exact stored name instead of
  // guessing one that might substring-match the wrong product.
  const [suggestions, setSuggestions] = useState([]);
  const [suggestLoading, setSuggestLoading] = useState(false);
  useEffect(() => {
    const q = searchText.trim();
    if (q.length < 2) { setSuggestions([]); return; }
    let cancelled = false;
    setSuggestLoading(true);
    const t = setTimeout(() => {
      api.rateEngineProductsSuggest(q, session)
        .then((res) => { if (!cancelled) setSuggestions(res?.names || []); })
        .catch(() => { if (!cancelled) setSuggestions([]); })
        .finally(() => { if (!cancelled) setSuggestLoading(false); });
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [searchText, session]);

  const searchNmw = async () => {
    if (searchText.trim()) addPendingName();
    const names = searchText.trim() ? [...pendingNames, searchText.trim()] : pendingNames;
    if (!names.length) { setError('Add at least one product name first.'); return; }
    setError(''); setPicking(true);
    try {
      const results = [];
      for (const q of names) {
        const res = await api.rateEngineVariantsSearch(q, days || 90, session);
        results.push(...(res.results || []));
      }
      setPicker((p) => ({ window_days: days || 90, results: p ? [...p.results.filter((r) => !names.includes(r.query)), ...results] : results }));
      setSelected((s) => ({ ...s, ...autoSelect(results) }));
      setPendingNames([]);
    } catch (err) {
      setError(err.message || 'Search failed');
    } finally {
      setPicking(false);
    }
  };

  const toggle = (query, idx, variant) => {
    const key = `${query}|${idx}`;
    setSelected((s) => {
      const next = { ...s };
      if (next[key]) delete next[key]; else next[key] = variant;
      return next;
    });
  };

  const chosen = Object.values(selected);

  const generate = async (fmt) => {
    if (!chosen.length) { setError('Select at least one NMW variant first.'); return; }
    setError('');
    const body = { tenant, days: days || 90, variants: chosen.map((v) => ({ product_name: v.product_name, mrp: v.mrp, sale_unit: v.sale_unit, purchase_unit: v.purchase_unit })) };
    if (fmt === 'xlsx') {
      setExporting(true);
      try {
        const { blob, filename } = await api.rateEngineVarianceReportExcel(body, session);
        saveBlob(blob, filename);
      } catch (err) {
        setError(err.message || 'Export failed');
      } finally {
        setExporting(false);
      }
      return;
    }
    setLoading(true);
    try {
      const res = await api.rateEngineVarianceReport(body, session);
      setResult(res);
    } catch (err) {
      setError(err.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  const asSheets = result && {
    title: `NMW vs ${result.tenant} - Rate Variance (${result.batch_wise ? 'batch-wise' : 'bill-wise'})`,
    notes: [
      `YTD total loss: ${result.ytd_total_loss?.toLocaleString('en-IN')}. ${result.unit_mismatch_count} line(s) unit-mismatched, ${result.unit_unknown_count} line(s) unit unknown (not assumed equal). ${result.unmatched_mrp_lines} line(s) matched by name but not by MRP (left out).`,
    ],
    sheets: [
      { name: 'Top 25 Products', columns: [
        { key: 'product_code', label: 'Code' }, { key: 'product_name', label: 'Product', width: 34 },
        { key: 'total_loss', label: 'Total Loss', format: 'money' },
      ], rows: result.top_products.map((p) => ({ product_code: p.product_code, product_name: p.product_name, total_loss: p.total_loss })) },
      { name: 'Monthwise', columns: [
        { key: 'ym', label: 'Month' }, { key: 'store', label: 'Store' },
        { key: 'qty', label: 'Qty', format: 'num1' }, { key: 'loss', label: 'Loss', format: 'money' },
      ], rows: result.monthwise },
      { name: `${(result.group_field || 'bill_no').replace('_', ' ')}-wise Detail`, columns: [
        { key: 'bill_no', label: 'Bill No' }, { key: 'batch_code', label: 'Batch' }, { key: 'grn_date', label: 'Date', format: 'date' },
        { key: 'store', label: 'Store' }, { key: 'product_code', label: 'Code' }, { key: 'product_name', label: 'Product', width: 34 },
        { key: 'mrp', label: 'MRP', format: 'money' }, { key: 'qty', label: 'Qty', format: 'num1' },
        { key: 'actual_cost', label: 'Actual Cost', format: 'money' }, { key: 'nmw_low_rate', label: 'NMW Low Rate', format: 'money' },
        { key: 'nmw_rate_source', label: 'NMW Rate Source', width: 30 }, { key: 'unit', label: 'Unit' },
        { key: 'unit_mismatch', label: 'Unit Mismatch?' }, { key: 'loss', label: 'Loss', format: 'money' },
      ], rows: result.bill_rows },
    ],
  };

  return (
    <>
      <div className="rta-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={source === 'upload'} className={`rta-chip${source === 'upload' ? ' active' : ''}`} onClick={() => setSource('upload')}>Upload reference Excel</button>
        <button type="button" role="tab" aria-selected={source === 'nmw'} className={`rta-chip${source === 'nmw' ? ' active' : ''}`} onClick={() => setSource('nmw')}>Pick straight from NMW</button>
      </div>

      {source === 'upload' && (
        <div className="trp-bar rta-bar">
          <label className="trp-field rta-grow">Reference Excel (column "Product Name")
            <input type="file" accept=".xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
          <NumField label="Source window (days)" value={days} onChange={setDays} max={365} />
          <div className="trp-actions">
            <button type="button" className="secondary-button" disabled={picking || !file} onClick={upload}>
              {picking ? 'Reading NMW…' : '1. Upload & find NMW variants'}
            </button>
          </div>
        </div>
      )}

      {source === 'nmw' && (
        <>
          <div className="trp-bar rta-bar">
            <label className="trp-field rta-grow rta-typeahead">Search NMW products (pick from the list, or press Enter to add as typed)
              <input className="rta-cell" value={searchText} onChange={(e) => setSearchText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addPendingName(); } }} placeholder="Type at least 2 letters, e.g. OMEE" autoComplete="off" />
              {searchText.trim().length >= 2 && (
                <div className="rta-suggest">
                  {suggestLoading && <div className="rta-suggest-row rta-suggest-empty">Searching NMW…</div>}
                  {!suggestLoading && suggestions.length === 0 && <div className="rta-suggest-row rta-suggest-empty">No NMW product matches "{searchText.trim()}"</div>}
                  {!suggestLoading && suggestions.map((name) => (
                    <button key={name} type="button" className="rta-suggest-row" onClick={() => addPendingName(name)}>{name}</button>
                  ))}
                </div>
              )}
            </label>
            <NumField label="Source window (days)" value={days} onChange={setDays} max={365} />
            <div className="trp-actions">
              <button type="button" className="primary-button" disabled={picking || (!pendingNames.length && !searchText.trim())} onClick={searchNmw}>
                {picking ? 'Searching NMW…' : `Submit & fetch (${pendingNames.length + (searchText.trim() ? 1 : 0)})`}
              </button>
            </div>
          </div>
          {pendingNames.length > 0 && (
            <div className="rta-chips">
              {pendingNames.map((n) => (
                <button key={n} type="button" className="rta-chip active" title="Remove" onClick={() => removePendingName(n)}>{n} ✕</button>
              ))}
            </div>
          )}
        </>
      )}

      {picker && (
        <div className="trp-tablewrap rta-match">
          <table className="trp-table">
            <thead><tr><th className="trp-left">Reference name</th><th className="trp-left">NMW variant found (select the real one(s))</th></tr></thead>
            <tbody>
              {picker.results.map((r) => (
                <tr key={r.query}>
                  <td className="trp-left">{r.query}</td>
                  <td className="trp-left">
                    {r.variants.length === 0 && <span className="rta-warn">no NMW purchase in the last {picker.window_days} days</span>}
                    {r.variants.map((v, idx) => {
                      const key = `${r.query}|${idx}`;
                      return (
                        <label key={key} className="rta-picker-row">
                          <input type="checkbox" checked={!!selected[key]} onChange={() => toggle(r.query, idx, v)} />
                          <span>{v.product_name} · MRP {v.mrp ?? '-'} · unit {v.sale_unit || v.purchase_unit || '?'} · cost {v.min_cost}–{v.max_cost} ({v.line_count} lines)</span>
                        </label>
                      );
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {picker && (
        <div className="trp-bar rta-bar">
          <label className="trp-field">Target tenant
            <select value={tenant} onChange={(e) => setTenant(e.target.value)}>
              <option value="SMS">SMS (bill-wise)</option>
              <option value="SUCCESS">Success (batch-wise)</option>
            </select>
          </label>
          <div className="trp-actions">
            <button type="button" className="primary-button" disabled={loading || !chosen.length} onClick={() => generate('json')}>
              {loading ? 'Working…' : `2. Generate ${tenant} report`}
            </button>
            <button type="button" className="secondary-button" disabled={exporting || !chosen.length} onClick={() => generate('xlsx')}>
              {exporting ? 'Preparing…' : 'Download Excel'}
            </button>
          </div>
        </div>
      )}

      {error && <div className="status-line error">{error}</div>}
      {asSheets && <ResultView result={asSheets} onExcel={() => generate('xlsx')} busy={exporting} />}
    </>
  );
}

// NMW 90-day batch-wise purchase activity: cost/PTR/MRP/unit for every
// product with a real transaction in the window, even if current stock = 0
// (this is a transaction report, not a stock snapshot).
function NmwActivityTab({ session }) {
  const [days, setDays] = useState(90);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const fetchIt = async () => {
    setError(''); setLoading(true);
    try {
      setResult(await api.rateEngineNmwActivity(days || 90, session));
    } catch (err) {
      setError(err.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  const exportExcel = async () => {
    setExporting(true);
    try {
      const { blob, filename } = await api.rateEngineNmwActivityExcel(days || 90, session);
      saveBlob(blob, filename);
    } catch (err) {
      setError(err.message || 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <div className="trp-bar rta-bar">
        <NumField label="Window (days)" value={days} onChange={setDays} max={365} />
        <div className="trp-actions">
          <button type="button" className="primary-button" disabled={loading} onClick={fetchIt}>
            {loading ? 'Fetching NMW…' : 'Fetch NMW activity'}
          </button>
        </div>
      </div>
      {error && <div className="status-line error">{error}</div>}
      {result && <ResultView result={result} onExcel={exportExcel} busy={exporting} />}
      {!result && !loading && <div className="empty-state">Fetch every NMW batch-wise purchase (cost, PTR, MRP, unit) in the window, including products currently at stock = 0.</div>}
    </>
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

      {tab === 'nmw' && <NmwVarianceTab session={session} />}
      {tab === 'nmwActivity' && <NmwActivityTab session={session} />}

      {!['nmw', 'nmwActivity'].includes(tab) && error && <div className="status-line error">{error}</div>}
      {!['nmw', 'nmwActivity'].includes(tab) && (result ? <ResultView result={result} onExcel={exportExcel} busy={exporting} />
        : !loading && <div className="empty-state">{tab === 'quote'
          ? 'Paste the quoted list, press "Match products", check the matches, then "Compare & order".'
          : 'Choose suppliers and press Show.'}</div>)}
    </section>
  );
}
