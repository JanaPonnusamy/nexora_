import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAsyncData } from '../../hooks/useAsyncData'
import { deviceControllerService as dc } from '../../services/deviceControllerService'
import type { DcDevice, DcTerminalRow, DcTerminalSession } from '../../types/deviceController'
import { SxButton, SxChip, SxSearch, SxSegmented, type Tone } from './ui'
import './device-controller.css'

// eslint-disable-next-line no-control-regex
const ANSI = /\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07/g
const live = (s?: string) => s === 'OPENING' || s === 'OPEN' || s === 'CLOSING'
const sessionTone = (s?: string): Tone => (s === 'OPEN' ? 'success' : s === 'OPENING' || s === 'CLOSING' ? 'warning' : 'muted')

function fmt(value: string | null | undefined) {
  if (!value) return '—'
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString()
}

function deviceLabel(d: DcDevice) {
  const stores = d.stores.map((s) => s.store_code).join(', ')
  return `${d.hostname || d.machine_name || d.device_id}${stores ? ` · ${stores}` : ''}`
}

export function RemoteTerminal() {
  const [params, setParams] = useSearchParams()
  const devicesQuery = useAsyncData(() => dc.devices())
  const [tabs, setTabs] = useState<DcTerminalSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [layout, setLayout] = useState<'tabs' | 'grid'>('tabs')
  const [picker, setPicker] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const openedFromLink = useRef(false)

  // Re-attach to sessions still live on HO (a page reload keeps them).
  useEffect(() => {
    dc.terminals(true)
      .then(({ sessions }) => {
        setTabs((cur) => [...cur, ...sessions.filter((s) => !cur.some((c) => c.session_id === s.session_id))])
        if (sessions.length) setActiveId((cur) => cur ?? sessions[0].session_id)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const open = useCallback(async (deviceId: string) => {
    setError(null)
    try {
      const session = await dc.openTerminal(deviceId)
      setTabs((cur) => [...cur, session])
      setActiveId(session.session_id)
      setPicker(false)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  // /sync/terminal?device=<id> opens a terminal straight away (from Device Control).
  useEffect(() => {
    const deviceId = params.get('device')
    if (deviceId && !openedFromLink.current) {
      openedFromLink.current = true
      void open(deviceId)
      params.delete('device')
      setParams(params, { replace: true })
    }
  }, [params, setParams, open])

  const updateTab = useCallback((s: Partial<DcTerminalSession> & { session_id: string }) => {
    setTabs((cur) => cur.map((t) => (t.session_id === s.session_id ? { ...t, ...s } : t)))
  }, [])

  const closeTab = async (id: string) => {
    const tab = tabs.find((t) => t.session_id === id)
    if (tab && live(tab.status)) {
      try { await dc.closeTerminal(id) } catch { /* already gone */ }
    }
    setTabs((cur) => cur.filter((t) => t.session_id !== id))
    setActiveId((cur) => (cur === id ? tabs.find((t) => t.session_id !== id)?.session_id ?? null : cur))
  }

  const devices = devicesQuery.data?.devices ?? []
  const shown = layout === 'grid' ? tabs : tabs.filter((t) => t.session_id === activeId)

  return (
    <div className="rt">
      <div className="rt-bar">
        <div className="rt-tabs" role="tablist">
          {tabs.map((t) => (
            <div key={t.session_id} role="tab" aria-selected={t.session_id === activeId}
              className={`rt-tab${t.session_id === activeId ? ' rt-tab--active' : ''}`}
              onClick={() => setActiveId(t.session_id)}>
              <span className={`rt-dot rt-dot--${sessionTone(t.status)}`} />
              <span className="rt-tab__label">{t.hostname || t.device_id.slice(0, 8)}</span>
              <button type="button" className="rt-tab__x" aria-label="Close terminal"
                onClick={(e) => { e.stopPropagation(); void closeTab(t.session_id) }}>×</button>
            </div>
          ))}
          <button type="button" className="rt-tab rt-tab--new" onClick={() => setPicker((v) => !v)}>
            <i className="bi bi-plus-lg" /> New terminal
          </button>
        </div>
        <div className="d-flex gap-2 align-items-center">
          <SxSegmented
            ariaLabel="Layout"
            value={layout}
            onChange={setLayout}
            options={[{ label: 'Tabs', value: 'tabs' }, { label: 'Side by side', value: 'grid' }]}
          />
          <SxButton sm icon="bi-clock-history" onClick={() => setShowHistory((v) => !v)}>Audit log</SxButton>
        </div>
      </div>

      {error && <div className="dc-banner dc-banner--danger">{error}</div>}
      {picker && <DevicePicker devices={devices} loading={devicesQuery.isLoading} onPick={(id) => void open(id)} onClose={() => setPicker(false)} />}
      {showHistory && <AuditLog onClose={() => setShowHistory(false)} />}

      {tabs.length === 0 && !picker && (
        <div className="rt-empty">
          <i className="bi bi-terminal" />
          <div>No terminal open. Choose <b>New terminal</b> and pick a store PC.</div>
          <div className="dc-muted">Sessions run PowerShell as the PC&apos;s SYSTEM account. Every command and every line of output is recorded with your user name.</div>
        </div>
      )}

      <div className={layout === 'grid' ? 'rt-grid' : ''}>
        {shown.map((t) => <TerminalPane key={t.session_id} session={t} onStatus={updateTab} />)}
      </div>
    </div>
  )
}

function DevicePicker({
  devices, loading, onPick, onClose,
}: { devices: DcDevice[]; loading: boolean; onPick: (id: string) => void; onClose: () => void }) {
  const [q, setQ] = useState('')
  const list = useMemo(() => {
    const term = q.trim().toLowerCase()
    return devices
      .filter((d) => d.registration_status === 'active')
      .filter((d) => !term || deviceLabel(d).toLowerCase().includes(term) || (d.local_ip ?? '').includes(term))
      .sort((a, b) => Number(b.online) - Number(a.online) || deviceLabel(a).localeCompare(deviceLabel(b)))
  }, [devices, q])
  return (
    <div className="rt-picker">
      <div className="dc-enroll__head">
        <b>Open a terminal on…</b>
        <button type="button" className="dc-banner__close" onClick={onClose} aria-label="Close">×</button>
      </div>
      <SxSearch value={q} onChange={setQ} placeholder="Store, PC name or IP…" />
      <div className="rt-picker__list">
        {loading && <div className="dc-muted">Loading PCs…</div>}
        {!loading && list.length === 0 && <div className="dc-muted">No enrolled PCs match.</div>}
        {list.map((d) => (
          <button key={d.device_id} type="button" className="rt-picker__item" onClick={() => onPick(d.device_id)}>
            <span className={`rt-dot rt-dot--${d.online ? 'success' : 'muted'}`} />
            <span className="rt-picker__name">{deviceLabel(d)}</span>
            <span className="dc-muted">{d.local_ip ?? ''} {d.online ? '' : '· offline'}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function TerminalPane({
  session, onStatus,
}: { session: DcTerminalSession; onStatus: (s: Partial<DcTerminalSession> & { session_id: string }) => void }) {
  const [rows, setRows] = useState<DcTerminalRow[]>([])
  const [status, setStatus] = useState(session.status)
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [histIdx, setHistIdx] = useState(-1)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const screenRef = useRef<HTMLPreElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const id = session.session_id

  // Long-poll output until the session ends or the pane unmounts.
  useEffect(() => {
    const ctrl = new AbortController()
    let after = 0
    let stopped = false
    const loop = async () => {
      while (!stopped) {
        try {
          const res = await dc.terminalOutput(id, after, 20, ctrl.signal)
          if (res.rows.length) {
            after = res.rows[res.rows.length - 1].seq
            setRows((cur) => [...cur, ...res.rows])
          }
          setStatus(res.status)
          onStatus({ session_id: id, status: res.status })
          if (!live(res.status) && !res.rows.length) break
        } catch (e) {
          if (ctrl.signal.aborted) return
          setError((e as Error).message)
          await new Promise((r) => setTimeout(r, 3000))
        }
      }
    }
    void loop()
    return () => { stopped = true; ctrl.abort() }
  }, [id, onStatus])

  useEffect(() => {
    const el = screenRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [rows])

  const send = async (text: string) => {
    if (!live(status)) return
    setSending(true)
    setError(null)
    try {
      await dc.terminalInput(id, text)
      if (text.trim()) setHistory((h) => [text, ...h.filter((x) => x !== text)].slice(0, 100))
      setHistIdx(-1)
      setInput('')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send(input)
    } else if (e.key === 'ArrowUp' && !input.includes('\n')) {
      e.preventDefault()
      const next = Math.min(histIdx + 1, history.length - 1)
      if (next >= 0) { setHistIdx(next); setInput(history[next]) }
    } else if (e.key === 'ArrowDown' && !input.includes('\n')) {
      e.preventDefault()
      const next = histIdx - 1
      setHistIdx(Math.max(-1, next))
      setInput(next >= 0 ? history[next] : '')
    } else if (e.key === 'c' && e.ctrlKey && !window.getSelection()?.toString()) {
      e.preventDefault()
      void dc.terminalReset(id)
    }
  }

  return (
    <div className="rt-pane">
      <div className="rt-pane__head">
        <span className="rt-pane__title">
          <i className="bi bi-terminal" /> {session.hostname || session.device_id.slice(0, 8)}
        </span>
        <SxChip compact dot tone={sessionTone(status)}>{status === 'OPENING' ? 'connecting…' : status.toLowerCase()}</SxChip>
        <span className="dc-muted">opened by {session.opened_by ?? '—'}</span>
        <span className="rt-pane__spacer" />
        <SxButton sm icon="bi-x-octagon" disabled={!live(status)} title="Stop the running command (Ctrl+C) -- starts a fresh PowerShell"
          onClick={() => void dc.terminalReset(id)}>Ctrl+C</SxButton>
        <SxButton sm icon="bi-eraser" onClick={() => setRows([])} title="Clear the screen (history stays in the audit log)">Clear</SxButton>
      </div>
      <pre ref={screenRef} className="rt-screen" onClick={() => inputRef.current?.focus()}>
        {rows.map((r) => (
          <span key={r.seq} className={`rt-${r.direction.toLowerCase()}`}>
            {r.direction === 'IN' ? `${r.data}\n` : r.direction === 'SYS' ? `[${r.data}]\n` : r.data.replace(ANSI, '')}
          </span>
        ))}
        {status === 'OPENING' && <span className="rt-sys">[waiting for the PC to pick up the session…]{'\n'}</span>}
      </pre>
      {error && <div className="dc-banner dc-banner--danger">{error}</div>}
      <div className="rt-input">
        <span className="rt-input__ps">PS&gt;</span>
        <textarea
          ref={inputRef}
          rows={Math.min(6, input.split('\n').length)}
          value={input}
          disabled={!live(status)}
          placeholder={live(status) ? 'Type a command · Enter to run · Shift+Enter new line · ↑ history' : 'Session ended'}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          spellCheck={false}
          autoFocus
        />
        <SxButton sm variant="primary" icon="bi-arrow-return-left" busy={sending} disabled={!live(status)} onClick={() => void send(input)} />
      </div>
    </div>
  )
}

function AuditLog({ onClose }: { onClose: () => void }) {
  const sessionsQuery = useAsyncData(() => dc.terminals(false))
  const [viewing, setViewing] = useState<DcTerminalSession | null>(null)
  const [rows, setRows] = useState<DcTerminalRow[]>([])

  useEffect(() => {
    if (!viewing) return
    setRows([])
    dc.terminalOutput(viewing.session_id, 0, 0).then((r) => setRows(r.rows)).catch(() => setRows([]))
  }, [viewing])

  return (
    <div className="rt-picker">
      <div className="dc-enroll__head">
        <b>Terminal audit log</b>
        <button type="button" className="dc-banner__close" onClick={onClose} aria-label="Close">×</button>
      </div>
      <div className="rt-audit">
        <div className="rt-picker__list">
          {(sessionsQuery.data?.sessions ?? []).map((s) => (
            <button key={s.session_id} type="button"
              className={`rt-picker__item${viewing?.session_id === s.session_id ? ' rt-picker__item--active' : ''}`}
              onClick={() => setViewing(s)}>
              <span className={`rt-dot rt-dot--${sessionTone(s.status)}`} />
              <span className="rt-picker__name">{s.hostname ?? s.device_id.slice(0, 8)}</span>
              <span className="dc-muted">{s.opened_by} · {fmt(s.opened_at)}</span>
            </button>
          ))}
        </div>
        <pre className="rt-screen rt-screen--audit">
          {!viewing && <span className="rt-sys">Pick a session to see everything that was typed and printed.</span>}
          {rows.map((r) => (
            <span key={r.seq} className={`rt-${r.direction.toLowerCase()}`}>
              {r.direction === 'IN' ? `${r.data}   ⟵ ${r.actor ?? ''} ${fmt(r.created_at)}\n`
                : r.direction === 'SYS' ? `[${r.data} · ${fmt(r.created_at)}]\n` : r.data.replace(ANSI, '')}
            </span>
          ))}
        </pre>
      </div>
    </div>
  )
}
