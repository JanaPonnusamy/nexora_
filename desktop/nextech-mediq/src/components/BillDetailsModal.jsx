// Shared Bill Details popup for Stock Enquiry (storeClientStockEnquiry.jsx)
// and Quick Stock (StockMatrixView.jsx) — both modules call the SAME
// component so the two screens render an identical modal instead of their
// own divergent copies (Stock Enquiry's old .purchase-detail-card/
// .bill-detail-card relied on undefined --nx-* tokens, which rendered as
// washed-out/transparent text on a near-invisible surface, and was hard-
// capped at 420px wide — "compressed content"; Quick Stock's BillDrawer used
// the app's real --ntm-* tokens and looked correct). This component uses
// ONLY --ntm-* tokens (defined in src/themes/tokens.css) so it always
// renders on-theme regardless of which module hosts it.
import React, { useEffect, useMemo, useState } from 'react';
import './billDetailsModal.css';

function formatMoney(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(2) : '—';
}

function formatQty(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString('en-IN') : (value ?? '0');
}

function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' });
}

function text(value) {
  if (value == null) return null;
  const s = String(value).trim();
  if (!s || s === '-' || s === '—') return null;
  return s;
}

function useEscapeToClose(onClose) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);
}

/**
 * Shared Bill Details modal.
 *
 * Props:
 *  - storeLabel, storeName: store header identity.
 *  - billNo, billDate, customer: bill header fields (customer is a fallback;
 *    the fetched line items' own `customer`/`salesman` take precedence once
 *    loaded, same as both modules' previous behavior).
 *  - fetchItems: () => Promise<row[]> — caller supplies its own already-wired
 *    service call (billItems() in Quick Stock, api.getBillItems() in Stock
 *    Enquiry) so this component never hardcodes an API path or auth mode.
 *  - visibility: 'FULL' | 'SUMMARY' | 'NONE' — Stock Enquiry's existing
 *    role-gated history tier (historyVisibility(session)). 'FULL' shows PTR
 *    and Salesman; 'SUMMARY' hides them but still shows Customer; 'NONE'
 *    hides Customer too. Quick Stock has no role gating today, so it passes
 *    the default 'FULL' (full detail for every session), preserving its
 *    existing (ungated) behavior exactly.
 *  - highlightProductName: when set, the product row whose name matches
 *    (case-insensitive) gets the "selected line" highlight — Stock Enquiry's
 *    existing is-selected row behavior. Quick Stock passes nothing (no
 *    single-row highlight), matching its existing behavior.
 *  - onClose: () => void.
 */
