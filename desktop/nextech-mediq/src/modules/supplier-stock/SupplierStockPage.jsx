// Supplier Stock Analysis — port of desktop/supplier-stock-client's
// SupplierStockAnalysis: supplier list, product search, warehouse-stock
// filter, detail panel, and supplier Excel import (SupplierStockImport).
// Mapping save and assignment save are not ported.
//
// procurement.supplier_stock is keyed per-store and only ever imported
// against the tenant's warehouse store (e.g. NMW) — a retail store like
// NMA has zero rows of its own. So this page does NOT reuse the header's
// Tenant/Store chip as the query scope (that just leaked "no suppliers"
// for every non-warehouse store, incl. NMA). Instead, same as the legacy
// desktop/supplier-stock-client screen, it resolves the tenant's
// warehouse store itself from useAuth().stores and always queries with
// that store_id, regardless of which store is selected in the header —
// so NMA (and any other non-warehouse store) users see the same
// warehouse-scoped supplier stock without having to switch stores.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { PageLayout } from '../../layouts/PageLayout.jsx';
import { useAuth } from '../../contexts/AuthContext.jsx';
import {
  listSuppliers,
  listSupplierProducts,
  warehouseStockCounts,
  warehouseStockProducts,
} from '../../services/supplierStockService.js';
import { SupplierList } from './SupplierList.jsx';
import { SupplierProductsGrid } from './SupplierProductsGrid.jsx';
import { SupplierProductDetailPanel } from './SupplierProductDetailPanel.jsx';
import { EmptyState } from '../../components/states/EmptyState.jsx';
import { SupplierStockImport } from './SupplierStockImport.jsx';
import { SupplierMailImport } from './SupplierMailImport.jsx';

const SEARCH_DEBOUNCE_MS = 350;

const STOCK_FILTERS = [
  { value: '', label: 'All suppliers (no warehouse filter)' },
  { value: 'zero', label: 'Zero warehouse stock' },
  { value: 'positive', label: 'Positive warehouse stock' },
  { value: 'zero_other_positive', label: 'Zero here, positive elsewhere' },
  { value: 'zero_all_zero', label: 'Zero everywhere' },
];

function isWarehouseStore(store) {
  return Boolean(store?.is_warehouse) || String(store?.store_code || '').trim().toUpperCase() === 'NMW';
}

