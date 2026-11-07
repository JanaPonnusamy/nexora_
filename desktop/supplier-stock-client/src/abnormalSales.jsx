import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// Abnormal bill-sale review, shared by the Order Workspace and the Procurement
// screen (rulebook PRR-SALE-ABNORMAL / PRR-SALE-WARNING, computed server-side
// by modules/procurement/abnormal_sales.py):
//   abnormal -- a bill sold >= 5x the product's usual bill (listed first);
//   warning  -- a bill sold >= 3x (warning + sales details at review time);
//   reviewed -- every flagged bill is already marked "do not consider".
// Marking a bill only changes the NEXT calculation (next order process /
// refresh) -- the quantity on screen is not recomputed.

function fmtQty(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}
function fmtDate(value) {
  const parts = String(value || '').slice(0, 10).split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0].slice(2)}` : (value || '—');
}

// Product level from its bills after a local mark/unmark (server rule: any
// counted abnormal bill -> abnormal, else any counted flagged bill -> warning,
// else reviewed).
function relevel(item) {
  const live = item.bills.filter((b) => !b.dont_consider);
  const level = live.some((b) => b.level === 'abnormal') ? 'abnormal' : live.length ? 'warning' : 'reviewed';
  return { ...item, level };
}

// load(): Promise<{items, abnormal_multiplier, warning_multiplier}>
// save(productCode, bill, value): Promise
// key: anything that should trigger a reload (store / refresh / tick).
export function useAbnormalSales({ load, save, key, enabled = true }) {
  const [state, setState] = useState({ loading: false, error: '', items: [], abnormal: 5, warning: 3 });
  const [busy, setBusy] = useState('');
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(() => {
    if (!enabled) { setState({ loading: false, error: '', items: [], abnormal: 5, warning: 3 }); return () => {}; }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: '', items: [] }));
    loadRef.current()
      .then((d) => {
        if (cancelled) return;
        setState({
          loading: false, error: '', items: Array.isArray(d?.items) ? d.items : [],
          abnormal: d?.abnormal_multiplier ?? 5, warning: d?.warning_multiplier ?? 3,
        });
      })
      .catch((e) => { if (!cancelled) setState((s) => ({ ...s, loading: false, error: e.message || 'Could not load abnormal sales.' })); });
    return () => { cancelled = true; };
  }, [enabled]);

  useEffect(() => reload(), [reload, key]);

  const byCode = useMemo(() => Object.fromEntries(state.items.map((i) => [String(i.product_code), i])), [state.items]);
  const abnormalCount = useMemo(() => state.items.filter((i) => i.level === 'abnormal').length, [state.items]);

  const toggle = useCallback(async (productCode, bill, value) => {
    const k = `${productCode}|${bill.bill_no}|${bill.bill_date}`;
    setBusy(k);
    try {
      await save(productCode, bill, value);
      setState((s) => ({
        ...s,
        items: s.items.map((i) => (String(i.product_code) !== String(productCode) ? i : relevel({
          ...i,
          bills: i.bills.map((b) => (b.bill_no === bill.bill_no && b.bill_date === bill.bill_date ? { ...b, dont_consider: value } : b)),
        }))),
      }));
      return null;
    } catch (e) {
      return e.message || 'Could not save.';
    } finally {
      setBusy('');
    }
  }, [save]);

  return { ...state, byCode, abnormalCount, reload, toggle, busy };
}

const MARK_TITLE = {
  abnormal: 'Abnormal sale — a bill sold far above this product\'s usual bill. Review it.',
  warning: 'High sale — a bill sold well above this product\'s usual bill.',
  reviewed: 'Abnormal sale already marked "do not consider in order".',
};

// Small ⚠ beside the product name.
export function AbnormalMark({ info }) {
  if (!info) return null;
  const top = info.bills?.[0];
  const title = `${MARK_TITLE[info.level] || ''}${top ? ` Bill ${top.bill_no}: ${fmtQty(top.qty)} = ${top.ratio}× usual ${fmtQty(top.avg_other)}.` : ''}`;
  return <span className={`abn-mark abn-mark--${info.level}`} title={title} aria-label={title}>⚠</span>;
}

// Warning + sales details for the selected product, with the per-bill
// "Don't consider in order" mark.
// infoOnly: a one-line, read-only note for the current row outside the
// Abnormal review process -- ONLY the >= 5x (abnormal) bills, no warning
// bills, no "Don't consider" toggles, and short enough that it doesn't push
// the current row out of the grid (owner ruling 2026-10-26).
export function AbnormalSalesStrip({ info, productName, multipliers, busy, readOnly, onToggle, infoOnly = false }) {
  const [error, setError] = useState('');
  useEffect(() => { setError(''); }, [info?.product_code]);
  if (!info) return null;
  if (infoOnly) {
    const bills = info.bills.filter((b) => b.level === 'abnormal');
    if (!bills.length) return null;
    return (
      <div className="abn-strip abn-strip--abnormal abn-strip--info" role="note">
        <span className="abn-strip-icon" aria-hidden="true">⚠</span>
        <strong className="abn-strip-name" title={productName || ''}>{productName || `#${info.product_code}`}</strong>
        <span className="abn-strip-text">Abnormal sale ({multipliers.abnormal}× usual bill {fmtQty(info.avg_bill_qty)}):</span>
        <span className="abn-info-bills">
          {bills.map((b) => (
            <span key={`${b.bill_no}|${b.bill_date}`} className={`abn-info-bill${b.dont_consider ? ' abn-bill-excluded' : ''}`}
              title={`${b.bill_no} · ${fmtDate(b.bill_date)} · ${b.customer || '—'} · ${fmtQty(b.qty)} = ${b.ratio}× usual${b.dont_consider ? ' · not considered' : ''}`}>
              {b.bill_no} · {fmtDate(b.bill_date)} · {b.customer || '—'} · <b>{fmtQty(b.qty)} = {b.ratio}×</b>
            </span>
          ))}
        </span>
      </div>
    );
  }
  const top = info.bills[0];
  const heading = info.level === 'abnormal'
    ? `Abnormal sales found — a bill sold ${top?.ratio}× the usual bill (${multipliers.abnormal}× rule).`
    : info.level === 'warning'
      ? `Warning — a bill sold ${top?.ratio}× the usual bill (${multipliers.warning}× rule). Check before ordering.`
      : 'Abnormal sales reviewed — marked bills are left out of the next calculation.';
  return (
    <div className={`abn-strip abn-strip--${info.level}`} role="alert">
      <div className="abn-strip-head">
        <span className="abn-strip-icon" aria-hidden="true">⚠</span>
        <strong className="abn-strip-name" title={productName || ''}>{productName || `#${info.product_code}`}</strong>
        <span className="abn-strip-text">{heading}</span>
        <span className="abn-strip-meta">Usual bill <b>{fmtQty(info.avg_bill_qty)}</b> · {info.bill_count} bills in 90 days</span>
      </div>
      <div className="abn-strip-bills">
        <table className="ow-intel-table">
          <thead><tr><th>Bill</th><th>Date</th><th>Customer</th><th className="ow-num">Qty</th><th className="ow-num">Usual</th><th className="ow-num">×</th><th>Don't consider in order</th></tr></thead>
          <tbody>
            {info.bills.map((b) => {
              const k = `${info.product_code}|${b.bill_no}|${b.bill_date}`;
              return (
                <tr key={k} className={b.dont_consider ? 'abn-bill-excluded' : `abn-bill--${b.level}`}>
                  <td>{b.bill_no}</td>
                  <td>{fmtDate(b.bill_date)}</td>
                  <td className="abn-customer" title={b.customer || ''}>{b.customer || '—'}</td>
                  <td className="ow-num">{fmtQty(b.qty)}</td>
                  <td className="ow-num">{fmtQty(b.avg_other)}</td>
                  <td className="ow-num"><b>{b.ratio}×</b></td>
                  <td>
                    <label className="abn-toggle">
                      <input type="checkbox" checked={Boolean(b.dont_consider)} disabled={readOnly || busy === k}
                        onChange={async (e) => {
                          const err = await onToggle(info.product_code, b, e.target.checked);
                          setError(err || '');
                        }} />
                      <span>{busy === k ? 'Saving…' : b.dont_consider ? 'Not considered' : 'Consider'}</span>
                    </label>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {error && <div className="abn-strip-error">{error}</div>}
    </div>
  );
}
