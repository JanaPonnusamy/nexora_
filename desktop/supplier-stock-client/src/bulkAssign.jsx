import { useEffect, useMemo, useState } from 'react';
import { api } from './api/client.js';

// Order Workspace process "Bulk Assign · Best Margin" (after Qty Check):
// every reviewed, still-unassigned line (Pending Order, Or Qty > 0) is
// proposed to the supplier with the best margin over its last 5 supplies;
// a product with no usable supply goes to its most frequent supplier. The
// proposal is computed server-side (repository.auto_assign_proposals) and
// recomputed again on Assign, so this screen only picks which lines to send.

function fmtQty(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}

function basisLabel(row, lastSupplies) {
  if (row.basis === 'best_margin') return `Best margin · ${row.supplies} of last ${Math.min(row.supplies_seen, lastSupplies)}`;
  if (row.basis === 'most_frequent') return row.supplies_seen ? 'Most frequent (no active supplier in last supplies)' : 'Most frequent (not received)';
  return 'No supplier history';
}

export function OwBulkAssign({ store, session, finalized, reloadKey, selectedCode, onSelect, onAssigned, onError, onAssign, extraControls, confirmText }) {
  const [data, setData] = useState({ loading: true, rows: [], lastSupplies: 5 });
  const [unticked, setUnticked] = useState(() => new Set());
  const [assigning, setAssigning] = useState(false);

  useEffect(() => {
    if (!store) return undefined;
    let cancelled = false;
    setData((d) => ({ ...d, loading: true, rows: [] }));
    setUnticked(new Set());
    api.legacyAutoAssignPreview(store, session)
      .then((r) => {
        if (cancelled) return;
        const rows = Array.isArray(r?.rows) ? r.rows : [];
        setData({ loading: false, rows, lastSupplies: r?.last_supplies ?? 5 });
        if (rows.length) onSelect(rows[0].product_code);
      })
      .catch((e) => { if (!cancelled) { setData((d) => ({ ...d, loading: false })); onError(e.message); } });
    return () => { cancelled = true; };
    // onSelect/onError are parent setters; reload only on store/tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store, session, reloadKey]);

  const assignable = useMemo(() => data.rows.filter((r) => r.supplier_code), [data.rows]);
  const picked = useMemo(() => assignable.filter((r) => !unticked.has(r.product_code)), [assignable, unticked]);
  const supplierCount = useMemo(() => new Set(picked.map((r) => r.supplier_code)).size, [picked]);
  const noSupplier = data.rows.length - assignable.length;

  const toggle = (code) => setUnticked((cur) => {
    const next = new Set(cur);
    if (next.has(code)) next.delete(code); else next.add(code);
    return next;
  });
  const allTicked = assignable.length > 0 && picked.length === assignable.length;
  const toggleAll = () => setUnticked(allTicked ? new Set(assignable.map((r) => r.product_code)) : new Set());

  const assign = () => {
    if (!picked.length) return;
    if (!window.confirm(confirmText || `Assign ${picked.length} product(s) to ${supplierCount} supplier(s) by best margin?`)) return;
    setAssigning(true);
    // onAssign (when given) owns the write -- e.g. the Procurement screen's
    // "check stock on the supplier's site first"; otherwise assign by history.
    const run = onAssign ? onAssign(picked) : api.legacyAutoAssign(store, picked.map((r) => r.product_code), session);
    Promise.resolve(run)
      .then((res) => onAssigned(res))
      .catch((e) => onError(e.message))
      .finally(() => setAssigning(false));
  };

  return (
    <div className="ow-bulk-assign">
      <div className="ow-bulk-bar">
        <span>
          {data.loading ? 'Loading proposals…' : (
            <>
              <b>{picked.length}</b> of {assignable.length} line(s) · <b>{supplierCount}</b> supplier(s)
              {noSupplier > 0 && <> · <span className="ow-bulk-none">{noSupplier} without supplier</span></>}
            </>
          )}
        </span>
        {extraControls}
        <button type="button" className="ow-btn ow-btn-primary" disabled={finalized || assigning || !picked.length}
          title={finalized ? 'Order is finalized' : 'Assign the ticked lines to their proposed supplier'}
          onClick={assign}>
          {assigning ? 'Assigning…' : `Assign ${picked.length}`}
        </button>
      </div>
      <table className="ow-fixed">
        <colgroup>
          <col style={{ width: '4%' }} /><col style={{ width: '34%' }} /><col style={{ width: '8%' }} />
          <col style={{ width: '26%' }} /><col style={{ width: '9%' }} /><col style={{ width: '19%' }} />
        </colgroup>
        <thead>
          <tr>
            <th><input type="checkbox" aria-label="Tick all" checked={allTicked} disabled={!assignable.length} onChange={toggleAll} /></th>
            <th>Product</th>
            <th className="ow-num">Or Qty</th>
            <th>Supplier</th>
            <th className="ow-num">Margin %</th>
            <th>Basis</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => (
            <tr key={row.product_code}
              className={[selectedCode === row.product_code ? 'ow-row-sel' : '', row.supplier_code ? '' : 'ow-bulk-row-none'].join(' ').trim() || undefined}
              onClick={() => onSelect(row.product_code)}>
              <td onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" aria-label={`Assign ${row.product_name}`} disabled={!row.supplier_code}
                  checked={Boolean(row.supplier_code) && !unticked.has(row.product_code)}
                  onChange={() => toggle(row.product_code)} />
              </td>
              <td title={row.product_name}>{row.product_name}</td>
              <td className="ow-num">{fmtQty(row.order_qty)}</td>
              <td title={row.supplier_name || ''}>{row.supplier_name || '—'}</td>
              <td className="ow-num">{row.margin == null ? '—' : row.margin.toFixed(2)}</td>
              <td title={basisLabel(row, data.lastSupplies)}>{basisLabel(row, data.lastSupplies)}</td>
            </tr>
          ))}
          {!data.rows.length && (
            <tr><td colSpan={6} className="ow-empty">{data.loading ? 'Loading…' : 'No qty-checked products are waiting on a supplier assignment.'}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
