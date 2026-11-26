// Ported verbatim from desktop/supplier-stock-client/src/supplierCompare.jsx
// (owner instruction: copy logic unchanged, only adapt API plumbing/theme).
// Only change: api.legacySupplierStockCompare(…, session) -> direct service
// import with session dropped.
import { useEffect, useState } from 'react';
import { legacySupplierStockCompare } from '../../services/legacyOrderService.js';
import { pwCompareSuppliers } from './procurementWorkspaceView.js';
import { orderCache } from './orderCacheSync.js';

const cleanName = (s) => String(s ?? '').replace(/\s+/g, ' ').trim();
const fmt = (v, digits = 2) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: digits }) : '—';
};
const pct = (v) => `${fmt(v, 2)}%`;
const offerText = (l) => (Number(l.sch) > 0 && Number(l.free) > 0 ? `${l.sch}+${l.free}` : '—');
const nameOf = (l) => cleanName(l.supplier_name) || `Supplier ${l.supplier_code}`;

export function useSupplierCompare({ store, enabled, reloadKey }) {
  const [state, setState] = useState({ loading: false, byCode: {}, error: '' });
  useEffect(() => {
    if (!store || !enabled) { setState({ loading: false, byCode: {}, error: '' }); return undefined; }
    let cancelled = false;
    setState((cur) => ({ ...cur, loading: true, error: '' }));
    orderCache.compare(store, () => legacySupplierStockCompare(store))
      .then((r) => { if (!cancelled) setState({ loading: false, byCode: r && typeof r === 'object' ? r : {}, error: '' }); })
      .catch((e) => { if (!cancelled) setState({ loading: false, byCode: {}, error: e.message || 'Could not load supplier stock.' }); });
    return () => { cancelled = true; };
  }, [store, enabled, reloadKey]);
  return state;
}

export function SupplierCompareBadge({ lines, currentCodes, orderQty }) {
  if (!lines?.length || !currentCodes?.length) return null;
  const { verdict, current } = pwCompareSuppliers(lines, currentCodes, orderQty);
  if (verdict.kind === 'switch') {
    return (
      <span className="pw-cmp-badge pw-cmp-badge--better"
        title={`${nameOf(verdict.best)}: ${pct(verdict.best.eff)} (vs ${pct(current.eff)}), ${fmt(verdict.best.stock)} in stock`}>
        ▲{fmt(verdict.gain, 1)}%
      </span>
    );
  }
  if (verdict.kind === 'nostock' && verdict.best) {
    return <span className="pw-cmp-badge pw-cmp-badge--warn" title={`Current supplier has no stock — ${nameOf(verdict.best)} has ${fmt(verdict.best.stock)}`}>Alt</span>;
  }
  return null;
}

function Verdict({ verdict, current, currentName, assignedName }) {
  const best = verdict.best;
  const shortNote = verdict.short && best ? ` — only ${fmt(best.stock)} in stock for this qty` : '';
  let tone = 'ok';
  let icon = '✓';
  let text;
  switch (verdict.kind) {
    case 'switch':
      tone = 'better'; icon = '▲';
      text = <><b>{nameOf(best)}</b> gives <b>{pct(best.eff)}</b> (+{fmt(verdict.gain, 1)}%) and has <b>{fmt(best.stock)}</b> in stock{shortNote}</>;
      break;
    case 'stay':
      text = <><b>{verdict.blocked.map(nameOf).join(', ')}</b> {verdict.blocked.length > 1 ? 'have' : 'has'} a better discount but <b>no stock</b> — place with <b>{currentName}</b>{shortNote}</>;
      break;
    case 'best':
      text = <><b>{currentName}</b> is the best deal in stock ({pct(current.eff)}){shortNote}</>;
      break;
    case 'only':
      text = <>No other supplier has stock — place with <b>{currentName}</b> ({fmt(current.stock)} in stock){shortNote}</>;
      break;
    case 'nostock':
      tone = 'warn'; icon = '!';
      text = <><b>{currentName}</b> has no live stock — <b>{nameOf(best)}</b> has <b>{fmt(best.stock)}</b> at {pct(best.eff)}{shortNote}</>;
      break;
    case 'pick':
      tone = 'info'; icon = '★';
      text = <>Best in stock: <b>{nameOf(best)}</b> — {pct(best.eff)}, {fmt(best.stock)} in stock{shortNote}</>;
      break;
    default:
      tone = 'warn'; icon = '!';
      text = <>No supplier has live stock for this product.</>;
  }
  return (
    <div className={`pw-cmp-verdict pw-cmp-verdict--${tone}`}>
      <span className="pw-cmp-verdict__icon" aria-hidden="true">{icon}</span>
      <span className="pw-cmp-verdict__text">{text}</span>
      {assignedName && <span className="pw-cmp-assigned">Assigned · {cleanName(assignedName)}</span>}
    </div>
  );
}

