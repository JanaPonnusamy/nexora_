import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { api } from './api/client.js';
import { TrendBars, TrendTip, fmtMonthLabel as fmtOwMonthLabel, trendMax } from './trendChart.jsx';
import { asArray, fmtOwDate, fmtOwMoney, fmtOwPct, fmtOwQty, fmtOwSigned, owLandingPct } from './OwFormatters.js';

// Purchase/Sales/Monthly-Trend intelligence panel, shared by Order Workspace
// (rendered directly) and Procurement (via App.jsx's PROCUREMENT_UI bridge
// -> ProcurementWorkspace.jsx). Extracted from App.jsx unchanged (NEXORA
// MEDIQ Phase 4 structural refactor) -- no behavior altered in the move.

const owIntelCache = new Map();
const OW_INTEL_TTL_MS = 5 * 60 * 1000;
function owIntelCacheGet(key) {
  const hit = owIntelCache.get(key);
  if (!hit) return null;
  if (Date.now() - hit.at > OW_INTEL_TTL_MS) { owIntelCache.delete(key); return null; }
  return hit.promise;
}
function owIntelCacheSet(key, promise) {
  owIntelCache.set(key, { promise, at: Date.now() });
  if (owIntelCache.size > 400) owIntelCache.delete(owIntelCache.keys().next().value);
}

function owLatestByDate(rows, field) {
  if (!Array.isArray(rows) || !rows.length) return null;
  return rows.reduce((best, row) => {
    const stamp = Date.parse(row?.[field] || '');
    const bestStamp = Date.parse(best?.[field] || '');
    if (Number.isFinite(stamp) && (!Number.isFinite(bestStamp) || stamp > bestStamp)) return row;
    return best;
  });
}

