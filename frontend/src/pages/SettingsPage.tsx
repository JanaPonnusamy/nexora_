import { useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../components/common/PageHeader'
import { ApiError } from '../services/apiClient'
import {
  automationSettingsService,
  type AutomationSettingsResponse,
} from '../services/automationSettingsService'
import {
  whatsappService,
  type WhatsAppProfile,
  type WhatsAppState,
  type WhatsAppTarget,
} from '../services/whatsappService'
import './settings.css'

type AutomationFormState = {
  repoPath: string
  pythonCommand: string
}

type WhatsAppSettingsForm = {
  browserCommand: string
  deliveryMode: 'manual_browser' | 'selenium'
  launchWaitSeconds: string
}

type WhatsAppProfileForm = {
  profileId: string
  profileName: string
  ownerType: string
  ownerName: string
  tenantId: string
  storeId: string
  defaultPhone: string
  notes: string
  isDefault: boolean
}

type WhatsAppTargetForm = {
  targetId: string
  profileId: string
  targetKind: 'contact' | 'group'
  targetName: string
  targetRef: string
  canSend: boolean
  canRead: boolean
  isActive: boolean
  notes: string
}

const emptyAutomationForm: AutomationFormState = {
  repoPath: '',
  pythonCommand: '',
}

const emptyWhatsAppProfile: WhatsAppProfileForm = {
  profileId: '',
  profileName: '',
  ownerType: 'store',
  ownerName: '',
  tenantId: '',
  storeId: '',
  defaultPhone: '',
  notes: '',
  isDefault: false,
}

const emptyWhatsAppTarget: WhatsAppTargetForm = {
  targetId: '',
  profileId: '',
  targetKind: 'contact',
  targetName: '',
  targetRef: '',
  canSend: true,
  canRead: false,
  isActive: true,
  notes: '',
}

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span className={`badge rounded-pill ${ok ? 'text-bg-success' : 'text-bg-danger'}`}>
      {ok ? 'Ready' : 'Needs attention'}
    </span>
  )
}

function profileToForm(profile: WhatsAppProfile): WhatsAppProfileForm {
  return {
    profileId: profile.profile_id,
    profileName: profile.profile_name,
    ownerType: profile.owner_type,
    ownerName: profile.owner_name,
    tenantId: profile.tenant_id,
    storeId: profile.store_id,
    defaultPhone: profile.default_phone,
    notes: profile.notes,
    isDefault: profile.is_default,
  }
}

function targetToForm(target: WhatsAppTarget): WhatsAppTargetForm {
  return {
    targetId: target.target_id,
    profileId: target.profile_id,
    targetKind: target.target_kind,
    targetName: target.target_name,
    targetRef: target.target_ref,
    canSend: target.can_send,
    canRead: target.can_read,
    isActive: target.is_active,
    notes: target.notes,
  }
}