export function SupplierCompareCard({
  lines, currentCodes, currentName, orderQty, assignedName, canAssign, lockedReason, busy, onAssign,
}) {
  const { ranked, current, verdict } = pwCompareSuppliers(lines, currentCodes, orderQty);
  const maxEff = Math.max(1, ...ranked.map((l) => l.eff));
  const qty = Number(orderQty) || 0;
  const cur = cleanName(currentName) || 'current supplier';
  const compact = verdict.kind === 'only' && ranked.every((l) => l.current);
  return (
    <div className={`pw-cmp${compact ? ' pw-cmp--compact' : ''}`} role="region" aria-label="Supplier stock compare">
      <div className="pw-cmp-head">
        <span className="pw-cmp-title">Supplier stock</span>
        <Verdict verdict={verdict} current={current} currentName={cur} assignedName={assignedName} />
        {canAssign && verdict.kind === 'switch' && (
          <button type="button" className="pw-mini-btn pw-mini-btn--ok" disabled={busy} title={`Assign to ${nameOf(verdict.best)}`} onClick={() => onAssign(verdict.best)}>
            {busy ? '…' : `Assign ${nameOf(verdict.best)}`}
          </button>
        )}
        {canAssign && current?.inStock && ['stay', 'best', 'only'].includes(verdict.kind) && (
          <button type="button" className="pw-mini-btn pw-mini-btn--ok" disabled={busy} title={`Assign to ${cur} (Enter)`} onClick={() => onAssign(null)}>
            {busy ? '…' : 'Assign here'}
          </button>
        )}
        {!canAssign && lockedReason && <span className="pw-cmp-lock">{lockedReason}</span>}
      </div>
      {!compact && <div className="pw-cmp-list" role="table">
        <div className="pw-cmp-line pw-cmp-line--head" role="row">
          <span role="columnheader">Supplier</span>
          <span role="columnheader" className="pw-cmp-num">Stock</span>
          <span role="columnheader" className="pw-cmp-num">Disc</span>
          <span role="columnheader" className="pw-cmp-num">Offer</span>
          <span role="columnheader" title="Disc% stacked with the free-qty offer">Effective</span>
          <span role="columnheader" className="pw-cmp-num">PTR</span>
          <span role="columnheader" />
        </div>
        {ranked.map((l) => {
          const stockTone = !l.inStock ? 'out' : qty > 0 && Number(l.stock) < qty ? 'short' : 'in';
          const isBest = verdict.best && l.supplier_code === verdict.best.supplier_code && verdict.kind !== 'none';
          return (
            <div key={l.supplier_code} role="row"
              className={`pw-cmp-line${l.current ? ' is-current' : ''}${isBest ? ' is-best' : ''}${l.inStock ? '' : ' is-out'}`}>
              <span className="pw-cmp-sup" role="cell" title={l.supplier_product_name ? `${nameOf(l)} — ${l.supplier_product_name}` : nameOf(l)}>
                <span className="pw-cmp-sup__name">{nameOf(l)}</span>
                {l.current && <span className="pw-cmp-tag pw-cmp-tag--current">Current</span>}
                {isBest && !l.current && <span className="pw-cmp-tag pw-cmp-tag--best">Best</span>}
              </span>
              <span role="cell" className="pw-cmp-num">
                <span className={`pw-cmp-stock pw-cmp-stock--${stockTone}`}
                  title={stockTone === 'short' ? `Less than the order qty (${fmt(qty)})` : undefined}>
                  {l.inStock ? fmt(l.stock) : 'No stock'}
                </span>
              </span>
              <span role="cell" className="pw-cmp-num">{pct(l.discount)}</span>
              <span role="cell" className="pw-cmp-num">{offerText(l)}</span>
              <span role="cell" className="pw-cmp-eff">
                <span className="pw-cmp-bar"><span style={{ width: `${Math.max(3, (l.eff / maxEff) * 100)}%` }} /></span>
                <b>{pct(l.eff)}</b>
              </span>
              <span role="cell" className="pw-cmp-num">{l.ptr != null ? fmt(l.ptr) : '—'}</span>
              <span role="cell" className="pw-cmp-act">
                {canAssign && !l.current && l.inStock && (
                  <button type="button" className="pw-cmp-assign" disabled={busy} title={`Place this product with ${nameOf(l)}`}
                    onClick={() => onAssign(l)}>Assign</button>
                )}
              </span>
            </div>
          );
        })}
      </div>}
    </div>
  );
}
