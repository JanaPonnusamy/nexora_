import React, { useEffect, useMemo, useState } from 'react';
import { PageLayout } from '../../layouts/PageLayout.jsx';
import { EmptyState } from '../../components/states/EmptyState.jsx';
import { ErrorState } from '../../components/states/ErrorState.jsx';
import { LoadingState } from '../../components/states/LoadingState.jsx';
import { useAuth } from '../../contexts/AuthContext.jsx';
import { presentTable } from './presentTable.js';
import { workspaceModule } from './moduleRegistry.js';

const PAGE_SIZE = 40;

function errorTitle(status) {
  if (status === 401) return 'Sign-in required';
  if (status === 403) return 'Not allowed';
  if (status === 404) return 'Not found';
  if (status === 422) return 'Request rejected';
  if (status >= 500) return 'Server error';
  if (status === 0) return 'Network error';
  return 'Request failed';
}

export function WorkspaceModulePage({ moduleId }) {
  const spec = workspaceModule(moduleId);
  const { tenantId, storeId, storeName } = useAuth();
  const [fields, setFields] = useState({});
  const [choices, setChoices] = useState([]);
  const [choice, setChoice] = useState('');
  const [choiceError, setChoiceError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [payload, setPayload] = useState(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (!spec?.choices) return undefined;
    let cancelled = false;
    setChoiceError(null);
    spec.choices.load()
      .then((rows) => {
        if (cancelled) return;
        const list = Array.isArray(rows) ? rows : [];
        setChoices(list);
        setChoice((current) => current || list[0]?.value || '');
      })
      .catch((err) => {
        if (!cancelled) setChoiceError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [spec]);

  async function run(event) {
    event?.preventDefault();
    if (!spec) return;
    if (spec.needsTenant && !tenantId) {
      setError({ status: 0, message: 'Select a tenant in the header first.' });
      return;
    }
    if (spec.needsStore && !storeId) {
      setError({ status: 0, message: 'Select a store in the header first.' });
      return;
    }
    const missing = (spec.fields || []).find((field) => field.required && !String(fields[field.name] || '').trim());
    if (missing) {
      setError({ status: 422, message: `${missing.label} is required.` });
      return;
    }
    if (spec.choices && !choice) {
      setError({ status: 422, message: 'Choose a branch first.' });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await spec.load({
        tenantId,
        storeId,
        storeName,
        ...fields,
        [spec.choices?.name || 'storeName']: choice,
      });
      setPayload(data);
      setPage(0);
    } catch (err) {
      setPayload(null);
      setError({ status: err?.status ?? 0, message: err?.message || 'Request failed' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!spec?.autoLoad) return undefined;
    if (spec.choices && !choice) return undefined;
    run();
    return undefined;
    // Reload when the workspace context changes. Form fields stay manual.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleId, tenantId, storeId, choice]);

  const table = useMemo(() => (payload ? presentTable(payload) : { columns: [], rows: [] }), [payload]);
  const pageCount = Math.max(1, Math.ceil(table.rows.length / PAGE_SIZE));
  const visibleRows = table.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  if (!spec) {
    return (
      <PageLayout title="Unavailable">
        <EmptyState title="This module is not registered" />
      </PageLayout>
    );
  }

  const hasInputs = Boolean(spec.choices) || (spec.fields || []).length > 0;

  return (
    <PageLayout title={spec.title} dense>
      {spec.notice ? <p className="ntm-workbench__notice">{spec.notice}</p> : null}
      <form className={`ntm-workbench__filters${hasInputs ? '' : ' ntm-workbench__filters--bare'}`} onSubmit={run}>
        <div className="ntm-workbench__filters-inputs">
          {spec.needsTenant ? <span className="ntm-workbench__context">Tenant from the header</span> : null}
          {spec.needsStore ? <span className="ntm-workbench__context">{storeName || 'Store from the header'}</span> : null}
          {spec.choices ? (
            <label>
              {spec.choices.label}
              <select value={choice} onChange={(event) => setChoice(event.target.value)}>
                {choices.length === 0 ? <option value="">No branches returned</option> : null}
                {choices.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>
          ) : null}
          {(spec.fields || []).map((field) => (
            <label key={field.name}>
              {field.label}
              <input
                type={field.type || 'text'}
                value={fields[field.name] || ''}
                placeholder={field.placeholder || ''}
                autoComplete="off"
                onChange={(event) => setFields((current) => ({ ...current, [field.name]: event.target.value }))}
              />
            </label>
          ))}
        </div>
        <button type="submit" className="ntm-button ntm-button--primary" disabled={loading}>
          {loading ? 'Loading…' : 'Load'}
        </button>
      </form>
      {choiceError ? <ErrorState title={errorTitle(choiceError.status)} message={choiceError.message} onRetry={() => spec.choices && setChoice('')} /> : null}
      {loading && !payload ? <LoadingState label="Loading live data…" /> : null}
      {error ? <ErrorState title={errorTitle(error.status)} message={error.message} onRetry={() => run()} /> : null}
      {!loading && !error && payload && table.rows.length === 0 ? (
        <EmptyState title="No rows" description="The API returned no rows for this selection." />
      ) : null}
      {table.rows.length > 0 ? (
        <>
          <div className="ntm-workbench__meta">
            <span>{table.rows.length} row{table.rows.length === 1 ? '' : 's'}</span>
            {table.rows.length > PAGE_SIZE ? <span>Page {page + 1} of {pageCount}</span> : null}
          </div>
          <div className="ntm-workbench__scroll">
            <table className="ntm-workbench__table">
              <thead>
                <tr>
                  {table.columns.map((column) => <th key={column.key}>{column.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row, index) => (
                  <tr key={`${page}-${index}`}>
                    {table.columns.map((column) => <td key={column.key}>{row[column.key]}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {table.rows.length > PAGE_SIZE ? (
            <div className="ntm-workbench__pager">
              <button type="button" className="ntm-button ntm-button--secondary" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button>
              <span>{page + 1} / {pageCount}</span>
              <button type="button" className="ntm-button ntm-button--secondary" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => value + 1)}>Next</button>
            </div>
          ) : null}
        </>
      ) : null}
    </PageLayout>
  );
}
