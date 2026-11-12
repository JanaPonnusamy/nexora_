import { useEffect, useRef, useState } from 'react';
import { api } from './api/client.js';
import { asArray, fmtOwDate, fmtOwMoney, fmtOwPct, fmtOwQty, owLandingPct } from './OwFormatters.js';

// Purchase invoice / sales bill detail modal, shared by Order Workspace
// (rendered directly) and Procurement (via App.jsx's PROCUREMENT_UI bridge
// -> ProcurementWorkspace.jsx). Extracted from App.jsx unchanged (NEXORA
// MEDIQ Phase 4 structural refactor) -- no behavior altered in the move.

const OW_DOC_COLUMNS = {
  purchase: [
    ['ProductName', 'Product', 'name'], ['UnitDescription', 'Unit', 'text'], ['SaleUnit', 'Pack', 'qty'],
    ['Qty', 'Qty', 'qty'], ['FreeQty', 'Offer', 'qty'], ['MRP', 'MRP', 'money'], ['PTR', 'PTR', 'money'],
    ['ItemCost', 'Cost', 'money'], ['DIS', 'Dis%', 'pct'], ['_land', 'Land%', 'pct'], ['BatchCode', 'Batch', 'text'],
  ],
  sales: [
    ['ProductName', 'Product', 'name'], ['UnitDescription', 'Unit', 'text'], ['SaleUnit', 'Pack', 'qty'],
    ['Qty', 'Qty', 'qty'], ['FreeQty', 'Offer', 'qty'], ['MRP', 'MRP', 'money'], ['PTR', 'PTR', 'money'],
    ['ItemCost', 'Cost', 'money'], ['DIS', 'Dis%', 'pct'], ['Rate', 'Rate', 'money'], ['Amount', 'Amount', 'money'],
    ['Batch', 'Batch', 'text'], ['Expiry', 'Expiry', 'date'],
  ],
};
const owBlank = (v) => v === null || v === undefined || String(v).trim() === '';
function owFmtDocCell(type, value) {
  if (owBlank(value)) return '—';
  if (type === 'money') return fmtOwMoney(value);
  if (type === 'qty') return fmtOwQty(value);
  if (type === 'pct') return fmtOwPct(value);
  if (type === 'date') return fmtOwDate(value);
  return String(value).trim();
}
function owFmtDateTime(value) {
  const t = value ? new Date(value) : null;
  return t && !Number.isNaN(t.getTime())
    ? t.toLocaleString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '';
}
const owSum = (lines, f) => lines.reduce((t, l) => t + (Number(f(l)) || 0), 0);

