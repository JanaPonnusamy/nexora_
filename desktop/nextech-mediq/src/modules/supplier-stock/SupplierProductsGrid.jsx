import React from 'react';
import { EmptyState } from '../../components/states/EmptyState.jsx';
import { LoadingState } from '../../components/states/LoadingState.jsx';
import { ErrorState } from '../../components/states/ErrorState.jsx';
import { formatCurrency, formatQty, isLowStock, isOutOfStock } from '../../utilities/format.js';

const MAPPING_LABEL = {
  not_mapped: 'Not mapped',
  partially_matched: 'Partial',
  fully_matched: 'Mapped',
};

export function SupplierProductsGrid({ products, status, error, selectedId, onSelect, onRetry, emptyHint }) {
  if (status === 'idle') {
    return <EmptyState title="Pick a supplier" description={emptyHint || 'Pick a supplier on the left, or choose a warehouse-stock filter above, to list products.'} />;
  }
  if (status === 'loading') return <LoadingState label="Loading products…" />;
  if (status === 'error') return <ErrorState title="Could not load products" message={error} onRetry={onRetry} />;
  if (!products || products.length === 0) {
    return <EmptyState title="No products" description="No products matched this supplier or filter." />;
  }

  return (
    <div className="ntm-supplier-grid__scroll">
      <table className="ntm-data-grid" role="grid">
        <thead>
          <tr>
            <th>Product</th>
            <th>Store</th>
            <th>Stock</th>
            <th>PTR</th>
            <th>MRP</th>
            <th>Mapping</th>
          </tr>
        </thead>
        <tbody>
          {products.map((row, idx) => {
            const id = row.supplier_stock_id ?? idx;
            const outOfStock = isOutOfStock(row.available_stock);
            const low = !outOfStock && isLowStock(row.available_stock);
            return (
              <tr
                key={id}
                className={`ntm-data-grid__row${selectedId === id ? ' is-selected' : ''}`}
                tabIndex={-1}
                onClick={() => onSelect(row)}
                aria-selected={selectedId === id}
              >
                <td>
                  <div className="ntm-supplier-grid__product-name">{row.supplier_product_name || row.mapped_product_name || '—'}</div>
                  <div className="ntm-supplier-grid__product-code">{row.supplier_product_code || row.product_code || ''}</div>
                </td>
                <td>{row.store_code || row.store_name || '—'}</td>
                <td>
                  <span className={`ntm-stock-pill${outOfStock ? ' ntm-stock-pill--out' : low ? ' ntm-stock-pill--low' : ''}`}>
                    {formatQty(row.available_stock)}
                  </span>
                </td>
                <td>{formatCurrency(row.ptr)}</td>
                <td>{formatCurrency(row.mrp)}</td>
                <td>
                  <span className={`ntm-mapping-badge ntm-mapping-badge--${row.mapping_scope_status || 'not_mapped'}`}>
                    {MAPPING_LABEL[row.mapping_scope_status] || 'Not mapped'}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
