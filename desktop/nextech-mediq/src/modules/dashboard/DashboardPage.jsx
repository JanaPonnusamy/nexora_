import React from 'react';
import { Link } from 'react-router-dom';
import { PageLayout } from '../../layouts/PageLayout.jsx';
import { Icon } from '../../ui/icons.jsx';
import { Icon3D } from '../../ui/icons3d.jsx';
import bannerArt from '../../assets/ai/dashboard-banner.webp';
import { isNavItemEnabled, statusLabel } from '../../navigation/navConfig.js';
import { visibleNavGroups, visibleNavItems } from '../../navigation/access.js';
import { useAuth } from '../../contexts/AuthContext.jsx';

export function DashboardPage() {
  const { user, tenantId, storeName } = useAuth();
  const greeting = user?.first_name || user?.username || 'Operator';
  const visible = visibleNavItems(user);
  const groups = visibleNavGroups(user);
  const readyCount = visible.filter(isNavItemEnabled).length;
  const plannedCount = visible.filter((item) => !isNavItemEnabled(item)).length;

  return (
    <PageLayout title="Dashboard">
      <section className="ntm-dashboard__banner" style={{ backgroundImage: `url(${bannerArt})` }}>
        <p className="ntm-dashboard__ai"><Icon name="spark" size={12} /> AI-Powered Workspace</p>
        <h2 className="ntm-dashboard__hello">Welcome back, {greeting}.</h2>
        <p className="ntm-dashboard__sub">Inventory, procurement and supplier intelligence across every branch.</p>
      </section>
      <div className="ntm-card-grid">
        <article className="ntm-card">
          <h2>Workspace</h2>
          <p className="ntm-metric">{readyCount}</p>
          <p className="ntm-card__hint">Modules currently reachable in the shell</p>
        </article>
        <article className="ntm-card">
          <h2>Planned</h2>
          <p className="ntm-metric">{plannedCount}</p>
          <p className="ntm-card__hint">Destinations reserved, not implemented</p>
        </article>
        <article className="ntm-card">
          <h2>Session</h2>
          <p className="ntm-metric ntm-metric--text">{storeName || (tenantId ? 'Tenant selected' : 'No tenant')}</p>
          <p className="ntm-card__hint">Tenant and store come from the login and the directory the server returns for this session.</p>
        </article>
      </div>

      <h2 className="ntm-section-title">Module map</h2>
      <div className="ntm-module-map">
        {groups.map((group) => (
          <section key={group.id} className="ntm-card ntm-card--list">
            <header>
              <Icon3D name={group.icon} size={30} />
              <h3>{group.label}</h3>
            </header>
            <ul>
              {group.items.map((item) => (
                <li key={item.id}>
                  <Link to={item.path}>
                    <span>{item.label}</span>
                    <em className={`ntm-status-chip ntm-status-chip--${item.status}`}>{statusLabel(item.status)}</em>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </PageLayout>
  );
}
