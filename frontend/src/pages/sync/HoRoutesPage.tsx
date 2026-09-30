import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { hoRouteService, type HoRoute, type HoRouteInput } from '../../services/hoRouteService'

const EMPTY: HoRouteInput = { label: '', url: '', route_order: 100, is_active: true }

export default function HoRoutesPage() {
  const [routes, setRoutes] = useState<HoRoute[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState<HoRouteInput>(EMPTY)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setRoutes(await hoRouteService.list())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load routes')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const run = async (fn: () => Promise<HoRoute[]>) => {
    setBusy(true)
    setError(null)
    try {
      setRoutes(await fn())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const addRoute = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.label.trim() || !form.url.trim()) return
    await run(() => hoRouteService.create(form))
    setForm(EMPTY)
  }

  return (
    <div className="container-fluid px-0">
      <PageHeader
        title="HO Routes"
        breadcrumb={['Sync', 'HO Routes']}
      />

      <div className="alert alert-info py-2 small">
        <i className="bi bi-info-circle me-1" aria-hidden="true" />
        Agents and desktop clients pull this list every cycle and cache it, then fail over across
        it automatically. <strong>To migrate HO:</strong> add the new server's URL here while the
        current HO is still up — every store learns it and switches over when the old HO goes down.
        (This propagates the URL only; the new HO must already hold the platform data.)
      </div>

      {error && <div className="alert alert-danger py-2">{error}</div>}

      <div className="card mb-3">
        <div className="card-body">
          <form className="row g-2 align-items-end" onSubmit={addRoute}>
            <div className="col-sm-2">
              <label className="form-label small mb-1">Label</label>
              <input
                className="form-control form-control-sm"
                value={form.label}
                placeholder="LAN / STATIC / DOMAIN"
                onChange={(e) => setForm({ ...form, label: e.target.value })}
              />
            </div>
            <div className="col-sm-5">
              <label className="form-label small mb-1">URL</label>
              <input
                className="form-control form-control-sm"
                value={form.url}
                placeholder="http://new-ho:8000"
                onChange={(e) => setForm({ ...form, url: e.target.value })}
              />
            </div>
            <div className="col-sm-2">
              <label className="form-label small mb-1">Order</label>
              <input
                type="number"
                className="form-control form-control-sm"
                value={form.route_order}
                onChange={(e) => setForm({ ...form, route_order: Number(e.target.value) })}
              />
            </div>
            <div className="col-sm-3">
              <button type="submit" className="btn btn-primary btn-sm w-100" disabled={busy}>
                <i className="bi bi-plus-lg me-1" aria-hidden="true" />
                Add route
              </button>
            </div>
          </form>
        </div>
      </div>

      <div className="card">
        <div className="card-body p-0">
          {loading ? (
            <div className="p-3 text-muted">Loading…</div>
          ) : (
            <table className="table table-sm mb-0 align-middle">
              <thead>
                <tr>
                  <th style={{ width: '10%' }}>Order</th>
                  <th style={{ width: '15%' }}>Label</th>
                  <th>URL</th>
                  <th style={{ width: '12%' }}>Active</th>
                  <th style={{ width: '10%' }} className="text-end">Delete</th>
                </tr>
              </thead>
              <tbody>
                {routes.map((r) => (
                  <tr key={r.route_id} className={r.is_active ? '' : 'text-muted'}>
                    <td>{r.route_order}</td>
                    <td>{r.label}</td>
                    <td><code>{r.url}</code></td>
                    <td>
                      <div className="form-check form-switch mb-0">
                        <input
                          className="form-check-input"
                          type="checkbox"
                          checked={r.is_active}
                          disabled={busy}
                          onChange={() =>
                            run(() => hoRouteService.update(r.route_id, { is_active: !r.is_active }))
                          }
                        />
                      </div>
                    </td>
                    <td className="text-end">
                      <button
                        type="button"
                        className="btn btn-outline-danger btn-sm"
                        disabled={busy}
                        onClick={() => run(() => hoRouteService.remove(r.route_id))}
                      >
                        <i className="bi bi-trash" aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
                {!routes.length && (
                  <tr>
                    <td colSpan={5} className="text-muted p-3">No routes configured.</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