function owMoneyOrNull(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

// trendFit {fetch, min, max} (Procurement): fetch `fetch` calendar months and
// draw the latest `min` that have data, or up to `max` when the chart is wide
// enough. Omitted (Order Workspace) = the legacy 4-month window, all drawn.
export function OrderIntelligence({ store, productCode, visibleCodes, product, mode, session, onError, sections = ['trend', 'purchase', 'sales'], onPurchaseSelect, onSalesSelect, onLatest, trendFit, exactRow = false }) {
  const [purchase, setPurchase] = useState([]);
  const [sales, setSales] = useState([]);
  const [monthly, setMonthly] = useState([]);
  const [trendShown, setTrendShown] = useState(0);
  const trendMonths = trendFit?.fetch;
  const intelKey = (code) => `${store}|${mode}|${code}${trendMonths ? `|m${trendMonths}` : ''}`;
  const [loading, setLoading] = useState(false);

  // Arrow-key row navigation can fire a selectedCode change every ~30-50ms
  // while the operator holds the key down; fetching Purchase/Sales/Trend on
  // every single intermediate row (three HTTP round-trips each) is what
  // makes the sidebar visibly lag behind the highlighted row -- VB.NET's
  // equivalent was an in-memory DataTable lookup, not a network call. Settle
  // briefly before fetching so only the row the operator actually stops on
  // triggers a request; fast scrolling no longer queues up a fetch per row.
  const [settledCode, setSettledCode] = useState(productCode);
  useEffect(() => {
    if (productCode === settledCode) return undefined;
    const t = setTimeout(() => setSettledCode(productCode), 120);
    return () => clearTimeout(t);
  }, [productCode, settledCode]);

  // Per-(store,mode) detail cache so a product's Purchase/Sales/Trend is
  // fetched at most once -- revisiting a row (or landing on one already
  // prefetched below) is instant, with no spinner or network wait. Values are
  // the in-flight Promise itself, so a prefetch and a real selection of the
  // same code dedupe to one request. Cleared when the store/mode changes so it
  // never grows unbounded or serves another store's data.
  const fetchDetails = useCallback((code) => {
    if (!store || code == null) return Promise.resolve({ purchase: [], sales: [], monthly: [] });
    const key = intelKey(code);
    const hit = owIntelCacheGet(key);
    if (hit) return hit;
    const p = Promise.all([
      api.legacyPurchaseDetails(store, code, mode, session).catch(() => (exactRow ? null : [])),
      api.legacySalesDetails(store, code, mode, session).catch(() => (exactRow ? null : [])),
      api.legacyMonthlyStats(store, code, mode, session, trendMonths).catch(() => (exactRow ? null : []))
    ]).then(([pp, ss, mm]) => {
      // Procurement (exactRow): a call that failed (HO unreachable) is not
      // cached as "no history" -- the next visit to the row asks again.
      if (pp === null || ss === null || mm === null) owIntelCache.delete(key);
      return { purchase: asArray(pp), sales: asArray(ss), monthly: asArray(mm), failed: pp === null && ss === null && mm === null };
    })
      .catch(() => { owIntelCache.delete(key); return { purchase: [], sales: [], monthly: [] }; });
    owIntelCacheSet(key, p);
    return p;
  }, [store, mode, session, exactRow]);

  const [pricedCode, setPricedCode] = useState(null);
  const [failed, setFailed] = useState(false);
  const onLatestRef = useRef(onLatest);
  onLatestRef.current = onLatest;

  useEffect(() => {
    if (!store || settledCode == null) { setPurchase([]); setSales([]); setMonthly([]); setPricedCode(null); return undefined; }
    let cancelled = false;
    setPricedCode(null);
    // Only show the spinner for a genuine fetch; a cached/prefetched row
    // resolves on the same tick and shouldn't flash "loading".
    const cached = Boolean(owIntelCacheGet(intelKey(settledCode)));
    if (!cached) setLoading(true);
    fetchDetails(settledCode)
      .then((data) => {
        if (cancelled) return;
        setPurchase(data.purchase);
        setSales(data.sales);
        setMonthly(data.monthly);
        setFailed(Boolean(data.failed));
        setPricedCode(settledCode);
      })
      .catch((e) => { if (!cancelled) onError?.(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [store, settledCode, mode, session, fetchDetails]);

  // Warm the cache for the next few rows (and the previous one, for Up-arrow)
  // in the background, so arrow navigation lands on already-loaded data.
  useEffect(() => {
    if (!store || settledCode == null || !visibleCodes?.length) return;
    const idx = visibleCodes.indexOf(settledCode);
    if (idx < 0) return;
    const ahead = visibleCodes.slice(idx + 1, idx + 1 + 4);
    const behind = idx > 0 ? [visibleCodes[idx - 1]] : [];
    [...ahead, ...behind].forEach((code) => { if (code != null) fetchDetails(code); });
  }, [store, settledCode, mode, session, visibleCodes, fetchDetails]);

  useEffect(() => {
    const publish = onLatestRef.current;
    if (!publish || pricedCode == null || String(pricedCode) !== String(settledCode)) return;
    const latest = owLatestByDate(purchase, 'GRNDate');
    const sale = owLatestByDate(sales, 'Bill_Time');
    publish({
      code: pricedCode,
      cost: latest ? owMoneyOrNull(latest.ItemCost) : null,
      ptr: latest ? owMoneyOrNull(latest.PTR) : null,
      purchaseMrp: latest ? owMoneyOrNull(latest.MRP) : null,
      discount: latest && latest.DIS != null && latest.DIS !== '' ? latest.DIS : null,
      supplier: latest?.SupplierName || null,
      grnDate: latest?.GRNDate || null,
      freeQty: latest ? owMoneyOrNull(latest.FreeQty) : null,
      receivedQty: latest ? owMoneyOrNull(latest.RStock) : null,
      lastSaleDate: sale?.Bill_Time || null,
    });
  }, [purchase, sales, pricedCode, settledCode]);

  const empty = productCode == null;
  // Procurement (exactRow): show Purchase / Sales / Trend only once they
  // belong to the highlighted row. Until then the panels say Loading, never
  // the previous row's figures (a slow HO link used to hold them for rows).
  const stale = exactRow && !empty && (pricedCode == null || String(pricedCode) !== String(productCode));
  const loadFailed = exactRow && !stale && failed;
  const purchaseRows = stale ? [] : purchase;
  const salesRows = stale ? [] : sales;
  const monthlyRows = stale ? [] : monthly;
  const busy = loading || stale;
  const emptyText = (none) => (empty ? 'Select a product.' : busy ? 'Loading…' : loadFailed ? 'Could not load — HO not reachable. Move away and back to retry.' : none);

  const sectionMap = {
    trend: (
      <section className="ow-panel ow-panel--chart" key="trend">
        <div className="ow-panel-title">
          Monthly Trend<span className="ow-panel-subtitle">Stock movement — last {(trendFit ? trendShown : monthlyRows.length) || 4} months</span>
          {busy && <span className="ow-intel-loading">…</span>}
        </div>
        <div className="ow-panel-body">
          {empty ? <div className="ow-empty">Select a product.</div> : <OwTrendChart rows={monthlyRows} loading={busy} fit={trendFit} onShown={setTrendShown} />}
        </div>
      </section>
    ),
    purchase: (
      <section className="ow-panel ow-panel--purchase" key="purchase">
        <div className="ow-panel-title">Purchase / GRN</div>
        <div className="ow-panel-scroll">
          <table className="ow-intel-table">
            <thead><tr><th className="ow-num">Stock</th><th className="ow-num">Free</th><th className="ow-num ow-grp">Dis%</th><th className="ow-num">Land%</th><th className="ow-num ow-grp ow-col-cost">Cost</th><th className="ow-num ow-col-ptr">PTR</th><th className="ow-num ow-col-mrp">MRP</th><th className="ow-grp">GRN Date</th><th className="ow-intel-grow">Supplier</th></tr></thead>
            <tbody>
              {purchaseRows.map((row, i) => (
                <tr key={i} className={`ow-intel-clickable${Number(row.FreeQty) > 0 ? ' ow-freerow' : ''}`} title="Click to see the whole purchase invoice" onClick={() => onPurchaseSelect?.(row)}>
                  <td className="ow-num">{fmtOwQty(row.RStock)}</td>
                  <td className="ow-num">{fmtOwQty(row.FreeQty)}</td>
                  <td className="ow-num ow-grp">{fmtOwPct(row.DIS)}</td>
                  <td className="ow-num">{fmtOwPct(owLandingPct(row.PTR, row.ItemCost))}</td>
                  <td className="ow-num ow-grp ow-col-cost">{fmtOwMoney(row.ItemCost)}</td>
                  <td className="ow-num ow-col-ptr">{fmtOwMoney(row.PTR)}</td>
                  <td className="ow-num ow-col-mrp">{fmtOwMoney(row.MRP)}</td>
                  <td className="ow-grp">{fmtOwDate(row.GRNDate)}</td>
                  <td className="ow-intel-grow">{row.SupplierName ?? '—'}</td>
                </tr>
              ))}
              {!purchaseRows.length && <tr><td colSpan={9} className="ow-empty">{emptyText('No purchase history.')}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    ),
    sales: (
      <section className="ow-panel ow-panel--sales" key="sales">
        <div className="ow-panel-title">Bill / Sales</div>
        <div className="ow-panel-scroll">
          <table className="ow-intel-table">
            <thead><tr><th className="ow-num">Qty</th><th>Bill Time</th><th className="ow-intel-cust">Salesman</th><th className="ow-intel-cust">Customer</th><th className="ow-num">Dis%</th><th className="ow-num">MRP</th></tr></thead>
            <tbody>
              {salesRows.map((row, i) => (
                <tr key={i} className="ow-intel-clickable" title="Click to see the whole sales bill" onClick={() => onSalesSelect?.(row)}>
                  <td className="ow-num">{fmtOwQty(row.TotalQuantity)}</td>
                  <td>{fmtOwDate(row.Bill_Time)}</td>
                  <td className="ow-intel-cust" title={row.Salesmanname}>{row.Salesmanname ?? '—'}</td>
                  <td className="ow-intel-cust" title={row.CUSTOMERNAME}>{row.CUSTOMERNAME ?? '—'}</td>
                  <td className="ow-num">{fmtOwPct(row.dis)}</td>
                  <td className="ow-num">{fmtOwMoney(row.mrp)}</td>
                </tr>
              ))}
              {!salesRows.length && <tr><td colSpan={6} className="ow-empty">{emptyText('No sales history.')}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    ),
  };
  return <>{sections.map((key) => sectionMap[key])}</>;
}

// Stock-movement trend: IN (blue) / OUT (green) / STOCK (red) bars share one
// unsigned scale; ADJUSTMENT (purple) is a small diverging bar in its own lane
// with its own scale, since its magnitude is usually far smaller than the raw
// quantities and it is the only series that can be negative -- forcing it
// onto the shared axis would either crush the other three bars or make
// Adjustment invisible. Both IN and OUT are already return-adjusted per
// qty_check_monthly_stats' verified formula (IN = purchase + transfer_in +
// sales_return, OUT = sales + transfer_out + purchase_return); Adjustment
// already includes expiry returns, so it is deliberately NOT added again into
// OUT (see that function's docstring) -- the tooltip labels this explicitly
// rather than silently doing the math wrong.
const OW_TREND_SERIES = [
  { key: 'total_in', label: 'In', cls: 'in' },
  { key: 'total_out', label: 'Out', cls: 'out' },
  { key: 'stock', label: 'Stock', cls: 'stock' },
];

// A month group needs ~66px (three 15px bars + labels) plus the plot's 10px
// gap; `fit` {min, max} picks how many of the latest rows fit the width.
const OW_TREND_GROUP_PX = 76;

function OwTrendChart({ rows: allRows, loading, fit, onShown }) {
  const [hover, setHover] = useState(null); // { row, rect }
  const [width, setWidth] = useState(0);
  const rootRef = useRef(null);
  const hasRows = allRows.length > 0;
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!fit || !el) return undefined;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, [fit, hasRows]);
  const count = fit ? Math.max(fit.min, Math.min(fit.max, Math.floor((width - 10) / OW_TREND_GROUP_PX))) : allRows.length;
  const rows = fit ? allRows.slice(-count) : allRows;
  useEffect(() => { onShown?.(rows.length); }, [rows.length, onShown]);
  if (!rows.length) return <div className="ow-empty">{loading ? 'Loading…' : 'No monthly statistics.'}</div>;

  const maxLevel = trendMax(rows, OW_TREND_SERIES);
  const maxAdj = Math.max(1, ...rows.map((r) => Math.abs(Number(r.adjustment) || 0)));

  const showTip = (e, row) => setHover({ row, rect: e.currentTarget.getBoundingClientRect() });
  const hideTip = () => setHover(null);

  return (
    <div className="ow-chart" ref={rootRef}>
      <div className="ow-chart-plot">
        {rows.map((row, i) => {
          const adj = Number(row.adjustment) || 0;
          const adjPct = adj === 0 ? 0 : Math.min(100, (Math.abs(adj) / maxAdj) * 100);
          return (
            <div
              className="ow-chart-group"
              key={`${row.month}-${i}`}
              onMouseEnter={(e) => showTip(e, row)}
              onMouseLeave={hideTip}
              onFocus={(e) => showTip(e, row)}
              onBlur={hideTip}
              tabIndex={0}
            >
              <TrendBars series={OW_TREND_SERIES} row={row} max={maxLevel} fmt={fmtOwQty} />
              <div className="ow-chart-adjlane">
                <div className="ow-chart-adjtrack-pos">
                  {adj > 0 && (
                    <div className="ow-chart-adjbar is-pos" style={{ height: `${adjPct}%` }}>
                      <span className="ow-chart-adjval">{fmtOwSigned(adj)}</span>
                    </div>
                  )}
                </div>
                <div className="ow-chart-adjtrack-base" />
                <div className="ow-chart-adjtrack-neg">
                  {adj < 0 && (
                    <div className="ow-chart-adjbar is-neg" style={{ height: `${adjPct}%` }}>
                      <span className="ow-chart-adjval">{fmtOwSigned(adj)}</span>
                    </div>
                  )}
                  {adj === 0 && (
                    <div className="ow-chart-adjbar is-zero">
                      <span className="ow-chart-adjval">0</span>
                    </div>
                  )}
                </div>
              </div>
              <div className="ow-chart-month">{fmtOwMonthLabel(row.month)}</div>
            </div>
          );
        })}
      </div>
      <div className="ow-chart-legend">
        <span><i className="ow-chart-dot ow-chart-dot--in" />In</span>
        <span><i className="ow-chart-dot ow-chart-dot--out" />Out</span>
        <span><i className="ow-chart-dot ow-chart-dot--stock" />Stock</span>
        <span><i className="ow-chart-dot ow-chart-dot--adj" />Adjustment</span>
      </div>
      {hover && <OwChartTooltip row={hover.row} anchorRect={hover.rect} />}
    </div>
  );
}

// Rich floating tooltip for one month (TrendTip: portaled to document.body).
// Purely presentational: every value it shows already comes from
// qty_check_monthly_stats' response, computed once on the backend.
function OwChartTooltip({ row, anchorRect }) {
  return (
    <TrendTip anchorRect={anchorRect}>
      <div className="ow-chart-tip-month">{fmtOwMonthLabel(row.month)}</div>
      <div className="ow-chart-tip-section ow-chart-tip-section--in">
        <div className="ow-chart-tip-head">IN</div>
        <div className="ow-chart-tip-row"><span>Purchase</span><b>{fmtOwQty(row.gross_purchase)}</b></div>
        <div className="ow-chart-tip-row"><span>Transfer In</span><b>{fmtOwQty(row.transfer_in)}</b></div>
        <div className="ow-chart-tip-row"><span>Sales Return</span><b>{fmtOwQty(row.sales_return)}</b></div>
        <div className="ow-chart-tip-row ow-chart-tip-total"><span>Total IN</span><b>{fmtOwQty(row.total_in)}</b></div>
      </div>
      <div className="ow-chart-tip-section ow-chart-tip-section--out">
        <div className="ow-chart-tip-head">OUT</div>
        <div className="ow-chart-tip-row"><span>Sales</span><b>{fmtOwQty(row.gross_sales)}</b></div>
        <div className="ow-chart-tip-row"><span>Transfer Out</span><b>{fmtOwQty(row.transfer_out)}</b></div>
        <div className="ow-chart-tip-row"><span>Purchase Return</span><b>{fmtOwQty(row.purchase_return)}</b></div>
        <div className="ow-chart-tip-row ow-chart-tip-total"><span>Total OUT</span><b>{fmtOwQty(row.total_out)}</b></div>
      </div>
      <div className="ow-chart-tip-section ow-chart-tip-section--stock">
        <div className="ow-chart-tip-head">STOCK</div>
        <div className="ow-chart-tip-row ow-chart-tip-single"><b>{fmtOwQty(row.stock)}</b></div>
      </div>
      <div className="ow-chart-tip-section ow-chart-tip-section--adj">
        <div className="ow-chart-tip-head">ADJUSTMENT</div>
        <div className="ow-chart-tip-row ow-chart-tip-single"><b>{fmtOwSigned(row.adjustment)}</b></div>
        <div className="ow-chart-tip-note">includes expiry returns</div>
      </div>
    </TrendTip>
  );
}
