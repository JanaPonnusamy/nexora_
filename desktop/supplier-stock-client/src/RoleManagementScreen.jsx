// NEXORA MEDIQ Phase 6D: Masters > Role Management + Permission Management.
// Same standalone-module pattern as SchemaSyncPage.jsx/UserManagementScreen.jsx.
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

function RoleEditDialog({ role, onClose, onSaved, session }) {
  const isNew = !role;
  const [form, setForm] = useState(() => (
    role ? { role_name: role.role_name, description: role.description || '' } : { role_name: '', description: '' }
  ));
  const [status, setStatus] = useState({ state: 'idle', message: '' });

  async function submit(event) {
    event.preventDefault();
    const roleName = form.role_name.trim();
    if (!roleName) {
      setStatus({ state: 'error', message: 'Role name is required.' });
      return;
    }
    setStatus({ state: 'loading', message: 'Saving…' });
    try {
      const payload = { role_name: roleName, description: form.description.trim() || null };
      if (isNew) await api.createRole(payload, session);
      else await api.updateRole(role.role_id, payload, session);
      onSaved();
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <form className="modal-card" onSubmit={submit}>
        <h3>{isNew ? 'Create role' : `Edit ${role.role_name}`}</h3>
        <label>
          Role name
          <input
            value={form.role_name}
            onChange={(e) => setForm({ ...form, role_name: e.target.value })}
            autoFocus
          />
        </label>
        <label>
          Description
          <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </label>
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

const ACTIONS = [
  { key: 'can_view', label: 'View' },
  { key: 'can_create', label: 'Create' },
  { key: 'can_edit', label: 'Edit' },
  { key: 'can_delete', label: 'Delete' },
  { key: 'can_export', label: 'Export' },
];

function PermissionMatrixDialog({ role, onClose, session }) {
  const [matrix, setMatrix] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(null); // module_id currently saving, or null

  async function load() {
    setLoading(true);
    setError('');
    try {
      const roleMatrix = await api.getRolePermissions(role.role_id, session);
      setMatrix(roleMatrix);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function setFlag(mod, actionKey, value) {
    setSaving(mod.module_id);
    setError('');
    const nextFlags = ACTIONS.reduce((acc, a) => {
      acc[a.key] = a.key === actionKey ? value : Boolean(mod[a.key]);
      return acc;
    }, {});
    try {
      const updated = await api.setRolePermissions(role.role_id, mod.module_id, nextFlags, session);
      setMatrix(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-card" style={{ width: 'min(760px, 100%)' }}>
        <h3>Permissions — {role.role_name}</h3>
        {error && <p className="status error">{error}</p>}
        {loading ? (
          <p className="hint">Loading…</p>
        ) : !matrix || !matrix.modules?.length ? (
          <p className="hint">No module permissions are seeded for this role yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Module</th>
                {ACTIONS.map((a) => <th key={a.key}>{a.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {matrix.modules.map((mod) => (
                <tr key={mod.module_id}>
                  <td>{mod.module_name}</td>
                  {ACTIONS.map((a) => (
                    <td key={a.key}>
                      <input
                        type="checkbox"
                        checked={Boolean(mod[a.key])}
                        disabled={saving === mod.module_id}
                        onChange={(e) => setFlag(mod, a.key, e.target.checked)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="action-row">
          <button type="button" className="secondary-button" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

export default function RoleManagementScreen({ session }) {
  const [roles, setRoles] = useState([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);
  const [permissionsFor, setPermissionsFor] = useState(null);
  const [actionError, setActionError] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const rows = await api.listRoles({ search: search || undefined, status: statusFilter || undefined }, session);
      setRoles(Array.isArray(rows) ? rows : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [search, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  async function toggleActive(role) {
    setActionError('');
    try {
      await api.setRoleStatus(role.role_id, !role.is_active, session);
      load();
    } catch (e) {
      // Surfaces the backend's last-active-superadmin 409 as-is (35c6018).
      setActionError(e.message);
    }
  }

  const rows = useMemo(() => roles, [roles]);

  return (
    <section className="screen-panel">
      <ScreenHeader title="Role Management" subtitle="Create roles and manage which modules each one can view, create, edit, delete or export." />

      <div className="toolbar-row">
        <input
          placeholder="Search role name…"
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
          + New role
        </button>
      </div>

      {actionError && <p className="status error">{actionError}</p>}
      {error && <p className="status error">{error}</p>}

      <div className="settings-section">
        {loading ? (
          <p className="hint">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="hint">No roles match this filter.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Role name</th>
                <th>Description</th>
                <th>Assigned users</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.role_id}>
                  <td>{r.role_name}</td>
                  <td>{r.description || '—'}</td>
                  <td>{r.assigned_users}</td>
                  <td>
                    <span className={`status ${r.is_active ? 'ok' : 'error'}`}>
                      {r.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="action-row">
                    <button type="button" className="link-button" onClick={() => setPermissionsFor(r)}>Permissions</button>
                    <button type="button" className="link-button" onClick={() => setEditing(r)}>Edit</button>
                    <button type="button" className="link-button" onClick={() => toggleActive(r)}>
                      {r.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing !== null && (
        <RoleEditDialog
          role={editing.role_id ? editing : null}
          session={session}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
      {permissionsFor && (
        <PermissionMatrixDialog role={permissionsFor} session={session} onClose={() => setPermissionsFor(null)} />
      )}
    </section>
  );
}
