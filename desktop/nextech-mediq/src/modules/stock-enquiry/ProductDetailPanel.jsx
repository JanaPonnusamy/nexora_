import React, { useEffect, useState } from 'react';
import { productCore } from '../../services/stockEnquiryService.js';
import { LoadingState } from '../../components/states/LoadingState.jsx';
import { ErrorState } from '../../components/states/ErrorState.jsx';
import { EmptyState } from '../../components/states/EmptyState.jsx';
import { formatCurrency, formatDate, formatQty } from '../../utilities/format.js';
import { Icon } from '../../ui/icons.jsx';

// /products/core's four result sets are raw SQL Server stored-procedure
// rows with no Pydantic model (verified against service.py/repository.py).
// Field names below were confirmed against a REAL live response on
// 2026-11-14 (tenant "Nathan Medicals", a product with actual stock) —
// not guessed. Each column still takes a short fallback-key list as
// defense-in-depth against a future SP change, but the first key in every
// list is the verified real one.
function firstDefined(row, keys, fallback = undefined) {
  for (const key of keys) {
    if (row && row[key] !== undefined && row[key] !== null) return row[key];
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
          {columns.map((col) => (
            <th key={col.label}>{col.label}</th>
          ))}
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

export function ProductDetailPanel({ tenantId, storeId, storeName, product, onClose }) {
  const [core, setCore] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!product || !storeId) return;
    let cancelled = false;
    setStatus('loading');
    setError(null);
    productCore(tenantId, storeId, product.product_code)
      .then((data) => {
        if (cancelled) return;
        setCore(data);
        setStatus('success');
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load product detail');
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId, storeId, product]);

  if (!product) return null;

  return (
    <aside className="ntm-detail-panel" role="dialog" aria-label={`Details for ${product.product_name}`}>
      <header className="ntm-detail-panel__header">
        <div>
          <h2>{product.product_name}</h2>
          <p className="ntm-detail-panel__meta">
            {product.product_code} · {storeName}
          </p>
        </div>
        <button type="button" className="ntm-icon-button" onClick={onClose} aria-label="Close detail panel">
          <Icon name="close" />
        </button>
      </header>

      <div className="ntm-detail-panel__summary">
        <div>
          <span className="ntm-detail-panel__summary-label">Stock</span>
          <strong>{formatQty(product.stock)}</strong>
        </div>
        <div>
          <span className="ntm-detail-panel__summary-label">MRP</span>
          <strong>{formatCurrency(product.mrp)}</strong>
        </div>
        <div>
          <span className="ntm-detail-panel__summary-label">Unit</span>
          <strong>{product.sale_unit || '—'}</strong>
        </div>
      </div>

      {status === 'loading' ? <LoadingState label="Loading batch and movement detail…" /> : null}
      {status === 'error' ? <ErrorState title="Could not load detail" message={error} /> : null}

      {status === 'success' && core ? (
        <div className="ntm-detail-panel__sections">
          <section>
            <h3>Batches</h3>
            <RawRowsTable
              rows={core.batches}
              emptyLabel="No batch detail available for this product."
              columns={[
                { label: 'Batch', keys: ['batch_no', 'BatchCode', 'batch'] },
                { label: 'Stock', keys: ['stock', 'Stock'], render: (r) => formatQty(firstDefined(r, ['stock', 'Stock'])) },
                { label: 'Expiry', keys: ['expiry_date', 'Expiry'], render: (r) => formatDate(firstDefined(r, ['expiry_date', 'Expiry'])) },
                { label: 'PTR', keys: ['ptr', 'PTR'], render: (r) => formatCurrency(firstDefined(r, ['ptr', 'PTR'])) },
                { label: 'MRP', keys: ['mrp', 'MRP'], render: (r) => formatCurrency(firstDefined(r, ['mrp', 'MRP'])) },
                { label: 'Unit', keys: ['sale_unit', 'SaleUnit'] },
              ]}
            />
          </section>

          <section>
            <h3>Recent purchases</h3>
            <RawRowsTable
              rows={core.purchases}
              emptyLabel="No purchase history in the selected window."
              columns={[
                { label: 'Date', keys: ['date', 'GRNDate'], render: (r) => formatDate(firstDefined(r, ['date', 'GRNDate'])) },
                { label: 'GRN No', keys: ['grn_no', 'GRNNo'] },
                { label: 'Supplier', keys: ['supplier', 'SupplierName'] },
                { label: 'Qty', keys: ['qty', 'StockReceived'], render: (r) => formatQty(firstDefined(r, ['qty', 'StockReceived'])) },
                { label: 'Free', keys: ['free', 'FreeQty'], render: (r) => formatQty(firstDefined(r, ['free', 'FreeQty'])) },
                { label: 'PTR', keys: ['ptr', 'PTR'], render: (r) => formatCurrency(firstDefined(r, ['ptr', 'PTR'])) },
                { label: 'Cost', keys: ['cost', 'ItemCost'], render: (r) => formatCurrency(firstDefined(r, ['cost', 'ItemCost'])) },
              ]}
            />
          </section>

          <section>
            <h3>Recent sales</h3>
            <RawRowsTable
              rows={core.sales}
              emptyLabel="No sales history in the selected window."
              columns={[
                { label: 'Date', keys: ['date', 'TransactionDate'], render: (r) => formatDate(firstDefined(r, ['date', 'TransactionDate'])) },
                { label: 'Bill No', keys: ['bill_no', 'Bnumber'] },
                { label: 'Customer', keys: ['customer', 'CustomerName'] },
                { label: 'Qty', keys: ['qty', 'Quantity'], render: (r) => formatQty(firstDefined(r, ['qty', 'Quantity'])) },
                { label: 'MRP', keys: ['mrp', 'MRP'], render: (r) => formatCurrency(firstDefined(r, ['mrp', 'MRP'])) },
              ]}
            />
          </section>

          <section>
            <h3>Monthly movement</h3>
            <RawRowsTable
              rows={core.movement}
              emptyLabel="No movement summary available."
              columns={[
                { label: 'Period', keys: ['period', 'Month', 'MonthOfStatistics'] },
                { label: 'Purchased', keys: ['pur', 'PUR'], render: (r) => formatQty(firstDefined(r, ['pur', 'PUR'])) },
                { label: 'Sold', keys: ['sal', 'SAL'], render: (r) => formatQty(firstDefined(r, ['sal', 'SAL'])) },
                { label: 'Transfer In', keys: ['tin', 'TIN'], render: (r) => formatQty(firstDefined(r, ['tin', 'TIN'])) },
                { label: 'Transfer Out', keys: ['tout', 'TOUT'], render: (r) => formatQty(firstDefined(r, ['tout', 'TOUT'])) },
                { label: 'Adjustment', keys: ['adj', 'ADJ'], render: (r) => formatQty(firstDefined(r, ['adj', 'ADJ'])) },
                { label: 'Closing Stock', keys: ['stk', 'STK'], render: (r) => formatQty(firstDefined(r, ['stk', 'STK'])) },
              ]}
            />
          </section>
        </div>
      ) : null}

      {status === 'success' && !core ? <EmptyState title="No detail returned" /> : null}
    </aside>
  );
}
