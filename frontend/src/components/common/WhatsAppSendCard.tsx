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
  /** Pre-select the saved target whose name matches this (e.g. a store's
   *  configured WhatsApp group), so the user isn't asked to recreate the
   *  mapping every send. Falls back to preferredPhone, then the default. */
  preferredTargetName?: string
  preferredPhone?: string
}

export function WhatsAppSendCard({
  disabled = false,
  title,
  buttonLabel = 'Send to WhatsApp',
  defaultCaption,
  buildFile,
  preferredTargetName,
  preferredPhone,
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
  const [launching, setLaunching] = useState(false)
  const [addingContact, setAddingContact] = useState(false)
  const [newContactName, setNewContactName] = useState('')
  const [newContactPhone, setNewContactPhone] = useState('')
  const [savingContact, setSavingContact] = useState(false)

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
        }

        const wantedGroup = preferredTargetName?.trim().toLowerCase()
        const matchedTarget = wantedGroup
          ? payload.targets.find((target) => target.can_send && target.target_name.trim().toLowerCase() === wantedGroup)
          : undefined
        const matchedPhoneTarget = !matchedTarget && preferredPhone
          ? payload.targets.find((target) => target.can_send && target.target_kind === 'contact' && target.target_ref === preferredPhone)
          : undefined
        const resolvedTarget = matchedTarget ?? matchedPhoneTarget
          ?? payload.targets.find((target) => target.can_send && target.is_active)

        if (resolvedTarget) {
          setTargetId(resolvedTarget.target_id)
          setProfileId(resolvedTarget.profile_id)
        } else if (preferredPhone) {
          setPhone(preferredPhone)
        } else if (defaultProfile) {
          setPhone(defaultProfile.default_phone || '')
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

  const addContact = async () => {
    if (!profileId) {
      setError('Choose a WhatsApp profile first.')
      return
    }
    const name = newContactName.trim()
    const ref = newContactPhone.trim()
    if (!name || !ref) {
      setError('Enter a contact name and phone number.')
      return
    }
    setSavingContact(true)
    setStatus('')
    setError('')
    try {
      const result = await whatsappService.saveTarget({
        profile_id: profileId,
        target_kind: 'contact',
        target_name: name,
        target_ref: ref,
        can_send: true,
        can_read: false,
        is_active: true,
        notes: '',
      })
      setState((current) => (current ? { ...current, targets: result.targets } : current))
      setTargetId(result.target.target_id)
      setNewContactName('')
      setNewContactPhone('')
      setAddingContact(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to add this contact.')
    } finally {
      setSavingContact(false)
    }
  }

  const needsQrLogin = /not logged in/i.test(error)

  const launchQr = async () => {
    if (!profileId) {
      setError('Choose a WhatsApp profile first.')
      return
    }
    setLaunching(true)
    setStatus('')
    setError('')
    try {
      const result = await whatsappService.launchProfile(profileId)
      setStatus(result.message || 'WhatsApp opened — scan the QR code, then click Send report.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to launch WhatsApp for this profile.')
    } finally {
      setLaunching(false)
    }
  }

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
          {error && (
            <div className="alert alert-danger mb-0">
              {error}
              {needsQrLogin && (
                <button
                  type="button"
                  className="btn btn-outline-danger btn-sm ms-2"
                  disabled={launching}
                  onClick={() => void launchQr()}
                >
                  {launching ? 'Launching...' : 'Launch WhatsApp (Scan QR)'}
                </button>
              )}
            </div>
          )}
          {status && !error && <div className="alert alert-success mb-0">{status}</div>}

          {!loading && state && (
            <>
              <div className="wa-send__grid">
                <label className="form-label">
                  Saved target
                  <div className="wa-send__target-row">
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
                    <button
                      type="button"
                      className="btn btn-outline-secondary btn-sm"
                      onClick={() => setAddingContact((current) => !current)}
                    >
                      + Contact
                    </button>
                  </div>
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

              {addingContact && (
                <div className="wa-send__add-contact">
                  <input
                    className="form-control"
                    placeholder="Contact name"
                    value={newContactName}
                    onChange={(event) => setNewContactName(event.target.value)}
                  />
                  <input
                    className="form-control"
                    placeholder="Phone (with country code)"
                    value={newContactPhone}
                    onChange={(event) => setNewContactPhone(event.target.value)}
                  />
                  <button
                    type="button"
                    className="btn btn-success btn-sm"
                    disabled={savingContact}
                    onClick={() => void addContact()}
                  >
                    {savingContact ? 'Saving...' : 'Save contact'}
                  </button>
                </div>
              )}

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
                Mode: {state.capabilities.delivery_mode === 'selenium' ? 'Automated (background)' : 'Manual browser'}
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
