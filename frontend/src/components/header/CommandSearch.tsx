import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { NAV_DESTINATIONS } from '../sidebar/navLookup'
import { useAccess } from '../../hooks/useAccess'

/** Search across every destination the current role can reach. */
export function CommandSearch() {
  const navigate = useNavigate()
  const { can } = useAccess()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const permitted = useMemo(
    () => NAV_DESTINATIONS.filter((item) => !item.cap || can(item.cap)),
    [can],
  )

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return permitted
    return permitted.filter((item) =>
      `${item.group ?? ''} ${item.label}`.toLowerCase().includes(needle),
    )
  }, [permitted, query])

  // Opening always starts from a clean slate, so the reset lives with the
  // state change rather than in an effect watching it.
  const openPalette = useCallback(() => {
    setQuery('')
    setCursor(0)
    setOpen(true)
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      setOpen((wasOpen) => {
        if (wasOpen) return false
        setQuery('')
        setCursor(0)
        return true
      })
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // Derived rather than stored, so a shrinking result set can never leave the
  // cursor pointing past the end.
  const activeIndex = Math.min(cursor, Math.max(0, results.length - 1))
  const active = results[activeIndex]

  useEffect(() => {
    const items = listRef.current?.querySelectorAll<HTMLElement>('.cmdk__item')
    items?.[activeIndex]?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  const go = (to: string) => {
    setOpen(false)
    navigate(to)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (results.length === 0) return
      const step = event.key === 'ArrowDown' ? 1 : -1
      setCursor((activeIndex + step + results.length) % results.length)
      return
    }
    if (event.key === 'Enter' && active) {
      event.preventDefault()
      go(active.to)
    }
  }

  return (
    <>
      <button type="button" className="app-search-trigger" onClick={openPalette}>
        <i className="bi bi-search" aria-hidden="true" />
        <span className="app-search-trigger__text">Search</span>
        <kbd className="app-search-trigger__kbd">⌘K</kbd>
      </button>

      {open && (
        <div className="cmdk-layer" role="presentation" onMouseDown={() => setOpen(false)}>
          <div
            className="cmdk"
            role="dialog"
            aria-modal="true"
            aria-label="Search destinations"
            onMouseDown={(event) => event.stopPropagation()}
            onKeyDown={onKeyDown}
          >
            <div className="cmdk__field">
              <i className="bi bi-search" aria-hidden="true" />
              <input
                ref={inputRef}
                className="cmdk__input"
                placeholder="Jump to…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Search destinations"
              />
              <kbd className="app-search-trigger__kbd">Esc</kbd>
            </div>

            <div className="cmdk__list" ref={listRef}>
              {results.length === 0 && (
                <p className="cmdk__empty">No destination matches “{query.trim()}”.</p>
              )}
              {results.map((item, index) => (
                <button
                  key={item.to}
                  type="button"
                  className={`cmdk__item${index === activeIndex ? ' is-cursor' : ''}`}
                  onMouseMove={() => setCursor(index)}
                  onClick={() => go(item.to)}
                >
                  <i className={`bi ${item.icon} cmdk__icon`} aria-hidden="true" />
                  <span className="cmdk__label">{item.label}</span>
                  {item.group && <span className="cmdk__group">{item.group}</span>}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
