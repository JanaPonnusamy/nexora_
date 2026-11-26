// Non-Moving Stock -- read-only analysis workspace over /api/non-moving-analysis:
//   * Own Store Analysis: every in-stock product with its last valid sale,
//     age class, stock value and expiry, server-side filtered / sorted / paged.
//   * Other Stores Analysis: products idle here, compared with every mapped
//     store (product_mapping, same as Procurement's Other-stores panel).
//   * Transfer Opportunities: recommendations only -- nothing is moved; a
//     proposal is an Excel for the existing authorised transfer process.
//   * Stock Value & Expiry Risk: classification value, store comparison,
//     monthly movement, expiry risk.
// The detail panel reuses Procurement's Monthly Trend / Purchase / Sales
// panels (ui.IntelPanel = OrderIntelligence) and the All Stores chart.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AgGridReact } from 'ag-grid-react';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import { api } from './api/client.js';
import { StoreTrendsPanel } from './storeTrends.jsx';
import { TrendBars, TrendTip, fmtMonthLabel, trendMax } from './trendChart.jsx';
import {
  AGE_PRESETS, CLASSES, CLASS_BY_KEY, COMPARATORS, DEFAULT_SHOW_ID, FLAG_TEXT, NON_MOVING_KEYS, OWN_COLS_BY_KEY,
  OWN_COLS_DEFAULT_ORDER, OWN_COLS_MANDATORY, OWN_COL_GROUPS, SECTIONS, SHOW_PRESETS, SHOW_PRESET_BY_ID,
  activeFilterCount, barPct, filtersEqual, fmtCompact, fmtDate, fmtDays, fmtMoney, fmtQty, inReview, ownParams,
  readColSettings, readReview, resolveOwnCols, toggleReview, writeColSettings, writeReview,
} from './nonMovingView.js';

// Midnight Glass skin for the Own Store AG Grid -- mirrors the .nms-table
// CSS custom properties (dark navy canvas, 12-13.5px type, ~32px rows) rather
// than AG Grid's default look. Dark/light is fixed to dark here because this
// desktop client's data screens are dark-only (see styles.css
// :root[data-theme="dark"] -- Non-Moving Stock does not expose a light mode).
//
// AG Grid is pinned to v32.3.9 (pre-Theming-API) -- v36's Theming API
// (`theme={...}`, `themeQuartz.withParams(...)`) emits CSS using native
// nesting (`&` selectors), which Electron 22's Chromium 108 cannot parse
// (nesting landed in Chromium 112). That silently dropped core layout rules
// (`.ag-root.ag-layout-normal { flex: 1 1 auto }`), collapsing the whole grid
// to a ~10px sliver -- confirmed live via CDP (CSS.getMatchedStylesForNode
// showed the nested block as inert). v32 ships plain, already-compiled CSS
// (ag-theme-quartz.css, imported above) with no nesting, so this skin is
// applied the old way: override that theme's real `--ag-*` custom
// properties, scoped to this grid's wrapper, instead of calling
// themeQuartz.withParams(...). See nms-aggrid-wrap's ag-theme-quartz rules
// in styles.css for the actual --ag-* overrides (border-color, hover, etc).

const PAGE_SIZE = 200;
const TREND_FIT = { fetch: 6, min: 4, max: 5 };
const DETAIL_TABS = [
  { id: 'summary', label: 'Summary' },
  { id: 'sales', label: 'Sales' },
  { id: 'purchase', label: 'Purchase / GRN' },
  { id: 'batches', label: 'Batches & Expiry' },
  { id: 'stores', label: 'Other Stores' },
  { id: 'transfers', label: 'Transfers' },
];
const ROW_ACTIONS = [
  { tab: 'summary', label: 'View product details' },
  { tab: 'sales', label: 'View sales history' },
  { tab: 'purchase', label: 'View purchase / GRN history' },
  { tab: 'batches', label: 'View batch / expiry details' },
  { tab: 'stores', label: 'Check other stores' },
];

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function stamp(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit', hour12: true });
}

function ClassBadge({ value, label }) {
  const c = CLASS_BY_KEY[value];
  return <span className={`nms-cls nms-cls--${c?.tone || 'none'}`}>{label || c?.label || value || '—'}</span>;
}

function ExpiryBadge({ value }) {
  const tone = value === 'Expired' ? 'bad' : value === 'Near expiry' ? 'warn' : value === 'OK' ? 'ok' : 'muted';
  return <span className={`nms-exp nms-exp--${tone}`}>{value || '—'}</span>;
}

function Kpi({ label, value, sub, tone }) {
  return (
    <div className={`nms-kpi${tone ? ` nms-kpi--${tone}` : ''}`}>
      <span className="nms-kpi-label">{label}</span>
      <strong className="nms-kpi-value">{value}</strong>
      {sub && <span className="nms-kpi-sub">{sub}</span>}
    </div>
  );
}

// Sortable header cell (server-side sort). `groupStart` draws the stronger
// separator between logical column groups (Column Settings).
function Th({ col, sort, onSort, className = '' }) {
  const groupCls = col.groupStart ? ' nms-colgroup-start' : '';
  if (!col.sort) return <th className={`${col.num ? 'nms-num' : 'trp-left'}${groupCls} ${className}`} style={col.w ? { width: col.w } : undefined}>{col.label}</th>;
  const active = sort.key === col.sort;
  return (
    <th className={`nms-sortable ${col.num ? 'nms-num' : 'trp-left'}${groupCls} ${className}`} style={col.w ? { width: col.w } : undefined}
      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onClick={() => onSort(col.sort)}>
      {col.label}<span className="nms-sort">{active ? (sort.dir === 'asc' ? '▲' : '▼') : ''}</span>
    </th>
  );
}

function Pager({ page, total, pageSize, onPage, extra }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="nms-pager">
      <span>{fmtQty(from)}–{fmtQty(to)} of <b>{fmtQty(total)}</b></span>
      <button type="button" className="secondary-button" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹ Prev</button>
      <span>Page {page} / {pages}</span>
      <button type="button" className="secondary-button" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next ›</button>
      {extra}
    </div>
  );
}

// Arrow-key row navigation for a grid body (the wrapper is focusable).
function useGridKeys(count, selected, setSelected, onEnter, onExtra) {
  return (e) => {
    if (!count) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const next = Math.min(count - 1, Math.max(0, (selected < 0 ? -1 : selected) + (e.key === 'ArrowDown' ? 1 : -1)));
      setSelected(next);
    } else if (e.key === 'Enter' && selected >= 0) {
      e.preventDefault();
      onEnter?.(selected);
    } else {
      onExtra?.(e);
    }
  };
}

