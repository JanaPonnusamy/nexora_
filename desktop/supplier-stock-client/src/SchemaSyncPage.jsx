import { useState } from 'react';
import { api } from './api/client.js';

const EMPTY_CONNECTION = { host: '', port: 1433, database: '', username: '', password: '' };

function ScreenHeader({ title, subtitle }) {
  return (
    <header className="screen-header">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </header>
  );
}

function ConnectionForm({ title, hint, value, onChange, testResult, onTest, onEnsureDatabase, testing, ensuring, showCreateDb }) {
  function set(field, v) {
    onChange({ ...value, [field]: v });
  }
  return (
    <div className="schema-sync-conn-card">
      <h3>{title}</h3>
      {hint && <p className="schema-sync-hint">{hint}</p>}
      <label>
        Host / Static IP
        <input value={value.host} onChange={(e) => set('host', e.target.value)} placeholder="e.g. 192.168.10.73" />
      </label>
      <label>
        Port
        <input
          type="number"
          value={value.port}
          onChange={(e) => set('port', Number(e.target.value) || 1433)}
          placeholder="1433"
        />
      </label>
      <label>
        Database name
        <input value={value.database} onChange={(e) => set('database', e.target.value)} placeholder="e.g. OrderNMC" />
      </label>
      <label>
        Username
        <input value={value.username} onChange={(e) => set('username', e.target.value)} placeholder="sa" />
      </label>
      <label>
        Password
        <input type="password" value={value.password} onChange={(e) => set('password', e.target.value)} />
      </label>
      <div className="schema-sync-conn-actions">
        <button type="button" className="secondary-button" onClick={onTest} disabled={testing}>
          {testing ? 'Testing…' : 'Test connection'}
        </button>
        {showCreateDb && testResult?.ok && !testResult?.database_exists && (
          <button type="button" className="secondary-button" onClick={onEnsureDatabase} disabled={ensuring}>
            {ensuring ? 'Creating…' : 'Create database'}
          </button>
        )}
      </div>
      {testResult && (
        <span className={`status ${testResult.ok ? (testResult.database_exists ? 'ok' : 'loading') : 'error'}`}>
          {testResult.message}
        </span>
      )}
    </div>
  );
}

const SEVERITY_LABEL = {
  info: 'Info',
  warn: 'Review',
  'destructive-skipped': 'Manual review required'
};

