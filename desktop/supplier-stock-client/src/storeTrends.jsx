import { useEffect, useState } from 'react';
import { api } from './api/client.js';
import { TrendBars, TrendTip, fmtMonthLabel, trendMax } from './trendChart.jsx';

// Procurement "All Stores" panel: the selected product's latest 4 months at
// every store (this store first, then each store's mapped code -- the same
// product_mapping resolution as the Suggestion panel's "Other stores"), as one
// miniature In / Out / Stock chart per store (one row each, the same months
// in the same columns for every store). Source: each store's monthly
// ProductTrans rollup; OUT includes transfer-out, so a warehouse's despatch
// to the branches shows as movement. The bars are Monthly Trend's
// (trendChart.jsx), on ONE scale across all stores so rows compare; a month
// with no ProductTrans row shows "no data", never a made-up 0.

const cache = new Map();
const CACHE_MS = 3 * 60 * 1000;
const SERIES = [{ key: 'in', label: 'In', cls: 'in' }, { key: 'out', label: 'Out', cls: 'out' }, { key: 'stock', label: 'Stock', cls: 'stock' }];

function useStoreTrends({ tenantId, storeId, productCode, session }) {
  const [state, setState] = useState({ loading: false, error: '', data: null });
  const key = tenantId && storeId && productCode != null ? `${tenantId}|${storeId}|${productCode}` : '';
  useEffect(() => {
    if (!key) { setState({ loading: false, error: '', data: null }); return undefined; }
    const hit = cache.get(key);
    if (hit && Date.now() - hit.at < CACHE_MS) { setState({ loading: false, error: '', data: hit.data }); return undefined; }
    let cancelled = false;
    setState({ loading: true, error: '', data: null });
    const t = setTimeout(() => {
      api.procurementStoreTrends(tenantId, storeId, productCode, session)
        .then((data) => { cache.set(key, { at: Date.now(), data }); if (!cancelled) setState({ loading: false, error: '', data }); })
        .catch((e) => { if (!cancelled) setState({ loading: false, error: e.message || 'Could not load store trends.', data: null }); });
    }, 150);
    return () => { cancelled = true; clearTimeout(t); };
  }, [key, tenantId, storeId, productCode, session]);
  return state;
}

function qty(v) {
  const n = Number(v);
  return v == null || !Number.isFinite(n) ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

// Bar label: exact up to 999, then 1.2k / 12k / 1.2M so three labels fit over
// a 3-bar cluster without overlapping (the tooltip shows the exact value).
function barQty(v) {
  const n = Number(v) || 0;
  const a = Math.abs(n);
  if (a < 1000) return n.toLocaleString(undefined, { maximumFractionDigits: a < 10 ? 1 : 0 });
  const [d, unit] = a < 1e6 ? [1e3, 'k'] : [1e6, 'M'];
  const x = n / d;
  return `${Math.abs(x) < 10 ? x.toFixed(1).replace(/\.0$/, '') : Math.round(x)}${unit}`;
}

// 'YYYY-MM' -> "Aug '26" (narrow panels).
function shortMonth(ym) {
  const [mon, y] = fmtMonthLabel(ym).split(' ');
  return y ? `${mon} '${y.slice(2)}` : mon;
}

function storeTitle(store) {
  return `${store.store_name || store.store_code}${store.product_name ? ` · ${store.product_name}` : ''} (#${store.product_code})`;
}

function hasRow(month) {
  return month.in != null || month.out != null || month.stock != null;
}

// One store-month: Monthly Trend's bar cluster, or "no data" when the store
// has no ProductTrans row for the month. Hovering shows the exact values.
function MonthCell({ store, month, max, onTip }) {
  const show = (e) => onTip({ store, month, rect: e.currentTarget.getBoundingClientRect() });
  const hide = () => onTip(null);
  return (
    <div className="st-cell" onMouseEnter={show} onMouseLeave={hide}>
      {hasRow(month)
        ? <TrendBars series={SERIES} row={month} max={max} fmt={barQty} />
        : <div className="st-nodata">no data</div>}
    </div>
  );
}

function StoreMonthTip({ tip }) {
  const { store, month, rect } = tip;
  return (
    <TrendTip anchorRect={rect} width={168}>
      <div className="ow-chart-tip-month">{store.store_code} · {fmtMonthLabel(month.ym)}</div>
      {hasRow(month) ? SERIES.map((s) => (
        <div key={s.key} className={`ow-chart-tip-section ow-chart-tip-section--${s.cls}`}>
          <div className="ow-chart-tip-row"><span className="ow-chart-tip-head">{s.label}</span><b>{qty(month[s.key])}</b></div>
        </div>
      )) : <div className="ow-chart-tip-note">No ProductTrans record for this month.</div>}
    </TrendTip>
  );
}

// Clicking a store shows its Trend / Purchase / Sales in the detail panels
// (onPick); the store being shown is `peeked`.
function pickProps(store, peeked, onPick) {
  if (!onPick) return {};
  return {
    role: 'button',
    tabIndex: 0,
    'aria-pressed': peeked,
    onClick: () => onPick(store),
    onKeyDown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(store); } },
  };
}