function useScrollSelected(ref, selected) {
  useEffect(() => {
    ref.current?.querySelector(`tr[data-idx="${selected}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [ref, selected]);
}

// ---------------------------------------------------------------------------
// Grouped bars (the Monthly Trend renderer) -- one group per label.
function BarChart({ groups, series, tipRows, height = 150, onPick }) {
  const [tip, setTip] = useState(null);
  const max = trendMax(groups.map((g) => g.values), series);
  const fmt = (v) => (v >= max * 0.12 ? fmtShort(v) : '');
  return (
    <div className="nms-chart" style={{ height }}>
      <div className="ow-chart-plot">
        {groups.map((g, i) => (
          <div key={g.key || g.label} className={`ow-chart-group${g.current ? ' nms-chart-current' : ''}`} tabIndex={0}
            onMouseEnter={(e) => setTip({ i, rect: e.currentTarget.getBoundingClientRect() })} onMouseLeave={() => setTip(null)}
            onClick={() => onPick?.(g)}>
            <TrendBars series={series} row={g.values} max={max} fmt={fmt} />
          </div>
        ))}
      </div>
      <div className="nms-chart-labels">
        {groups.map((g) => <div key={g.key || g.label} className={`ow-chart-month${g.current ? ' nms-chart-current-label' : ''}`}>{g.label}</div>)}
      </div>
      {tip && groups[tip.i] && (
        <TrendTip anchorRect={tip.rect}>
          <div className="ow-chart-tip-month">{groups[tip.i].label}</div>
          {(tipRows ? tipRows(groups[tip.i]) : series.map((s) => [s.label, fmtMoney(groups[tip.i].values[s.key])])).map(([k, v]) => (
            <div key={k} className="ow-chart-tip-row"><span>{k}</span><b>{v}</b></div>
          ))}
        </TrendTip>
      )}
    </div>
  );
}

// Bar label: 13.2L / 2.1K / 640 (no space, so neighbouring labels do not collide).
function fmtShort(v) {
  const n = Number(v) || 0;
  if (n >= 1e7) return `${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(1)}L`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(Math.round(n));
}

function Legend({ series }) {
  return (
    <span className="st-legend">
      {series.map((s) => <span key={s.key}><i className={`nms-swatch ow-chart-bar--${s.cls}`} />{s.label}</span>)}
    </span>
  );
}

// Horizontal value bars by classification (one shared scale).
function ClassBars({ rows, valueKey = 'cost_value', onPick, active }) {
  const max = Math.max(1, ...rows.map((r) => Number(r[valueKey]) || 0));
  return (
    <div className="nms-hbars">
      {rows.map((r) => (
        <button key={r.key} type="button" className={`nms-hbar${active === r.key ? ' is-active' : ''}`} onClick={() => onPick?.(r.key)}
          title={`${r.label}: ${fmtQty(r.products)} products · ${fmtQty(r.qty)} qty · ₹${fmtMoney(r.cost_value)} cost · ₹${fmtMoney(r.mrp_value)} MRP`}>
          <span className="nms-hbar-label">{r.label}</span>
          <span className="nms-hbar-track"><span className={`nms-hbar-fill nms-fill--${CLASS_BY_KEY[r.key]?.tone}`} style={{ width: `${barPct(r[valueKey], max)}%` }} /></span>
          <span className="nms-hbar-val">{valueKey === 'products' ? fmtQty(r.products) : `₹${fmtCompact(r[valueKey])}`}</span>
          <span className="nms-hbar-sub">{fmtQty(r.products)}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Product detail panel.
function ProductDetail({ ui, session, tenantId, store, row: rowIn, tab, setTab, onClose, review, onToggleReview, visibleCodes }) {
  const IntelPanel = ui?.IntelPanel;
  let row = rowIn;
  const code = row?.product_code ?? null;
  const [batches, setBatches] = useState({ loading: false, rows: [], error: '' });
  const [net, setNet] = useState({ loading: false, data: null, error: '' });
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!code || !store) return undefined;
    let cancelled = false;
    setBatches({ loading: true, rows: [], error: '' });
    api.nonMoving('product/batches', { tenant_id: tenantId, store_id: store.store_id, product_code: code }, session)
      .then((d) => { if (!cancelled) setBatches({ loading: false, rows: d.batches || [], error: '' }); })
      .catch((e) => { if (!cancelled) setBatches({ loading: false, rows: [], error: e.message }); });
    return () => { cancelled = true; };
  }, [code, store, tenantId, session]);

  const needNet = tab === 'stores' || tab === 'transfers' || tab === 'summary';
  useEffect(() => {
    if (!code || !store || !needNet) return undefined;
    let cancelled = false;
    setNet((s) => (s.data?.product?.product_code === code ? s : { loading: true, data: null, error: '' }));
    api.nonMoving('product', { tenant_id: tenantId, store_id: store.store_id, product_code: code }, session)
      .then((d) => { if (!cancelled) setNet({ loading: false, data: d, error: '' }); })
      .catch((e) => { if (!cancelled) setNet({ loading: false, data: null, error: e.message }); });
    return () => { cancelled = true; };
  }, [code, store, tenantId, session, needNet]);

  if (!row) {
    return <aside className="nms-detail nms-detail--empty"><div className="empty-state">Select a product to see its details.</div></aside>;
  }
  const full = net.data?.product?.product_code === row.product_code ? net.data.product : null;
  if (full) row = full;
  const flagged = row.flags || [];
  const inList = inReview(review, store.store_id, row.product_code);
  const fact = (label, value, title) => <div className="nms-fact" title={title}><span>{label}</span><b>{value}</b></div>;
  const transfers = net.data?.transfers || [];
  const blocks = net.data?.transfer_blocks || [];
  return (
    <aside className="nms-detail" aria-label="Product details">
      <div className="nms-detail-head">
        <div className="nms-detail-title">
          <strong title={row.product_name}>{row.product_name}</strong>
          <span>{[row.product_code, row.unit, row.pack ? `Pack ${row.pack}` : `Unit ${fmtQty(row.sale_unit)}`, row.product_type, store.store_code].filter(Boolean).join(' · ')}</span>
        </div>
        <ClassBadge value={row.classification} label={row.classification_label} />
        <button type="button" className={`secondary-button nms-review-btn${inList ? ' is-on' : ''}`} onClick={() => onToggleReview(row)}
          title="Add to / remove from the manual review list (R)">{inList ? '★ In review' : '☆ Review'}</button>
        <button type="button" className="secondary-button" onClick={onClose} title="Close details">✕</button>
      </div>
      <div className="nms-detail-tabs" role="tablist">
        {DETAIL_TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={`rta-chip${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}{t.id === 'transfers' && transfers.length ? <span className="rta-count">{transfers.length}</span> : null}
          </button>
        ))}
      </div>
      {err && <div className="status-line error">{err}</div>}
      <div className="nms-detail-body">
        {tab === 'summary' && (
          <>
            <div className="nms-facts">
              {fact('Current stock', fmtQty(row.stock), 'Store stock (latest POS monthly balance)')}
              {fact('Batch stock', fmtQty(row.batch_stock), `${row.batch_count} batch(es) in stock`)}
              {fact('Value (cost)', `₹${fmtMoney(row.cost_value)}`, 'POS batch stock value at cost')}
              {fact('Value (PTR)', `₹${fmtMoney(row.ptr_value)}`)}
              {fact('Value (MRP)', `₹${fmtMoney(row.mrp_value)}`)}
              {fact('Last sale', fmtDate(row.last_sale_date), row.last_sale_source ? `Source: ${row.last_sale_source}` : 'No sale on record')}
              {fact('Days since sale', fmtDays(row.days_since_sale))}
              {fact('Sales 30 / 90 / 180 d', `${fmtQty(row.sales_30)} / ${fmtQty(row.sales_90)} / ${fmtQty(row.sales_180)}`)}
              {fact('Last purchase', fmtDate(row.last_purchase_date), 'Supplier purchase (internal transfers excluded)')}
              {fact('Last GRN', fmtDate(row.last_grn_date), 'Any receipt, including transfers in')}
              {fact('Supplier', row.supplier_name || '—')}
              {fact('Expiry', <ExpiryBadge value={row.expiry_status} />, row.earliest_expiry ? `Earliest ${fmtDate(row.earliest_expiry)}` : '')}
            </div>
            {flagged.length > 0 && (
              <ul className="nms-flags">
                {flagged.map((f) => <li key={f} className={`nms-flag nms-flag--${f === 'STOCK_MISMATCH' || f === 'SALE_DATE_CONFLICT' ? 'warn' : 'info'}`}>{FLAG_TEXT[f] || f}</li>)}
              </ul>
            )}
            {IntelPanel && (
              <div className="nms-intel">
                <IntelPanel sections={['trend']} trendFit={TREND_FIT} store={store.store_code} productCode={code}
                  visibleCodes={visibleCodes} mode="local" session={session} onError={setErr} />
              </div>
            )}
            <div className="nms-intel nms-intel--stores">
              <StoreTrendsPanel tenantId={tenantId} storeId={store.store_id} productCode={code} session={session} layout="rows" />
            </div>
          </>
        )}
        {(tab === 'sales' || tab === 'purchase') && IntelPanel && (
          <div className="nms-intel nms-intel--full">
            <IntelPanel sections={[tab]} trendFit={TREND_FIT} store={store.store_code} productCode={code}
              visibleCodes={visibleCodes} mode="local" session={session} onError={setErr} />
          </div>
        )}
        {tab === 'batches' && (
          <div className="trp-tablewrap nms-subtable">
            <table className="trp-table nms-table">
              <thead><tr>
                <th className="trp-left">Batch</th><th className="nms-num">Stock</th><th className="trp-left">Expiry</th>
                <th className="trp-left">Received</th><th className="trp-left">Last Sold</th><th className="nms-num">PTR</th>
                <th className="nms-num">Cost Value</th><th className="trp-left">Supplier</th><th className="trp-left">Rack</th>
              </tr></thead>
              <tbody>
                {batches.rows.map((b) => {
                  const expired = b.expiry_date && new Date(b.expiry_date) < new Date();
                  return (
                    <tr key={b.batch_code} className={expired ? 'nms-row-bad' : undefined}>
                      <td className="trp-left">{b.batch || b.batch_code}</td>
                      <td className="nms-num">{fmtQty(b.stock)}</td>
                      <td className="trp-left">{fmtDate(b.expiry_date)}{expired ? ' (expired)' : ''}</td>
                      <td className="trp-left">{fmtDate(b.received_date)}</td>
                      <td className="trp-left">{fmtDate(b.last_sale_date)}</td>
                      <td className="nms-num">{fmtMoney(b.ptr)}</td>
                      <td className="nms-num">{fmtMoney(b.cost_value)}</td>
                      <td className="trp-left nms-ellipsis" title={b.supplier_name}>{b.supplier_name || b.supplier_code || '—'}</td>
                      <td className="trp-left">{b.rack || '—'}</td>
                    </tr>
                  );
                })}
                {!batches.rows.length && <tr><td colSpan={9} className="nms-empty-cell">{batches.loading ? 'Loading batches…' : batches.error || 'No batch holds stock.'}</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {tab === 'stores' && (
          <>
            <div className="trp-tablewrap nms-subtable">
              <table className="trp-table nms-table">
                <thead><tr>
                  <th className="trp-left">Store</th><th className="nms-num">Stock</th><th className="trp-left">Last Sale</th>
                  <th className="nms-num">Days</th><th className="nms-num">30d</th>
                  <th className="nms-num">Value</th><th className="trp-left">Class</th>
                </tr></thead>
                <tbody>
                  {(net.data?.stores || []).map((s) => (
                    <tr key={s.store_id} className={s.current ? 'nms-row-current' : undefined} title={`${s.ambiguous ? 'This store maps to more than one product - check the mapping. ' : ''}Code ${s.product_code} · 90-day sales ${fmtQty(s.sales_90)} (avg ${fmtQty(s.monthly_avg)} / month)`}>
                      <td className="trp-left"><b>{s.store_code}</b>{s.is_warehouse ? ' (WH)' : ''}{s.ambiguous ? ' ⚠' : ''}</td>
                      <td className="nms-num">{fmtQty(s.stock)}</td>
                      <td className="trp-left">{fmtDate(s.last_sale_date)}</td>
                      <td className="nms-num">{fmtDays(s.days_since_sale)}</td>
                      <td className="nms-num">{fmtQty(s.sales_30)}</td>
                      <td className="nms-num">{fmtMoney(s.cost_value)}</td>
                      <td className="trp-left"><ClassBadge value={s.classification} label={s.classification_label} /></td>
                    </tr>
                  ))}
                  {!(net.data?.stores || []).length && <tr><td colSpan={7} className="nms-empty-cell">{net.loading ? 'Loading every store… (the first load builds all stores)' : net.error || 'Not mapped to any other store.'}</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="nms-intel nms-intel--stores">
              <StoreTrendsPanel tenantId={tenantId} storeId={store.store_id} productCode={code} session={session} layout="rows" />
            </div>
          </>
        )}
        {tab === 'transfers' && (
          <div className="nms-transfer-list">
            {net.loading && <div className="empty-state">Working out transfers across every store…</div>}
            {net.error && <div className="status-line error">{net.error}</div>}
            {transfers.map((t) => (
              <div key={t.id} className="nms-transfer-card">
                <div className="nms-transfer-route"><b>{t.source_store}</b> → <b>{t.dest_store}</b> <span className="nms-transfer-qty">{fmtQty(t.suggested_qty)} units</span> <span>₹{fmtMoney(t.transfer_value)}</span></div>
                <div className="nms-transfer-reason">{t.reason}</div>
                <div className="nms-transfer-calc">{t.calculation}</div>
              </div>
            ))}
            {blocks.map((b) => (
              <div key={`${b.store_id}-${b.product_code}`} className="nms-transfer-card nms-transfer-card--blocked">
                <div className="nms-transfer-route">No transfer from <b>{b.store_code}</b>: {b.reason}</div>
                {(b.details || []).length > 0 && <div className="nms-transfer-calc">{b.details.join(' · ')}</div>}
              </div>
            ))}
            {!net.loading && !transfers.length && !blocks.length && <div className="empty-state">No transfer recommendation involves this product.</div>}
          </div>
        )}
      </div>
    </aside>
  );
}

// Row action menu (⋯).
function RowMenu({ row, onAction, inList, onReview }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);
  return (
    <span className="nms-actions" ref={ref}>
      <button type="button" className={`nms-icon-btn${inList ? ' is-on' : ''}`} title={inList ? 'Remove from manual review' : 'Add to manual review'}
        onClick={(e) => { e.stopPropagation(); onReview(row); }}>{inList ? '★' : '☆'}</button>
      <button type="button" className="nms-icon-btn" title="Actions" aria-haspopup="menu" aria-expanded={open}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}>⋯</button>
      {open && (
        <div className="nms-menu" role="menu">
          {ROW_ACTIONS.map((a) => (
            <button key={a.tab} type="button" role="menuitem" onClick={(e) => { e.stopPropagation(); setOpen(false); onAction(row, a.tab); }}>{a.label}</button>
          ))}
          <button type="button" role="menuitem" onClick={(e) => { e.stopPropagation(); setOpen(false); onReview(row); }}>{inList ? 'Remove from manual review' : 'Add to manual review'}</button>
        </div>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Six-month Sales Trend (double-click a row). Fetched only on open --
// /api/non-moving-analysis/product/sales-trend, product-level (PSI has no
// reliable batch key for historical reporting -- see the module docstring),
// clearly labelled as such below the chart. Reuses the BarChart / TrendTip
// machinery the Value tab already draws its charts with, as two independently
// scaled mini-charts (qty and value can't share one axis).
const TREND_QTY_SERIES = [{ key: 'qty', label: 'Sales qty', cls: 'in' }];
const TREND_VALUE_SERIES = [{ key: 'sales_value', label: 'Sales value (₹)', cls: 'out' }];

function SalesTrendModal({ session, tenantId, store, row, onClose }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, data: null, error: '' });
    api.nonMoving('product/sales-trend', { tenant_id: tenantId, store_id: store.store_id, product_code: row.product_code, months: 6 }, session)
      .then((d) => { if (!cancelled) setState({ loading: false, data: d, error: '' }); })
      .catch((e) => { if (!cancelled) setState({ loading: false, data: null, error: e.message || 'Could not load the sales trend' }); });
    return () => { cancelled = true; };
  }, [session, tenantId, store, row]);
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [onClose]);
  const months = state.data?.months || [];
  const hasAnySale = months.some((m) => m.qty > 0);
  const totalQty = months.reduce((t, m) => t + m.qty, 0);
  const totalValue = months.reduce((t, m) => t + m.sales_value, 0);
  const qtyGroups = months.map((m) => ({ key: m.ym, label: fmtMonthLabel(m.ym), values: m }));
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="nms-trend-modal" role="dialog" aria-modal="true" aria-label="Sales trend" onClick={(e) => e.stopPropagation()}>
        <div className="nms-trend-head">
          <div className="nms-trend-title">
            <strong title={row.product_name}>{row.product_name}</strong>
            <span>{[row.product_code, store.store_code, store.store_name].filter(Boolean).join(' · ')} · 6-month sales trend</span>
          </div>
          <button type="button" className="secondary-button" onClick={onClose} aria-label="Close" title="Close (Esc)">✕</button>
        </div>
        <div className="nms-trend-body">
          {state.loading && <div className="empty-state">Loading the last 6 months of sales…</div>}
          {state.error && <div className="status-line error">{state.error}</div>}
          {!state.loading && !state.error && (
            <>
              <div className="trp-subnote nms-note">Product-level trend from the synced sale lines (sync.ProductSaleInformation) -- batch-level history isn't available for historical sales. Returns are already netted off each month.</div>
              {!hasAnySale && <div className="empty-state">No sales recorded for this product at {store.store_code} in the last 6 months.</div>}
              <div className="nms-trend-charts">
                <section className="ow-panel nms-card">
                  <div className="ow-panel-title">Monthly sales qty</div>
                  <BarChart groups={qtyGroups} series={TREND_QTY_SERIES} height={150}
                    tipRows={(g) => [['Qty', fmtQty(g.values.qty)], ['Value', `₹${fmtMoney(g.values.sales_value)}`], ['Transactions', fmtQty(g.values.transactions)]]} />
                </section>
                <section className="ow-panel nms-card">
                  <div className="ow-panel-title">Monthly sales value (₹)</div>
                  <BarChart groups={qtyGroups} series={TREND_VALUE_SERIES} height={150}
                    tipRows={(g) => [['Value', `₹${fmtMoney(g.values.sales_value)}`], ['Qty', fmtQty(g.values.qty)], ['Transactions', fmtQty(g.values.transactions)]]} />
                </section>
              </div>
              <div className="trp-tablewrap nms-subtable">
                <table className="trp-table nms-table">
                  <thead><tr><th className="trp-left">Month</th><th className="nms-num">Sales Qty</th><th className="nms-num">Sales Value</th><th className="nms-num">Transactions</th></tr></thead>
                  <tbody>
                    {months.map((m) => (
                      <tr key={m.ym}>
                        <td className="trp-left">{fmtMonthLabel(m.ym)}</td>
                        <td className="nms-num">{fmtQty(m.qty)}</td>
                        <td className="nms-num">{fmtMoney(m.sales_value)}</td>
                        <td className="nms-num">{fmtQty(m.transactions)}</td>
                      </tr>
                    ))}
                    {!months.length && <tr><td colSpan={4} className="nms-empty-cell">No data.</td></tr>}
                  </tbody>
                  {months.length > 0 && (
                    <tfoot><tr>
                      <td className="trp-left"><b>Total</b></td>
                      <td className="nms-num"><b>{fmtQty(totalQty)}</b></td>
                      <td className="nms-num"><b>{fmtMoney(totalValue)}</b></td>
                      <td className="nms-num">—</td>
                    </tr></tfoot>
                  )}
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Column Settings: the same show / move-up-down / width-px / Default columns
// model as Procurement's ⚙ panel (ProcurementWorkspace.jsx pw-col-list), on
// the pw-settings* styling it already defines -- a second grid, not a second
// settings system. Persistence is this module's own (readColSettings), so
// nothing here touches Procurement's saved column config.
function ColumnSettings({ settings, onChange, onClose, anchorRef }) {
  const ref = useRef(null);
  useEffect(() => {
    const close = (e) => { if (!ref.current?.contains(e.target) && !anchorRef?.current?.contains(e.target)) onClose(); };
    const esc = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [onClose, anchorRef]);
  const toggle = (key) => {
    if (OWN_COLS_MANDATORY.includes(key)) return;
    const hidden = settings.hidden.includes(key) ? settings.hidden.filter((k) => k !== key) : [...settings.hidden, key];
    onChange({ ...settings, hidden });
  };
  const move = (key, dir) => {
    const i = settings.order.indexOf(key);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= settings.order.length) return;
    const order = [...settings.order];
    [order[i], order[j]] = [order[j], order[i]];
    onChange({ ...settings, order });
  };
  const setWidth = (key, value) => {
    const widths = { ...settings.widths };
    if (value === '' || value == null) delete widths[key]; else widths[key] = Number(value);
    onChange({ ...settings, widths });
  };
  return (
    <div className="pw-settings" ref={ref} role="dialog" aria-label="Non-Moving Stock column settings">
      <span className="pw-section-label">Columns <small>(show, move, width · Supplier / Product / Stock always shown)</small></span>
      <ul className="pw-col-list">
        {settings.order.map((key, i, arr) => {
          const col = OWN_COLS_BY_KEY[key];
          if (!col) return null;
          const on = col.mandatory || !settings.hidden.includes(key);
          return (
            <li key={key} className={`pw-col-list__row${on ? '' : ' is-off'}`} title={col.label}>
              <label className="pw-col-list__name">
                <input type="checkbox" checked={on} disabled={col.mandatory} onChange={() => toggle(key)} />
                <span>{col.label}</span>
              </label>
              <button type="button" className="pw-col-list__mv" disabled={i === 0} aria-label={`Move ${col.label} up`} onClick={() => move(key, -1)}>▲</button>
              <button type="button" className="pw-col-list__mv" disabled={i === arr.length - 1} aria-label={`Move ${col.label} down`} onClick={() => move(key, 1)}>▼</button>
              <input type="number" min={30} max={400} className="pw-col-list__w" aria-label={`${col.label} width`}
                placeholder={String(col.w || '')} value={settings.widths?.[key] ?? ''} onChange={(e) => setWidth(key, e.target.value)} />
            </li>
          );
        })}
      </ul>
      <div className="pw-colsettings-actions">
        <button type="button" className="ow-btn ow-btn-sm" onClick={() => onChange({ order: OWN_COLS_DEFAULT_ORDER, hidden: [], widths: {} })}>Default columns</button>
        <button type="button" className="secondary-button" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

// Default report = the Show preset "Non-Moving (180+ days / no sales)"
// (see SHOW_PRESETS in nonMovingView.js) -- a NEW default distinct from the
// old nonMovingOnly/>90-day flag, expressed as minDays only (already
// includes never-sold rows, see the comment on SHOW_PRESETS).
const DEFAULT_FILTERS = {
  search: '', classes: [], ptype: '', supplier: '', expiry: '', includeZero: false,
  ...SHOW_PRESET_BY_ID[DEFAULT_SHOW_ID], show: DEFAULT_SHOW_ID, age: '',
};
delete DEFAULT_FILTERS.id; delete DEFAULT_FILTERS.label;

// Own Store grid cell content by column key (product_code / supplier /
// product_name / action are rendered inline at the call site).
function renderOwnCell(key, r) {
  switch (key) {
    case 'product_code': return r.product_code;
    case 'supplier': return r.supplier_name || '—';
    case 'product_name': return <>{r.product_name}{r.flags?.length ? <span className="nms-flagdot" title={r.flags.map((f) => FLAG_TEXT[f] || f).join('\n')}>●</span> : null}</>;
    case 'pack': return r.pack || fmtQty(r.sale_unit);
    case 'batch_count': return fmtQty(r.batch_count);
    case 'stock': return fmtQty(r.stock);
    case 'expiry_status': return <ExpiryBadge value={r.expiry_status} />;
    case 'last_grn_date': return fmtDate(r.last_grn_date);
    case 'last_sale_date': return fmtDate(r.last_sale_date);
    case 'days_since_sale': return <b>{fmtDays(r.days_since_sale)}</b>;
    case 'ptr_value': return fmtMoney(r.ptr_value);
    case 'cost_value': return fmtMoney(r.cost_value);
    case 'mrp_value': return fmtMoney(r.mrp_value);
    case 'classification': return <ClassBadge value={r.classification} label={r.classification_label} />;
    default: return null;
  }
}

// AG Grid column defs for the Own Store grid, built from the same
// OWN_COLS_DEF / column-settings model the ⚙ panel already edits (order,
// hidden, widths) -- the panel keeps driving plain objects; this just maps
// the resolved list to AG Grid's shape once per render.
function buildAgColumns(cols, { review, store, onReview, onAction }) {
  const base = cols.map((c) => {
    if (c.key === 'action') {
      return {
        colId: 'action', headerName: '', width: c.w, pinned: false, sortable: false, resizable: false,
        cellRenderer: (p) => (
          <RowMenu row={p.data} inList={inReview(review, store.store_id, p.data.product_code)} onReview={onReview} onAction={onAction} />
        ),
      };
    }
    const comparator = COMPARATORS[c.sortType] || null;
    return {
      colId: c.key,
      headerName: c.label,
      field: c.sort || c.key,
      width: c.w,
      minWidth: 50,
      resizable: true,
      sortable: true,
      comparator: comparator || undefined,
      type: c.num ? 'rightAligned' : undefined,
      cellClass: `${c.num ? 'nms-num' : 'trp-left'}${c.groupStart ? ' nms-colgroup-start' : ''}${c.key === 'product_name' ? ' nms-name' : ''}${c.key === 'supplier' ? ' nms-ellipsis' : ''}`,
      cellRenderer: (p) => renderOwnCell(c.key, p.data),
      tooltipValueGetter: (p) => (c.key === 'product_name' ? p.data.product_name : c.key === 'supplier' ? p.data.supplier_name
        : c.key === 'last_sale_date' && p.data.last_sale_source ? `Source: ${p.data.last_sale_source}` : undefined),
    };
  });
  return [
    { colId: 'rownum', headerName: '#', width: 44, pinned: 'left', sortable: false, resizable: false,
      cellClass: 'nms-num nms-muted', valueGetter: (p) => (p.node ? p.node.rowIndex + 1 : ''), type: 'rightAligned' },
    ...base,
  ];
}

function OwnStoreSection({ ui, session, tenantId, store, refreshTick, onLoaded, review, onToggleReview, setError }) {
  // `filters` = pending toolbar state (what the controls show); `applied` =
  // the filter state the last fetch actually used. A filter change never
  // fires a query by itself -- only Apply Filters / Enter-in-search /
  // Reset / Refresh advance `applied`, per the owner's explicit requirement
  // that the user always knows when a change triggers a backend query.
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [applied, setApplied] = useState(DEFAULT_FILTERS);
  const [searchText, setSearchText] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  // Local (grid-scoped) load error, separate from the page-level error
  // banner (setError) -- so the grid area itself can show a clear Failed
  // state with Retry, distinct from Loading and from a genuine zero-row
  // Empty result (owner requirement: never confuse the three).
  const [loadError, setLoadError] = useState('');
  const [retryTick, setRetryTick] = useState(0);
  const [selectedCode, setSelectedCode] = useState(null);
  const [detailTab, setDetailTab] = useState('summary');
  const [showDetail, setShowDetail] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [colSettings, setColSettings] = useState(() => readColSettings(globalThis.localStorage, tenantId, store?.store_id));
  const [showColSettings, setShowColSettings] = useState(false);
  const [trendRow, setTrendRow] = useState(null);
  const gridApiRef = useRef(null);
  const colBtnRef = useRef(null);
  const lastTick = useRef(refreshTick);
  const abortRef = useRef(null);

  useEffect(() => { setColSettings(readColSettings(globalThis.localStorage, tenantId, store?.store_id)); }, [tenantId, store?.store_id]);
  const setCols = (next) => { setColSettings(next); writeColSettings(globalThis.localStorage, tenantId, store?.store_id, next); };
  const cols = useMemo(() => resolveOwnCols(colSettings), [colSettings]);

  // Store change resets both pending and applied state to the default
  // report (switching stores is a fresh analysis, not a filter tweak).
  useEffect(() => { setFilters(DEFAULT_FILTERS); setApplied(DEFAULT_FILTERS); setSearchText(''); }, [store?.store_id]);

  const dirty = !filtersEqual(filters, applied);
  const applyFilters = useCallback(() => setApplied(filters), [filters]);
  const resetFilters = useCallback(() => { setFilters(DEFAULT_FILTERS); setApplied(DEFAULT_FILTERS); setSearchText(''); }, []);

  // Own Store loads EVERY filtered row in one request (all_rows=true) --
  // no page/page_size, no Prev/Next: the grid itself does client-side sort
  // and virtual scrolling over the full set (owner requirement: no silent
  // row cap anywhere in this path). A stale response (superseded by a
  // newer filter change) is ignored via AbortController, same idiom the
  // rest of this file uses the `cancelled` flag for. Fires on `applied`
  // only -- never on `filters` -- so a pending (unapplied) toolbar change
  // never triggers a query by itself.
  useEffect(() => {
    if (!store) return undefined;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const refresh = lastTick.current !== refreshTick;
    lastTick.current = refreshTick;
    setLoading(true);
    setError('');
    setLoadError('');
    const params = { ...ownParams(tenantId, store.store_id, applied, { key: 'cost_value', dir: 'desc' }, 1, 1), all_rows: 'true', page: undefined, page_size: undefined };
    api.nonMoving('own-store', { ...params, refresh: refresh ? 'true' : undefined }, session, controller.signal)
      .then((d) => {
        if (controller.signal.aborted) return;
        setData(d);
        setSelectedCode((cur) => (cur && d.rows.some((r) => r.product_code === cur)) ? cur : (d.rows[0]?.product_code ?? null));
        onLoaded?.(d);
      })
      .catch((e) => {
        if (controller.signal.aborted) return;
        const msg = e.message || 'Could not load the analysis';
        setError(msg);
        setLoadError(msg);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [store, applied, refreshTick, retryTick, tenantId, session]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = data?.rows || [];
  const selectedIdx = selectedCode == null ? -1 : rows.findIndex((r) => r.product_code === selectedCode);
  const row = selectedIdx >= 0 ? rows[selectedIdx] : null;
  const visibleCodes = useMemo(() => rows.slice(Math.max(0, selectedIdx - 1), selectedIdx + 5).map((r) => r.product_code), [rows, selectedIdx]);
  const set = (patch) => setFilters((f) => ({ ...f, ...patch, search: searchText }));
  const review_ = useCallback((r) => onToggleReview({ ...r, store_id: store.store_id, store_code: store.store_code }), [onToggleReview, store]);
  const openTab = useCallback((r, tab) => { setSelectedCode(r.product_code); setDetailTab(tab); setShowDetail(true); }, []);
  const onRowClicked = useCallback((e) => {
    setSelectedCode(e.data.product_code);
    e.event?.currentTarget?.closest('.nms-aggrid-wrap')?.focus();
  }, []);
  const onRowDoubleClicked = useCallback((e) => setTrendRow(e.data), []);
  const getRowId = useCallback((p) => String(p.data.product_code), []);
  const getRowClass = useCallback((p) => (p.data?.flags?.includes('STOCK_MISMATCH') ? 'nms-row-flag' : undefined), []);

  const agColumns = useMemo(() => buildAgColumns(cols, { review, store, onReview: review_, onAction: openTab }),
    [cols, review, store, review_, openTab]);

  // Explicit Loading/Error/Empty overlay control -- AG Grid only infers
  // "no rows" from an empty rowData array, which would otherwise show the
  // Empty message while a fetch is still in flight or just failed (the
  // "blank grid with no explanation" bug this screen had). Loading always
  // wins; a failed load replaces the grid area with .nms-grid-error instead
  // (see render below) rather than AG Grid's own overlay.
  useEffect(() => {
    const api_ = gridApiRef.current;
    if (!api_) return;
    if (loading) api_.showLoadingOverlay();
    else if (loadError) api_.hideOverlay();
    else if (!rows.length) api_.showNoRowsOverlay();
    else api_.hideOverlay();
  }, [loading, loadError, rows.length]);

  // Keep AG Grid's own row selection (used for the highlight CSS) in sync
  // with selectedCode -- needed when selection changes from outside the
  // grid (row menu "View product details" etc.) or after a reload replaces
  // the row objects.
  useEffect(() => {
    const api_ = gridApiRef.current;
    if (!api_) return;
    api_.deselectAll();
    if (selectedCode != null) {
      const node = api_.getRowNode(String(selectedCode));
      node?.setSelected(true);
    }
  }, [selectedCode, rows]);

  const onGridKeyDown = (e) => {
    if ((e.key === 'r' || e.key === 'R') && row) { e.preventDefault(); review_(row); }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!rows.length) return;
      e.preventDefault();
      const i = rows.findIndex((r) => r.product_code === selectedCode);
      const next = Math.min(rows.length - 1, Math.max(0, (i < 0 ? -1 : i) + (e.key === 'ArrowDown' ? 1 : -1)));
      const code = rows[next]?.product_code;
      if (code != null) {
        setSelectedCode(code);
        gridApiRef.current?.ensureNodeVisible(gridApiRef.current.getRowNode(String(code)));
      }
    }
    if (e.key === 'Enter' && row) { e.preventDefault(); setDetailTab('summary'); setShowDetail(true); }
  };
  const exportExcel = async () => {
    setExporting(true);
    try {
      const { blob, filename } = await api.nonMovingExcel('own-store', ownParams(tenantId, store.store_id, applied, { key: 'cost_value', dir: 'desc' }, 1, 1), session);
      saveBlob(blob, filename);
    } catch (e) { setError(e.message || 'Export failed'); } finally { setExporting(false); }
  };
  const byClass = data?.by_class || [];
  // Classification chips reflect/toggle the PENDING Show selection (a chip
  // IS one of the SHOW_PRESETS -- clicking Active, say, has no dedicated
  // preset, so a bare class toggle still goes through pending state and
  // needs Apply like every other filter change).
  const toggleClass = (key) => set({ classes: filters.classes.includes(key) ? filters.classes.filter((k) => k !== key) : [...filters.classes, key], show: '', nonMovingOnly: false, minDays: '', maxDays: '' });
  const filterCount = activeFilterCount(applied);
  const onSearchKeyDown = (e) => { if (e.key === 'Enter') { e.preventDefault(); setApplied({ ...filters, search: searchText }); } };

  return (
    <div className={`nms-split${showDetail ? '' : ' nms-split--nodetail'}`}>
      <div className="nms-main">
        <div className="trp-bar nms-filters">
          <label className="trp-field nms-grow">Search
            <input type="search" placeholder="Product name, code or supplier… (Enter to apply)" value={searchText}
              onChange={(e) => { setSearchText(e.target.value); set({ search: e.target.value }); }} onKeyDown={onSearchKeyDown} />
          </label>
          <label className="trp-field">Show
            <select value={filters.show || ''} onChange={(e) => { const p = SHOW_PRESET_BY_ID[e.target.value]; set(p ? { ...p, show: p.id, age: '' } : { show: '' }); }}>
              {SHOW_PRESETS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              <option value="">Custom</option>
            </select>
          </label>
          <label className="trp-field">Age
            <select value={filters.age} onChange={(e) => { const p = AGE_PRESETS.find((x) => x.id === e.target.value); set({ age: p.id, minDays: p.min, maxDays: p.max, show: '' }); }}>
              {AGE_PRESETS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </label>
          <label className="trp-field">Type
            <select value={filters.ptype} onChange={(e) => set({ ptype: e.target.value })}>
              <option value="">Pharma + Non Pharma</option><option value="pharma">Pharma</option><option value="nonpharma">Non Pharma</option>
            </select>
          </label>
          <label className="trp-field">Supplier
            <select value={filters.supplier} onChange={(e) => set({ supplier: e.target.value })} className="nms-supplier">
              <option value="">All suppliers</option>
              {(data?.suppliers || []).map((s) => <option key={s.code} value={s.code}>{s.name || s.code} ({s.products})</option>)}
            </select>
          </label>
          <label className="trp-field">Expiry
            <select value={filters.expiry} onChange={(e) => set({ expiry: e.target.value })}>
              <option value="">Any</option>
              <option value="expired">Expired</option>
              <option value="near">Expiring within 90 days</option>
              <option value="risk">Expired or near expiry</option>
              <option value="valid">Valid stock</option>
            </select>
          </label>
          <label className="nms-check"><input type="checkbox" checked={filters.includeZero} onChange={(e) => set({ includeZero: e.target.checked })} /> Zero stock</label>
          <div className="trp-actions">
            <button type="button" className={`primary-button nms-apply-btn${dirty ? ' is-dirty' : ''}`} onClick={applyFilters} disabled={!dirty}
              title={dirty ? 'Filters changed -- click to run the report with the new filters' : 'Filters are already applied'}>
              {dirty && <span className="nms-apply-dot" aria-hidden="true" />}Apply Filters
            </button>
            {(dirty || !filtersEqual(applied, DEFAULT_FILTERS)) && <button type="button" className="secondary-button" onClick={resetFilters}>Reset</button>}
            <button type="button" className="secondary-button" onClick={() => setShowDetail((v) => !v)}>{showDetail ? 'Hide details' : 'Show details'}</button>
            <span className="nms-colbtn-wrap">
              <button type="button" className="secondary-button" ref={colBtnRef} title="Show/hide, reorder and resize columns" onClick={() => setShowColSettings((v) => !v)}>⚙ Columns</button>
              {showColSettings && <ColumnSettings settings={colSettings} onChange={setCols} onClose={() => setShowColSettings(false)} anchorRef={colBtnRef} />}
            </span>
            <button type="button" className="primary-button" disabled={exporting || !data} onClick={exportExcel}>{exporting ? 'Preparing…' : 'Export Excel'}</button>
          </div>
        </div>
        {dirty && <div className="nms-filter-pending">Filters changed -- click <b>Apply Filters</b> (or press Enter in Search) to run the report.</div>}
        <div className="nms-classbar" role="group" aria-label="Classification filter">
          {byClass.map((c) => (
            <button key={c.key} type="button" className={`nms-classchip nms-cls--${CLASS_BY_KEY[c.key]?.tone}${filters.classes.includes(c.key) ? ' is-on' : ''}`}
              title={`${c.label}: ₹${fmtMoney(c.cost_value)} at cost · ${fmtQty(c.qty)} qty`} onClick={() => toggleClass(c.key)}>
              {c.label} <b>{fmtQty(c.products)}</b> <span>₹{fmtCompact(c.cost_value)}</span>
            </button>
          ))}
        </div>
        <div className="nms-aggrid-wrap ag-theme-quartz" tabIndex={0} onKeyDown={onGridKeyDown} aria-label="Own store products (arrow keys move, Enter opens, click selects, double-click opens the sales trend, R adds to review)">
          <AgGridReact
            rowData={rows}
            columnDefs={agColumns}
            getRowId={getRowId}
            getRowClass={getRowClass}
            rowSelection="single"
            suppressRowClickSelection={false}
            onRowClicked={onRowClicked}
            onRowDoubleClicked={onRowDoubleClicked}
            onGridReady={(p) => { gridApiRef.current = p.api; }}
            domLayout="normal"
            loadingOverlayComponentParams={{ loadingMessage: `Analysing ${store?.store_code || ''}…` }}
            overlayLoadingTemplate={`<span class="nms-empty-cell">Analysing ${store?.store_code || ''}… the first load reads every sale, purchase and batch (up to a minute).</span>`}
            overlayNoRowsTemplate={'<span class="nms-empty-cell">No products match these filters.</span>'}
            animateRows={false}
            suppressCellFocus
          />
          {/* Loading / Empty / Failed are kept visually distinct (owner
              requirement): Loading shows AG Grid's own overlay (driven by
              `loading` below, never confused with a genuine zero-row
              result); Failed replaces the grid area entirely with an
              actionable retry, so a backend error never just LOOKS like an
              empty report. */}
          {loading && <div className="nms-grid-loading-badge">Loading…</div>}
          {loadError && !loading && (
            <div className="nms-grid-error" role="alert">
              <div className="nms-grid-error-msg">Could not load this report.<br /><span>{loadError}</span></div>
              <button type="button" className="primary-button" onClick={() => setRetryTick((t) => t + 1)}>Retry</button>
            </div>
          )}
        </div>
        {data && (
          <div className="nms-statusbar">
            <span><b>{fmtQty(data.total)}</b> products</span>
            <span><b>{fmtQty(rows.length)}</b> shown</span>
            {filterCount > 0 && <span className="nms-statusbar-filters">{filterCount} filter{filterCount > 1 ? 's' : ''} active</span>}
            <span className="nms-statusbar-sum">Qty: <b>{fmtQty(data.filtered_qty)}</b> · Value: <b>₹{fmtMoney(data.filtered_value)}</b> at cost{loading ? ' · updating…' : ''}</span>
          </div>
        )}
      </div>
      {showDetail && (
        <ProductDetail ui={ui} session={session} tenantId={tenantId} store={store} row={row} tab={detailTab} setTab={setDetailTab}
          onClose={() => setShowDetail(false)} review={review} onToggleReview={review_} visibleCodes={visibleCodes} />
      )}
      {trendRow && (
        <SalesTrendModal session={session} tenantId={tenantId} store={store} row={trendRow} onClose={() => setTrendRow(null)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function OtherStoresSection({ ui, session, tenantId, store, refreshTick, onLoaded, review, onToggleReview, setError }) {
  const [scope, setScope] = useState('selling');
  const [searchText, setSearchText] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState({ key: 'other_sales_30', dir: 'desc' });
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(-1);
  const [detailTab, setDetailTab] = useState('stores');
  const [exporting, setExporting] = useState(false);
  const gridRef = useRef(null);
  const lastTick = useRef(refreshTick);

  useEffect(() => { const t = setTimeout(() => setSearch(searchText), 300); return () => clearTimeout(t); }, [searchText]);
  useEffect(() => { setPage(1); }, [scope, search, sort, store]);
  const params = { tenant_id: tenantId, store_id: store?.store_id, scope, search: search || undefined, sort: sort.key, direction: sort.dir };
  useEffect(() => {
    if (!store) return undefined;
    let cancelled = false;
    const refresh = lastTick.current !== refreshTick;
    lastTick.current = refreshTick;
    setLoading(true);
    setError('');
    api.nonMoving('other-stores', { ...params, page, page_size: PAGE_SIZE, refresh: refresh ? 'true' : undefined }, session)
      .then((d) => { if (!cancelled) { setData(d); setSelected(d.rows.length ? 0 : -1); onLoaded?.(d); } })
      .catch((e) => { if (!cancelled) setError(e.message || 'Could not load other stores'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [store, scope, search, sort, page, refreshTick, tenantId, session]); // eslint-disable-line react-hooks/exhaustive-deps

  useScrollSelected(gridRef, selected);
  const rows = data?.rows || [];
  const others = (data?.stores || []).filter((s) => String(s.store_id).toUpperCase() !== String(store?.store_id).toUpperCase());
  const row = selected >= 0 ? rows[selected] : null;
  const onSort = (key) => setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'product_name' ? 'asc' : 'desc' }));
  const onKeyDown = useGridKeys(rows.length, selected, setSelected, () => setDetailTab('stores'));
  const cols = [
    { label: '#', w: 40, num: true }, { label: 'Product', sort: 'product_name' },
    { label: 'Stock here', sort: 'stock', num: true, w: 70 }, { label: 'Value (₹)', sort: 'cost_value', num: true, w: 84 },
    { label: 'Days', sort: 'days_since_sale', num: true, w: 54 }, { label: 'Here', sort: 'classification', w: 122 },
    { label: 'Selling', sort: 'active_stores', num: true, w: 56 }, { label: 'Their stock', sort: 'other_stock', num: true, w: 74 },
    { label: 'Their 30d sales', sort: 'other_sales_30', num: true, w: 84 },
  ];
  const detailRow = row ? { ...row, flags: [], batch_stock: null, batch_count: 0, sale_unit: 1, product_type: '', expiry_status: '' } : null;
  const exportExcel = async () => {
    setExporting(true);
    try { const { blob, filename } = await api.nonMovingExcel('other-stores', params, session); saveBlob(blob, filename); }
    catch (e) { setError(e.message || 'Export failed'); } finally { setExporting(false); }
  };
  return (
    <div className="nms-split">
      <div className="nms-main">
        <div className="trp-bar nms-filters">
          <label className="trp-field nms-grow">Search<input type="search" value={searchText} placeholder="Product name or code…" onChange={(e) => setSearchText(e.target.value)} /></label>
          <label className="trp-field">Show
            <select value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="selling">Idle here, selling elsewhere (30 d)</option>
              <option value="all">Idle here, mapped to any store</option>
            </select>
          </label>
          <div className="trp-actions">
            <button type="button" className="primary-button" disabled={exporting || !data} onClick={exportExcel}>{exporting ? 'Preparing…' : 'Export Excel'}</button>
          </div>
        </div>
        <div className="trp-subnote nms-note">Products non-moving at <b>{store?.store_code}</b> (&gt; 90 days or never sold) next to the same product at every mapped store: <b>stock / 30-day sales</b> per store; green = selling, grey = idle.</div>
        <div className="trp-tablewrap nms-grid" ref={gridRef} tabIndex={0} onKeyDown={onKeyDown}>
          <table className="trp-table nms-table">
            <thead><tr>
              {cols.map((c) => <Th key={c.label} col={c} sort={sort} onSort={onSort} />)}
              {others.map((s) => <th key={s.store_id} className="nms-num nms-storecol" title={s.store_name}>{s.store_code}</th>)}
            </tr></thead>
            <tbody>
              {rows.map((r, i) => {
                const by = Object.fromEntries((r.stores || []).map((c) => [String(c.store_id).toUpperCase(), c]));
                return (
                  <tr key={r.product_code} data-idx={i} className={i === selected ? 'is-selected' : undefined} onClick={() => setSelected(i)}>
                    <td className="nms-num nms-muted">{(page - 1) * PAGE_SIZE + i + 1}</td>
                    <td className="trp-left nms-name" title={`${r.product_name} (${r.product_code})`}>{r.product_name}{r.ambiguous ? <span className="nms-flagdot" title="A store maps to more than one product">●</span> : null}</td>
                    <td className="nms-num">{fmtQty(r.stock)}</td>
                    <td className="nms-num">{fmtMoney(r.cost_value)}</td>
                    <td className="nms-num"><b>{fmtDays(r.days_since_sale)}</b></td>
                    <td className="trp-left"><ClassBadge value={r.classification} label={r.classification_label} /></td>
                    <td className="nms-num">{r.active_stores}/{r.mapped_stores}</td>
                    <td className="nms-num">{fmtQty(r.other_stock)}</td>
                    <td className="nms-num"><b>{fmtQty(r.other_sales_30)}</b></td>
                    {others.map((s) => {
                      const c = by[String(s.store_id).toUpperCase()];
                      if (!c) return <td key={s.store_id} className="nms-num nms-muted" title="Not mapped">—</td>;
                      return (
                        <td key={s.store_id} className={`nms-num nms-cell ${c.sales_30 > 0 ? 'nms-cell--selling' : 'nms-cell--idle'}`}
                          title={`${s.store_code}: stock ${fmtQty(c.stock)}, 30d sales ${fmtQty(c.sales_30)}, last sale ${fmtDate(c.last_sale_date)} (${fmtDays(c.days_since_sale)} days), ${c.classification_label}`}>
                          {fmtQty(c.stock)} / {fmtQty(c.sales_30)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
              {!rows.length && <tr><td colSpan={cols.length + others.length} className="nms-empty-cell">{loading ? 'Comparing every store… the first load builds all stores (1–2 minutes).' : 'No idle product here is selling in another store.'}</td></tr>}
            </tbody>
          </table>
        </div>
        {data && <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} extra={loading ? <span className="nms-pager-sum">updating…</span> : null} />}
      </div>
      <ProductDetail ui={ui} session={session} tenantId={tenantId} store={store} row={detailRow} tab={detailTab} setTab={setDetailTab}
        onClose={() => setSelected(-1)} review={review} onToggleReview={(r) => onToggleReview({ ...r, store_id: store.store_id, store_code: store.store_code })} visibleCodes={[]} />
    </div>
  );
}

// ---------------------------------------------------------------------------
const reviewedKey = (tenantId) => `nexora.desktop.nmTransferReviewed.${tenantId || 'none'}`;

function TransfersSection({ session, tenantId, store, refreshTick, onLoaded, setError, allStores }) {
  const [direction, setDirection] = useState('out');
  const [searchText, setSearchText] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState({ key: 'transfer_value', dir: 'desc' });
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [chosen, setChosen] = useState(() => new Set());
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState('');
  const [reviewed, setReviewed] = useState(() => { try { return JSON.parse(localStorage.getItem(reviewedKey(tenantId)) || '{}'); } catch { return {}; } });
  const lastTick = useRef(refreshTick);

  useEffect(() => { const t = setTimeout(() => setSearch(searchText), 300); return () => clearTimeout(t); }, [searchText]);
  useEffect(() => { setPage(1); setChosen(new Set()); }, [direction, search, sort, store]);
  const params = { tenant_id: tenantId, store_id: direction === 'tenant' ? undefined : store?.store_id, direction: direction === 'tenant' ? 'all' : direction, search: search || undefined, sort: sort.key, order: sort.dir };
  useEffect(() => {
    if (!store) return undefined;
    let cancelled = false;
    const refresh = lastTick.current !== refreshTick;
    lastTick.current = refreshTick;
    setLoading(true);
    setError('');
    api.nonMoving('transfers', { ...params, page, page_size: PAGE_SIZE, refresh: refresh ? 'true' : undefined }, session)
      .then((d) => { if (!cancelled) { setData(d); onLoaded?.(d); } })
      .catch((e) => { if (!cancelled) setError(e.message || 'Could not load transfer opportunities'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [store, direction, search, sort, page, refreshTick, tenantId, session]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = data?.rows || [];
  const toggle = (id) => setChosen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const markReviewed = (id, verdict) => setReviewed((m) => {
    const next = { ...m };
    if (next[id] === verdict) delete next[id]; else next[id] = verdict;
    try { localStorage.setItem(reviewedKey(tenantId), JSON.stringify(next)); } catch { /* storage unavailable */ }
    return next;
  });
  const onSort = (key) => setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'product_name' ? 'asc' : 'desc' }));
  const proposal = async () => {
    setBusy('proposal');
    try {
      const { blob, filename } = await api.nonMovingExcel('transfers/proposal', null, session, { tenant_id: tenantId, store_id: store.store_id, ids: [...chosen] });
      saveBlob(blob, filename);
    } catch (e) { setError(e.message || 'Could not prepare the proposal'); } finally { setBusy(''); }
  };
  const exportAll = async () => {
    setBusy('export');
    try { const { blob, filename } = await api.nonMovingExcel('transfers', params, session); saveBlob(blob, filename); }
    catch (e) { setError(e.message || 'Export failed'); } finally { setBusy(''); }
  };
  const cols = [
    { label: '', w: 28 }, { label: 'Product', sort: 'product_name' },
    { label: 'From', sort: 'store_code', w: 54 }, { label: 'Stock', num: true, w: 58 }, { label: 'Days', sort: 'source_days_since_sale', num: true, w: 54 },
    { label: 'Class', w: 118 }, { label: 'To', w: 50 }, { label: 'Stock', num: true, w: 56 }, { label: 'Sales 30/90 d', num: true, w: 84 },
    { label: 'Need', sort: 'dest_need', num: true, w: 54 }, { label: 'Suggested', sort: 'suggested_qty', num: true, w: 72 },
    { label: 'From after', num: true, w: 66 }, { label: 'To after', num: true, w: 60 }, { label: 'Value (₹)', sort: 'transfer_value', num: true, w: 80 },
    { label: 'Review', w: 92 },
  ];
  return (
    <div className="nms-main nms-main--full">
      <div className="nms-banner" role="note">Recommendations only — nothing is moved or posted. A proposal is an Excel for the existing authorised stock-transfer process.</div>
      <div className="trp-bar nms-filters">
        <label className="trp-field nms-grow">Search<input type="search" value={searchText} placeholder="Product name or code…" onChange={(e) => setSearchText(e.target.value)} /></label>
        <label className="trp-field">Direction
          <select value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="out">Out of {store?.store_code} (its idle / excess stock)</option>
            <option value="in">Into {store?.store_code} (its demand)</option>
            <option value="all">Both directions for {store?.store_code}</option>
            {allStores && <option value="tenant">Every store</option>}
          </select>
        </label>
        <div className="trp-actions">
          <button type="button" className="secondary-button" disabled={!!busy || !data} onClick={exportAll}>{busy === 'export' ? 'Preparing…' : 'Export Excel'}</button>
          <button type="button" className="primary-button" disabled={!!busy || !chosen.size} onClick={proposal}
            title="Excel of the ticked recommendations for approval">{busy === 'proposal' ? 'Preparing…' : `Prepare Transfer Proposal${chosen.size ? ` (${chosen.size})` : ''}`}</button>
        </div>
      </div>
      {data && (
        <div className="nms-summary-line">
          <span><b>{fmtQty(data.total)}</b> recommendations · <b>{fmtQty(data.total_qty)}</b> units · <b>₹{fmtMoney(data.total_value)}</b> at cost</span>
          {data.blocked?.length > 0 && direction !== 'in' && (
            <span className="nms-blocked" title="Non-moving products with no recommendation, by reason (all are in the Excel 'No Transfer' sheet)">
              No transfer: {data.blocked.slice(0, 4).map((b) => `${b.reason} ${fmtQty(b.products)}`).join(' · ')}
            </span>
          )}
        </div>
      )}
      <div className="trp-tablewrap nms-grid">
        <table className="trp-table nms-table">
          <thead>
            <tr><th colSpan={2} /><th colSpan={4} className="trp-center nms-group">Source</th><th colSpan={4} className="trp-center nms-group">Destination</th><th colSpan={4} className="trp-center nms-group">Proposal</th><th /></tr>
            <tr>{cols.map((c, i) => <Th key={`${c.label}-${i}`} col={c} sort={sort} onSort={onSort} />)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Fragment key={r.id}>
                <tr className={`${open === r.id ? 'is-selected' : ''}${reviewed[r.id] === 'reject' ? ' nms-row-muted' : ''}`} onClick={() => setOpen(open === r.id ? null : r.id)} title="Click for the calculation">
                  <td onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={chosen.has(r.id)} onChange={() => toggle(r.id)} aria-label="Include in proposal" /></td>
                  <td className="trp-left nms-name" title={`${r.product_name} (${r.source_code} → ${r.dest_code})`}>{r.product_name}</td>
                  <td className="trp-left"><b>{r.source_store}</b></td>
                  <td className="nms-num">{fmtQty(r.source_stock)}</td>
                  <td className="nms-num">{fmtDays(r.source_days_since_sale)}</td>
                  <td className="trp-left"><ClassBadge value={r.source_classification} label={r.source_classification_label} /></td>
                  <td className="trp-left"><b>{r.dest_store}</b></td>
                  <td className="nms-num">{fmtQty(r.dest_stock)}</td>
                  <td className="nms-num">{fmtQty(r.dest_sales_30)} / {fmtQty(r.dest_sales_90)}</td>
                  <td className="nms-num">{fmtQty(r.dest_need)}</td>
                  <td className="nms-num nms-strong">{fmtQty(r.suggested_qty)}</td>
                  <td className="nms-num">{fmtQty(r.source_after)}</td>
                  <td className="nms-num">{fmtQty(r.dest_after)}</td>
                  <td className="nms-num">{fmtMoney(r.transfer_value)}</td>
                  <td className="trp-left" onClick={(e) => e.stopPropagation()}>
                    <button type="button" className={`nms-icon-btn${reviewed[r.id] === 'ok' ? ' is-ok' : ''}`} title="Reviewed - looks right" onClick={() => markReviewed(r.id, 'ok')}>✓</button>
                    <button type="button" className={`nms-icon-btn${reviewed[r.id] === 'reject' ? ' is-bad' : ''}`} title="Reviewed - not suitable" onClick={() => markReviewed(r.id, 'reject')}>✕</button>
                  </td>
                </tr>
                {open === r.id && (
                  <tr className="nms-calc-row"><td /><td colSpan={cols.length - 1}>
                    <div className="nms-transfer-reason">{r.reason}</div>
                    <div className="nms-transfer-calc">{r.calculation}</div>
                    <div className="nms-transfer-calc">Codes: {r.source_store} {r.source_code} → {r.dest_store} {r.dest_code} · source transferable {fmtQty(r.source_transferable)} (expired {fmtQty(r.source_expired_qty)}, near-expiry {fmtQty(r.source_near_expiry_qty)}, earliest expiry {fmtDate(r.source_earliest_expiry)})</div>
                  </td></tr>
                )}
              </Fragment>
            ))}
            {!rows.length && <tr><td colSpan={cols.length} className="nms-empty-cell">{loading ? 'Working out transfers across every store… the first load builds all stores (1–2 minutes).' : 'No transfer recommendation for this selection.'}</td></tr>}
          </tbody>
        </table>
      </div>
      {data && <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} extra={loading ? <span className="nms-pager-sum">updating…</span> : null} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
const STORE_SERIES = [
  { key: 'non_moving_value', label: 'Non-moving value', cls: 'nm-idle' },
  { key: 'dead_value', label: 'Dead stock value', cls: 'nm-dead' },
  { key: 'expiry_risk_value', label: 'Expiry risk value', cls: 'nm-exp' },
];
const MONTH_SERIES = [
  { key: 'qty_in', label: 'In (purchase + transfer in)', cls: 'in' },
  { key: 'qty_out', label: 'Out (sales + transfer out)', cls: 'out' },
];

function ValueSection({ dash, loading, store, session, tenantId, setError }) {
  const [busy, setBusy] = useState(false);
  const [valueKey, setValueKey] = useState('cost_value');
  if (!dash) return <div className="empty-state">{loading ? 'Building every store’s valuation… the first load takes 1–2 minutes.' : 'No data.'}</div>;
  const k = dash.kpis;
  const exportExcel = async () => {
    setBusy(true);
    try { const { blob, filename } = await api.nonMovingExcel('dashboard', { tenant_id: tenantId, store_id: store.store_id }, session); saveBlob(blob, filename); }
    catch (e) { setError(e.message || 'Export failed'); } finally { setBusy(false); }
  };
  const storeGroups = dash.stores.map((s) => ({ key: s.store_id, label: s.store_code, current: s.current, values: s, raw: s }));
  const monthGroups = (dash.monthly || []).map((m) => ({ key: m.ym, label: fmtMonthLabel(m.ym), values: m }));
  const nmShare = k.stock_value ? (k.non_moving_value / k.stock_value) * 100 : 0;
  return (
    <div className="nms-value">
      <div className="nms-value-head">
        <div className="trp-subnote nms-note">Valuation basis: <b>cost</b> = POS batch stock value at cost (GrsStkValueatCost). PTR and MRP values are separate measures, never mixed. Near expiry = expiring within 90 days.</div>
        <button type="button" className="primary-button" disabled={busy} onClick={exportExcel}>{busy ? 'Preparing…' : 'Export Excel'}</button>
      </div>
      <div className="nms-value-grid">
        <section className="ow-panel nms-card">
          <div className="ow-panel-title">{store.store_code} stock value <span className="ow-panel-subtitle">cost / PTR / MRP</span></div>
          <div className="nms-facts nms-facts--3">
            <div className="nms-fact"><span>All stock (cost)</span><b>₹{fmtMoney(k.stock_value)}</b></div>
            <div className="nms-fact"><span>All stock (PTR)</span><b>₹{fmtMoney(k.stock_ptr_value)}</b></div>
            <div className="nms-fact"><span>All stock (MRP)</span><b>₹{fmtMoney(k.stock_mrp_value)}</b></div>
            <div className="nms-fact"><span>Non-moving qty</span><b>{fmtQty(k.non_moving_qty)}</b></div>
            <div className="nms-fact"><span>Non-moving (cost)</span><b>₹{fmtMoney(k.non_moving_value)}</b><em>{nmShare.toFixed(1)}% of stock</em></div>
            <div className="nms-fact"><span>Non-moving (MRP)</span><b>₹{fmtMoney(k.non_moving_mrp_value)}</b></div>
            <div className="nms-fact nms-fact--bad"><span>Critical dead stock</span><b>₹{fmtMoney(k.dead_value)}</b><em>{fmtQty(k.dead_products)} products</em></div>
            <div className="nms-fact nms-fact--bad"><span>Expired stock</span><b>₹{fmtMoney(k.expired_value)}</b><em>{fmtQty(k.expired_qty)} qty</em></div>
            <div className="nms-fact nms-fact--warn"><span>Near expiry (90 d)</span><b>₹{fmtMoney(k.near_expiry_value)}</b></div>
          </div>
          {k.stock_mismatch_products > 0 && <div className="trp-subnote nms-note">{fmtQty(k.stock_mismatch_products)} products have store stock that disagrees with their batch stock — shown, never valued from the higher figure.</div>}
        </section>
        <section className="ow-panel nms-card">
          <div className="ow-panel-title">Stock value by classification
            <span className="nms-toggle">
              {[['cost_value', 'Cost'], ['mrp_value', 'MRP'], ['products', 'Products']].map(([key, label]) => (
                <button key={key} type="button" className={`rta-chip${valueKey === key ? ' active' : ''}`} onClick={() => setValueKey(key)}>{label}</button>
              ))}
            </span>
          </div>
          <ClassBars rows={dash.by_class} valueKey={valueKey} />
        </section>
        <section className="ow-panel nms-card">
          <div className="ow-panel-title">Store-wise non-moving stock (cost) <Legend series={STORE_SERIES} /></div>
          <BarChart groups={storeGroups} series={STORE_SERIES} height={170}
            tipRows={(g) => [['Non-moving', `₹${fmtMoney(g.raw.non_moving_value)} (${fmtQty(g.raw.non_moving_products)})`], ['Dead stock', `₹${fmtMoney(g.raw.dead_value)}`], ['Expiry risk', `₹${fmtMoney(g.raw.expiry_risk_value)}`], ['All stock', `₹${fmtMoney(g.raw.stock_value)}`], ['Transfers out / in', `${g.raw.transfer_out} / ${g.raw.transfer_in}`]]} />
        </section>
        <section className="ow-panel nms-card">
          <div className="ow-panel-title">{store.store_code} monthly stock movement (qty) <Legend series={MONTH_SERIES} /></div>
          <BarChart groups={monthGroups} series={MONTH_SERIES} height={170}
            tipRows={(g) => [['In', fmtQty(g.values.qty_in)], ['Out', fmtQty(g.values.qty_out)], ['Closing value (cost)', `₹${fmtMoney(g.values.stock_value)}`], ['Stocked / idle products', `${fmtQty(g.values.stocked_products)} / ${fmtQty(g.values.idle_products)}`]]} />
          <div className="trp-subnote nms-note">The current month is partial. Source: POS monthly rollup (ProductTrans).</div>
        </section>
      </div>
      <section className="ow-panel nms-card">
        <div className="ow-panel-title">Store comparison</div>
        <div className="trp-tablewrap nms-subtable">
          <table className="trp-table nms-table">
            <thead><tr>
              <th className="trp-left">Store</th><th className="nms-num">In stock</th><th className="nms-num">Stock value</th><th className="nms-num">Non-moving</th>
              <th className="nms-num">Non-moving value</th><th className="nms-num">Share</th><th className="nms-num">Dead value</th><th className="nms-num">Expired</th>
              <th className="nms-num">Near expiry</th><th className="nms-num">Transfers out / in</th>
            </tr></thead>
            <tbody>
              {dash.stores.map((s) => (
                <tr key={s.store_id} className={s.current ? 'nms-row-current' : undefined}>
                  <td className="trp-left"><b>{s.store_code}</b>{s.is_warehouse ? ' (WH)' : ''}</td>
                  <td className="nms-num">{fmtQty(s.products_analyzed)}</td>
                  <td className="nms-num">{fmtMoney(s.stock_value)}</td>
                  <td className="nms-num">{fmtQty(s.non_moving_products)}</td>
                  <td className="nms-num">{fmtMoney(s.non_moving_value)}</td>
                  <td className="nms-num">{s.stock_value ? `${((s.non_moving_value / s.stock_value) * 100).toFixed(1)}%` : '—'}</td>
                  <td className="nms-num">{fmtMoney(s.dead_value)}</td>
                  <td className="nms-num">{fmtMoney(s.expired_value)}</td>
                  <td className="nms-num">{fmtMoney(s.near_expiry_value)}</td>
                  <td className="nms-num">{s.transfer_out} / {s.transfer_in}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="ow-panel nms-card">
        <div className="ow-panel-title">Highest expiry risk at {store.store_code} <span className="ow-panel-subtitle">expired + near-expiry value</span></div>
        <div className="trp-tablewrap nms-subtable">
          <table className="trp-table nms-table">
            <thead><tr><th className="trp-left">Code</th><th className="trp-left">Product</th><th className="nms-num">Stock</th><th className="nms-num">Expired qty</th><th className="nms-num">Expired value</th><th className="nms-num">Near-expiry qty</th><th className="nms-num">Near-expiry value</th><th className="trp-left">Earliest expiry</th><th className="nms-num">Days since sale</th><th className="trp-left">Classification</th></tr></thead>
            <tbody>
              {dash.expiry_top.map((r) => (
                <tr key={r.product_code}>
                  <td className="trp-left">{r.product_code}</td>
                  <td className="trp-left nms-name" title={r.product_name}>{r.product_name}</td>
                  <td className="nms-num">{fmtQty(r.stock)}</td>
                  <td className="nms-num">{fmtQty(r.expired_qty)}</td>
                  <td className="nms-num">{fmtMoney(r.expired_value)}</td>
                  <td className="nms-num">{fmtQty(r.near_expiry_qty)}</td>
                  <td className="nms-num">{fmtMoney(r.near_expiry_value)}</td>
                  <td className="trp-left">{fmtDate(r.earliest_expiry)}</td>
                  <td className="nms-num">{fmtDays(r.days_since_sale)}</td>
                  <td className="trp-left"><ClassBadge value={r.classification} label={r.classification_label} /></td>
                </tr>
              ))}
              {!dash.expiry_top.length && <tr><td colSpan={10} className="nms-empty-cell">No expired or near-expiry stock.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
function ReviewDrawer({ list, onRemove, onClear, onClose, session, tenantId, setError }) {
  const [busy, setBusy] = useState(false);
  const exportExcel = async () => {
    setBusy(true);
    try {
      const { blob, filename } = await api.nonMovingExcel('review/export', null, session, { tenant_id: tenantId, items: list.map((it) => ({ store_id: it.store_id, product_code: it.product_code })) });
      saveBlob(blob, filename);
    } catch (e) { setError(e.message || 'Export failed'); } finally { setBusy(false); }
  };
  return (
    <div className="nms-drawer" role="dialog" aria-label="Manual review list">
      <div className="nms-drawer-head">
        <strong>Manual review list ({list.length})</strong>
        <span className="trp-subnote nms-note">Kept on this PC.</span>
        <button type="button" className="primary-button" disabled={busy || !list.length} onClick={exportExcel}>{busy ? 'Preparing…' : 'Export Excel'}</button>
        <button type="button" className="secondary-button" disabled={!list.length} onClick={onClear}>Clear</button>
        <button type="button" className="secondary-button" onClick={onClose}>✕</button>
      </div>
      <div className="nms-drawer-body">
        {list.map((it) => (
          <div key={`${it.store_id}|${it.product_code}`} className="nms-drawer-row">
            <b>{it.store_code}</b><span>{it.product_code}</span><span className="nms-ellipsis" title={it.product_name}>{it.product_name}</span><em>{fmtDate(it.added)}</em>
            <button type="button" className="nms-icon-btn" title="Remove" onClick={() => onRemove(it)}>✕</button>
          </div>
        ))}
        {!list.length && <div className="empty-state">Nothing yet — use ☆ on a product (or R in the grid).</div>}
      </div>
    </div>
  );
}

export default function NonMovingStock({ session, settings, ui, hidden }) {
  const tenantId = settings?.tenantId || session?.user?.tenant_id || '';
  const [stores, setStores] = useState([]);
  const [storeId, setStoreId] = useState('');
  const [scope, setScope] = useState('all');
  const [section, setSection] = useState('own');
  const [error, setError] = useState('');
  const [refreshTick, setRefreshTick] = useState(0);
  const [ownInfo, setOwnInfo] = useState(null);
  const [dash, setDash] = useState(null);
  const [dashLoading, setDashLoading] = useState(false);
  const [review, setReview] = useState(() => readReview(globalThis.localStorage, tenantId));
  const [showReview, setShowReview] = useState(false);
  const [dataStamp, setDataStamp] = useState('');
  const lastDashTick = useRef(refreshTick);

  useEffect(() => { setReview(readReview(globalThis.localStorage, tenantId)); }, [tenantId]);
  useEffect(() => {
    if (!tenantId) return;
    api.nonMoving('stores', { tenant_id: tenantId }, session)
      .then((d) => {
        const list = d.stores || [];
        setStores(list);
        setScope(d.scope || 'all');
        setStoreId((cur) => {
          if (cur && list.some((s) => s.store_id === cur)) return cur;
          const own = list.find((s) => String(s.store_id).toUpperCase() === String(session?.user?.store_id || '').toUpperCase());
          return (own || list.find((s) => !s.is_warehouse) || list[0])?.store_id || '';
        });
      })
      .catch((e) => setError(e.message || 'Could not load stores'));
  }, [tenantId, session]);

  const store = stores.find((s) => s.store_id === storeId) || null;

  // Tenant-wide KPIs + charts (transfer count, store comparison). Loaded after
  // the own-store grid so the first screen is not held up by every store.
  const loadDash = useCallback((refresh) => {
    if (!store) return undefined;
    let cancelled = false;
    setDashLoading(true);
    api.nonMoving('dashboard', { tenant_id: tenantId, store_id: store.store_id, refresh: refresh ? 'true' : undefined }, session)
      .then((d) => { if (!cancelled) setDash(d); })
      .catch((e) => { if (!cancelled) setError(e.message || 'Could not load the summary'); })
      .finally(() => { if (!cancelled) setDashLoading(false); });
    return () => { cancelled = true; };
  }, [store, tenantId, session]);

  useEffect(() => { setDash(null); setOwnInfo(null); setDataStamp(''); }, [storeId]);
  // The KPIs / charts reload after the open section has (re)loaded its own
  // data, so a Refresh never shows the summary of the previous snapshot.
  useEffect(() => {
    if (!store || !dataStamp) return undefined;
    return loadDash(false);
  }, [store, dataStamp]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (section !== 'value' || !store) return undefined;
    const refresh = lastDashTick.current !== refreshTick;
    lastDashTick.current = refreshTick;
    if (!refresh && (dash || dashLoading)) return undefined;
    return loadDash(refresh);
  }, [section, store, refreshTick]); // eslint-disable-line react-hooks/exhaustive-deps

  const onToggleReview = useCallback((item) => {
    setReview((list) => {
      const next = toggleReview(list, item);
      writeReview(globalThis.localStorage, tenantId, next);
      return next;
    });
  }, [tenantId]);

  const k = dash?.kpis || ownInfo?.kpis;
  const refreshedAt = section === 'own' ? ownInfo?.refreshed_at : dash?.refreshed_at || ownInfo?.refreshed_at;

  if (!tenantId) {
    return (
      <section className="screen-panel trp-screen" hidden={hidden}>
        <header className="screen-header"><div><h2>Non-Moving Stock</h2></div></header>
        <div className="status-line error">No tenant selected for this login.</div>
      </section>
    );
  }

  return (
    <section className="screen-panel trp-screen nms-screen" hidden={hidden}>
      <header className="screen-header nms-header">
        <div><h2>Non-Moving Stock</h2><p>Idle stock, capital locked, expiry risk and branch transfer opportunities. Analysis only.</p></div>
        <div className="nms-header-tools">
          <label className="trp-field">Store
            <select value={storeId} onChange={(e) => setStoreId(e.target.value)} disabled={stores.length < 2} title={scope === 'own' ? 'Purchase managers see their own store' : undefined}>
              {stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_code} — {s.store_name}{s.is_warehouse ? ' (warehouse)' : ''}</option>)}
            </select>
          </label>
          <span className="nms-stamp" title="Each store's snapshot is kept for 30 minutes; Refresh re-reads it">{refreshedAt ? `Data as of ${stamp(refreshedAt)}` : 'Loading…'}</span>
          <button type="button" className="secondary-button" onClick={() => setRefreshTick((t) => t + 1)} title="Re-read sales, purchases and batches now">↻ Refresh</button>
          <button type="button" className="secondary-button" onClick={() => setShowReview((v) => !v)}>☆ Review list ({review.length})</button>
        </div>
      </header>

      <div className="nms-kpis">
        <Kpi label="Products analysed" value={k ? fmtQty(k.products_analyzed) : '…'} sub="in stock" />
        <Kpi label="Non-moving products" value={k ? fmtQty(k.non_moving_products) : '…'} sub="> 90 days or never sold" tone="warn" />
        <Kpi label="Critical dead stock" value={k ? fmtQty(k.dead_products) : '…'} sub={k ? `₹${fmtCompact(k.dead_value)} · > 365 days` : ''} tone="bad" />
        <Kpi label="Non-moving value" value={k ? `₹${fmtCompact(k.non_moving_value)}` : '…'} sub={k && k.stock_value ? `${((k.non_moving_value / k.stock_value) * 100).toFixed(1)}% of ₹${fmtCompact(k.stock_value)} (cost)` : ''} tone="warn" />
        <Kpi label="Expiry risk value" value={k ? `₹${fmtCompact(k.expiry_risk_value)}` : '…'} sub={k ? `expired ₹${fmtCompact(k.expired_value)} · near ₹${fmtCompact(k.near_expiry_value)}` : ''} tone="bad" />
        <Kpi label="Transfer opportunities" value={dash ? fmtQty(dash.kpis.transfer_opportunities) : (dashLoading ? 'building…' : '…')}
          sub={dash ? `₹${fmtCompact(dash.kpis.transfer_value)} out · ${fmtQty(dash.kpis.transfer_in_opportunities)} inbound` : 'all stores'} tone="ok" />
      </div>

      <div className="rta-tabs nms-tabs" role="tablist">
        {SECTIONS.map((s) => (
          <button key={s.id} type="button" role="tab" aria-selected={section === s.id} className={`rta-chip${section === s.id ? ' active' : ''}`}
            onClick={() => { setSection(s.id); setError(''); }}>{s.label}</button>
        ))}
      </div>
      {error && <div className="status-line error">{error}</div>}

      {store && section === 'own' && (
        <OwnStoreSection ui={ui} session={session} tenantId={tenantId} store={store} refreshTick={refreshTick} onLoaded={(d) => { setOwnInfo(d); setDataStamp(d.refreshed_at); }}
          review={review} onToggleReview={onToggleReview} setError={setError} />
      )}
      {store && section === 'other' && (
        <OtherStoresSection ui={ui} session={session} tenantId={tenantId} store={store} refreshTick={refreshTick} onLoaded={(d) => setDataStamp(d.refreshed_at)}
          review={review} onToggleReview={onToggleReview} setError={setError} />
      )}
      {store && section === 'transfer' && <TransfersSection session={session} tenantId={tenantId} store={store} refreshTick={refreshTick} onLoaded={(d) => setDataStamp(d.refreshed_at)} setError={setError} allStores={scope === 'all'} />}
      {store && section === 'value' && <ValueSection dash={dash} loading={dashLoading} store={store} session={session} tenantId={tenantId} setError={setError} />}
      {!store && !error && <div className="empty-state">Loading stores…</div>}

      {showReview && (
        <ReviewDrawer list={review} session={session} tenantId={tenantId} setError={setError} onClose={() => setShowReview(false)}
          onRemove={(it) => onToggleReview(it)} onClear={() => { setReview([]); writeReview(globalThis.localStorage, tenantId, []); }} />
      )}
    </section>
  );
}
