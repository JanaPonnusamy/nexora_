// NEXORA MEDIQ Phase 6G: unified ERP dashboard. Same standalone-module
// pattern as SchemaSyncPage.jsx/UserManagementScreen.jsx.
//
// Every widget here is wired to a real, already-existing backend endpoint
// (confirmed by reading each one's source before wiring it -- see
// docs/NEXORA_MEDIQ_AUDIT/28_PHASE6_ERP_WORKSPACE_IMPLEMENTATION_REPORT.md
// for the full survey). Two candidates from the authorization's own list
// -- Supplier Stock status and a general Inventory summary -- had no
// existing lightweight summary endpoint to wire to, and are rendered as
// "Planned" placeholders rather than invented numbers, per the
// authorization's explicit instruction not to fabricate metrics.
import { useEffect, useState } from 'react';
import { api } from './api/client.js';

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

function fmtMoney(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—';
}

function DashboardTile({ title, children, planned = false }) {
  return (
    <div className="settings-section dashboard-tile">
      <h3>
        {title}
        {planned && <span className="dashboard-planned-badge">Planned</span>}
      </h3>
      {children}
    </div>
  );
}

function currentMonthRange() {
  const now = new Date();
  const to = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const fromDate = new Date(now.getFullYear(), now.getMonth() - 5, 1);
  const from = `${fromDate.getFullYear()}-${String(fromDate.getMonth() + 1).padStart(2, '0')}`;
  return { from, to };
}

