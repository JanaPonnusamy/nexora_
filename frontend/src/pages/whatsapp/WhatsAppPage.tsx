import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { WhatsAppQrLogin } from '../../components/common/WhatsAppQrLogin'
import { ApiError } from '../../services/apiClient'
import {
  whatsappService,
  type WhatsAppChat,
  type WhatsAppChatMessage,
  type WhatsAppProfile,
  type WhatsAppSendLogEntry,
} from '../../services/whatsappService'
import './whatsapp.css'

type KindFilter = 'all' | 'group' | 'contact'

function relTime(iso: string): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const secs = Math.round((Date.now() - then) / 1000)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`
  return new Date(iso).toLocaleString()
}

export default function WhatsAppPage() {
  const [profiles, setProfiles] = useState<WhatsAppProfile[]>([])
  const [profileId, setProfileId] = useState('')
  const [chats, setChats] = useState<WhatsAppChat[]>([])
  const [chatsLoadedAt, setChatsLoadedAt] = useState('')
  const [loadingChats, setLoadingChats] = useState(false)
  const [search, setSearch] = useState('')
  const [kindFilter, setKindFilter] = useState<KindFilter>('all')
  const [selected, setSelected] = useState<WhatsAppChat | null>(null)

  const [message, setMessage] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [sending, setSending] = useState(false)
  const [banner, setBanner] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  const [sendLog, setSendLog] = useState<WhatsAppSendLogEntry[]>([])
  const [showQr, setShowQr] = useState(false)
  const [error, setError] = useState('')

  const [messages, setMessages] = useState<WhatsAppChatMessage[]>([])
  const [loadingMsgs, setLoadingMsgs] = useState(false)
  const [msgsFor, setMsgsFor] = useState('')
  const [days, setDays] = useState(10)

  const refreshLog = useCallback(async () => {
    try {
      const res = await whatsappService.getSendLog(60)
      setSendLog(res.entries)
    } catch {
      /* non-fatal */
    }
  }, [])

  // Initial load: profiles (default selected) + send log.
  useEffect(() => {
    void (async () => {
      try {
        const state = await whatsappService.getState()
        setProfiles(state.profiles)
        const def =
          state.capabilities.default_profile_id ||
          (state.profiles.find((p) => p.is_default) ?? state.profiles[0])?.profile_id ||
          ''
        setProfileId(def)
        if (state.send_log) setSendLog(state.send_log)
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Unable to load WhatsApp profiles.')
      }
    })()
  }, [])

  const loadChats = useCallback(async () => {
    if (!profileId) return
    setLoadingChats(true)
    setError('')
    try {
      const res = await whatsappService.listChats(profileId)
      setChats(res.chats)
      setChatsLoadedAt(res.checked_at)
      if (res.count === 0) {
        setError(
          'No chats were read. Make sure this profile is linked (click "Link WhatsApp"), then reload.',
        )
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Unable to read chats.'
      setError(msg)
      if (/log/i.test(msg) && /in/i.test(msg)) setShowQr(true)
    } finally {
      setLoadingChats(false)
    }
  }, [profileId])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return chats.filter((c) => {
      if (kindFilter !== 'all' && c.kind !== kindFilter) return false
      if (q && !c.name.toLowerCase().includes(q)) return false
      return true
    })
  }, [chats, search, kindFilter])

  const groupCount = useMemo(() => chats.filter((c) => c.kind === 'group').length, [chats])

  const doSend = useCallback(async () => {
    if (!selected || !profileId) return
    if (!message.trim() && !file) {
      setBanner({ kind: 'err', text: 'Type a message or attach a file first.' })
      return
    }
    setSending(true)
    setBanner(null)
    try {
      const res = file
        ? await whatsappService.sendChatFile(profileId, selected.name, message, file)
        : await whatsappService.sendChat(profileId, selected.name, message)
      if (res.status === 'sent') {
        setBanner({ kind: 'ok', text: `Sent to ${selected.name}.` })
        setMessage('')
        setFile(null)
      } else {
        setBanner({ kind: 'err', text: res.message || 'Send failed.' })
      }
    } catch (err) {
      setBanner({ kind: 'err', text: err instanceof ApiError ? err.message : 'Send failed.' })
    } finally {
      setSending(false)
      void refreshLog()
    }
  }, [selected, profileId, message, file, refreshLog])

  const selectChat = useCallback((c: WhatsAppChat) => {
    setSelected(c)
    setMessages([])
    setMsgsFor('')
    setBanner(null)
  }, [])

  const loadMessages = useCallback(async () => {
    if (!selected || !profileId) return
    setLoadingMsgs(true)
    try {
      const res = await whatsappService.readChatMessages(profileId, selected.name, days)
      setMessages(res.messages)
      setMsgsFor(selected.name)
    } catch (err) {
      setBanner({ kind: 'err', text: err instanceof ApiError ? err.message : 'Could not read messages.' })
    } finally {
      setLoadingMsgs(false)
    }
  }, [selected, profileId])

  const downloadContacts = useCallback(() => {
    if (!chats.length) return
    const rows = [['Name', 'Type'], ...chats.map((c) => [c.name, c.kind])]
    const csv = rows
      .map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\r\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `whatsapp-contacts-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [chats])

  return (
    <div className="wa-page">
      <PageHeader
        title="WhatsApp"
        breadcrumb={['System', 'WhatsApp']}
        description="Read your WhatsApp chats and groups, download the list, and message any contact or group."
      />

      <div className="wa-toolbar">
        <label className="wa-toolbar__field">
          <span>Account</span>
          <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
            {profiles.length === 0 && <option value="">No profiles</option>}
            {profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {p.profile_name}
                {p.is_default ? ' (default)' : ''}
              </option>
            ))}
          </select>
        </label>
        <button className="btn btn-primary btn-sm" onClick={loadChats} disabled={!profileId || loadingChats}>
          <i className="bi bi-arrow-clockwise" /> {loadingChats ? 'Reading chats…' : 'Load / reload chats'}
        </button>
        <button className="btn btn-outline-secondary btn-sm" onClick={downloadContacts} disabled={!chats.length}>
          <i className="bi bi-download" /> Download ({chats.length})
        </button>
        <button className="btn btn-outline-success btn-sm" onClick={() => setShowQr(true)} disabled={!profileId}>
          <i className="bi bi-whatsapp" /> Link WhatsApp
        </button>
        {chatsLoadedAt && (
          <span className="wa-toolbar__meta">
            {chats.length} chats · {groupCount} groups · read {relTime(chatsLoadedAt)}
          </span>
        )}
      </div>

      {error && <div className="alert alert-warning wa-alert">{error}</div>}

      <div className="wa-layout">
        {/* Left: chat list */}
        <aside className="wa-list">
          <div className="wa-list__search">
            <i className="bi bi-search" />
            <input
              placeholder="Search name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="wa-list__filters">
            {(['all', 'group', 'contact'] as KindFilter[]).map((k) => (
              <button
                key={k}
                className={`wa-chip${kindFilter === k ? ' wa-chip--on' : ''}`}
                onClick={() => setKindFilter(k)}
              >
                {k === 'all' ? 'All' : k === 'group' ? 'Groups' : 'Contacts'}
              </button>
            ))}
          </div>
          <div className="wa-list__scroll">
            {/* Free-type: message any group/contact by exact name even if it is
                not in the (recent) scraped list. WhatsApp search finds all. */}
            {search.trim() &&
              !chats.some((c) => c.name.toLowerCase() === search.trim().toLowerCase()) && (
                <button
                  className="wa-row wa-row--adhoc"
                  onClick={() => selectChat({ name: search.trim(), kind: 'contact' })}
                >
                  <span className="wa-avatar wa-avatar--adhoc">
                    <i className="bi bi-send" />
                  </span>
                  <span className="wa-row__name">
                    Message “{search.trim()}” <em>(exact name)</em>
                  </span>
                </button>
              )}
            {filtered.length === 0 && !loadingChats && !search.trim() && (
              <div className="wa-list__empty">
                {chats.length === 0 ? 'Load chats, or type a name above to message it directly.' : 'No matches.'}
              </div>
            )}
            {filtered.map((c) => (
              <button
                key={`${c.kind}:${c.name}`}
                className={`wa-row${selected?.name === c.name ? ' wa-row--on' : ''}`}
                onClick={() => selectChat(c)}
              >
                <span className={`wa-avatar wa-avatar--${c.kind}`}>
                  <i className={`bi ${c.kind === 'group' ? 'bi-people-fill' : 'bi-person-fill'}`} />
                </span>
                <span className="wa-row__name">{c.name}</span>
                {c.kind === 'group' && <span className="wa-tag">Group</span>}
              </button>
            ))}
          </div>
        </aside>

        {/* Right: compose */}
        <section className="wa-compose">
          {selected ? (
            <>
              <div className="wa-compose__head">
                <span className={`wa-avatar wa-avatar--${selected.kind}`}>
                  <i className={`bi ${selected.kind === 'group' ? 'bi-people-fill' : 'bi-person-fill'}`} />
                </span>
                <div>
                  <div className="wa-compose__name">{selected.name}</div>
                  <div className="wa-compose__kind">{selected.kind === 'group' ? 'Group' : 'Contact'}</div>
                </div>
                <div className="wa-compose__spacer" />
                <select
                  className="wa-days"
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value))}
                  title="How far back to read"
                >
                  <option value={3}>Last 3 days</option>
                  <option value={7}>Last 7 days</option>
                  <option value={10}>Last 10 days</option>
                  <option value={30}>Last 30 days</option>
                </select>
                <button className="btn btn-outline-secondary btn-sm" onClick={loadMessages} disabled={loadingMsgs}>
                  <i className="bi bi-chat-left-text" /> {loadingMsgs ? 'Reading…' : 'Load messages'}
                </button>
              </div>

              {msgsFor === selected.name && (
                <div className="wa-thread">
                  {messages.length === 0 && !loadingMsgs && (
                    <div className="wa-thread__empty">No messages read.</div>
                  )}
                  {messages.map((m, i) => (
                    <div key={i} className={`wa-msg wa-msg--${m.direction}`}>
                      {m.text && <div className="wa-msg__text">{m.text}</div>}
                      {m.meta && <div className="wa-msg__meta">{m.meta}</div>}
                    </div>
                  ))}
                </div>
              )}
              {banner && (
                <div className={`alert ${banner.kind === 'ok' ? 'alert-success' : 'alert-danger'} wa-alert`}>
                  {banner.text}
                </div>
              )}
              <textarea
                className="wa-compose__text"
                placeholder="Type a message…"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={5}
              />
              <div className="wa-compose__actions">
                <label className="btn btn-outline-secondary btn-sm wa-file">
                  <i className="bi bi-paperclip" /> {file ? file.name : 'Attach file'}
                  <input
                    type="file"
                    hidden
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                {file && (
                  <button className="btn btn-link btn-sm text-danger" onClick={() => setFile(null)}>
                    remove
                  </button>
                )}
                <div className="wa-compose__spacer" />
                <button className="btn btn-success" onClick={doSend} disabled={sending}>
                  <i className="bi bi-send" /> {sending ? 'Sending…' : 'Send'}
                </button>
              </div>
            </>
          ) : (
            <div className="wa-compose__empty">
              <i className="bi bi-chat-dots" />
              <p>Select a contact or group to send a message.</p>
            </div>
          )}

          {/* Send log */}
          <div className="wa-log">
            <div className="wa-log__head">
              <span>Recent sends</span>
              <button className="btn btn-link btn-sm" onClick={() => void refreshLog()}>
                refresh
              </button>
            </div>
            <div className="wa-log__scroll">
              {sendLog.length === 0 && <div className="wa-log__empty">No sends yet.</div>}
              {sendLog.map((e) => (
                <div key={e.id} className={`wa-log__row wa-log__row--${e.status}`}>
                  <span className={`wa-log__dot wa-log__dot--${e.status}`} />
                  <div className="wa-log__body">
                    <div className="wa-log__line">
                      <strong>{e.target_name}</strong>
                      <span className="wa-log__time">{relTime(e.at)}</span>
                    </div>
                    {e.status === 'failed' ? (
                      <div className="wa-log__err">{e.error}</div>
                    ) : (
                      e.message_preview && <div className="wa-log__msg">{e.message_preview}</div>
                    )}
                    {e.status === 'failed' && e.snapshot && (
                      <div className="wa-log__snap">snapshot: {e.snapshot}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      {showQr && profileId && (
        <WhatsAppQrLogin
          profileId={profileId}
          onLoggedIn={() => {
            setShowQr(false)
            void loadChats()
          }}
          onClose={() => setShowQr(false)}
        />
      )}
    </div>
  )
}