function DiffSection({ title, items }) {
  if (!items || !items.length) return null;
  return (
    <div className="schema-sync-diff-section">
      <h4>{title} ({items.length})</h4>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Schema</th><th>Object</th><th>Detail</th><th>Status</th></tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={`${item.schema_name}.${item.object_name}.${idx}`} className={item.severity === 'destructive-skipped' ? 'row-warn' : ''}>
                <td>{item.schema_name}</td>
                <td>{item.object_name}</td>
                <td>{item.detail}</td>
                <td>{SEVERITY_LABEL[item.severity] || item.severity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function SchemaSyncPage({ session }) {
  const [source, setSource] = useState(EMPTY_CONNECTION);
  const [target, setTarget] = useState(EMPTY_CONNECTION);
  const [sourceTest, setSourceTest] = useState(null);
  const [targetTest, setTargetTest] = useState(null);
  const [testingSource, setTestingSource] = useState(false);
  const [testingTarget, setTestingTarget] = useState(false);
  const [ensuring, setEnsuring] = useState(false);
  const [compareStatus, setCompareStatus] = useState({ state: 'idle', message: '' });
  const [compareResult, setCompareResult] = useState(null);
  const [applyStatus, setApplyStatus] = useState({ state: 'idle', message: '' });
  const [applyResult, setApplyResult] = useState(null);

  async function testSource() {
    setTestingSource(true);
    setSourceTest(null);
    try {
      const result = await api.testSchemaSyncConnection(source, session);
      setSourceTest(result);
    } catch (error) {
      setSourceTest({ ok: false, database_exists: false, message: error.message });
    } finally {
      setTestingSource(false);
    }
  }

  async function testTarget() {
    setTestingTarget(true);
    setTargetTest(null);
    try {
      const result = await api.testSchemaSyncConnection(target, session);
      setTargetTest(result);
    } catch (error) {
      setTargetTest({ ok: false, database_exists: false, message: error.message });
    } finally {
      setTestingTarget(false);
    }
  }

  async function ensureTargetDatabase() {
    setEnsuring(true);
    try {
      const result = await api.ensureSchemaSyncDatabase(target, session);
      setTargetTest({ ok: result.ok, database_exists: result.ok, message: result.message });
    } catch (error) {
      setTargetTest({ ok: false, database_exists: false, message: error.message });
    } finally {
      setEnsuring(false);
    }
  }

  const canCompare = Boolean(source.host && source.database && source.username && target.host && target.database && target.username);

  async function runCompare() {
    setCompareStatus({ state: 'loading', message: 'Reading both schemas and comparing…' });
    setCompareResult(null);
    setApplyResult(null);
    try {
      const result = await api.compareSchemaSync(source, target, session);
      setCompareResult(result);
      setCompareStatus({
        state: 'ok',
        message: `Comparison complete — ${result.summary.total_statements} change(s) planned.`
      });
    } catch (error) {
      setCompareStatus({ state: 'error', message: error.message });
    }
  }

  async function runApply() {
    if (!compareResult?.statements?.length) return;
    const confirmed = window.confirm(
      `This will apply ${compareResult.statements.length} change(s) directly to Production (${target.host}/${target.database}). Continue?`
    );
    if (!confirmed) return;
    setApplyStatus({ state: 'loading', message: 'Applying changes to Production…' });
    try {
      const result = await api.applySchemaSync(target, compareResult.statements, session);
      setApplyResult(result);
      setApplyStatus({
        state: result.ok ? 'ok' : 'error',
        message: `Applied ${result.applied} of ${result.applied + result.failed} statement(s).${result.failed ? ` ${result.failed} failed - see log below.` : ''}`
      });
    } catch (error) {
      setApplyStatus({ state: 'error', message: error.message });
    }
  }

  return (
    <section className="screen-panel schema-sync-page">
      <ScreenHeader
        title="Schema Sync"
        subtitle="Compare a Development SQL Server against Production/HO and push missing tables, columns, indexes and stored procedures. Development is always read-only."
      />

      <div className="schema-sync-conn-grid">
        <ConnectionForm
          title="Source — Development (read-only)"
          hint="Never written to."
          value={source}
          onChange={setSource}
          testResult={sourceTest}
          onTest={testSource}
          testing={testingSource}
          showCreateDb={false}
        />
        <ConnectionForm
          title="Target — Production / HO"
          hint="Schema changes are applied here. If the database doesn't exist yet, it will be created."
          value={target}
          onChange={setTarget}
          testResult={targetTest}
          onTest={testTarget}
          onEnsureDatabase={ensureTargetDatabase}
          testing={testingTarget}
          ensuring={ensuring}
          showCreateDb
        />
      </div>

      <div className="schema-sync-compare-actions">
        <button type="button" className="primary-button" onClick={runCompare} disabled={!canCompare || compareStatus.state === 'loading'}>
          {compareStatus.state === 'loading' ? 'Comparing…' : 'Compare schemas'}
        </button>
        {compareStatus.message && <span className={`status ${compareStatus.state}`}>{compareStatus.message}</span>}
      </div>

      {compareResult && (
        <div className="schema-sync-report">
          <DiffSection title="Tables missing in Production" items={compareResult.tables_missing_in_target} />
          <DiffSection title="Tables that exist only in Production (review, not touched)" items={compareResult.tables_only_in_target} />
          <DiffSection title="Dev-only scratch/backup tables skipped" items={compareResult.tables_skipped_as_artifacts} />
          <DiffSection title="Column differences" items={compareResult.column_diffs} />
          <DiffSection title="Index differences" items={compareResult.index_diffs} />
          <DiffSection title="Constraint differences" items={compareResult.constraint_diffs} />
          <DiffSection title="Stored procedures / views / functions / triggers" items={compareResult.programmable_diffs} />

          {compareResult.statements.length > 0 && (
            <div className="schema-sync-apply-actions">
              <button type="button" className="primary-button" onClick={runApply} disabled={applyStatus.state === 'loading'}>
                {applyStatus.state === 'loading' ? 'Applying…' : `Update Production (${compareResult.statements.length} change${compareResult.statements.length === 1 ? '' : 's'})`}
              </button>
              {applyStatus.message && <span className={`status ${applyStatus.state}`}>{applyStatus.message}</span>}
            </div>
          )}

          {applyResult && (
            <div className="schema-sync-diff-section">
              <h4>Apply log</h4>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>#</th><th>Category</th><th>Object</th><th>Result</th><th>Message</th></tr>
                  </thead>
                  <tbody>
                    {applyResult.results.map((r) => (
                      <tr key={r.seq} className={r.ok ? '' : 'row-warn'}>
                        <td>{r.seq}</td>
                        <td>{r.category}</td>
                        <td>{r.object_name}</td>
                        <td>{r.ok ? 'OK' : 'FAILED'}</td>
                        <td>{r.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