export function SupplierStockPage() {
  const { tenantId, stores, user } = useAuth();
  const [importOpen, setImportOpen] = useState(false);
  const [mailOpen, setMailOpen] = useState(false);
  const [importNotice, setImportNotice] = useState('');

  const warehouses = stores.filter((store) => String(store.tenant_id) === String(tenantId) && isWarehouseStore(store));
  const [warehouseId, setWarehouseId] = useState('');
  useEffect(() => {
    if (!warehouses.length) {
      if (warehouseId) setWarehouseId('');
      return;
    }
    if (!warehouses.some((w) => String(w.store_id) === String(warehouseId))) {
      setWarehouseId(warehouses[0].store_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, warehouses.map((w) => w.store_id).join(',')]);

  const selectedWarehouse = warehouses.find((w) => String(w.store_id) === String(warehouseId)) || null;
  const storeId = selectedWarehouse?.store_id || '';
  const storeName = selectedWarehouse?.store_name || '';

  const [suppliers, setSuppliers] = useState([]);
  const [supplierStatus, setSupplierStatus] = useState('idle');
  const [supplierError, setSupplierError] = useState(null);
  const [supplierSearch, setSupplierSearch] = useState('');
  const [selectedSupplier, setSelectedSupplier] = useState(null);

  const [stockFilter, setStockFilter] = useState('');
  const [counts, setCounts] = useState(null);

  const [products, setProducts] = useState([]);
  const [productStatus, setProductStatus] = useState('idle');
  const [productError, setProductError] = useState(null);
  const [productSearch, setProductSearch] = useState('');
  const [onlyAvailable, setOnlyAvailable] = useState(true);

  const [selectedRow, setSelectedRow] = useState(null);

  const supplierDebounceRef = useRef(null);
  const productDebounceRef = useRef(null);
  const requestIdRef = useRef(0);

  const loadSuppliers = useCallback(() => {
    if (!tenantId) return;
    setSupplierStatus('loading');
    setSupplierError(null);
    listSuppliers(tenantId, storeId, supplierSearch)
      .then((rows) => {
        setSuppliers(Array.isArray(rows) ? rows : []);
        setSupplierStatus('success');
      })
      .catch((err) => {
        setSupplierError(err.message || 'Failed to load suppliers');
        setSupplierStatus('error');
      });
  }, [tenantId, storeId, supplierSearch]);

  useEffect(() => {
    clearTimeout(supplierDebounceRef.current);
    supplierDebounceRef.current = setTimeout(loadSuppliers, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(supplierDebounceRef.current);
  }, [loadSuppliers]);

  useEffect(() => {
    if (!tenantId || !storeId) return;
    warehouseStockCounts(tenantId, storeId)
      .then((data) => setCounts(data))
      .catch(() => setCounts(null));
  }, [tenantId, storeId]);

  const loadProducts = useCallback(() => {
    if (!tenantId) return;
    if (stockFilter) {
      if (!storeId) {
        setProductStatus('error');
        setProductError('No warehouse is configured for this tenant.');
        return;
      }
      const requestId = ++requestIdRef.current;
      setProductStatus('loading');
      setProductError(null);
      warehouseStockProducts(tenantId, storeId, stockFilter, productSearch)
        .then((rows) => {
          if (requestId !== requestIdRef.current) return;
          setProducts(Array.isArray(rows) ? rows : []);
          setProductStatus('success');
        })
        .catch((err) => {
          if (requestId !== requestIdRef.current) return;
          setProductError(err.message || 'Failed to load warehouse stock');
          setProductStatus('error');
        });
      return;
    }
    if (!selectedSupplier) {
      setProducts([]);
      setProductStatus('idle');
      return;
    }
    const requestId = ++requestIdRef.current;
    setProductStatus('loading');
    setProductError(null);
    listSupplierProducts(tenantId, storeId, selectedSupplier.supplier_code, { search: productSearch, onlyAvailable })
      .then((rows) => {
        if (requestId !== requestIdRef.current) return;
        setProducts(Array.isArray(rows) ? rows : []);
        setProductStatus('success');
      })
      .catch((err) => {
        if (requestId !== requestIdRef.current) return;
        setProductError(err.message || 'Failed to load supplier products');
        setProductStatus('error');
      });
  }, [tenantId, storeId, stockFilter, selectedSupplier, productSearch, onlyAvailable]);

  useEffect(() => {
    clearTimeout(productDebounceRef.current);
    productDebounceRef.current = setTimeout(loadProducts, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(productDebounceRef.current);
  }, [loadProducts]);

  function selectSupplier(supplier) {
    setStockFilter('');
    setSelectedSupplier(supplier);
    setSelectedRow(null);
  }

  function handleImported(supplierCode, message) {
    setImportNotice(message);
    loadSuppliers();
    if (storeId) {
      warehouseStockCounts(tenantId, storeId).then(setCounts).catch(() => {});
    }
    const existing = suppliers.find((s) => String(s.supplier_code).trim() === supplierCode);
    selectSupplier(existing || { supplier_code: supplierCode, supplier_name: supplierCode });
  }

  function changeStockFilter(value) {
    setStockFilter(value);
    setSelectedSupplier(null);
    setSelectedRow(null);
  }

  return (
    <PageLayout
      title="Supplier Stock"
      description={
        warehouses.length === 0
          ? 'No warehouse is configured for this tenant.'
          : storeName
            ? `Warehouse: ${storeName}`
            : 'Select a tenant to resolve its warehouse.'
      }
      dense
    >
      <div className="ntm-supplier-stock__toolbar">
        <button
          type="button"
          className={`ntm-button${importOpen ? '' : ' ntm-button--primary'}`}
          disabled={!tenantId || !storeId}
          title={storeId ? 'Import a supplier stock Excel file' : 'No warehouse is configured for this tenant'}
          onClick={() => { setMailOpen(false); setImportOpen((open) => !open); }}
        >
          {importOpen ? 'Close import' : 'Import Supplier Excel'}
        </button>
        <button
          type="button"
          className="ntm-button"
          disabled={!tenantId || !storeId}
          title="Import supplier stock files automatically from the tenant mailbox"
          onClick={() => { setImportOpen(false); setMailOpen((open) => !open); }}
        >
          {mailOpen ? 'Close mail import' : 'Mail Import'}
        </button>
        {warehouses.length > 1 ? (
          <label>
            Warehouse
            <select value={warehouseId} onChange={(event) => setWarehouseId(event.target.value)}>
              {warehouses.map((w) => (
                <option key={w.store_id} value={w.store_id}>
                  {w.store_name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label>
          Warehouse stock
          <select value={stockFilter} onChange={(event) => changeStockFilter(event.target.value)}>
            {STOCK_FILTERS.map((option) => (
              <option key={option.value || 'all'} value={option.value}>
                {option.label}
                {counts && option.value && counts[option.value] !== undefined ? ` (${counts[option.value]})` : ''}
              </option>
            ))}
          </select>
        </label>
        <label>
          Product search
          <input
            type="text"
            value={productSearch}
            onChange={(event) => setProductSearch(event.target.value)}
            placeholder="Search supplier products…"
            autoComplete="off"
          />
        </label>
        {!stockFilter ? (
          <label className="ntm-supplier-stock__checkbox">
            <input type="checkbox" checked={onlyAvailable} onChange={(event) => setOnlyAvailable(event.target.checked)} />
            In stock only
          </label>
        ) : null}
      </div>

      {importOpen && tenantId && storeId ? (
        <SupplierStockImport
          key={storeId}
          tenantId={tenantId}
          storeId={storeId}
          storeName={storeName}
          importedBy={user?.username || user?.name}
          initialSupplierCode={selectedSupplier?.supplier_code ? String(selectedSupplier.supplier_code).trim() : ''}
          onImported={handleImported}
        />
      ) : null}
      {mailOpen && tenantId && storeId ? <SupplierMailImport key={storeId} tenantId={tenantId} storeId={storeId} /> : null}
      {importNotice && !importOpen ? <div className="ntm-supplier-stock__import-status is-ok">{importNotice}</div> : null}

      {!tenantId ? (
        <EmptyState title="Select a tenant" description="Choose a tenant in the header to load suppliers." />
      ) : (
        <div className="ntm-supplier-stock">
          <SupplierList
            suppliers={suppliers}
            status={supplierStatus}
            error={supplierError}
            search={supplierSearch}
            onSearchChange={setSupplierSearch}
            selectedCode={stockFilter ? null : selectedSupplier?.supplier_code}
            onSelect={selectSupplier}
            onRetry={loadSuppliers}
          />

          <div className="ntm-supplier-stock__main">
            <SupplierProductsGrid
              products={products}
              status={productStatus}
              error={productError}
              selectedId={selectedRow?.supplier_stock_id}
              onSelect={setSelectedRow}
              onRetry={loadProducts}
              emptyHint={
                stockFilter
                  ? 'No products matched this warehouse-stock filter.'
                  : 'Pick a supplier on the left, or choose a warehouse-stock filter above, to list products.'
              }
            />
          </div>

          {selectedRow ? (
            <SupplierProductDetailPanel tenantId={tenantId} row={selectedRow} onClose={() => setSelectedRow(null)} />
          ) : null}
        </div>
      )}
    </PageLayout>
  );
}
