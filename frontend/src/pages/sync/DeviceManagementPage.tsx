import { useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import {
  deviceService,
  type Device,
  type EnrollmentCode,
} from '../../services/deviceService'
import { storeService } from '../../services/storeService'
import type { Store } from '../../types/store'

function timeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

export default function DeviceManagementPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [stores, setStores] = useState<Store[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [assignSel, setAssignSel] = useState<Record<string, string>>({})

  // --- enrollment-code generation (super-admin: mints a one-time code the
  // remote NMV-style device types into its Settings app to self-register) ---
  const [enrollStore, setEnrollStore] = useState('')
  const [ttlMinutes, setTtlMinutes] = useState(15)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [code, setCode] = useState<EnrollmentCode | null>(null)
  const [copied, setCopied] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, s] = await Promise.all([deviceService.list(), storeService.list()])
      setDevices(d)
      setStores(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load devices')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const storesById = useMemo(() => {
    const m = new Map<string, Store>()
    stores.forEach((s) => m.set(s.store_id, s))
    return m
  }, [stores])

  const activeStores = useMemo(() => stores.filter((s) => s.is_active), [stores])

  // Default the picker to NMV (the first remote store) if present, else the
  // first active store, once the list has loaded.
  useEffect(() => {
    if (enrollStore || !activeStores.length) return
    const nmv = activeStores.find((s) => (s.store_code || '').toUpperCase() === 'NMV')
    setEnrollStore(nmv?.store_code || activeStores[0].store_code)
  }, [activeStores, enrollStore])

  const generate = async () => {
    if (!enrollStore) return
    setGenerating(true)
    setGenError(null)
    setCode(null)
    setCopied(false)
    try {
      const result = await deviceService.generateEnrollmentCode(
        enrollStore,
        Math.round(ttlMinutes * 60),
      )
      setCode(result)
    } catch (e) {
      setGenError(e instanceof Error ? e.message : 'Failed to generate enrollment code')
    } finally {
      setGenerating(false)
    }
  }

  const copyCode = async () => {
    if (!code) return
    try {
      await navigator.clipboard.writeText(code.enrollment_code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      setGenError('Could not copy to clipboard — select and copy the code manually.')
    }
  }

  const act = async (deviceId: string, fn: () => Promise<unknown>) => {
    setBusyId(deviceId)
    setError(null)
    try {
      await fn()
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Store Agent Devices" breadcrumb={['Sync', 'Devices']} />

      <div className="alert alert-info py-2 small">
        <i className="bi bi-info-circle me-1" aria-hidden="true" />
        Machines that registered via the zero-config store-agent setup. Assign one or more stores to
        a device here — the agent picks them up automatically and syncs each. Revoke to immediately
        cut a lost/decommissioned machine's access.
      </div>

      {/* Enroll a new remote (NMV-style) device: mint a one-time code bound to a
          store. The device types it into its Settings app to self-register. */}
      <div className="card mb-3">
        <div className="card-body">
          <h2 className="h6 mb-1">
            <i className="bi bi-key me-1" aria-hidden="true" />
            Generate a device enrollment code
          </h2>
          <p className="small text-muted mb-3">
            For a remote store whose device self-enrolls (e.g. NMV). Pick the store, generate a
            one-time code, and type it into the device's Settings → “Enrollment code” → “Enroll
            device”. The code is bound to that store, single-use, and expires — it can only ever
            enroll the store you choose here.
          </p>

          <div className="d-flex flex-wrap gap-2 align-items-end">
            <div>
              <label className="form-label small mb-1" htmlFor="enroll-store">Store</label>
              <select
                id="enroll-store"
                className="form-select form-select-sm"
                style={{ minWidth: 240 }}
                value={enrollStore}
                disabled={generating || !activeStores.length}
                onChange={(e) => setEnrollStore(e.target.value)}
              >
                {!activeStores.length && <option value="">No active stores</option>}
                {activeStores.map((s) => (
                  <option key={s.store_id} value={s.store_code}>
                    {s.store_code} — {s.store_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="form-label small mb-1" htmlFor="enroll-ttl">Valid for (minutes)</label>
              <input
                id="enroll-ttl"
                type="number"
                min={5}
                max={1440}
                className="form-control form-control-sm"
                style={{ width: 140 }}
                value={ttlMinutes}
                disabled={generating}
                onChange={(e) => setTtlMinutes(Math.max(5, Math.min(1440, Number(e.target.value) || 15)))}
              />
            </div>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={generating || !enrollStore}
              onClick={() => void generate()}
            >
              {generating ? 'Generating…' : 'Generate code'}
            </button>
          </div>

          {genError && <div className="alert alert-danger py-2 mt-3 mb-0 small">{genError}</div>}

          {code && (
            <div className="alert alert-success mt-3 mb-0">
              <div className="small text-muted mb-1">
                One-time code for <strong>{code.store_code}</strong> — shown once, not retrievable
                again. Copy it now.
              </div>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <code className="fs-5 fw-bold user-select-all">{code.enrollment_code}</code>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => void copyCode()}>
                  <i className="bi bi-clipboard me-1" aria-hidden="true" />
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <div className="small text-muted mt-1">
                Expires {code.expires_at ? new Date(code.expires_at + 'Z').toLocaleString() : `in ${Math.round(code.expires_in_seconds / 60)} min`}
                {' · '}single-use · generating again replaces any previous unused code for this store.
              </div>
            </div>
          )}
        </div>
      </div>

      {error && <div className="alert alert-danger py-2">{error}</div>}

      {loading ? (
        <div className="card"><div className="card-body text-muted">Loading…</div></div>
      ) : !devices.length ? (
        <div className="card"><div className="card-body text-muted">No devices registered yet.</div></div>
      ) : (
        devices.map((d) => {
          const assigned = new Set(d.stores.map((s) => s.store_id))
          // Only offer ACTIVE, not-yet-assigned stores — inactive/test stores
          // are skipped by the agent anyway, so hiding them avoids mis-assigning.
          const assignable = stores.filter((s) => s.is_active && !assigned.has(s.store_id))
          const revoked = d.status !== 'active'
          return (
            <div className="card mb-3" key={d.device_id}>
              <div className="card-body">
                <div className="d-flex justify-content-between align-items-start flex-wrap gap-2">
                  <div>
                    <h2 className="h6 mb-1">
                      {d.machine_name || d.device_fingerprint}
                      <span className={`badge ms-2 ${revoked ? 'bg-danger' : 'bg-success'}`}>
                        {d.status}
                      </span>
                    </h2>
                    <div className="small text-muted">
                      <code>{d.device_fingerprint}</code> · {d.app_type || 'agent'}{' '}
                      {d.app_version ? `v${d.app_version}` : ''} · last seen {timeAgo(d.last_seen_at)}
                      {d.registered_by_username ? ` · by ${d.registered_by_username}` : ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-outline-danger btn-sm"
                    disabled={busyId === d.device_id || revoked}
                    onClick={() => act(d.device_id, () => deviceService.revoke(d.device_id))}
                  >
                    <i className="bi bi-slash-circle me-1" aria-hidden="true" />
                    Revoke
                  </button>
                </div>

                <hr className="my-2" />

                <div className="d-flex flex-wrap gap-2 align-items-center mb-2">
                  <span className="small text-muted me-1">Assigned stores:</span>
                  {d.stores.length ? (
                    d.stores.map((s) => (
                      <span key={s.store_id} className="badge bg-light text-dark border">
                        {s.store_code || storesById.get(s.store_id)?.store_code || s.store_id}
                        <button
                          type="button"
                          className="btn-close btn-close-sm ms-2"
                          style={{ fontSize: '0.6rem' }}
                          aria-label="Unassign"
                          disabled={busyId === d.device_id}
                          onClick={() =>
                            act(d.device_id, () =>
                              deviceService.unassignStore(d.device_id, s.store_id),
                            )
                          }
                        />
                      </span>
                    ))
                  ) : (
                    <span className="small text-muted fst-italic">none</span>
                  )}
                </div>

                <div className="d-flex gap-2 align-items-center" style={{ maxWidth: 480 }}>
                  <select
                    className="form-select form-select-sm"
                    value={assignSel[d.device_id] || ''}
                    disabled={busyId === d.device_id || revoked || !assignable.length}
                    onChange={(e) => setAssignSel({ ...assignSel, [d.device_id]: e.target.value })}
                  >
                    <option value="">Add a store…</option>
                    {assignable.map((s) => (
                      <option key={s.store_id} value={s.store_id}>
                        {s.store_code} — {s.store_name}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={busyId === d.device_id || revoked || !assignSel[d.device_id]}
                    onClick={() => {
                      const storeId = assignSel[d.device_id]
                      if (!storeId) return
                      act(d.device_id, () => deviceService.assignStore(d.device_id, storeId)).then(
                        () => setAssignSel({ ...assignSel, [d.device_id]: '' }),
                      )
                    }}
                  >
                    Assign
                  </button>
                </div>
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}
