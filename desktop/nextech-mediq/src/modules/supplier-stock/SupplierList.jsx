import React from 'react';
import { EmptyState } from '../../components/states/EmptyState.jsx';
import { LoadingState } from '../../components/states/LoadingState.jsx';
import { ErrorState } from '../../components/states/ErrorState.jsx';

export function SupplierList({ suppliers, status, error, search, onSearchChange, selectedCode, onSelect, onRetry }) {
  return (
    <aside className="ntm-supplier-list">
      <input
        type="text"
        className="ntm-supplier-list__search"
        placeholder="Search supplier…"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        autoComplete="off"
      />

      {status === 'loading' ? <LoadingState label="Loading suppliers…" /> : null}
      {status === 'error' ? <ErrorState title="Could not load suppliers" message={error} onRetry={onRetry} /> : null}
      {status === 'success' && suppliers.length === 0 ? (
        <EmptyState title="No suppliers" description="No supplier stock has been imported for this warehouse yet." />
      ) : null}

      {status === 'success' && suppliers.length > 0 ? (
        <>
          <p className="ntm-supplier-list__count">{suppliers.length} supplier(s)</p>
          <ul className="ntm-supplier-list__items" role="listbox">
            {suppliers.map((supplier) => {
              const code = supplier.supplier_code;
              const isSelected = code === selectedCode;
              return (
                <li key={code}>
                  <button
                    type="button"
                    className={`ntm-supplier-list__item${isSelected ? ' is-selected' : ''}`}
                    onClick={() => onSelect(supplier)}
                    aria-selected={isSelected}
                  >
                    <span className="ntm-supplier-list__name">{supplier.supplier_name || code}</span>
                    <span className="ntm-supplier-list__meta">
                      {supplier.available_count ?? 0}/{supplier.product_count ?? 0} in stock
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </aside>
  );
}