function pickTitle(store, onPick) {
  return `${storeTitle(store)}${onPick ? (store.current ? '' : ' -- click to see its trend, purchase & sales') : ''}`;
}

// One scale for every store and month, so the rows compare.
function allStoresMax(stores) {
  return trendMax(stores.flatMap((s) => s.months), SERIES);
}

// Side / Middle dock: one row per store, months as aligned columns.
function StoreRow({ store, max, peeked, onPick, onTip }) {
  return (
    <div className={`st-row${store.current ? ' st-row--current' : ''}${peeked ? ' st-row--peek' : ''}${onPick ? ' st-pickable' : ''}`}
      {...pickProps(store, peeked, onPick)}>
      <div className="st-store" title={pickTitle(store, onPick)}>
        <b>{store.store_code}</b>
        <span className="st-code">{store.current ? 'this store' : `#${store.product_code}`}</span>
      </div>
      {store.months.map((m) => <MonthCell key={m.ym} store={store} month={m} max={max} onTip={onTip} />)}
    </div>
  );
}

// Bottom dock: the stores side by side, one card each.
function StoreCard({ store, max, peeked, onPick, onTip }) {
  return (
    <div className={`st-card${store.current ? ' st-card--current' : ''}${peeked ? ' st-card--peek' : ''}${onPick ? ' st-pickable' : ''}`}
      {...pickProps(store, peeked, onPick)}>
      <div className="st-card-head" title={pickTitle(store, onPick)}>
        <b>{store.store_code}</b>
        <span className="st-code">{store.current ? 'this store' : `#${store.product_code}`}</span>
      </div>
      <div className="st-card-plot">
        {store.months.map((m) => (
          <div className="st-card-month" key={m.ym}>
            <MonthCell store={store} month={m} max={max} onTip={onTip} />
            <span className="st-month" title={fmtMonthLabel(m.ym)}>{shortMonth(m.ym)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// layout: 'rows' (Middle / Side dock) or 'cards' (Bottom dock).
// peekStore: the store_code whose details the other panels are showing;
// onPick(store) is called when a store is clicked.
export function StoreTrendsPanel({ tenantId, storeId, productCode, session, layout = 'rows', peekStore = null, onPick }) {
  const { loading, error, data } = useStoreTrends({ tenantId, storeId, productCode, session });
  const [tip, setTip] = useState(null); // { store, month, rect }
  useEffect(() => setTip(null), [data]);
  const stores = data?.stores || [];
  const months = data?.months || [];
  const max = allStoresMax(stores);
  let body;
  if (productCode == null) body = <div className="ow-empty">Select a product.</div>;
  else if (!tenantId || !storeId) body = <div className="ow-empty">This store is not linked to the platform.</div>;
  else if (error) body = <div className="ow-empty">{error}</div>;
  else if (!stores.length) body = <div className="ow-empty">{loading ? 'Loading…' : 'No store data.'}</div>;
  else if (layout === 'cards') {
    body = <div className="st-cards">{stores.map((s) => <StoreCard key={s.store_id} store={s} max={max} peeked={peekStore === s.store_code} onPick={onPick} onTip={setTip} />)}</div>;
  } else {
    body = (
      <div className="st-table">
        <div className="st-row st-head">
          <div className="st-store">Store</div>
          {months.map((ym) => <div key={ym} className="st-month"><span className="st-m-long">{fmtMonthLabel(ym)}</span><span className="st-m-short">{shortMonth(ym)}</span></div>)}
        </div>
        {stores.map((s) => <StoreRow key={s.store_id} store={s} max={max} peeked={peekStore === s.store_code} onPick={onPick} onTip={setTip} />)}
      </div>
    );
  }
  return (
    <section className={`ow-panel ow-panel--stores st-layout-${layout}`} data-peek-zone="">
      <div className="ow-panel-title">
        All Stores<span className="ow-panel-subtitle">Last {months.length || 4} months per store</span>
        {loading && <span className="ow-intel-loading">…</span>}
        <span className="st-legend">{SERIES.map((s) => <span key={s.key}><i className={`ow-chart-dot ow-chart-dot--${s.cls}`} />{s.label}</span>)}</span>
      </div>
      <div className="ow-panel-scroll">{body}</div>
      {tip && <StoreMonthTip tip={tip} />}
    </section>
  );
}
