import { useCallback, useEffect, useState } from 'react'
import { legacyOrderService } from '../../services/legacyOrderService'
import { ApiError } from '../../services/apiClient'
import { useAuth } from '../../hooks/useAuth'
import { isSuperAdmin } from '../label-export/labelExportAccess'
import type { LegacyStore, MessageSetting, MessageType, OrderEntryAutomation } from '../../types/legacyOrder'
import '../legacy-order/pm-order-entry.css'

const MESSAGE_TYPE_LABEL: Record<MessageType, string> = {
  ORDER_GENERATED: 'Order generated',
  STOCK_LIST: 'Stock list',
  TIME_LIST: 'Time list',
  STOCK_READY: 'Stock ready',
  ENTRY_READY: 'Entry ready',
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return fallback
}

/** Admin-only: Order Entry automation settings, moved off the PM-facing
 *  screen entirely per owner ruling 2026-11-24 ("pm user dont want to know
 *  exactly what they doing ... that must fix admin with store settings page
 *  automation button no need here"). Extracted from the former
 *  OrderEntryAutomationPanel that used to live inline on PmOrderEntryPage.
 *  Same backend endpoints (GET/PUT .../automation, .../message-settings) --
 *  no server changes. */
export default function OrderAutomationPage() {
  const { user } = useAuth()
  const admin = isSuperAdmin(user)

  const [stores, setStores] = useState<LegacyStore[]>([])
  const [store, setStore] = useState('')
  const [automation, setAutomation] = useState<OrderEntryAutomation | null>(null)
  const [messages, setMessages] = useState<MessageSetting[]>([])
  const [targetDrafts, setTargetDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!admin) return
    legacyOrderService
      .listStores(true)
      .then((rows) => {
        setStores(rows)
        setStore((cur) => cur || rows[0]?.store_name || '')
      })
      .catch((err: unknown) => setError(errorMessage(err, 'Could not load stores.')))
  }, [admin])

  const load = useCallback(() => {
    if (!store) return
    setError('')
    Promise.all([legacyOrderService.getOrderEntryAutomation(store), legacyOrderService.getMessageSettings(store)])
      .then(([auto, msgs]) => {
        setAutomation(auto)
        setMessages(msgs)
        setTargetDrafts(
          Object.fromEntries(msgs.map((m) => [m.message_type, (m.targets || []).map((t) => t.name).join(', ')])),
        )
      })
      .catch((err: unknown) => setError(errorMessage(err, 'Could not load automation settings.')))
  }, [store])

  useEffect(() => {
    setAutomation(null)
    setMessages([])
    load()
  }, [load])

  const saveAutomation = async (patch: Partial<OrderEntryAutomation>) => {
    if (!automation) return
    setSaving(true)
    setError('')
    setNote('')
    try {
      const next = { ...automation, ...patch }
      const saved = await legacyOrderService.setOrderEntryAutomation(store, {
        automated_order_enabled: next.automated_order_enabled,
        production_mode: next.production_mode,
        min_delay_seconds: next.min_delay_seconds,
        max_delay_seconds: next.max_delay_seconds,
      })
      setAutomation(saved)
      setNote('Saved.')
    } catch (err) {
      setError(errorMessage(err, 'Could not save.'))
    } finally {
      setSaving(false)
    }
  }

  const saveMessage = async (messageType: MessageType, enabled: boolean) => {
    setSaving(true)
    setError('')
    setNote('')
    try {
      const names = (targetDrafts[messageType] || '')
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const targets = names.map((name) => ({ name, kind: 'contact' as const }))
      const saved = await legacyOrderService.setMessageSetting(store, messageType, { enabled, targets })
      setMessages((cur) => cur.map((m) => (m.message_type === messageType ? saved : m)))
      setNote('Saved.')
    } catch (err) {
      setError(errorMessage(err, 'Could not save.'))
    } finally {
      setSaving(false)
    }
  }

  if (!admin) {
    return (
      <section className="pm-order-entry">
        <div className="status-line error">Order Automation settings are restricted to platform admins.</div>
      </section>
    )
  }

  return (
    <section className="pm-order-entry">
      <header className="poe-screen-head">
        <div>
          <h2>Order Automation</h2>
          <p>Automated Order Entry settings and WhatsApp message types, per store. Not visible to PM users.</p>
        </div>
        <div className="poe-tools">
          {stores.length > 1 && (
            <select aria-label="Store" value={store} onChange={(e) => setStore(e.target.value)}>
              {stores.map((s) => (
                <option key={s.store_name} value={s.store_name}>
                  {s.display_name || s.store_name}
                </option>
              ))}
            </select>
          )}
        </div>
      </header>

      {error && <div className="status-line error">{error}</div>}
      {note && <div className="status-line poe-ok">{note}</div>}

      {!automation ? (
        <p className="poe-muted">Loading…</p>
      ) : (
        <>
          <section className="poe-card">
            <header className="poe-card-head">
              <h3>Automation · {store}</h3>
            </header>
            <div className="poe-form">
              <label className="poe-checkbox">
                <input
                  type="checkbox"
                  checked={!!automation.automated_order_enabled}
                  disabled={saving}
                  onChange={(e) => saveAutomation({ automated_order_enabled: e.target.checked })}
                />
                Automated order entry — queue a random settle delay (1–7 min) and auto-process the submitted
                bill/GRN instead of generating immediately.
              </label>
              <label className="poe-checkbox">
                <input
                  type="checkbox"
                  checked={!!automation.production_mode}
                  disabled={saving}
                  onChange={(e) => saveAutomation({ production_mode: e.target.checked })}
                />
                Production mode — send real WhatsApp notices (off = test mode, notices are logged only).
              </label>
              <div className="poe-form-row">
                <label>
                  <span>Min delay (sec)</span>
                  <input
                    type="number"
                    min={0}
                    value={automation.min_delay_seconds}
                    disabled={saving}
                    onChange={(e) =>
                      setAutomation((a) => (a ? { ...a, min_delay_seconds: Number(e.target.value) } : a))
                    }
                    onBlur={() => saveAutomation({})}
                  />
                </label>
                <label>
                  <span>Max delay (sec)</span>
                  <input
                    type="number"
                    min={0}
                    value={automation.max_delay_seconds}
                    disabled={saving}
                    onChange={(e) =>
                      setAutomation((a) => (a ? { ...a, max_delay_seconds: Number(e.target.value) } : a))
                    }
                    onBlur={() => saveAutomation({})}
                  />
                </label>
              </div>
            </div>
          </section>

          <section className="poe-card">
            <header className="poe-card-head">
              <h3>Message types</h3>
            </header>
            <div className="poe-tablewrap">
              <table className="poe-table">
                <thead>
                  <tr>
                    <th className="poe-left">Type</th>
                    <th>Enabled</th>
                    <th className="poe-left">Targets (comma-separated)</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {messages.map((m) => (
                    <tr key={m.message_type}>
                      <td className="poe-left">{MESSAGE_TYPE_LABEL[m.message_type] || m.message_type}</td>
                      <td>
                        <input
                          type="checkbox"
                          checked={!!m.enabled}
                          disabled={saving}
                          onChange={(e) => saveMessage(m.message_type, e.target.checked)}
                        />
                      </td>
                      <td className="poe-left">
                        <input
                          value={targetDrafts[m.message_type] || ''}
                          disabled={saving}
                          placeholder="Group or contact name"
                          onChange={(e) => setTargetDrafts((cur) => ({ ...cur, [m.message_type]: e.target.value }))}
                        />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={saving}
                          onClick={() => saveMessage(m.message_type, m.enabled)}
                        >
                          Save
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </section>
  )
}
