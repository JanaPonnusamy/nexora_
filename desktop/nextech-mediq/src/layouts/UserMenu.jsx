import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../ui/icons.jsx';
import { useAuth } from '../contexts/AuthContext.jsx';
import { visibleNavItems } from '../navigation/access.js';

export function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const canOpenSettings = visibleNavItems(user).some((item) => item.id === 'settings');
  const name = user?.first_name || user?.username || 'Signed in';
  const handle = user?.username ? `@${user.username}` : '';

  async function signOut() {
    await logout();
    setOpen(false);
  }

  return (
    <div className="ntm-menu">
      <button
        type="button"
        className="ntm-user-trigger"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="ntm-avatar" aria-hidden="true">
          {(name || 'N').slice(0, 1).toUpperCase()}
        </span>
        <span className="ntm-user-trigger__meta">
          <strong>{name}</strong>
          {handle ? <em>{handle}</em> : null}
        </span>
        <Icon name="chevron" size={14} />
      </button>
      {open ? (
        <div className="ntm-popover" role="menu">
          {canOpenSettings ? (
            <button type="button" role="menuitem" onClick={() => { setOpen(false); navigate('/settings'); }}>
              <Icon name="settings" size={14} /> Settings
            </button>
          ) : null}
          <button type="button" role="menuitem" onClick={signOut}>
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
