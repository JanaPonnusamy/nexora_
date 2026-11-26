import React, { useEffect, useState } from 'react';
import {
  supplierStockMatch,
  supplierStockDashboardStock,
  supplierStockDashboardDetails,
} from '../../services/supplierStockService.js';
import { LoadingState } from '../../components/states/LoadingState.jsx';
import { ErrorState } from '../../components/states/ErrorState.jsx';
import { formatCurrency, formatDate, formatQty } from '../../utilities/format.js';
import { Icon } from '../../ui/icons.jsx';

// Field names below come from a research pass over the real screen's source
// (desktop/supplier-stock-client/src/App.jsx's SupplierStockAnalysis +
// ProductInfoBar/StoreDetailPanel, and backend/modules/supplier_stock_analysis/
// repository.py) — NOT a live-verified call like Stock Enquiry's
// ProductDetailPanel.jsx got in Phase 5. Every value below is looked up with
// a short fallback-key list for that reason; if a live check later finds a
// different real key, add it to the front of that row's list the same way
// Phase 5's panel was corrected.
function firstDefined(obj, keys, fallback = undefined) {
  for (const key of keys) {
    if (obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== '') return obj[key];
  }
  return fallback;
}

function RawRowsTable({ rows, columns, emptyLabel }) {
  if (!rows || rows.length === 0) {
    return <p className="ntm-detail-panel__empty-note">{emptyLabel}</p>;
  }
  return (
    <table className="ntm-data-grid ntm-data-grid--compact">
      <thead>
        <tr>
          {columns.map((col) => <th key={col.label}>{col.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, idx) => (
          <tr key={idx}>
            {columns.map((col) => (
              <td key={col.label}>{col.render ? col.render(row) : firstDefined(row, col.keys, '—')}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SupplierProductDetailPanel({ tenantId, row, onClose }) {
  const [match, setMatch] = useState(null);
  const [stock, setStock] = useState(null);
  const [details, setDetails] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!row) return undefined;
    const id = row.supplier_stock_id;
    if (!id) {
      setStatus('error');
      setError('This row has no supplier_stock_id, so detail cannot be loaded.');
      return undefined;
    }
    let cancelled = false;
    setStatus('loading');
    setError(null);
    setMatch(null);
    setStock(null);
    setDetails(null);

    Promise.all([
      supplierStockMatch(id, tenantId),
      supplierStockDashboardStock(id, tenantId),
    ])
      .then(([matchData, stockData]) => {
        if (cancelled) return;
        setMatch(matchData);
        setStock(stockData);
        const productCode = firstDefined(stockData, ['product_code']) || row.product_code;
        const sourceStoreId = row.store_id;
        return supplierStockDashboardDetails(id, tenantId, { sourceStoreId, productCode, months: 6 });
      })
      .then((detailsData) => {
        if (cancelled || !detailsData) return;
        setDetails(detailsData);
        setStatus('success');
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load supplier stock detail');
        setStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, [tenantId, row]);

  if (!row) return null;

  const offer = firstDefined(match, ['exact_match', 'supplier_stock']) ? match : null;
  const mappedName = firstDefined(match?.exact_match || {}, ['product_name', 'mapped_product_name']);
  const allStoreStock = stock?.all_store_stock || stock?.store_stock || [];
  const batches = details?.batches || [];
  const purchases = details?.purchases || [];

  return (
    <aside className="ntm-detail-panel" role="dialog" aria-label={`Details for ${row.supplier_product_name || row.product_code}`}>
      <header className="ntm-detail-panel__header">
        <div>
          <h2>{row.supplier_product_name || row.mapped_product_name || row.product_code}</h2>
          <p className="ntm-detail-panel__meta">
            {row.supplier_product_code || row.product_code} · {row.store_code || row.store_name}
          </p>
        </div>
        <button type="button" className="ntm-icon-button" onClick={onClose} aria-label="Close detail panel">
          <Icon name="close" />
        </button>
      </header>

      <div className="ntm-detail-panel__summary">
        <div>
          <span className="ntm-detail-panel__summary-label">Stock</span>
          <strong>{formatQty(row.available_stock)}</strong>
        </div>
        <div>
          <span className="ntm-detail-panel__summary-label">PTR</span>
          <strong>{formatCurrency(row.ptr)}</strong>
        </div>
        <div>
          <span className="ntm-detail-panel__summary-label">MRP</span>
          <strong>{formatCurrency(row.mrp)}</strong>
        </div>
      </div>

      {status === 'loading' ? <LoadingState label="Loading offer, mapping, stock, and history…" /> : null}
      {status === 'error' ? <ErrorState title="Could not load detail" message={error} /> : null}

      {status === 'success' ? (
        <div className="ntm-detail-panel__sections">
          <section>
            <h3>Offer</h3>
            <p className="ntm-detail-panel__empty-note">
              {firstDefined(offer?.supplier_stock || {}, ['scheme', 'offer_text']) || 'No offer on this line.'}
            </p>
          </section>

          <section>
            <h3>Mapped product</h3>
            <p className="ntm-detail-panel__empty-note">
              {mappedName || (row.has_mapping ? 'Mapped, name not returned.' : 'Not mapped to a store product yet.')}
            </p>
          </section>

          <section>
            <h3>Stock by store</h3>
            <RawRowsTable
              rows={allStoreStock}
              emptyLabel="No per-store stock returned."
              columns={[
                { label: 'Store', keys: ['store_name', 'store_code', 'StoreName'] },
                { label: 'Stock', keys: ['total_stock', 'stock', 'Stock'], render: (r) => formatQty(firstDefined(r, ['total_stock', 'stock', 'Stock'])) },
                { label: 'Match', keys: ['store_match_status', 'match_status'] },
              ]}
            />
          </section>

          <section>
            <h3>Near expiry</h3>
            <RawRowsTable
              rows={batches}
              emptyLabel="No near-expiry batch in the selected window."
              columns={[
                { label: 'Batch', keys: ['batch_no', 'BatchCode', 'batch'] },
                { label: 'Expiry', keys: ['expirydate', 'expiry_date', 'Expiry'], render: (r) => formatDate(firstDefined(r, ['expirydate', 'expiry_date', 'Expiry'])) },
                { label: 'Stock', keys: ['stock', 'Stock'], render: (r) => formatQty(firstDefined(r, ['stock', 'Stock'])) },
              ]}
            />
          </section>

          <section>
            <h3>Purchase history</h3>
            <RawRowsTable
              rows={purchases}
              emptyLabel="No purchase history in the selected window."
              columns={[
                { label: 'Date', keys: ['grndate', 'date', 'GRNDate'], render: (r) => formatDate(firstDefined(r, ['grndate', 'date', 'GRNDate'])) },
                { label: 'GRN No', keys: ['grn_no', 'GRNNo'] },
                { label: 'Qty', keys: ['qty', 'StockReceived'], render: (r) => formatQty(firstDefined(r, ['qty', 'StockReceived'])) },
                { label: 'Cost', keys: ['cost', 'ItemCost'], render: (r) => formatCurrency(firstDefined(r, ['cost', 'ItemCost'])) },
              ]}
            />
          </section>
        </div>
      ) : null}
    </aside>
  );
}
