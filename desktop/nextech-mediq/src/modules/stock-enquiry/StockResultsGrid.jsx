import React, { useMemo } from 'react';
import { EmptyState } from '../../components/states/EmptyState.jsx';
import { formatCurrency, formatQty, isLowStock, isOutOfStock } from '../../utilities/format.js';

const PAGE_SIZE = 200;

// Flattens the per-branch result into one row list so keyboard
// up/down and row selection work across branch boundaries, while still
// rendering grouped-by-branch headers. Avoids loading an external
// virtualization library for this: search results are bounded by
// (store count × matching products per store), which in practice stays
// well under the point a plain <table> struggles — a hard cap plus a
// "show more" affordance covers the pathological case without the added
// dependency weight.
function flattenRows(stores) {
  const rows = [];
  for (const branch of stores) {
    for (const product of branch.products) {
      rows.push({ branch, product });
    }
  }
  return rows;
}

export function StockResultsGrid({ result, selectedRowKey, onSelectRow, visibleCount, onShowMore }) {
  const stores = result?.stores ?? [];
  const summary = result?.summary;
  const allRows = useMemo(() => flattenRows(stores), [stores]);
  const rows = allRows.slice(0, visibleCount);
  const hasMore = allRows.length > rows.length;

  if (stores.length === 0 || summary?.total_products_found === 0) {
    return <EmptyState title="No matching products" description="Try a different product name, code, batch, or MRP." />;
  }

  let lastBranchId = null;

  return (
    <div className="ntm-stock-grid">
      {summary ? (
        <p className="ntm-stock-grid__summary">
          {summary.total_products_found} product(s) across {summary.stores_with_stock}/{summary.total_stores} branches with stock —
          total stock {formatQty(summary.total_stock_all_stores)}
        </p>
      ) : null}

      <div className="ntm-stock-grid__scroll">
      <table className="ntm-data-grid" role="grid">
        <thead>
          <tr>
            <th>Branch</th>
            <th>Product Code</th>
            <th>Product Name</th>
            <th>Unit</th>
            <th>Stock</th>
            <th>MRP</th>
            <th>Batch</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ branch, product }, idx) => {
            const rowKey = `${branch.store_id}-${product.product_code}-${product.batch_no ?? idx}`;
            const showBranchHeader = branch.store_id !== lastBranchId;
            lastBranchId = branch.store_id;
            const outOfStock = isOutOfStock(product.stock);
            const low = !outOfStock && isLowStock(product.stock);
            return (
              <React.Fragment key={rowKey}>
                {showBranchHeader ? (
                  <tr className="ntm-data-grid__branch-row" aria-hidden="true">
                    <td colSpan={7}>
                      {branch.store_name || branch.store_code || branch.store_id}
                      <span className="ntm-stock-grid__branch-total"> — {formatQty(branch.total_stock)} total stock</span>
                    </td>
                  </tr>
                ) : null}
                <tr
                  className={`ntm-data-grid__row${selectedRowKey === rowKey ? ' is-selected' : ''}`}
                  tabIndex={-1}
                  data-row-key={rowKey}
                  onClick={() => onSelectRow(rowKey, branch, product)}
                  aria-selected={selectedRowKey === rowKey}
                >
                  <td className="ntm-data-grid__branch-cell">{branch.store_code || branch.store_name}</td>
                  <td>{product.product_code}</td>
                  <td>{product.product_name}</td>
                  <td>{product.sale_unit}</td>
                  <td>
                    <span className={`ntm-stock-pill${outOfStock ? ' ntm-stock-pill--out' : low ? ' ntm-stock-pill--low' : ''}`}>
                      {formatQty(product.stock)}
                    </span>
                  </td>
                  <td>{formatCurrency(product.mrp)}</td>
                  <td>{product.batch_no || '—'}</td>
                </tr>
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
      </div>

      {hasMore ? (
        <button type="button" className="ntm-button ntm-button--secondary ntm-stock-grid__more" onClick={onShowMore}>
          Show more ({allRows.length - rows.length} remaining)
        </button>
      ) : null}
    </div>
  );
}

export { flattenRows, PAGE_SIZE };
