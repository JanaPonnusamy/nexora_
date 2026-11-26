// Excel import REPLACES the supplier's rows in supplier stock for the given
// warehouse store. Same backend flow as supplier-stock-client's
// SupplierExcelImport: preview (pre-fills saved column mapping) -> import.
import React, { useEffect, useMemo, useState } from 'react';
import { listOrderSuppliers, previewSupplierExcel, importSupplierExcel } from '../../services/supplierStockService.js';

export function SupplierStockImport({ tenantId, storeId, storeName, importedBy, initialSupplierCode, onImported }) {
  const [orderSuppliers, setOrderSuppliers] = useState([]);
  const [supplierCode, setSupplierCode] = useState(initialSupplierCode || '');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [status, setStatus] = useState({ state: 'idle', message: 'Choose a supplier and an Excel file to preview.' });

  useEffect(() => {
    if (!tenantId || !storeId) return undefined;
    let cancelled = false;
    listOrderSuppliers(tenantId, storeId)
      .then((res) => { if (!cancelled) setOrderSuppliers(res?.suppliers || []); })
      .catch((err) => { if (!cancelled) setStatus({ state: 'error', message: `Could not load suppliers: ${err.message}` }); });
    return () => { cancelled = true; };
  }, [tenantId, storeId]);

  const sortedSuppliers = useMemo(
    () => [...orderSuppliers]
      .filter((s) => s.supplier_code)
      .sort((a, b) => String(a.supplier_name || a.supplier_code).localeCompare(String(b.supplier_name || b.supplier_code))),
    [orderSuppliers]
  );

  const code = String(supplierCode || '').trim();

  useEffect(() => {
    if (!file) return undefined;
    let cancelled = false;
    setPreview(null);
    setStatus({ state: 'loading', message: 'Reading file…' });
    previewSupplierExcel(file, code ? { tenantId, storeId, supplierCode: code } : {})
      .then((result) => {
        if (cancelled) return;
        setPreview(result);
        setMapping(result.suggested_mapping || {});
        setStatus({
          state: 'ok',
          message: `${result.row_count} row(s) found in "${result.sheet_name}".${result.saved_mapping ? ' Saved mapping applied.' : ''}`,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus({ state: 'error', message: err.message });
      });
    return () => { cancelled = true; };
  }, [file, code, tenantId, storeId]);

  // One field per column: picking a field takes it off whichever column had it.
  function assign(header, target) {
    const next = {};
    Object.entries(mapping).forEach(([h, t]) => { next[h] = target && t === target ? '' : t; });
    next[header] = target;
    setMapping(next);
  }

  async function runImport() {
    if (!file || !code || !storeId) {
      setStatus({ state: 'error', message: 'Warehouse, supplier and a file are all required.' });
      return;
    }
    setStatus({ state: 'loading', message: `Importing ${preview?.row_count ?? ''} line(s)… please wait.` });
    try {
      const result = await importSupplierExcel({ tenantId, storeId, supplierCode: code, mapping, file, importedBy });
      if (result?.success === false) {
        setStatus({
          state: 'error',
          message: result.missing?.length
            ? `Import failed - missing mapping for: ${result.missing.join(', ')}`
            : `Import failed - ${result.error || 'check the column mapping'}`,
        });
        return;
      }
      const dropped = Math.max((preview?.row_count || 0) - result.imported, 0);
      const message = `Imported ${result.imported} product(s) to ${result.store_code || storeName} from ${preview?.row_count ?? '?'} line(s)`
        + `${dropped ? ` (${dropped} duplicate/blank/total line(s) merged or skipped)` : ''}; ${result.product_codes_resolved} matched to products.`;
      setStatus({ state: 'ok', message });
      onImported?.(code, message);
    } catch (err) {
      setStatus({ state: 'error', message: `Import failed - ${err.message}` });
    }
  }

  const busy = status.state === 'loading';

  return (
    <div className="ntm-supplier-stock__import">
      <div className="ntm-supplier-stock__toolbar">
        <label>
          Supplier
          <select value={code} onChange={(e) => setSupplierCode(e.target.value)} disabled={busy}>
            <option value="">Choose supplier…</option>
            {sortedSuppliers.map((s) => (
              <option key={s.supplier_code} value={String(s.supplier_code).trim()}>
                {s.supplier_name || s.supplier_code} ({String(s.supplier_code).trim()})
              </option>
            ))}
          </select>
        </label>
        <label>
          Warehouse
          <input type="text" value={storeName || 'No warehouse'} readOnly />
        </label>
        <label>
          Excel / text file
          <input type="file" accept=".xlsx,.xls,.txt,.csv" disabled={busy} onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
      </div>

      {preview ? (
        <div className="ntm-supplier-stock__mapping">
          <div>Match each column to a field. Required: {preview.targets.filter((t) => t.mandatory).map((t) => t.label).join(', ')}.</div>
          {preview.headers.map((header) => (
            <label key={header}>
              {header}
              <select value={mapping[header] || ''} onChange={(e) => assign(header, e.target.value)}>
                <option value="">Ignore</option>
                {preview.targets.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}{t.mandatory ? ' *' : ''}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
      ) : null}

      <div className="ntm-supplier-stock__import-actions">
        <button type="button" className="ntm-button ntm-button--primary" disabled={!file || !preview || !code || !storeId || busy} onClick={runImport}>
          Import to supplier stock
        </button>
        <span className={`ntm-supplier-stock__import-status is-${status.state}`}>{status.message}</span>
      </div>
    </div>
  );
}
