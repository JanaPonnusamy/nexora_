import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Icon } from '../ui/icons.jsx';
import { findNavItemByPath } from '../navigation/navConfig.js';
import { GuideBody, ProcurementFlow } from './HelpPage.jsx';
import { guideFor } from './pageGuides.js';

function isTyping(target) {
  const tag = target?.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable;
}

// F1, or "?" outside a text box, opens the Help & Guide page.
function useHelpShortcut() {
  const navigate = useNavigate();
  useEffect(() => {
    const onKey = (event) => {
      const wantsHelp = event.key === 'F1' || (event.key === '?' && !isTyping(event.target) && !event.ctrlKey && !event.metaKey);
      if (!wantsHelp) return;
      event.preventDefault();
      navigate('/help');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [navigate]);
}

/** Top-bar "? Guide" button: explains the page the user is looking at. */
export function GuideButton() {
  useHelpShortcut();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) {
    setLastPath(pathname);
    if (open) setOpen(false);
  }

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => { if (event.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const item = findNavItemByPath(pathname);
  const guide = guideFor(item);
  const onHelpPage = pathname === '/help';

  return (
    <>
      <button
        type="button"
        className="ntm-guide-trigger"
        onClick={() => (onHelpPage ? null : setOpen((value) => !value))}
        disabled={onHelpPage}
        aria-expanded={open}
        title="What does this page do? (F1 opens the full Help)"
      >
        <Icon name="spark" size={14} />
        <span>Guide</span>
      </button>
      {open ? createPortal(
        <>
          <button type="button" className="ntm-guide-scrim" aria-label="Close guide" onClick={() => setOpen(false)} />
          <aside className="ntm-guide-drawer" role="dialog" aria-label="Page guide">
            <header>
              <div>
                <span className="ntm-guide-drawer__eyebrow">Page guide</span>
                <h2>{item?.label || 'This page'}</h2>
              </div>
              <button type="button" className="ntm-guide-drawer__close" onClick={() => setOpen(false)} aria-label="Close guide">
                <Icon name="close" size={16} />
              </button>
            </header>
            <div className="ntm-guide-drawer__body ntm-help">
              {guide ? <GuideBody guide={guide} /> : <p className="ntm-help__purpose">This page has no guide yet.</p>}
              {item?.path === '/procurement' ? (
                <>
                  <h4>How procurement works</h4>
                  <ProcurementFlow />
                </>
              ) : null}
            </div>
            <footer>
              <Link to="/help" onClick={() => setOpen(false)}>Open the full Help & Guide →</Link>
            </footer>
          </aside>
        </>,
        document.body,
      ) : null}
    </>
  );
}
