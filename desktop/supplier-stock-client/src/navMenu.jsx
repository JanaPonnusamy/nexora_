// Grouped main menu. Every screen declares a `group` (see NAV_GROUPS); the
// menubar shows one button per group, and a group with more than one
// visible screen opens a dropdown. New screens only need a group key --
// the bar never grows past the handful of groups.
import { useEffect, useRef, useState } from 'react';

export const NAV_GROUPS = [
  { key: 'stock', label: 'Stock' },
  { key: 'purchase', label: 'Purchasing' },
  { key: 'reports', label: 'Reports' },
  { key: 'tools', label: 'Tools' },
  { key: 'system', label: 'Settings' },
];

function NavGroup({ group, items, activeScreen, onSelect }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const itemRefs = useRef([]);
  const active = items.find((item) => item.id === activeScreen);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!wrapRef.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDown);
    const at = Math.max(0, items.findIndex((item) => item.id === activeScreen));
    itemRefs.current[at]?.focus();
    return () => document.removeEventListener('mousedown', onDown);
  }, [open, items, activeScreen]);

  if (items.length === 1) {
    const [only] = items;
    return (
      <button type="button" className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={() => onSelect(only.id)}>
        {only.label}
      </button>
    );
  }

  const pick = (id) => { setOpen(false); onSelect(id); };
  const onMenuKey = (e, index) => {
    const move = { ArrowDown: 1, ArrowUp: -1 }[e.key];
    if (move) {
      e.preventDefault();
      itemRefs.current[(index + move + items.length) % items.length]?.focus();
    } else if (e.key === 'Escape' || e.key === 'Tab') {
      setOpen(false);
      wrapRef.current?.querySelector('.nav-group-button')?.focus();
    }
  };

  return (
    <div className="nav-group" ref={wrapRef}>
      <button
        type="button"
        className={`nav-group-button${active ? ' active' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); } }}
      >
        {group.label}
        {active && <span className="nav-group-current">{active.short || active.label}</span>}
        <span className="nav-group-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="nav-group-menu" role="menu" aria-label={group.label}>
          {items.map((item, index) => (
            <button
              key={item.id}
              ref={(el) => { itemRefs.current[index] = el; }}
              type="button"
              role="menuitem"
              className={item.id === activeScreen ? 'active' : ''}
              aria-current={item.id === activeScreen ? 'page' : undefined}
              onClick={() => pick(item.id)}
              onKeyDown={(e) => onMenuKey(e, index)}
            >
              <span className="nav-item-label">{item.label}</span>
              {item.hint && <span className="nav-item-hint">{item.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function NavMenu({ items, activeScreen, onSelect }) {
  return (
    <nav className="menubar-nav" aria-label="Main navigation">
      {NAV_GROUPS.map((group) => {
        const groupItems = items.filter((item) => (item.group || 'tools') === group.key);
        return groupItems.length
          ? <NavGroup key={group.key} group={group} items={groupItems} activeScreen={activeScreen} onSelect={onSelect} />
          : null;
      })}
    </nav>
  );
}