export default function DashboardScreen({ session, settings, isSuperAdminUser }) {
  const tenantId = settings?.tenantId || session?.user?.tenant_id || '';
  const storeId = session?.user?.roles?.[0]?.store_id || settings?.storeId || '';

  const [kpi, setKpi] = useState(null);
  const [kpiError, setKpiError] = useState('');
  const [kpiLoading, setKpiLoading] = useState(true);

  const [nonMoving, setNonMoving] = useState(null);
  const [nonMovingError, setNonMovingError] = useState('');

  const [sync, setSync] = useState(null);
  const [syncError, setSyncError] = useState('');

  const [activity, setActivity] = useState(null);
  const [activityError, setActivityError] = useState('');

  useEffect(() => {
    if (!tenantId) { setKpiLoading(false); return; }
    const { from, to } = currentMonthRange();
    setKpiLoading(true);
    api.procurementDashboard(tenantId, from, to, session)
      .then((d) => setKpi(d?.kpi || null))
      .catch((e) => setKpiError(e.message))
      .finally(() => setKpiLoading(false));
  }, [tenantId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!tenantId || !storeId) return;
    api.nonMovingTotals(tenantId, storeId, session)
      .then(setNonMoving)
      .catch((e) => setNonMovingError(e.message));
  }, [tenantId, storeId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isSuperAdminUser) return;
    api.syncLiveStatus(session).then(setSync).catch((e) => setSyncError(e.message));
  }, [isSuperAdminUser]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isSuperAdminUser) return;
    api.recentActivity(5, session).then(setActivity).catch((e) => setActivityError(e.message));
  }, [isSuperAdminUser]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="screen-panel dashboard-screen">
      <ScreenHeader title="Dashboard" subtitle="A unified view across procurement, inventory and operations." />

      <div className="dashboard-grid">
        <DashboardTile title="Procurement Overview">
          {!tenantId ? (
            <p className="hint">No tenant selected.</p>
          ) : kpiLoading ? (
            <p className="hint">Loading…</p>
          ) : kpiError ? (
            <p className="status error">{kpiError}</p>
          ) : kpi ? (
            <div className="dashboard-kpi-row">
              <div className="dashboard-kpi"><span>Purchase (6mo)</span><strong>{fmtMoney(kpi.Purchase)}</strong></div>
              <div className="dashboard-kpi"><span>Sales (6mo)</span><strong>{fmtMoney(kpi.Sales)}</strong></div>
              <div className="dashboard-kpi"><span>Gross Profit</span><strong>{kpi.GPPercent}%</strong></div>
            </div>
          ) : (
            <p className="hint">No data for this period.</p>
          )}
        </DashboardTile>

        <DashboardTile title="Pending Orders">
          {!tenantId ? (
            <p className="hint">No tenant selected.</p>
          ) : kpiLoading ? (
            <p className="hint">Loading…</p>
          ) : kpi ? (
            <div className="dashboard-kpi-row">
              <div className="dashboard-kpi"><span>Pending invoices</span><strong>{fmtMoney(kpi.PendingInvoices)}</strong></div>
              <div className="dashboard-kpi"><span>Pending amount</span><strong>{fmtMoney(kpi.PendingAmount)}</strong></div>
            </div>
          ) : (
            <p className="hint">No data for this period.</p>
          )}
        </DashboardTile>

        <DashboardTile title="Sales Summary">
          {!tenantId ? (
            <p className="hint">No tenant selected.</p>
          ) : kpiLoading ? (
            <p className="hint">Loading…</p>
          ) : kpi ? (
            <div className="dashboard-kpi-row">
              <div className="dashboard-kpi"><span>Closing stock</span><strong>{fmtMoney(kpi.ClosingStock)}</strong></div>
              <div className="dashboard-kpi"><span>Gross profit</span><strong>{fmtMoney(kpi.GP)}</strong></div>
            </div>
          ) : (
            <p className="hint">No data for this period.</p>
          )}
        </DashboardTile>

        <DashboardTile title="Non-Moving Stock Alerts">
          {!tenantId || !storeId ? (
            <p className="hint">No store selected.</p>
          ) : nonMovingError ? (
            <p className="status error">{nonMovingError}</p>
          ) : nonMoving ? (
            <div className="dashboard-kpi-row">
              <div className="dashboard-kpi"><span>Non-moving value</span><strong>{fmtMoney(nonMoving.nm_value)}</strong></div>
              <div className="dashboard-kpi"><span>Share of stock</span><strong>{nonMoving.nm_pct}%</strong></div>
              <div className="dashboard-kpi"><span>Items</span><strong>{nonMoving.nm_items}</strong></div>
            </div>
          ) : (
            <p className="hint">Loading…</p>
          )}
        </DashboardTile>

        <DashboardTile title="Supplier Stock Status" planned>
          <p className="hint">No lightweight tenant-wide summary endpoint exists yet for this widget (only the full per-product Supplier Stock Analysis grid). Carried forward as a known gap, not fabricated here.</p>
        </DashboardTile>

        <DashboardTile title="Inventory Summary" planned>
          <p className="hint">No lightweight summary endpoint exists yet for this widget (only per-product Stock Availability listings). Carried forward as a known gap, not fabricated here.</p>
        </DashboardTile>

        {isSuperAdminUser && (
          <DashboardTile title="Sync Status">
            {syncError ? (
              <p className="status error">{syncError}</p>
            ) : sync === null ? (
              <p className="hint">Loading…</p>
            ) : sync.length === 0 ? (
              <p className="status ok">All stores synced — nothing running right now.</p>
            ) : (
              <ul className="dashboard-list">
                {sync.map((row) => (
                  <li key={row.execution_id}>{row.store_name || row.store_code || row.store_id}: {row.execution_status}</li>
                ))}
              </ul>
            )}
          </DashboardTile>
        )}

        {isSuperAdminUser && (
          <DashboardTile title="Recent Activity">
            {activityError ? (
              <p className="status error">{activityError}</p>
            ) : activity === null ? (
              <p className="hint">Loading…</p>
            ) : activity.items.length === 0 ? (
              <p className="hint">No recent activity.</p>
            ) : (
              <ul className="dashboard-list">
                {activity.items.map((item) => (
                  <li key={item.log_id}>
                    <strong>{item.actor_name || item.actor_role}</strong> — {item.action}
                    {item.target_label ? ` (${item.target_label})` : ''}
                  </li>
                ))}
              </ul>
            )}
          </DashboardTile>
        )}
      </div>
    </section>
  );
}
