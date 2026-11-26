import React from 'react';

export const SEARCH_MODES = Object.freeze({ PRODUCT: 'product', BATCH: 'batch' });

export function StockSearchControls({
  mode,
  onModeChange,
  query,
  onQueryChange,
  onlyStock,
  onOnlyStockChange,
  batchFields,
  onBatchFieldsChange,
  inputRef,
}) {
  return (
    <div className="ntm-stock-enquiry__controls">
      <div className="ntm-stock-enquiry__mode-switch" role="group" aria-label="Search mode">
        <button
          type="button"
          className={`ntm-mode-tab${mode === SEARCH_MODES.PRODUCT ? ' is-active' : ''}`}
          onClick={() => onModeChange(SEARCH_MODES.PRODUCT)}
          aria-pressed={mode === SEARCH_MODES.PRODUCT}
        >
          Product
        </button>
        <button
          type="button"
          className={`ntm-mode-tab${mode === SEARCH_MODES.BATCH ? ' is-active' : ''}`}
          onClick={() => onModeChange(SEARCH_MODES.BATCH)}
          aria-pressed={mode === SEARCH_MODES.BATCH}
        >
          Batch / MRP
        </button>
      </div>

      {mode === SEARCH_MODES.PRODUCT ? (
        <>
          <input
            ref={inputRef}
            type="text"
            placeholder="Search product name or code… (↑↓ to navigate, Enter for detail)"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            className="ntm-stock-enquiry__search"
            autoFocus
          />
          <label className="ntm-stock-enquiry__checkbox">
            <input type="checkbox" checked={onlyStock} onChange={(e) => onOnlyStockChange(e.target.checked)} />
            Only stores with stock
          </label>
        </>
      ) : (
        <div className="ntm-stock-enquiry__batch-fields">
          <input
            type="text"
            placeholder="Batch number"
            value={batchFields.batch}
            onChange={(e) => onBatchFieldsChange({ ...batchFields, batch: e.target.value })}
            className="ntm-stock-enquiry__search ntm-stock-enquiry__search--narrow"
          />
          <input
            type="text"
            placeholder="MRP"
            value={batchFields.mrp}
            onChange={(e) => onBatchFieldsChange({ ...batchFields, mrp: e.target.value })}
            className="ntm-stock-enquiry__search ntm-stock-enquiry__search--narrow"
          />
          <input
            type="text"
            placeholder="Product name (optional)"
            value={batchFields.product}
            onChange={(e) => onBatchFieldsChange({ ...batchFields, product: e.target.value })}
            className="ntm-stock-enquiry__search"
          />
        </div>
      )}
    </div>
  );
}
