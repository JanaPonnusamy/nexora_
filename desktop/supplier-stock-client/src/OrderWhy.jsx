import { useEffect, useMemo, useRef, useState } from 'react';

// "Why is this product in the order?" -- Procurement's Product Summary card
// and its 90-day calculation popup. Data: GET /qty-check/{store}/{code}/why
// (legacy_order/order_reason.py): the engine's steps with the quantities the
// Order Process stored, plus the 90-day sales day by day. `load(store, code)`
// is the app's API call, so this file is identical in both desktop apps.

const whyCache = new Map(); // `${store}|${code}` -> Promise

const fmt = (v) => {
  const n = Number(v);
  if (v == null || Number.isNaN(n)) return '—';
  return Number.isInteger(n) ? n.toLocaleString('en-IN') : n.toLocaleString('en-IN', { maximumFractionDigits: 2 });
};
const fmtDate = (v) => {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
};

// Only ever returns data for `code` -- never the previous row's.
export function useOrderWhy(store, code, load) {
  const [state, setState] = useState({ key: null, data: null, error: '' });
  const key = store && code != null ? `${store}|${code}` : null;
  useEffect(() => {
    if (!key) return undefined;
    let cancelled = false;
    const timer = setTimeout(() => {
      let p = whyCache.get(key);
      if (!p) {
        p = load(store, code);
        whyCache.set(key, p);
        if (whyCache.size > 300) whyCache.delete(whyCache.keys().next().value);
      }
      p.then((data) => { if (!cancelled) setState({ key, data, error: '' }); })
        .catch((e) => { whyCache.delete(key); if (!cancelled) setState({ key, data: null, error: e.message || 'Could not load.' }); });
    }, 150);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const current = state.key === key;
  return { data: current ? state.data : null, error: current ? state.error : '', loading: Boolean(key) && !current };
}

// Clear cached answers (after a reload / new order run).
export function invalidateOrderWhy() { whyCache.clear(); }

function oneLine(w) {
  if (w.engine === 'RULEBOOK') {
    const win = w.steps.find((s) => s.winner);
    return `Target ${fmt(w.max_qty)}${win ? ` (${win.label.toLowerCase()})` : ''} − stock ${fmt(w.stock)} = ${fmt(w.max_qty - w.stock)} → ${fmt(w.calculated_qty)} pack${w.calculated_qty === 1 ? '' : 's'} of ${fmt(w.pack)}`;
  }
  if (w.wanted_type === 'Rare Moment' || w.wanted_type === 'Additional Row') {
    return `Stock ${fmt(w.stock)} · sold ${fmt(w.sale_count)}× in 90 days → ${fmt(w.calculated_qty)} pack top-up`;
  }
  const minD = w.min_days != null ? ` (${w.min_days} d)` : '';
  const maxD = w.max_days != null ? ` (${w.max_days} d)` : '';
  return `Stock ${fmt(w.stock)} < min ${fmt(w.min_qty)}${minD} → up to max ${fmt(w.max_qty)}${maxD} → need ${fmt(w.max_qty - w.stock)} → ${fmt(w.calculated_qty)} pack${w.calculated_qty === 1 ? '' : 's'} of ${fmt(w.pack)}`;
}

// finalQty: the grid's current Or Qty (edits included), so "changed" is live.
export function OrderWhyCard({ why, finalQty, onOpen }) {
  const { data: w, loading, error } = why;
  if (loading) return <div className="pw-why pw-why--muted">Working out why this product is in the order…</div>;
  if (error) return <div className="pw-why pw-why--muted">Why ordered: {error}</div>;
  if (!w) return null;
  const changed = finalQty != null && Number(finalQty) !== Number(w.calculated_qty);
  return (
    <div className="pw-why">
      <div className="pw-why-head">
        <span className="pw-why-label">Why in order</span>
        <span className={`pw-why-engine pw-why-engine--${w.engine.toLowerCase()}`}>{w.engine === 'RULEBOOK' ? 'Rule Book' : 'Legacy'}</span>
        <button type="button" className="pw-why-info" onClick={onOpen} title="Open the full 90-day calculation">ⓘ 90-day calculation</button>
      </div>
      <p className="pw-why-reason">{w.reason}</p>
      <div className="pw-why-math">{oneLine(w)}</div>
      <div className="pw-why-chips">
        <span>Sold <b>{fmt(w.sales.total_qty)}</b> in 90 d</span>
        <span><b>{fmt(w.sales.bills)}</b> bills · <b>{fmt(w.sales.sale_days)}</b> days</span>
        <span><b>{fmt(w.sales.avg_per_day)}</b>/day</span>
        {changed && <span className="pw-why-changed">Changed {fmt(w.calculated_qty)} → {fmt(finalQty)}</span>}
        {w.sales.excluded_qty > 0 && <span className="pw-why-excl" title="Bills marked “don't consider” (abnormal sales) are left out">−{fmt(w.sales.excluded_qty)} abnormal</span>}
      </div>
    </div>
  );
}

function DailyChart({ daily, from, to }) {
  const days = useMemo(() => {
    const start = new Date(from); start.setHours(0, 0, 0, 0);
    const end = new Date(to);
    const byDay = new Map(daily.map((d) => [String(d.date).slice(0, 10), d]));
    const out = [];
    for (let d = new Date(start); d <= end && out.length < 92; d.setDate(d.getDate() + 1)) {
      const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      out.push({ iso, ...(byDay.get(iso) || { qty: 0, bills: 0 }) });
    }
    return out;
  }, [daily, from, to]);
  const max = Math.max(1, ...days.map((d) => d.qty));
  const W = 6; const H = 70;
  return (
    <svg className="pw-whyd-chart" viewBox={`0 0 ${days.length * W} ${H + 2}`} preserveAspectRatio="none" role="img" aria-label="Daily sales, last 90 days">
      {days.map((d, i) => {
        const h = d.qty ? Math.max(2, (d.qty / max) * H) : 0;
        return (
          <rect key={d.iso} x={i * W + 1} y={H - h} width={W - 2} height={h || 1} rx="1"
            className={d.qty ? 'pw-whyd-bar' : 'pw-whyd-bar pw-whyd-bar--zero'}>
            <title>{`${fmtDate(d.iso)}: ${fmt(d.qty)} qty in ${d.bills} bill${d.bills === 1 ? '' : 's'}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}

export function OrderWhyDialog({ why, finalQty, onClose }) {
  const w = why?.data;
  const boxRef = useRef(null);
  useEffect(() => {
    if (!w) return undefined;
    boxRef.current?.focus(); // keys go to the popup, not the grid behind it
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [w, onClose]);
  if (!w) return null;
  const s = w.sales;
  const final = finalQty ?? w.final_qty;
  const changed = Number(final) !== Number(w.calculated_qty);
  const tiles = [
    ['Sold (valid)', fmt(s.total_qty)],
    ['Bills', fmt(s.bills)],
    ['Days with sales', `${fmt(s.sale_days)} / 90`],
    ['Average / day', fmt(s.avg_per_day)],
    ['Biggest bill', fmt(s.max_bill_qty)],
    ['Biggest day', `${fmt(s.max_day_qty)}${s.max_day_date ? ` · ${fmtDate(s.max_day_date)}` : ''}`],
  ];
  return (
    <div className="pw-whyd-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="pw-whyd" role="dialog" aria-modal="true" aria-labelledby="pw-whyd-title" tabIndex={-1} ref={boxRef}>
        <div className="pw-whyd-head">
          <div>
            <div className="pw-whyd-eyebrow">Why in order · {w.engine === 'RULEBOOK' ? 'Rule Book engine' : 'Legacy engine'}</div>
            <h2 id="pw-whyd-title">{w.product_name}</h2>
            <div className="pw-whyd-sub">#{w.product_code} · order {w.order_id} · {fmtDate(w.window.from)} – {fmtDate(w.window.to)}</div>
          </div>
          <button type="button" className="pw-whyd-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <p className="pw-whyd-reason">{w.reason}</p>

        <div className="pw-whyd-tiles">
          {tiles.map(([label, value]) => <div key={label}><b>{value}</b><span>{label}</span></div>)}
        </div>

        <div className="pw-whyd-section">Daily sales — last 90 days</div>
        <DailyChart daily={s.daily} from={w.window.from} to={w.window.to} />

        <div className="pw-whyd-section">Calculation</div>
        <table className="pw-whyd-steps">
          <tbody>
            {w.steps.map((st, i) => (
              <tr key={i} className={st.winner ? 'is-winner' : undefined}>
                <td className="pw-whyd-step-n">{i + 1}</td>
                <td>{st.label}{st.winner && <span className="pw-whyd-win">decides</span>}</td>
                <td className="pw-whyd-formula">{st.formula}</td>
                <td className="pw-whyd-val">{st.value}</td>
              </tr>
            ))}
            <tr className="pw-whyd-final">
              <td />
              <td>Final order qty</td>
              <td className="pw-whyd-formula">{changed ? `calculated ${fmt(w.calculated_qty)}, changed in Qty Check` : 'as calculated'}</td>
              <td className="pw-whyd-val">{fmt(final)}</td>
            </tr>
          </tbody>
        </table>

        <div className="pw-whyd-notes">
          {s.excluded_qty > 0 && <span>{fmt(s.excluded_qty)} qty in {s.excluded_lines} sale line(s) marked “don't consider” (abnormal) are not counted.</span>}
          <span>Last sale {fmtDate(w.last_sale)} · last received {fmtDate(w.last_received)}.</span>
          <span>Steps use the figures stored when the order was made; the daily sales are read now, so a sale entered since can differ slightly.</span>
        </div>
      </div>
    </div>
  );
}
