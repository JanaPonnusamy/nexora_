import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../ui/icons.jsx';
import { isNavItemEnabled, searchNavItems, statusLabel } from '../navigation/navConfig.js';

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const results = useMemo(() => searchNavItems(query).slice(0, 10), [query]);

  useEffect(() => {
    function onKey(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen(true);
      }
      if (event.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  function choose(item) {
    if (!isNavItemEnabled(item)) return;
    navigate(item.path);
    setOpen(false);
  }

  return (
    <>
      <button type="button" className="ntm-search-trigger" onClick={() => setOpen(true)}>
        <Icon name="search" />
        <span>Search workspace</span>
        <kbd>Ctrl K</kbd>
      </button>
      {open ? (
        <div className="ntm-overlay" role="presentation" onClick={() => setOpen(false)}>
          <div
            className="ntm-command"
            role="dialog"
            aria-modal="true"
            aria-label="Global search"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="ntm-command__input">
              <Icon name="search" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Jump to a module…"
                aria-label="Search modules"
              />
            </div>
            <ul className="ntm-command__list">
              {results.map((item) => {
                const enabled = isNavItemEnabled(item);
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className="ntm-command__item"
                      disabled={!enabled}
                      onClick={() => choose(item)}
                    >
                      <span>
                        <strong>{item.label}</strong>
                        <em>{item.groupLabel}</em>
                      </span>
                      <span className={`ntm-status-chip ntm-status-chip--${item.status}`}>
                        {statusLabel(item.status)}
                      </span>
                    </button>
                  </li>
                );
              })}
              {results.length === 0 ? <li className="ntm-command__empty">No matching destinations</li> : null}
            </ul>
          </div>
        </div>
      ) : null}
    </>
  );
}
