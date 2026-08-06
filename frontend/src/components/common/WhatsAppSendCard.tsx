import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../services/apiClient'
import { whatsappService, type WhatsAppState } from '../../services/whatsappService'
import './whatsapp-send-card.css'

interface WhatsAppSendCardProps {
  disabled?: boolean
  title: string
  buttonLabel?: string
  defaultCaption: string
  buildFile: () => Promise<File>
}

export function WhatsAppSendCard({
  disabled = false,
  title,
  buttonLabel = 'Send to WhatsApp',
  defaultCaption,
  buildFile,
}: WhatsAppSendCardProps) {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<WhatsAppState | null>(null)
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [profileId, setProfileId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [phone, setPhone] = useState('')
  const [message, setMessage] = useState(defaultCaption)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    setMessage(defaultCaption)
  }, [defaultCaption])

  useEffect(() => {
    if (!open || state) return
    setLoading(true)
    void whatsappService
      .getState()
      .then((payload) => {
        setState(payload)
        const defaultProfile =
          payload.profiles.find((profile) => profile.profile_id === payload.capabilities.default_profile_id)
          ?? payload.profiles[0]
        if (defaultProfile) {
          setProfileId(defaultProfile.profile_id)
          setPhone(defaultProfile.default_phone || '')
        }
        const defaultTarget = payload.targets.find((target) => target.can_send && target.is_active)
        if (defaultTarget) {
          setTargetId(defaultTarget.target_id)
        }
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Unable to load WhatsApp profiles.')
      })
      .finally(() => setLoading(false))
  }, [open, state])

  const selectedProfile = useMemo(
    () => state?.profiles.find((profile) => profile.profile_id === profileId) ?? null,
    [profileId, state],
  )
  const availableTargets = useMemo(
    () => (state?.targets ?? []).filter((target) => target.can_send && target.is_active),
    [state],
  )
  const selectedTarget = useMemo(
    () => availableTargets.find((target) => target.target_id === targetId) ?? null,
    [availableTargets, targetId],
  )

  useEffect(() => {
    if (selectedProfile && !phone) {
      setPhone(selectedProfile.default_phone || '')
    }
  }, [selectedProfile, phone])

  useEffect(() => {
    if (selectedTarget) {
      setPhone(selectedTarget.target_kind === 'contact' ? selectedTarget.target_ref : '')
      setProfileId(selectedTarget.profile_id)
    }
  }, [selectedTarget])

  const send = async () => {
    if (!profileId) {
      setError('Choose a WhatsApp profile first.')
      return
    }
    setSending(true)
    setStatus('')
    setError('')
    try {
      const file = await buildFile()
      const result = selectedTarget
        ? await whatsappService.sendTargetFile(selectedTarget.target_id, message, file)
        : await whatsappService.sendFile(profileId, phone, message, file)
      setStatus(result.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to send this report to WhatsApp.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="wa-send">
      <button
        type="button"
        className="btn btn-outline-success btn-sm"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        <i className="bi bi-whatsapp" /> {buttonLabel}
      </button>

      {open && (
        <div className="wa-send__panel">
          <div className="wa-send__head">
            <h3>{title}</h3>
            <small>Choose a profile, target number, and caption.</small>
          </div>

          {loading && <div className="text-body-secondary">Loading WhatsApp profiles...</div>}
          {error && <div className="alert alert-danger mb-0">{error}</div>}
          {status && !error && <div className="alert alert-success mb-0">{status}</div>}

          {!loading && state && (
            <>
              <div className="wa-send__grid">
                <label className="form-label">
                  Saved target
                  <select
                    className="form-select"
                    value={targetId}
                    onChange={(event) => setTargetId(event.target.value)}
                  >
                    <option value="">Direct phone</option>
                    {availableTargets.map((target) => (
                      <option key={target.target_id} value={target.target_id}>
                        {target.target_name} ({target.target_kind})
                      </option>
                    ))}
                  </select>
                </label>

                <label className="form-label">
                  Profile
                  <select
                    className="form-select"
                    value={profileId}
                    onChange={(event) => setProfileId(event.target.value)}
                  >
                    <option value="">Select profile</option>
                    {state.profiles.map((profile) => (
                      <option key={profile.profile_id} value={profile.profile_id}>
                        {profile.profile_name}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="form-label">
                  Phone
                  <input
                    className="form-control"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    placeholder="9198..."
                  />
                </label>
              </div>

              <label className="form-label">
                Caption
                <textarea
                  className="form-control"
                  rows={3}
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                />
              </label>

              <div className="wa-send__meta">
                Mode: {state.capabilities.delivery_mode === 'selenium' ? 'Selenium automation' : 'Manual browser'}
                {!state.capabilities.can_auto_send_attachment && ' | Attachments open in WhatsApp Web for manual send.'}
                {selectedTarget && ` | Target: ${selectedTarget.target_name}`}
              </div>

              <div className="wa-send__actions">
                <button
                  type="button"
                  className="btn btn-success"
                  disabled={sending || !profileId}
                  onClick={() => void send()}
                >
                  {sending ? 'Preparing...' : 'Send report'}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