export default function SettingsPage() {
  const [automationData, setAutomationData] = useState<AutomationSettingsResponse | null>(null)
  const [automationForm, setAutomationForm] = useState<AutomationFormState>(emptyAutomationForm)
  const [automationLoading, setAutomationLoading] = useState(true)
  const [automationSaving, setAutomationSaving] = useState(false)

  const [whatsAppData, setWhatsAppData] = useState<WhatsAppState | null>(null)
  const [whatsAppLoading, setWhatsAppLoading] = useState(true)
  const [whatsAppSaving, setWhatsAppSaving] = useState(false)
  const [whatsAppSettingsForm, setWhatsAppSettingsForm] = useState<WhatsAppSettingsForm>({
    browserCommand: '',
    deliveryMode: 'manual_browser',
    launchWaitSeconds: '15',
  })
  const [whatsAppProfileForm, setWhatsAppProfileForm] = useState<WhatsAppProfileForm>(emptyWhatsAppProfile)
  const [whatsAppTargetForm, setWhatsAppTargetForm] = useState<WhatsAppTargetForm>(emptyWhatsAppTarget)

  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const hydrateAutomation = (payload: AutomationSettingsResponse) => {
    setAutomationData(payload)
    setAutomationForm({
      repoPath: payload.settings.repo_path,
      pythonCommand: payload.settings.python_command,
    })
  }

  const hydrateWhatsApp = (payload: WhatsAppState) => {
    setWhatsAppData(payload)
    setWhatsAppSettingsForm({
      browserCommand: payload.settings.browser_command,
      deliveryMode: payload.settings.delivery_mode,
      launchWaitSeconds: String(payload.settings.launch_wait_seconds),
    })
  }

  const loadAutomation = async () => {
    setAutomationLoading(true)
    try {
      const payload = await automationSettingsService.get()
      hydrateAutomation(payload)
    } finally {
      setAutomationLoading(false)
    }
  }

  const loadWhatsApp = async () => {
    setWhatsAppLoading(true)
    try {
      const payload = await whatsappService.getState()
      hydrateWhatsApp(payload)
    } finally {
      setWhatsAppLoading(false)
    }
  }

  useEffect(() => {
    void Promise.allSettled([loadAutomation(), loadWhatsApp()]).catch(() => undefined)
  }, [])

  const saveAutomation = async () => {
    setAutomationSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = await automationSettingsService.update({
        repo_path: automationForm.repoPath,
        python_command: automationForm.pythonCommand,
      })
      hydrateAutomation(payload)
      setMessage('Automation settings saved and validated.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save automation settings.')
    } finally {
      setAutomationSaving(false)
    }
  }

  const saveWhatsAppSettings = async () => {
    setWhatsAppSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = await whatsappService.saveSettings({
        browser_command: whatsAppSettingsForm.browserCommand,
        delivery_mode: whatsAppSettingsForm.deliveryMode,
        launch_wait_seconds: Number(whatsAppSettingsForm.launchWaitSeconds) || 15,
      })
      hydrateWhatsApp(payload)
      setMessage('WhatsApp runtime settings saved.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save WhatsApp settings.')
    } finally {
      setWhatsAppSaving(false)
    }
  }

  const saveWhatsAppProfile = async () => {
    setWhatsAppSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = await whatsappService.saveProfile({
        profile_id: whatsAppProfileForm.profileId || undefined,
        profile_name: whatsAppProfileForm.profileName,
        owner_type: whatsAppProfileForm.ownerType,
        owner_name: whatsAppProfileForm.ownerName,
        tenant_id: whatsAppProfileForm.tenantId,
        store_id: whatsAppProfileForm.storeId,
        default_phone: whatsAppProfileForm.defaultPhone,
        notes: whatsAppProfileForm.notes,
        is_default: whatsAppProfileForm.isDefault,
      })
      setWhatsAppData((current) => current ? { ...current, profiles: payload.profiles, capabilities: payload.capabilities } : current)
      const savedProfile = payload.profile
      setWhatsAppProfileForm(profileToForm(savedProfile))
      setWhatsAppTargetForm((current) => ({ ...current, profileId: savedProfile.profile_id }))
      setMessage('WhatsApp profile saved.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save WhatsApp profile.')
    } finally {
      setWhatsAppSaving(false)
    }
  }

  const saveWhatsAppTarget = async () => {
    setWhatsAppSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = await whatsappService.saveTarget({
        target_id: whatsAppTargetForm.targetId || undefined,
        profile_id: whatsAppTargetForm.profileId,
        target_kind: whatsAppTargetForm.targetKind,
        target_name: whatsAppTargetForm.targetName,
        target_ref: whatsAppTargetForm.targetRef,
        can_send: whatsAppTargetForm.canSend,
        can_read: whatsAppTargetForm.canRead,
        is_active: whatsAppTargetForm.isActive,
        notes: whatsAppTargetForm.notes,
      })
      setWhatsAppData((current) => current ? { ...current, targets: payload.targets, messages: payload.messages, capabilities: payload.capabilities } : current)
      setWhatsAppTargetForm(targetToForm(payload.target))
      setMessage('WhatsApp target saved.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save WhatsApp target.')
    } finally {
      setWhatsAppSaving(false)
    }
  }

  const deleteWhatsAppProfile = async (profileId: string) => {
    setWhatsAppSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = await whatsappService.deleteProfile(profileId)
      setWhatsAppData((current) => current ? { ...current, profiles: payload.profiles, targets: payload.targets, messages: payload.messages, capabilities: payload.capabilities } : current)
      setWhatsAppProfileForm(emptyWhatsAppProfile)
      setMessage('WhatsApp profile removed.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to delete WhatsApp profile.')
    } finally {
      setWhatsAppSaving(false)
    }
  }

  const deleteWhatsAppTarget = async (targetId: string) => {
    setWhatsAppSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = await whatsappService.deleteTarget(targetId)
      setWhatsAppData((current) => current ? { ...current, targets: payload.targets, messages: payload.messages, capabilities: payload.capabilities } : current)
      setWhatsAppTargetForm(emptyWhatsAppTarget)
      setMessage('WhatsApp target removed.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to delete WhatsApp target.')
    } finally {
      setWhatsAppSaving(false)
    }
  }

  const launchWhatsAppProfile = async (profileId: string) => {
    setWhatsAppSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = await whatsappService.launchProfile(profileId)
      setMessage(payload.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to launch WhatsApp Web for this profile.')
    } finally {
      setWhatsAppSaving(false)
    }
  }

  const syncWhatsAppTarget = async (targetId: string) => {
    setWhatsAppSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = await whatsappService.syncTarget(targetId, 25)
      setWhatsAppData((current) => current ? { ...current, targets: payload.targets, messages: payload.messages, capabilities: payload.capabilities } : current)
      setMessage(`Synced ${payload.synced_count} message(s) for the selected target.`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to sync WhatsApp messages for this target.')
    } finally {
      setWhatsAppSaving(false)
    }
  }

  const automationDirty =
    !!automationData &&
    (
      automationForm.repoPath !== automationData.settings.repo_path
      || automationForm.pythonCommand !== automationData.settings.python_command
    )

  const defaultProfile = useMemo(
    () => whatsAppData?.profiles.find((profile) => profile.is_default) ?? whatsAppData?.profiles[0] ?? null,
    [whatsAppData],
  )

  const targetMessages = useMemo(() => {
    if (!whatsAppData || !whatsAppTargetForm.targetId) return whatsAppData?.messages ?? []
    return (whatsAppData.messages ?? []).filter((messageItem) => messageItem.target_id === whatsAppTargetForm.targetId)
  }, [whatsAppData, whatsAppTargetForm.targetId])

  return (
    <div className="container-fluid px-0 settings-page">
      <PageHeader title="Settings" breadcrumb={['Settings']} />
      <p className="text-body-secondary mt-n3 mb-4">
        Configure automation, git, Python, and WhatsApp delivery for web and desktop workflows.
      </p>

      {error && <div className="alert alert-danger">{error}</div>}
      {message && !error && <div className="alert alert-success">{message}</div>}

      <div className="settings-grid">
        <section className="settings-card">
          <div className="settings-card__header">
            <div>
              <h2>Git Automation</h2>
              <p>Set the repository root and Python command for `automation`.</p>
            </div>
            {automationData && <StatusBadge ok={automationData.status.automation.ok} />}
          </div>

          <div className="settings-form">
            <label className="form-label">
              Git repository path
              <input className="form-control" value={automationForm.repoPath} onChange={(event) => setAutomationForm((current) => ({ ...current, repoPath: event.target.value }))} disabled={automationLoading || automationSaving} />
            </label>
            <label className="form-label">
              Python command
              <input className="form-control" value={automationForm.pythonCommand} onChange={(event) => setAutomationForm((current) => ({ ...current, pythonCommand: event.target.value }))} disabled={automationLoading || automationSaving} />
            </label>
            <div className="settings-actions">
              <button type="button" className="btn btn-outline-primary" onClick={() => void loadAutomation()} disabled={automationLoading || automationSaving}>
                Validate
              </button>
              <button type="button" className="btn btn-primary" onClick={() => void saveAutomation()} disabled={automationLoading || automationSaving || !automationDirty}>
                {automationSaving ? 'Saving...' : 'Save settings'}
              </button>
            </div>
          </div>
        </section>

        <section className="settings-card">
          <div className="settings-card__header">
            <div>
              <h2>WhatsApp Runtime</h2>
              <p>Manage browser automation mode, report delivery, and inbox sync.</p>
            </div>
            {whatsAppData && <StatusBadge ok={whatsAppData.capabilities.browser_detected} />}
          </div>

          <div className="settings-form">
            <label className="form-label">
              Browser command
              <input className="form-control" value={whatsAppSettingsForm.browserCommand} onChange={(event) => setWhatsAppSettingsForm((current) => ({ ...current, browserCommand: event.target.value }))} disabled={whatsAppLoading || whatsAppSaving} />
            </label>
            <label className="form-label">
              Delivery mode
              <select className="form-select" value={whatsAppSettingsForm.deliveryMode} onChange={(event) => setWhatsAppSettingsForm((current) => ({ ...current, deliveryMode: event.target.value as 'manual_browser' | 'selenium' }))}>
                <option value="manual_browser">Manual browser</option>
                <option value="selenium">Selenium automation</option>
              </select>
            </label>
            <label className="form-label">
              Launch wait seconds
              <input className="form-control" type="number" min={10} value={whatsAppSettingsForm.launchWaitSeconds} onChange={(event) => setWhatsAppSettingsForm((current) => ({ ...current, launchWaitSeconds: event.target.value }))} />
            </label>
            <div className="settings-actions">
              <button type="button" className="btn btn-success" onClick={() => void saveWhatsAppSettings()} disabled={whatsAppSaving}>
                {whatsAppSaving ? 'Saving...' : 'Save WhatsApp settings'}
              </button>
              <button type="button" className="btn btn-outline-secondary" onClick={() => void loadWhatsApp()} disabled={whatsAppSaving}>
                Refresh
              </button>
            </div>
            {whatsAppData && (
              <div className="health-list">
                <article className={`health-item ${whatsAppData.capabilities.browser_detected ? 'is-ok' : 'is-error'}`}>
                  <div className="health-item__title">
                    <h3>Browser Runtime</h3>
                    <StatusBadge ok={whatsAppData.capabilities.browser_detected} />
                  </div>
                  <p>Default profile: {defaultProfile?.profile_name || 'Not set'}</p>
                  <small>Selenium available: {whatsAppData.capabilities.selenium_available ? 'Yes' : 'No'} | Read messages: {whatsAppData.capabilities.can_read_messages ? 'Yes' : 'No'}</small>
                </article>
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="settings-card settings-card--stack">
        <div className="settings-card__header">
          <div>
            <h2>WhatsApp Profiles</h2>
            <p>Create per-store, per-user, or shared profiles. Each one keeps its own QR session.</p>
          </div>
          {whatsAppData && <StatusBadge ok={whatsAppData.profiles.length > 0} />}
        </div>

        <div className="settings-form">
          <div className="settings-inline-grid">
            <label className="form-label">
              Profile name
              <input className="form-control" value={whatsAppProfileForm.profileName} onChange={(event) => setWhatsAppProfileForm((current) => ({ ...current, profileName: event.target.value }))} />
            </label>
            <label className="form-label">
              Owner type
              <select className="form-select" value={whatsAppProfileForm.ownerType} onChange={(event) => setWhatsAppProfileForm((current) => ({ ...current, ownerType: event.target.value }))}>
                <option value="store">Store</option>
                <option value="user">User</option>
                <option value="system">System</option>
              </select>
            </label>
          </div>
          <div className="settings-inline-grid">
            <label className="form-label">
              Owner name
              <input className="form-control" value={whatsAppProfileForm.ownerName} onChange={(event) => setWhatsAppProfileForm((current) => ({ ...current, ownerName: event.target.value }))} />
            </label>
            <label className="form-label">
              Default phone
              <input className="form-control" value={whatsAppProfileForm.defaultPhone} onChange={(event) => setWhatsAppProfileForm((current) => ({ ...current, defaultPhone: event.target.value }))} />
            </label>
          </div>
          <div className="settings-inline-grid">
            <label className="form-label">
              Tenant ID
              <input className="form-control" value={whatsAppProfileForm.tenantId} onChange={(event) => setWhatsAppProfileForm((current) => ({ ...current, tenantId: event.target.value }))} />
            </label>
            <label className="form-label">
              Store ID
              <input className="form-control" value={whatsAppProfileForm.storeId} onChange={(event) => setWhatsAppProfileForm((current) => ({ ...current, storeId: event.target.value }))} />
            </label>
          </div>
          <label className="form-label">
            Notes
            <textarea className="form-control" rows={3} value={whatsAppProfileForm.notes} onChange={(event) => setWhatsAppProfileForm((current) => ({ ...current, notes: event.target.value }))} />
          </label>
          <label className="form-check">
            <input className="form-check-input" type="checkbox" checked={whatsAppProfileForm.isDefault} onChange={(event) => setWhatsAppProfileForm((current) => ({ ...current, isDefault: event.target.checked }))} />
            <span className="form-check-label">Use as default profile</span>
          </label>
          <div className="settings-actions">
            <button type="button" className="btn btn-success" onClick={() => void saveWhatsAppProfile()} disabled={whatsAppSaving}>
              {whatsAppSaving ? 'Saving...' : whatsAppProfileForm.profileId ? 'Update profile' : 'Create profile'}
            </button>
            <button type="button" className="btn btn-outline-secondary" onClick={() => setWhatsAppProfileForm(emptyWhatsAppProfile)} disabled={whatsAppSaving}>
              New profile
            </button>
          </div>
        </div>

        <div className="settings-profile-list">
          {(whatsAppData?.profiles ?? []).map((profile) => (
            <article key={profile.profile_id} className="settings-profile-card">
              <div className="settings-profile-card__head">
                <div>
                  <strong>{profile.profile_name}</strong>
                  <small>{profile.owner_type}{profile.owner_name ? ` | ${profile.owner_name}` : ''}</small>
                </div>
                {profile.is_default && <span className="badge text-bg-success">Default</span>}
              </div>
              <p>{profile.default_phone || 'No default phone saved'}</p>
              <div className="settings-profile-card__actions">
                <button type="button" className="btn btn-outline-primary btn-sm" onClick={() => setWhatsAppProfileForm(profileToForm(profile))}>
                  Edit
                </button>
                <button type="button" className="btn btn-outline-success btn-sm" onClick={() => void launchWhatsAppProfile(profile.profile_id)} disabled={whatsAppSaving}>
                  Launch QR / Web
                </button>
                <button type="button" className="btn btn-outline-danger btn-sm" onClick={() => void deleteWhatsAppProfile(profile.profile_id)} disabled={whatsAppSaving}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="settings-card settings-card--stack">
        <div className="settings-card__header">
          <div>
            <h2>Allowed Contacts And Groups</h2>
            <p>Whitelisted targets only. Use these for group report sending and restricted inbox reading.</p>
          </div>
          {whatsAppData && <StatusBadge ok={whatsAppData.targets.length > 0} />}
        </div>

        <div className="settings-form">
          <div className="settings-inline-grid">
            <label className="form-label">
              Profile
              <select className="form-select" value={whatsAppTargetForm.profileId} onChange={(event) => setWhatsAppTargetForm((current) => ({ ...current, profileId: event.target.value }))}>
                <option value="">Select profile</option>
                {(whatsAppData?.profiles ?? []).map((profile) => (
                  <option key={profile.profile_id} value={profile.profile_id}>{profile.profile_name}</option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Target kind
              <select className="form-select" value={whatsAppTargetForm.targetKind} onChange={(event) => setWhatsAppTargetForm((current) => ({ ...current, targetKind: event.target.value as 'contact' | 'group' }))}>
                <option value="contact">Contact</option>
                <option value="group">Group</option>
              </select>
            </label>
          </div>
          <div className="settings-inline-grid">
            <label className="form-label">
              Target name
              <input className="form-control" value={whatsAppTargetForm.targetName} onChange={(event) => setWhatsAppTargetForm((current) => ({ ...current, targetName: event.target.value }))} />
            </label>
            <label className="form-label">
              {whatsAppTargetForm.targetKind === 'group' ? 'Group name' : 'Phone number'}
              <input className="form-control" value={whatsAppTargetForm.targetRef} onChange={(event) => setWhatsAppTargetForm((current) => ({ ...current, targetRef: event.target.value }))} />
            </label>
          </div>
          <label className="form-label">
            Notes
            <textarea className="form-control" rows={2} value={whatsAppTargetForm.notes} onChange={(event) => setWhatsAppTargetForm((current) => ({ ...current, notes: event.target.value }))} />
          </label>
          <div className="settings-inline-grid">
            <label className="form-check">
              <input className="form-check-input" type="checkbox" checked={whatsAppTargetForm.canSend} onChange={(event) => setWhatsAppTargetForm((current) => ({ ...current, canSend: event.target.checked }))} />
              <span className="form-check-label">Allow sending</span>
            </label>
            <label className="form-check">
              <input className="form-check-input" type="checkbox" checked={whatsAppTargetForm.canRead} onChange={(event) => setWhatsAppTargetForm((current) => ({ ...current, canRead: event.target.checked }))} />
              <span className="form-check-label">Allow inbox reading</span>
            </label>
          </div>
          <div className="settings-actions">
            <button type="button" className="btn btn-success" onClick={() => void saveWhatsAppTarget()} disabled={whatsAppSaving}>
              {whatsAppSaving ? 'Saving...' : whatsAppTargetForm.targetId ? 'Update target' : 'Create target'}
            </button>
            <button type="button" className="btn btn-outline-secondary" onClick={() => setWhatsAppTargetForm(emptyWhatsAppTarget)} disabled={whatsAppSaving}>
              New target
            </button>
          </div>
        </div>

        <div className="settings-profile-list">
          {(whatsAppData?.targets ?? []).map((target) => (
            <article key={target.target_id} className="settings-profile-card">
              <div className="settings-profile-card__head">
                <div>
                  <strong>{target.target_name}</strong>
                  <small>{target.target_kind} | {target.target_ref}</small>
                </div>
                <span className={`badge ${target.can_read ? 'text-bg-primary' : 'text-bg-secondary'}`}>{target.can_read ? 'Readable' : 'Send only'}</span>
              </div>
              <p>Last synced: {target.last_synced_at || 'Never'}</p>
              <div className="settings-profile-card__actions">
                <button type="button" className="btn btn-outline-primary btn-sm" onClick={() => setWhatsAppTargetForm(targetToForm(target))}>
                  Edit
                </button>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => void syncWhatsAppTarget(target.target_id)} disabled={whatsAppSaving || !target.can_read}>
                  Sync inbox
                </button>
                <button type="button" className="btn btn-outline-danger btn-sm" onClick={() => void deleteWhatsAppTarget(target.target_id)} disabled={whatsAppSaving}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="settings-card settings-card--stack">
        <div className="settings-card__header">
          <div>
            <h2>Incoming Messages</h2>
            <p>Recent inbox entries captured only from allowed contacts and groups.</p>
          </div>
          {whatsAppData && <StatusBadge ok={(whatsAppData.messages ?? []).length > 0} />}
        </div>
        <div className="settings-message-list">
          {targetMessages.length ? (
            targetMessages.map((messageItem) => (
              <article key={messageItem.message_id} className={`settings-message-card ${messageItem.direction === 'incoming' ? 'is-incoming' : 'is-outgoing'}`}>
                <div className="settings-message-card__head">
                  <strong>{messageItem.source_label}</strong>
                  <small>{messageItem.message_time}</small>
                </div>
                <p>{messageItem.message_text}</p>
              </article>
            ))
          ) : (
            <div className="empty-state">No messages synced yet. Enable read access on a target and click `Sync inbox`.</div>
          )}
        </div>
      </section>
    </div>
  )
}
