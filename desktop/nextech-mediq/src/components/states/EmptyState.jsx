import React from 'react';
import emptyIllustration from '../../assets/ai/empty-state.webp';

export function EmptyState({ title = 'Nothing to show', description, action }) {
  return (
    <div className="ntm-state ntm-state--empty">
      <img className="ntm-state__art" src={emptyIllustration} alt="" width="88" height="88" />
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action ? <div className="ntm-state__action">{action}</div> : null}
    </div>
  );
}
