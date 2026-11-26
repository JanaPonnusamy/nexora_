import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import './glass.css';

export function GlassPanel({ as: Tag = 'section', className = '', children, ...rest }) {
  return <Tag className={`ntm-glass ntm-glass-panel ${className}`.trim()} {...rest}>{children}</Tag>;
}

export function GlassCard({ className = '', children, ...rest }) {
  return <article className={`ntm-glass ntm-glass-card ${className}`.trim()} {...rest}>{children}</article>;
}

export function GlassToolbar({ className = '', children, ...rest }) {
  return <div className={`ntm-glass ntm-glass-toolbar ${className}`.trim()} {...rest}>{children}</div>;
}

export function GlassDialog({ title, children, onClose }) {
  return (
    <div className="ntm-glass-dialog__backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="ntm-glass ntm-glass-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="ntm-glass-dialog__head">
          <h2>{title}</h2>
          <button type="button" className="ntm-glass-button" onClick={onClose}>Close</button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function GlassDropdown({ label, children }) {
  const [open, setOpen] = useState(false);
  const [box, setBox] = useState(null);
  const ref = useRef(null);
  const menuRef = useRef(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return undefined;
    function onDoc(event) {
      if (!ref.current?.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !ref.current || !menuRef.current) {
      setBox(null);
      return undefined;
    }
    function place() {
      const rect = ref.current.getBoundingClientRect();
      const menu = menuRef.current.getBoundingClientRect();
      const width = Math.max(220, menu.width);
      let left = rect.right - width;
      if (left < 8) left = 8;
      if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8);
      let top = rect.bottom + 6;
      if (top + menu.height > window.innerHeight - 8) top = Math.max(8, rect.top - menu.height - 6);
      setBox({ top, left, width });
    }
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open]);

  return (
    <div className="ntm-glass-dropdown" ref={ref}>
      <button
        type="button"
        className="ntm-glass-button ntm-glass-dropdown__trigger"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>
      {open ? (
        <div
          ref={menuRef}
          className="ntm-glass ntm-glass-dropdown__menu is-fixed"
          id={menuId}
          role="menu"
          style={box ? { top: box.top, left: box.left, width: box.width } : { visibility: 'hidden' }}
          onClick={(event) => {
            if (event.target.closest('button, [role="menuitem"], [role="menuitemradio"]')) setOpen(false);
          }}
        >
          {typeof children === 'function' ? children(() => setOpen(false)) : children}
        </div>
      ) : null}
    </div>
  );
}

export function GlassInput(props) {
  return <input className="ntm-glass-input" {...props} />;
}

export function GlassButton({ variant = 'default', className = '', children, ...rest }) {
  return (
    <button type="button" className={`ntm-glass-button ntm-glass-button--${variant} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}

export function GlassSidebar({ className = '', children }) {
  return <div className={`ntm-glass ntm-glass-sidebar ${className}`.trim()}>{children}</div>;
}

export function GlassNavigation({ className = '', children }) {
  return <nav className={`ntm-glass-nav ${className}`.trim()}>{children}</nav>;
}

export function GlassStatusBadge({ tone = 'neutral', children }) {
  return <span className={`ntm-glass-badge ntm-glass-badge--${tone}`}>{children}</span>;
}
