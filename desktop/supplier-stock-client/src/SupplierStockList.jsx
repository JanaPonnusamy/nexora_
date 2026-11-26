// Supplier Stock List -- a plain read of the current SupplierStock rows
// (GET /api/supplier-stock-analysis/stock-list): pick a tenant and a
// supplier, optionally one store, and the rows load into the grid exactly as
// imported (Excel / mail import). No mapping analysis, no writes.
// The grid reuses the Non-Moving Stock skin (.nms-aggrid-wrap, AG Grid v32).
import { useEffect, useMemo, useRef, useState } from 'react';
import { AgGridReact } from 'ag-grid-react';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import { api } from './api/client.js';

const asList = (data, key) => (Array.isArray(data) ? data : Array.isArray(data?.[key]) ? data[key] : []);
const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
const fmtQty = (v) => num(v).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const fmtMoney = (v) => (v == null || v === '' ? '' : num(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
function fmtDate(v) {
  if (!v) return '';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

const COLUMNS = [
  { field: 'store_code', headerName: 'Store', width: 90, pinned: 'left' },
  { field: 'supplier_product_code', headerName: 'Product Code', width: 130 },
  { field: 'supplier_product_name', headerName: 'Product Name', flex: 1, minWidth: 240 },
  { field: 'packing', headerName: 'Packing', width: 110 },
  { field: 'stock', headerName: 'Stock', width: 100, type: 'rightAligned', valueFormatter: (p) => fmtQty(p.value) },
  { field: 'ptr', headerName: 'PTR', width: 95, type: 'rightAligned', valueFormatter: (p) => fmtMoney(p.value) },
  { field: 'mrp', headerName: 'MRP', width: 95, type: 'rightAligned', valueFormatter: (p) => fmtMoney(p.value) },
  { field: 'discount', headerName: 'Disc', width: 80 },
  { field: 'free', headerName: 'Free', width: 80 },
  { field: 'scheme', headerName: 'Scheme', width: 90 },
  { field: 'minimum_qty', headerName: 'Min Qty', width: 90 },
  { field: 'rack', headerName: 'Rack', width: 90 },
  { field: 'product_code', headerName: 'Our Code', width: 100 },
  { field: 'imported_at', headerName: 'Imported', width: 165, valueFormatter: (p) => fmtDate(p.value) },
];
const DEFAULT_COL = { resizable: true, sortable: true, filter: true };

export default function SupplierStockList({ session, settings, tenants }) {
  const [tenantId, setTenantId] = useState(settings?.tenantId || '');
  const [allStores, setAllStores] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [supplierCode, setSupplierCode] = useState('');
  const [storeId, setStoreId] = useState('');
  const [search, setSearch] = useState('');
  const [inStockOnly, setInStockOnly] = useState(false);
  const [rows, setRows] = useState([]);
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState({ state: 'idle', message: '' });
  const requestRef = useRef(0);

  useEffect(() => {
    if (!tenantId && settings?.tenantId) setTenantId(settings.tenantId);
  }, [settings?.tenantId, tenantId]);

  useEffect(() => {
    api.listStores(session).then((list) => setAllStores(asList(list, 'stores'))).catch(() => setAllStores([]));
  }, [session]);

  const tenantStores = useMemo(
    () => allStores
      .filter((s) => String(s.tenant_id) === String(tenantId))
      .sort((a, b) => String(a.store_code || '').localeCompare(String(b.store_code || ''))),
    [allStores, tenantId]
  );

  // Tenant change: reload the supplier list (every store of the tenant).
  useEffect(() => {
    setSuppliers([]);
    setSupplierCode('');
    setStoreId('');
    setRows([]);
    setResult(null);
    if (!tenantId) return undefined;
    let cancelled = false;
    setStatus({ state: 'loading', message: 'Loading suppliers…' });
    api.getSuppliers(session, { tenantId, storeId: '' })
      .then((data) => {
        if (cancelled) return;
        const list = asList(data, 'suppliers');
        setSuppliers(list);
        setStatus({ state: 'idle', message: list.length ? '' : 'No supplier stock imported for this tenant yet.' });
      })
      .catch((err) => { if (!cancelled) setStatus({ state: 'error', message: err.message }); });
    return () => { cancelled = true; };
  }, [session, tenantId]);

  function load(code = supplierCode, store = storeId) {
    if (!tenantId || !code) return;
    const id = ++requestRef.current;
    setStatus({ state: 'loading', message: 'Loading stock…' });
    api.supplierStockList(session, { tenantId, supplierCode: code, storeId: store })
      .then((data) => {
        if (id !== requestRef.current) return;
        setRows(asList(data, 'items'));
        setResult(data);
        setStatus({ state: 'idle', message: '' });
      })
      .catch((err) => {
        if (id !== requestRef.current) return;
        setRows([]);
        setResult(null);
        setStatus({ state: 'error', message: err.message });
      });
  }

  function chooseSupplier(code) {
    setSupplierCode(code);
    if (code) load(code, storeId);
    else { setRows([]); setResult(null); }
  }

  function chooseStore(id) {
    setStoreId(id);
    if (supplierCode) load(supplierCode, id);
  }

  const shown = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter((r) => (!inStockOnly || num(r.stock) > 0)
      && (!term
        || String(r.supplier_product_name || '').toLowerCase().includes(term)
        || String(r.supplier_product_code || '').toLowerCase().startsWith(term)));
  }, [rows, search, inStockOnly]);

  const totals = useMemo(() => {
    const stores = new Set();
    let stock = 0;
    let inStock = 0;
    let latest = null;
    shown.forEach((r) => {
      stores.add(r.store_code);
      stock += num(r.stock);
      if (num(r.stock) > 0) inStock += 1;
      if (r.imported_at && (!latest || r.imported_at > latest)) latest = r.imported_at;
    });
    return { stores: stores.size, stock, inStock, latest };
  }, [shown]);

  const supplier = suppliers.find((s) => String(s.supplier_code) === String(supplierCode));
  const loading = status.state === 'loading';

  return (
    <section className="screen-panel nms-screen ssl-screen">
      <header className="screen-header nms-header">
        <div>
          <h2>Supplier Stock List</h2>
          <p>Current supplier stock as imported (Excel or mail). Pick a tenant and a supplier.</p>
        </div>
      </header>

      <div className="ssl-toolbar">
        <label>
          Tenant
          <select value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {!tenantId ? <option value="">Select tenant</option> : null}
            {(tenants || []).map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>{String(t.tenant_name || t.tenant_code || t.tenant_id).trim()}</option>
            ))}
          </select>
        </label>
        <label>
          Supplier
          <select value={supplierCode} disabled={!suppliers.length} onChange={(e) => chooseSupplier(e.target.value)}>
            <option value="">{suppliers.length ? 'Select supplier' : '—'}</option>
            {suppliers.map((s) => (
              <option key={s.supplier_code} value={s.supplier_code}>
                {String(s.supplier_name || s.supplier_code).trim()} ({s.supplier_code}) · {fmtQty(s.product_count)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Store
          <select value={storeId} onChange={(e) => chooseStore(e.target.value)}>
            <option value="">All stores</option>
            {tenantStores.map((s) => (
              <option key={s.store_id} value={s.store_id}>{s.store_code} · {s.store_name}</option>
            ))}
          </select>
        </label>
        <label>
          Search
          <input type="text" value={search} placeholder="Product name or code" onChange={(e) => setSearch(e.target.value)} />
        </label>
        <label className="ssl-check">
          <input type="checkbox" checked={inStockOnly} onChange={(e) => setInStockOnly(e.target.checked)} /> In stock only
        </label>
        <button type="button" className="primary-button" disabled={!supplierCode || loading} onClick={() => load()}>
          {loading ? 'Loading…' : 'Reload'}
        </button>
      </div>

      {status.message ? <div className={`ssl-status is-${status.state}`}>{status.message}</div> : null}
      {result?.truncated ? (
        <div className="ssl-status is-error">Showing the first {fmtQty(result.limit)} rows only. Pick a store to see the rest.</div>
      ) : null}

      <div className="nms-aggrid-wrap ag-theme-quartz">
        <AgGridReact
          rowData={shown}
          columnDefs={COLUMNS}
          defaultColDef={DEFAULT_COL}
          getRowId={(p) => `${p.data.store_code}|${p.data.supplier_product_code}`}
          overlayNoRowsTemplate={supplierCode ? '<span>No stock rows for this selection.</span>' : '<span>Select a supplier to load its stock.</span>'}
          animateRows={false}
          enableCellTextSelection
        />
      </div>

      <div className="ssl-statusbar">
        {supplier ? <span><b>{String(supplier.supplier_name || supplier.supplier_code).trim()}</b></span> : null}
        <span><b>{fmtQty(shown.length)}</b> rows{shown.length !== rows.length ? ` of ${fmtQty(rows.length)}` : ''}</span>
        <span><b>{fmtQty(totals.inStock)}</b> in stock</span>
        <span><b>{totals.stores}</b> store{totals.stores === 1 ? '' : 's'}</span>
        <span>Total stock <b>{fmtQty(totals.stock)}</b></span>
        {totals.latest ? <span>Last import {fmtDate(totals.latest)}</span> : null}
      </div>
    </section>
  );
}
