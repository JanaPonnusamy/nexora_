import React from 'react';

export function LoadingState({ label = 'Loading…' }) {
  return (
    <div className="ntm-state ntm-state--loading" role="status">
      <span className="ntm-pulse" aria-hidden="true">
        <span className="ntm-pulse__ring" />
        <span className="ntm-pulse__ring ntm-pulse__ring--delay" />
        <span className="ntm-pulse__core">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none">
            <path d="M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7V3z" fill="currentColor" />
          </svg>
        </span>
      </span>
      <span>{label}</span>
    </div>
  );
}
