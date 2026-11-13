// NEXORA MEDIQ Phase 6C: Masters > User Management.
// Standalone module (same pattern as SchemaSyncPage.jsx): cannot import
// from App.jsx (circular import), so its own tiny ScreenHeader is
// duplicated rather than shared -- consistent with the existing convention.
//
// This screen is reachable only via the ERP sidebar's Administration group,
// which itself only shows to a session navItems already lets through --
// but every mutation here ALSO goes through the backend's
// require_super_admin gate (added in 35c6018) regardless of what this
// screen shows or hides, per Phase 6 S6 rule 4 ("hidden menus must never
// be treated as security enforcement").
import { useEffect, useMemo, useState } from 'react';
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

const EMPTY_FORM = { username: '', full_name: '', password: '' };

function UserEditDialog({ user, onClose, onSaved, session }) {
  const isNew = !user;
  const [form, setForm] = useState(() => (
    user ? { username: user.username, full_name: user.full_name, password: '' } : { ...EMPTY_FORM }
  ));
  const [status, setStatus] = useState({ state: 'idle', message: '' });

  async function submit(event) {
    event.preventDefault();
    const username = form.username.trim();
    const fullName = form.full_name.trim();
    if (!username || !fullName) {
      setStatus({ state: 'error', message: 'Username and full name are required.' });
      return;
    }
    if (isNew && !form.password.trim()) {
      setStatus({ state: 'error', message: 'Password is required for a new user.' });
      return;
    }
    setStatus({ state: 'loading', message: isNew ? 'Creating…' : 'Saving…' });
    try {
      if (isNew) {
        await api.createUser({ username, full_name: fullName, password: form.password }, session);
      } else {
        await api.updateUser(user.user_id, { username, full_name: fullName }, session);
      }
      onSaved();
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <form className="modal-card" onSubmit={submit}>
        <h3>{isNew ? 'Create user' : `Edit ${user.username}`}</h3>
        <label>
          Username
          <input
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            autoFocus
          />
        </label>
        <label>
          Full name
          <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </label>
        {isNew && (
          <label>
            Password
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </label>
        )}
        {status.state === 'error' && <p className="status error">{status.message}</p>}
        <div className="action-row">
          <button type="submit" className="primary-button" disabled={status.state === 'loading'}>
            {status.state === 'loading' ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="secondary-button" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </div>
  );
}

export default function UserManagementScreen({ session }) {
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null); // null = closed, {} = new, user row = edit
  const [actionError, setActionError] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const rows = await api.listUsers({ search: search || undefined, status: statusFilter || undefined }, session);
      setUsers(Array.isArray(rows) ? rows : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [search, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  async function toggleActive(user) {
    setActionError('');
    try {
      await api.setUserStatus(user.user_id, !user.is_active, session);
      load();
    } catch (e) {
      // The backend's last-superadmin guard (35c6018) surfaces here as a 409
      // with a clear message -- shown as-is, not swallowed.
      setActionError(e.message);
    }
  }

  const rows = useMemo(() => users, [users]);

  return (
    <section className="screen-panel">
      <ScreenHeader title="User Management" subtitle="Create, edit and activate the accounts that can sign in to NEXORA MEDIQ." />

      <div className="toolbar-row">
        <input
          placeholder="Search username or name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ maxWidth: 280 }}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <button type="button" className="primary-button" onClick={() => setEditing({})}>
          + New user
        </button>
      </div>

      {actionError && <p className="status error">{actionError}</p>}
      {error && <p className="status error">{error}</p>}

      <div className="settings-section">
        {loading ? (
          <p className="hint">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="hint">No users match this filter.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Full name</th>
                <th>Tenant</th>
                <th>Stores</th>
                <th>Roles</th>
                <th>Status</th>
                <th>Last login</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.user_id}>
                  <td>{u.username}</td>
                  <td>{u.full_name}</td>
                  <td>{u.tenant_name || '—'}</td>
                  <td>{u.store_count}</td>
                  <td>{u.role_count}</td>
                  <td>
                    <span className={`status ${u.is_active ? 'ok' : 'error'}`}>
                      {u.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>{u.last_login ? new Date(u.last_login).toLocaleString() : '—'}</td>
                  <td className="action-row">
                    <button type="button" className="link-button" onClick={() => setEditing(u)}>Edit</button>
                    <button type="button" className="link-button" onClick={() => toggleActive(u)}>
                      {u.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing !== null && (
        <UserEditDialog
          user={editing.user_id ? editing : null}
          session={session}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </section>
  );
}