export function OwDocumentCard({ kind, store, row, productCode, session, onClose }) {
  const [state, setState] = useState({ loading: true, error: '', header: null, lines: [] });
  const currentRef = useRef(null);
  useEffect(() => {
    let cancelled = false;
    const day = (v) => (v ? String(v).slice(0, 10) : '');
    let req;
    if (kind === 'purchase') {
      req = row.GRNNo == null
        ? Promise.reject(new Error('This purchase line has no GRN number.'))
        : api.legacyPurchaseInvoice(store, { grn_no: row.GRNNo, series: row.InvoiceSeries, grn_date: day(row.GRNDate), supplier_code: row.SupplierCode }, session)
          .then((lines) => ({ header: null, lines: asArray(lines) }));
    } else {
      req = api.legacySaleBill(store, { bnumber: row.Bnumber, bill_date: day(row.Bill_Time) }, session)
        .then((r) => ({ header: r?.header || null, lines: asArray(r?.lines) }));
    }
    req.then((d) => { if (!cancelled) setState({ loading: false, error: '', ...d }); })
      .catch((e) => { if (!cancelled) setState({ loading: false, error: e.message || 'Could not load.', header: null, lines: [] }); });
    return () => { cancelled = true; };
  }, [kind, store, row, session]);
  useEffect(() => {
    function closeOnEscape(event) { if (event.key === 'Escape') onClose(); }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);
  useEffect(() => { currentRef.current?.scrollIntoView({ block: 'nearest' }); }, [state.lines]);

  const lines = state.lines.map((l) => ({ ...l, _land: owLandingPct(l.PTR, l.ItemCost) }));
  const columns = OW_DOC_COLUMNS[kind].filter(([key], i) => i === 0 || lines.some((l) => !owBlank(l[key])));
  const isPurchase = kind === 'purchase';
  const series = String(row.InvoiceSeries || '').trim();
  const title = isPurchase
    ? `${store} • GRN #${row.GRNNo ?? '—'}${series ? ` (${series})` : ''} • ${fmtOwDate(row.GRNDate)}`
    : `${store} • Bill ${row.Bnumber ?? '—'} • ${owFmtDateTime(state.header?.Billtime || row.Bill_Time)}`;
  const party = isPurchase ? row.SupplierName : (state.header?.CustomerName || row.CUSTOMERNAME);
  const metrics = isPurchase
    ? [['Products', lines.length, 'qty'], ['Total Qty', owSum(lines, (l) => l.Qty), 'qty'], ['Total Offer', owSum(lines, (l) => l.FreeQty), 'qty'],
      ['Value @ PTR', owSum(lines, (l) => l.Qty * l.PTR), 'money'], ['Value @ Cost', owSum(lines, (l) => l.Qty * l.ItemCost), 'money']]
    : [['Products', lines.length, 'qty'], ['Total Qty', owSum(lines, (l) => l.Qty), 'qty'],
      ['Salesman', state.header?.Salesmanname || row.Salesmanname, 'text'], ['Bill Amount', state.header?.BillAmount, 'money']];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="purchase-detail-card ow-doc-card" role="dialog" aria-modal="true" aria-labelledby="ow-doc-title" onClick={(e) => e.stopPropagation()}>
        <div className="purchase-detail-header">
          <div className="purchase-detail-heading">
            <span className="purchase-detail-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M7 3h10v2h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2V3Zm2 2h6V4H9v1ZM5 8v11h14V8H5Zm3 3h8v2H8v-2Zm0 4h5v2H8v-2Z" /></svg>
            </span>
            <div>
              <span className="purchase-detail-eyebrow">{isPurchase ? 'Purchase Invoice' : 'Sales Bill'}</span>
              <strong id="ow-doc-title">{title}</strong>
            </div>
          </div>
          <button type="button" className="purchase-detail-close" onClick={onClose} aria-label="Close">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7.4 6 4.6 4.6L16.6 6 18 7.4 13.4 12l4.6 4.6-1.4 1.4-4.6-4.6L7.4 18 6 16.6l4.6-4.6L6 7.4 7.4 6Z" /></svg>
          </button>
        </div>
        <div className="purchase-detail-body">
          <div className={`purchase-party ${isPurchase && series === 'TI' ? 'purchase-party--transfer' : 'purchase-party--supplier'}`}>
            <span className="purchase-party-label">{isPurchase ? (series === 'TI' ? 'Source Store' : 'Supplier') : 'Customer'}</span>
            <strong className="purchase-party-name" title={party || ''}>{party || '—'}</strong>
          </div>
          <div className="purchase-metric-grid">
            {metrics.map(([label, value, type]) => (
              <div className="purchase-metric" key={label}><span>{label}</span><strong className={type === 'money' ? 'num-value' : ''}>{owFmtDocCell(type, value)}</strong></div>
            ))}
          </div>
          <div className="ow-doc-lines">
            <table className="ow-intel-table">
              <thead><tr><th className="ow-num">#</th>{columns.map(([key, label, type]) => <th key={key} className={type === 'name' || type === 'text' || type === 'date' ? undefined : 'ow-num'}>{label}</th>)}</tr></thead>
              <tbody>
                {lines.map((l, i) => {
                  const current = productCode != null && Number(l.ProductCode) === Number(productCode);
                  return (
                    <tr key={i} ref={current ? currentRef : undefined} className={`${current ? 'ow-doc-current' : ''}${Number(l.FreeQty) > 0 ? ' ow-freerow' : ''}`}>
                      <td className="ow-num">{i + 1}</td>
                      {columns.map(([key, , type]) => (
                        <td key={key} className={type === 'name' ? 'ow-doc-name' : type === 'text' || type === 'date' ? undefined : 'ow-num'} title={type === 'name' ? l[key] || '' : undefined}>
                          {type === 'name' ? (l[key] || `#${l.ProductCode}`) : owFmtDocCell(type, l[key])}
                        </td>
                      ))}
                    </tr>
                  );
                })}
                {!lines.length && <tr><td colSpan={columns.length + 1} className="ow-empty">{state.loading ? 'Loading…' : state.error || 'No lines found.'}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
