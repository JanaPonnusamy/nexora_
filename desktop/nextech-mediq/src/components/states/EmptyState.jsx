import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import emptyIllustration from '../../assets/ai/empty-state.webp';
import { findNavItemByPath } from '../../navigation/navConfig.js';
import { PAGE_GUIDES } from '../../help/pageGuides.js';

// An empty screen should still teach: under the message it says what the page
// is for and the first steps to get data onto it (from the page guide), with a
// link to the full Help. `hint={false}` turns that off for compact spots.
export function EmptyState({ title = 'Nothing to show', description, action, hint = true }) {
  const { pathname } = useLocation();
  const item = findNavItemByPath(pathname);
  const guide = hint && item ? PAGE_GUIDES[item.path] : null;

  return (
    <div className="ntm-state ntm-state--empty">
      <img className="ntm-state__art" src={emptyIllustration} alt="" width="88" height="88" />
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action ? <div className="ntm-state__action">{action}</div> : null}
      {guide ? (
        <div className="ntm-state__guide">
          <span className="ntm-state__guide-title">About this page</span>
          <p>{guide.purpose}</p>
          {guide.steps.length > 0 ? (
            <ol>{guide.steps.slice(0, 3).map((step) => <li key={step}>{step}</li>)}</ol>
          ) : null}
          <Link to="/help">Full guide and keyboard keys →</Link>
        </div>
      ) : null}
    </div>
  );
}