export function BillDetailsModal({
  storeLabel,
  storeName,
  billNo,
  billDate,
  customer: customerFallback,
  fetchItems,
  visibility = 'FULL',
  highlightProductName,
  onClose,
}) {
  const [items, setItems] = useState(null);
  const [failed, setFailed] = useState(false);
  useEscapeToClose(onClose);

  useEffect(() => {
    let live = true;
    setItems(null);
    setFailed(false);
    if (!billNo) {
      setItems([]);
      return undefined;
    }
    fetchItems()
      .then((rows) => { if (live) setItems(Array.isArray(rows) ? rows : (rows?.items ?? rows?.data ?? [])); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
    // fetchItems is a fresh closure per render by design (it captures the
    // caller's current tenant/store/bill) -- re-run whenever the bill identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [billNo, billDate]);

  const rows = items ?? [];
  const loading = items === null && !failed;
  const highlightKey = highlightProductName ? String(highlightProductName).trim().toLowerCase() : null;

  const salesman = rows.length > 0 && rows.every((r) => (r.salesman ?? null) === (rows[0]?.salesman ?? null))
    ? rows[0]?.salesman
    : null;
  const customer = text(customerFallback) ?? text(rows[0]?.customer);

  const totals = useMemo(() => {
    const totalItems = rows.length;
    const totalQty = rows.reduce((sum, r) => sum + (Number(r.qty) || 0), 0);
    const grandTotal = rows.reduce((sum, r) => sum + (Number(r.amount) || 0), 0);
    const totalDiscount = rows.reduce((sum, r) => {
      const base = (Number(r.mrp) || 0) * (Number(r.qty) || 0);
      return sum + base * ((Number(r.discount_pct) || 0) / 100);
    }, 0);
    return { totalItems, totalQty, grandTotal, totalDiscount };
  }, [rows]);

  const showCustomer = visibility !== 'NONE';
  const showFull = visibility === 'FULL';

  return (
    <div className="bdm-overlay" onClick={onClose}>
      <div
        className="bdm-modal"
        role="dialog"
        aria-label={`Bill ${billNo ?? ''} · ${storeLabel ?? ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bdm-head">
          <div className="bdm-head__title">
            <strong>Bill Details</strong>
            <span className="bdm-head__meta">
              {storeLabel ?? '—'}{storeName && storeName !== storeLabel ? ` · ${storeName}` : ''}
              {billNo ? ` · Bill ${billNo}` : ''}
            </span>
          </div>
          <button type="button" className="bdm-close" onClick={onClose}>✕ Close</button>
        </div>

        <div className="bdm-info">
          <div className="bdm-info__group">
            <div className="bdm-info__group-title">Store &amp; Transaction</div>
            <div className="bdm-info__row"><span>Store Code</span><strong>{storeLabel ?? '—'}</strong></div>
            <div className="bdm-info__row"><span>Store Name</span><strong>{storeName ?? '—'}</strong></div>
            <div className="bdm-info__row"><span>Transaction Date</span><strong>{formatDate(billDate)}</strong></div>
          </div>
          <div className="bdm-info__group">
            <div className="bdm-info__group-title">Customer &amp; Billing</div>
            {showCustomer && (
              <div className="bdm-info__row"><span>Customer Name</span><strong title={customer ?? undefined}>{customer ?? '—'}</strong></div>
            )}
            <div className="bdm-info__row"><span>Bill Number</span><strong>{billNo ?? '—'}</strong></div>
            {showFull && (
              <div className="bdm-info__row"><span>Salesman</span><strong>{salesman ?? '—'}</strong></div>
            )}
          </div>
        </div>

        <div className="bdm-products">
          <div className="bdm-products__title">Bill Product Details</div>
          {loading ? (
            <div className="bdm-empty">Loading bill detail…</div>
          ) : failed ? (
            <div className="bdm-empty">Could not load this bill. Please try again.</div>
          ) : rows.length === 0 ? (
            <div className="bdm-empty">No products found for this bill.</div>
          ) : (
            <div className="bdm-products__scroll">
              <table className="bdm-grid">
                <thead>
                  <tr>
                    <th>S.No</th>
                    <th>Product Code</th>
                    <th>Product Name</th>
                    <th>Unit</th>
                    <th className="bdm-num">Quantity</th>
                    <th className="bdm-num">MRP</th>
                    {showFull && <th className="bdm-num">PTR</th>}
                    <th className="bdm-num">Discount</th>
                    <th className="bdm-num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => {
                    const isHighlighted = highlightKey
                      && String(row.product_name ?? '').trim().toLowerCase() === highlightKey;
                    return (
                      <tr
                        key={`${row.product_code ?? row.product_name ?? i}`}
                        className={isHighlighted ? 'bdm-row--selected' : undefined}
                      >
                        <td>{row.line_no ?? i + 1}</td>
                        <td>{row.product_code ?? '—'}</td>
                        <td title={row.product_name ?? undefined}>{row.product_name ?? '—'}</td>
                        <td>{row.sale_unit ?? '—'}</td>
                        <td className="bdm-num">{formatQty(row.qty)}</td>
                        <td className="bdm-num">{formatMoney(row.mrp)}</td>
                        {showFull && <td className="bdm-num">{formatMoney(row.ptr)}</td>}
                        <td className="bdm-num">{row.discount_pct != null ? `${row.discount_pct}%` : '—'}</td>
                        <td className="bdm-num">{formatMoney(row.amount)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="bdm-totals">
          <div className="bdm-totals__item"><span>Total Items</span><strong>{totals.totalItems}</strong></div>
          <div className="bdm-totals__item"><span>Total Quantity</span><strong>{totals.totalQty.toLocaleString('en-IN')}</strong></div>
          <div className="bdm-totals__item"><span>Total Discount</span><strong>{formatMoney(totals.totalDiscount)}</strong></div>
          <div className="bdm-totals__item bdm-totals__item--grand"><span>Grand Total</span><strong>{formatMoney(totals.grandTotal)}</strong></div>
        </div>
      </div>
    </div>
  );
}
