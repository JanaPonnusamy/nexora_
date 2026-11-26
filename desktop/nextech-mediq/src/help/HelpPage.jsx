import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { PageLayout } from '../layouts/PageLayout.jsx';
import { Icon } from '../ui/icons.jsx';
import { useAuth } from '../contexts/AuthContext.jsx';
import { visibleNavGroups } from '../navigation/access.js';
import { statusLabel } from '../navigation/navConfig.js';
import { GLOBAL_SHORTCUTS, PROCUREMENT_FLOW, guideFor } from './pageGuides.js';

export function Keys({ keys }) {
  return (
    <span className="ntm-help__keys">
      {keys.map((key, index) => (
        <React.Fragment key={`${key}-${index}`}>
          {index > 0 ? <span className="ntm-help__plus" aria-hidden="true">+</span> : null}
          <kbd>{key}</kbd>
        </React.Fragment>
      ))}
    </span>
  );
}

export function KeyTable({ rows }) {
  return (
    <table className="ntm-help__table">
      <tbody>
        {rows.map((row) => (
          <tr key={row.keys.join('+')}>
            <th scope="row"><Keys keys={row.keys} /></th>
            <td>{row.does}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function GuideBody({ guide }) {
  return (
    <div className="ntm-help__guide">
      <p className="ntm-help__purpose">{guide.purpose}</p>
      {guide.steps.length > 0 ? (
        <>
          <h4>How to use it</h4>
          <ol>{guide.steps.map((step) => <li key={step}>{step}</li>)}</ol>
        </>
      ) : null}
      {guide.features.length > 0 ? (
        <>
          <h4>What you can do here</h4>
          <ul>{guide.features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
        </>
      ) : null}
      {guide.keys.length > 0 ? (
        <>
          <h4>Keyboard keys on this page</h4>
          <KeyTable rows={guide.keys} />
        </>
      ) : null}
    </div>
  );
}

export function ProcurementFlow() {
  return (
    <ol className="ntm-help__flow">
      {PROCUREMENT_FLOW.map((step) => (
        <li key={step.title}>
          <strong>{step.title}</strong>
          <span>{step.body}</span>
        </li>
      ))}
    </ol>
  );
}

export function HelpPage() {
  const { user } = useAuth();
  const [query, setQuery] = useState('');
  const groups = useMemo(() => visibleNavGroups(user), [user]);
  const needle = query.trim().toLowerCase();
  const filtered = useMemo(() => groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (!needle) return true;
        const guide = guideFor(item);
        return `${item.label} ${guide.purpose} ${guide.features.join(' ')}`.toLowerCase().includes(needle);
      }),
    }))
    .filter((group) => group.items.length > 0), [groups, needle]);
  const hasProcurement = groups.some((group) => group.items.some((item) => item.path === '/procurement'));

  return (
    <PageLayout
      title="Help & Guide"
      description="What each page is for, how to use it, and the keys that make it faster. Only the pages your login can open are listed."
    >
      <div className="ntm-help">
        <section className="ntm-help__card ntm-help__start">
          <h2><Icon name="spark" size={16} /> Getting started</h2>
          <ul>
            <li>Use the <strong>sidebar</strong> to open a page. Groups expand to show their pages.</li>
            <li>Press <Keys keys={['Ctrl', 'K']} /> to search for any page and jump to it.</li>
            <li>Press the <strong>? Guide</strong> button at the top of any page to see what that page does and its keys.</li>
            <li>Change the look from the <strong>theme</strong> button at the top. Five themes are available.</li>
          </ul>
        </section>

        <section className="ntm-help__card">
          <h2><Icon name="key" size={16} /> Keyboard shortcuts everywhere</h2>
          <KeyTable rows={GLOBAL_SHORTCUTS} />
        </section>

        {hasProcurement ? (
          <section className="ntm-help__card ntm-help__wide">
            <h2><Icon name="procurement" size={16} /> How procurement works</h2>
            <p className="ntm-help__lede">
              Procurement turns what your stores sold and hold into an order for each supplier. These are the steps, in order.
            </p>
            <ProcurementFlow />
            <p className="ntm-help__lede">Open the <Link to="/procurement">Procurement Workspace</Link> to start. Its keyboard keys are listed under that page below.</p>
          </section>
        ) : null}

        <section className="ntm-help__wide">
          <div className="ntm-help__searchrow">
            <h2>Pages you can use</h2>
            <label className="ntm-help__search">
              <Icon name="search" size={14} />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search pages and features"
                aria-label="Search help"
              />
            </label>
          </div>
          {filtered.length === 0 ? (
            <p className="ntm-help__none">No page matches “{query}”.</p>
          ) : filtered.map((group) => (
            <div key={group.id} className="ntm-help__group">
              <h3><Icon name={group.icon} size={15} /> {group.label}</h3>
              {group.items.map((item) => (
                <details key={item.id} className="ntm-help__item" open={Boolean(needle)}>
                  <summary>
                    <span className="ntm-help__item-name">{item.label}</span>
                    <span className={`ntm-status-chip ntm-status-chip--${item.status}`}>{statusLabel(item.status)}</span>
                  </summary>
                  <GuideBody guide={guideFor(item)} />
                  <Link className="ntm-help__open" to={item.path}>Open {item.label} →</Link>
                </details>
              ))}
            </div>
          ))}
        </section>
      </div>
    </PageLayout>
  );
}
