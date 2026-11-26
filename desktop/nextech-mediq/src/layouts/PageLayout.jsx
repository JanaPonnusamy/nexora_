import React from 'react';

export function PageLayout({ title, description, actions, children, dense = false }) {
  return (
    <section className={`ntm-page${dense ? ' ntm-page--dense' : ''}`}>
      <header className="ntm-page__header">
        <div>
          <h1 className="ntm-page__title">{title}</h1>
          {description ? <p className="ntm-page__lede">{description}</p> : null}
        </div>
        {actions ? <div className="ntm-page__actions">{actions}</div> : null}
      </header>
      <div className="ntm-page__body">{children}</div>
    </section>
  );
}
