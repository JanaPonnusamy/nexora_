import React, { useState } from 'react';
import { Icon } from '../ui/icons.jsx';

const SYSTEM_NOTES = [
  {
    id: 'backend',
    title: 'Live backend not verified in this session',
    body: 'Notifications will attach to real events once authentication and module APIs are confirmed against the NEXORA API.',
  },
];

export function NotificationArea() {
  const [open, setOpen] = useState(false);

  return (
    <div className="ntm-menu">
      <button
        type="button"
        className="ntm-icon-button"
        aria-expanded={open}
        aria-haspopup="true"
        aria-label="Notifications"
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="bell" />
      </button>
      {open ? (
        <div className="ntm-popover ntm-popover--wide" role="menu">
          <header className="ntm-popover__head">Notifications</header>
          {SYSTEM_NOTES.map((note) => (
            <article key={note.id} className="ntm-note">
              <strong>{note.title}</strong>
              <p>{note.body}</p>
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}
