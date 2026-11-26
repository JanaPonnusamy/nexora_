import React, { useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { BrandLockup } from '../components/BrandLockup.jsx';
import { Icon } from '../ui/icons.jsx';
import { Icon3D } from '../ui/icons3d.jsx';
import { useAuth } from '../contexts/AuthContext.jsx';
import { visibleNavGroups } from '../navigation/access.js';
import { isNavItemEnabled, statusLabel } from '../navigation/navConfig.js';
import { loadOpenGroups, saveOpenGroups } from './sidebarState.js';

function groupHasActive(group, pathname) {
  return group.items.some((item) => item.path === pathname);
}

export function Sidebar({ collapsed, onToggle }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const groups = visibleNavGroups(user);

  // Initialize ONCE from persisted storage (falling back to "all open").
  // Must not be recomputed on route changes — that was the bug: an
  // earlier version re-derived this via useMemo keyed on [pathname, groups],
  // which silently discarded the user's manual collapse choices on every
  // navigation. Now it is only ever mutated by explicit user toggles below.
  const [openGroups, setOpenGroups] = useState(() => {
    const persisted = loadOpenGroups();
    if (persisted) return persisted;
    const open = {};
    groups.forEach((group) => {
      open[group.id] = true;
    });
    return open;
  });

  // Accordion: opening a group closes every other one, so only one sublist
  // is ever expanded at a time (multiple open groups made the sidebar jump
  // around while scrolling).
  function toggleGroup(id) {
    setOpenGroups((prev) => {
      const wasOpen = prev[id] !== false;
      const next = {};
      groups.forEach((group) => {
        next[group.id] = group.id === id ? !wasOpen : false;
      });
      saveOpenGroups(next);
      return next;
    });
  }

  const name = user?.first_name || user?.username || 'Signed in';
  const handle = user?.username ? `@${user.username}` : '';

  async function handleLogout() {
    await logout();
  }

  return (
    <nav className={`ntm-sidebar${collapsed ? ' is-collapsed' : ''}`} aria-label="Primary">
      <div className="ntm-sidebar__brand">
        <BrandLockup variant={collapsed ? 'mark' : 'lockup'} />
      </div>
      <ul className="ntm-sidebar__groups">
        {groups.map((group) => {
          // In collapsed mode every group is shown as an icon rail so a
          // user can reach ANY item while collapsed, not just the group
          // that happens to contain the active route.
          const expanded = collapsed ? true : openGroups[group.id] !== false;
          const single = group.items.length === 1 && group.items[0].label === group.label;
          const hasActive = groupHasActive(group, pathname);
          const firstEnabled = group.items.find((item) => isNavItemEnabled(item));
          return (
            <li key={group.id} className="ntm-sidebar__group">
              {!single ? (
                <div className={`ntm-sidebar__group-row${collapsed && hasActive ? ' is-active-group' : ''}`}>
                  <button
                    type="button"
                    className="ntm-sidebar__group-toggle"
                    onClick={() => {
                      if (!collapsed && firstEnabled) {
                        setOpenGroups((prev) => {
                          const next = {};
                          groups.forEach((g) => {
                            next[g.id] = g.id === group.id;
                          });
                          saveOpenGroups(next);
                          return next;
                        });
                        navigate(firstEnabled.path);
                        return;
                      }
                      if (!collapsed) toggleGroup(group.id);
                    }}
                    title={group.label}
                  >
                    <Icon3D name={group.icon} size={collapsed ? 24 : 22} />
                    {!collapsed ? <span>{group.label}</span> : null}
                  </button>
                  {!collapsed ? (
                    <button
                      type="button"
                      className="ntm-sidebar__chevron-btn"
                      aria-expanded={expanded}
                      aria-label={`${expanded ? 'Collapse' : 'Expand'} ${group.label}`}
                      onClick={() => toggleGroup(group.id)}
                    >
                      <Icon
                        name="chevron"
                        size={12}
                        className={`ntm-sidebar__chevron${expanded ? ' is-open' : ''}`}
                      />
                    </button>
                  ) : null}
                </div>
              ) : null}
              {(expanded || single) && (
                <ul className="ntm-sidebar__list">
                  {group.items.map((item) => {
                    const enabled = isNavItemEnabled(item);
                    const className = ({ isActive }) =>
                      `ntm-sidebar__link${isActive ? ' is-active' : ''}`;
                    const tooltip = single || item.label === group.label
                      ? item.label
                      : `${group.label} ▸ ${item.label}`;
                    const inner = (
                      <>
                        {single
                          ? <Icon3D name={item.icon || group.icon} size={collapsed ? 24 : 22} />
                          : <Icon name={item.icon || group.icon} />}
                        {!collapsed ? <span className="ntm-sidebar__label">{item.label}</span> : null}
                        {!collapsed && !enabled ? (
                          <em className="ntm-sidebar__badge">{statusLabel(item.status)}</em>
                        ) : null}
                      </>
                    );
                    return (
                      <React.Fragment key={item.id}>
                        {/* Sub-section header within a single top-level group (currently
                            only "System & Administration": Synchronization / Administration).
                            Not a new nav level — purely a visual label, collapsed mode hides
                            it like other text so icon-only reachability is unaffected. */}
                        {item.sectionLabel && !collapsed ? (
                          <li className="ntm-sidebar__section-label" aria-hidden="true">
                            {item.sectionLabel}
                          </li>
                        ) : null}
                        <li>
                          {enabled ? (
                            <NavLink to={item.path} className={className} title={tooltip}>
                              {inner}
                            </NavLink>
                          ) : (
                            <NavLink
                              to={item.path}
                              className={({ isActive }) =>
                                `ntm-sidebar__link ntm-sidebar__link--planned${isActive ? ' is-active' : ''}`
                              }
                              title={`${tooltip} — planned`}
                            >
                              {inner}
                            </NavLink>
                          )}
                        </li>
                      </React.Fragment>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      <div className="ntm-sidebar__footer">
        <button
          type="button"
          className="ntm-sidebar__user"
          title={handle ? `${name} (${handle})` : name}
          onClick={handleLogout}
        >
          <span className="ntm-avatar" aria-hidden="true">
            {(name || 'N').slice(0, 1).toUpperCase()}
          </span>
          {!collapsed ? (
            <span className="ntm-sidebar__user-meta">
              <strong>{name}</strong>
              {handle ? <em>{handle}</em> : null}
            </span>
          ) : null}
          {!collapsed ? <Icon name="logout" size={14} className="ntm-sidebar__logout-icon" /> : null}
        </button>
        <button
          type="button"
          className="ntm-sidebar__collapse"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <Icon name="panel" />
          {!collapsed ? <span>Collapse</span> : null}
        </button>
      </div>
    </nav>
  );
}
