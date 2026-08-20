import { useCallback, useEffect, useMemo, useState } from 'react'
import type { PassGenRow, PassGenRowResult, PassGenStore } from '../../types/passGen'
import { passGenService } from '../../services/passGenService'
import './pass-gen.css'
import { FilterBar } from '../../design-system/components/FilterBar'

const MAX_DAYS_FIELD = 1295 // 2-char Base36 ceiling of the passcode format

let rowSeq = 0
function newRow(min = 13, max = 18): PassGenRow {
  rowSeq += 1
  return {
    row_id: `r${rowSeq}`,
    store_ids: [],
    min_days: min,
    max_days: max,
    order_yes: 1,
    compare_last_order: 0,
  }
}

function todayIso(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export default function PassGenPage() {
  const [stores, setStores] = useState<PassGenStore[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)

  // Shared across every row.
  const [orderNo, setOrderNo] = useState(1)
  const [targetDate, setTargetDate] = useState(todayIso())

  // Rows keep their values after generating — nothing here is ever reset.
  const [rows, setRows] = useState<PassGenRow[]>([newRow()])
  const [results, setResults] = useState<Record<string, PassGenRowResult>>({})

  const [showCodes, setShowCodes] = useState(false)

  const load = useCallback(() => {
    passGenService
      .listStores()
      .then(setStores)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load stores'))
  }, [])

  useEffect(load, [load])

  const unmapped = useMemo(() => stores.filter((s) => s.numeric_code === null), [stores])

  const patchRow = (rowId: string, patch: Partial<PassGenRow>) =>
    setRows((current) => current.map((r) => (r.row_id === rowId ? { ...r, ...patch } : r)))

  const toggleStore = (row: PassGenRow, storeId: string) => {
    const on = row.store_ids.includes(storeId)
    patchRow(row.row_id, {
      store_ids: on ? row.store_ids.filter((id) => id !== storeId) : [...row.store_ids, storeId],
    })
  }

  const generate = async (only?: PassGenRow) => {
    const target = only ? [only] : rows
    if (!target.length) return
    setBusy(true)
    setError(null)
    try {
      const response = await passGenService.generate({
        order_no: orderNo,
        target_date: targetDate,
        rows: target,
      })
      setResults((current) => {
        const next = { ...current }
        for (const row of response.rows) next[row.row_id] = row
        return next
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate passcodes')
    } finally {
      setBusy(false)
    }
  }

  const copy = async (key: string, text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(key)
    window.setTimeout(() => setCopied((c) => (c === key ? null : c)), 1200)
  }

  const copyAll = () => {
    const lines: string[] = []
    for (const row of rows) {
      const result = results[row.row_id]
      if (!result?.results.length) continue
      for (const r of result.results) {
        lines.push(`${r.store_code}\t${row.min_days}/${row.max_days}\t${r.passcode}`)
      }
    }
    if (lines.length) void copy('all', lines.join('\n'))
  }

  const saveCode = async (storeId: string, raw: string) => {
    const value = raw.trim() === '' ? null : Number(raw)
    if (value !== null && (Number.isNaN(value) || value < 0 || value > 99)) return
    try {
      setStores(await passGenService.setStoreCode(storeId, value))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save store code')
    }
  }

  return (
    <div className="pg-page">
      <div className="d-flex align-items-center justify-content-between mb-3">
        <div>
          <h1 className="h4 mb-1">Pass Gen</h1>
          <p className="text-secondary mb-0 small">
            Store passcodes for the ordering app. Rows keep their values, so you can generate again and again.
          </p>
        </div>
        <button className="btn btn-sm btn-outline-secondary" onClick={() => setShowCodes((v) => !v)}>
          <i className="bi bi-key me-1" />
          Store codes
        </button>
      </div>

      {error && (
        <div className="alert alert-danger py-2 small d-flex align-items-center justify-content-between">
          <span>{error}</span>
          <button className="btn btn-sm btn-outline-danger" onClick={load}>
            Retry
          </button>
        </div>
      )}

      {unmapped.length > 0 && (
        <div className="alert alert-warning py-2 small">
          No numeric passcode code for {unmapped.map((s) => s.store_code).join(', ')} — set one under
          <strong> Store codes</strong> or these stores are skipped.
        </div>
      )}

      {showCodes && (
        <table className="table table-sm align-middle pg-codes-table">
          <thead>
            <tr>
              <th>Store</th>
              <th>Name</th>
              <th>Numeric code</th>
            </tr>
          </thead>
          <tbody>
            {stores.map((store) => (
              <tr key={store.store_id}>
                <td className="fw-semibold">{store.store_code}</td>
                <td className="text-secondary small">{store.store_name}</td>
                <td>
                  <input
                    type="number"
                    className="form-control form-control-sm"
                    min={0}
                    max={99}
                    defaultValue={store.numeric_code ?? ''}
                    onBlur={(e) => void saveCode(store.store_id, e.target.value)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <FilterBar compact className="pg-toolbar" ariaLabel="Pass generation options">
        <div className="pg-field">
          <label htmlFor="pg-order-no">Order No</label>
          <input
            id="pg-order-no"
            type="number"
            className="form-control form-control-sm"
            style={{ width: '5rem' }}
            min={0}
            max={9}
            value={orderNo}
            onChange={(e) => setOrderNo(Math.min(9, Math.max(0, Number(e.target.value) || 0)))}
          />
        </div>
        <div className="pg-field">
          <label htmlFor="pg-date">Target Date</label>
          <input
            id="pg-date"
            type="date"
            className="form-control form-control-sm"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
          />
        </div>
        <div className="pg-toolbar-actions">
          <button className="btn btn-sm btn-outline-secondary" onClick={() => setRows((r) => [...r, newRow()])}>
            <i className="bi bi-plus-lg me-1" />
            Add row
          </button>
          <button className="btn btn-sm btn-outline-secondary" onClick={copyAll}>
            <i className="bi bi-clipboard me-1" />
            {copied === 'all' ? 'Copied' : 'Copy all'}
          </button>
          <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void generate()}>
            <i className="bi bi-key me-1" />
            Generate all rows
          </button>
        </div>
      </FilterBar>

      <div className="pg-rows">
        {rows.map((row) => {
          const result = results[row.row_id]
          return (
            <div className="pg-row" key={row.row_id}>
              <div className="pg-row-inputs">
                <div className="pg-field">
                  <label>Stores</label>
                  <div className="pg-chips">
                    <button
                      type="button"
                      className={`pg-chip ${row.store_ids.length === 0 ? 'is-on' : ''}`}
                      onClick={() => patchRow(row.row_id, { store_ids: [] })}
                    >
                      All
                    </button>
                    {stores.map((store) => (
                      <button
                        type="button"
                        key={store.store_id}
                        className={`pg-chip ${row.store_ids.includes(store.store_id) ? 'is-on' : ''}`}
                        disabled={store.numeric_code === null}
                        title={store.numeric_code === null ? 'No numeric code set' : store.store_name ?? ''}
                        onClick={() => toggleStore(row, store.store_id)}
                      >
                        {store.store_code}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="pg-field">
                  <label htmlFor={`min-${row.row_id}`}>Min days</label>
                  <input
                    id={`min-${row.row_id}`}
                    type="number"
                    className="form-control form-control-sm pg-days"
                    min={0}
                    max={MAX_DAYS_FIELD}
                    value={row.min_days}
                    onChange={(e) => patchRow(row.row_id, { min_days: Number(e.target.value) || 0 })}
                  />
                </div>
                <div className="pg-field">
                  <label htmlFor={`max-${row.row_id}`}>Max days</label>
                  <input
                    id={`max-${row.row_id}`}
                    type="number"
                    className="form-control form-control-sm pg-days"
                    min={0}
                    max={MAX_DAYS_FIELD}
                    value={row.max_days}
                    onChange={(e) => patchRow(row.row_id, { max_days: Number(e.target.value) || 0 })}
                  />
                </div>

                <div className="pg-field">
                  <label>Flags</label>
                  <div className="d-flex gap-3">
                    <div className="form-check mb-0">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        id={`ordy-${row.row_id}`}
                        checked={row.order_yes === 1}
                        onChange={(e) => patchRow(row.row_id, { order_yes: e.target.checked ? 1 : 0 })}
                      />
                      <label className="form-check-label small" htmlFor={`ordy-${row.row_id}`}>
                        Order Yes
                      </label>
                    </div>
                    <div className="form-check mb-0">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        id={`cmp-${row.row_id}`}
                        checked={row.compare_last_order === 1}
                        onChange={(e) =>
                          patchRow(row.row_id, { compare_last_order: e.target.checked ? 1 : 0 })
                        }
                      />
                      <label className="form-check-label small" htmlFor={`cmp-${row.row_id}`}>
                        Compare last order
                      </label>
                    </div>
                  </div>
                </div>

                <div className="pg-row-actions">
                  <button
                    className="btn btn-sm btn-outline-primary"
                    disabled={busy}
                    onClick={() => void generate(row)}
                  >
                    Generate
                  </button>
                  <button
                    className="btn btn-sm btn-outline-danger"
                    disabled={rows.length === 1}
                    onClick={() => {
                      setRows((current) => current.filter((r) => r.row_id !== row.row_id))
                      setResults((current) => {
                        const next = { ...current }
                        delete next[row.row_id]
                        return next
                      })
                    }}
                  >
                    <i className="bi bi-trash" />
                  </button>
                </div>
              </div>

              {result && (
                <div className="pg-results">
                  {result.results.map((r) => {
                    const key = `${row.row_id}:${r.store_id}`
                    return (
                      <div className="pg-result" key={key}>
                        <span className="pg-result-store">{r.store_code}</span>
                        <span className="pg-code">{r.passcode}</span>
                        <button
                          className="btn btn-sm btn-link p-0"
                          title="Copy"
                          onClick={() => void copy(key, r.passcode)}
                        >
                          <i className={`bi ${copied === key ? 'bi-check2' : 'bi-clipboard'}`} />
                        </button>
                      </div>
                    )
                  })}
                  {result.skipped.length > 0 && (
                    <span className="text-secondary small align-self-center">
                      Skipped {result.skipped.join(', ')} (no numeric code)
                    </span>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
