import React from 'react';

export function ErrorState({ title = 'Something went wrong', message, onRetry }) {
  return (
    <div className="ntm-state ntm-state--error" role="alert">
      <strong>{title}</strong>
      {message ? <p>{message}</p> : null}
      {onRetry ? (
        <button type="button" className="ntm-button ntm-button--secondary" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}
