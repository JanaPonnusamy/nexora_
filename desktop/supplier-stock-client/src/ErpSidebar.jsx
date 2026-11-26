// NEXORA MEDIQ Phase 6B: expandable/collapsible ERP sidebar, replacing the
// old flat horizontal menubar (navMenu.jsx's NavMenu) as the primary nav.
// NavMenu/NAV_GROUPS are left in place, untouched -- nothing else in
// App.jsx referencing them needs to change, and this component works from
// the SAME already-permission-filtered `items` App.jsx already computes
// (navItems), so no visibility-gating logic is duplicated or re-derived
// here. This file only decides layout/grouping/collapse state.
import { useEffect, useRef, useState } from 'react';
import { buildErpSections } from './erpNav.js';

const ERP_SIDEBAR_COLLAPSED_KEY = 'nexora.erpSidebar.collapsed';
const ERP_SIDEBAR_OPEN_SECTIONS_KEY = 'nexora.erpSidebar.openSections';

// How long the sidebar waits after a navigation, with no further sidebar
// interaction, before auto-collapsing. Kept to one named constant per the
// spec so a future tweak (within 10000-15000ms) is a one-line change.
const SIDEBAR_AUTO_COLLAPSE_DELAY = 12000;

function readStoredCollapsed() {
  try {
    return localStorage.getItem(ERP_SIDEBAR_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

function readStoredOpenSections() {
  try {
    const raw = localStorage.getItem(ERP_SIDEBAR_OPEN_SECTIONS_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) ? new Set(parsed) : null;
  } catch {
    return null;
  }
}

// Inline SVG icon set -- small, flat, consistent stroke weight, matching
// the app's existing icon-button style (see .logout-button's inline svg in
// App.jsx) rather than pulling in an icon-font/library dependency for a
// handful of glyphs.
const SECTION_ICON_PATHS = {
  dashboard: 'M4 13h7V4H4v9Zm0 7h7v-5H4v5Zm9 0h7V11h-7v9Zm0-16v5h7V4h-7Z',
  masters: 'M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5Z',
  procurement: 'M7 4h10l2 5H5l2-5Zm-2 7h14l-1.2 9.1a1 1 0 0 1-1 .9H7.2a1 1 0 0 1-1-.9L5 11Zm5 3v4m4-4v4',
  inventory: 'M3 7l9-4 9 4-9 4-9-4Zm0 0v10l9 4 9-4V7M12 11v10',
  reports: 'M5 20V10m6 10V4m6 16v-7',
  tools: 'M14.7 6.3a1 1 0 0 1 1.4 0l1.6 1.6a1 1 0 0 1 0 1.4L9.4 17.6l-3.2.7.7-3.2 7.8-7.8Zm3.3-2L20 6.3',
  admin: 'M12 2 4 5v6c0 5 3.4 8.3 8 11 4.6-2.7 8-6 8-11V5l-8-3Zm0 5.5 3 1.7v3.3L12 14l-3-1.5v-3.3l3-1.7Z',
  other: 'M4 6h16M4 12h16M4 18h16',
};

function SectionIcon({ name }) {
  const path = SECTION_ICON_PATHS[name] || SECTION_ICON_PATHS.other;
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="erp-nav-icon">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ErpSidebar({ items, activeScreen, onSelect }) {
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);
  const sections = buildErpSections(items);
  const activeSection = sections.find((s) => s.items.some((i) => i.id === activeScreen));
  const [openKeys, setOpenKeys] = useState(() => {
    const stored = readStoredOpenSections();
    if (stored) return stored;
    // First run: open whichever section holds the current screen so the
    // user isn't dropped into a sidebar with everything collapsed and no
    // visible indication of where they are.
    return new Set(activeSection ? [activeSection.key] : [sections[0]?.key].filter(Boolean));
  });
  const didAutoOpen = useRef(false);

  // Auto-collapse: after the user navigates, give them
  // SIDEBAR_AUTO_COLLAPSE_DELAY of no sidebar interaction before folding the
  // sidebar down, so the workspace reclaims the width. Hovering the sidebar,
  // using its keyboard focus, or a manual collapse/expand all cancel the
  // pending timer -- this only ever fires on its own, never forces a state
  // the user didn't effectively ask for.
  const autoCollapseTimer = useRef(null);
  const isPointerInsideRef = useRef(false);
  const isFocusInsideRef = useRef(false);
  const prevActiveScreenRef = useRef(activeScreen);

  const clearAutoCollapseTimer = () => {
    if (autoCollapseTimer.current) {
      clearTimeout(autoCollapseTimer.current);
      autoCollapseTimer.current = null;
    }
  };

  const scheduleAutoCollapse = () => {
    clearAutoCollapseTimer();
    autoCollapseTimer.current = setTimeout(() => {
      autoCollapseTimer.current = null;
      if (isPointerInsideRef.current || isFocusInsideRef.current) return;
      setCollapsed(true);
    }, SIDEBAR_AUTO_COLLAPSE_DELAY);
  };

  // Restart the timer once per successful navigation (activeScreen change),
  // but only while already expanded -- a collapsed sidebar has nothing left
  // to auto-collapse, and this must never auto-expand it.
  useEffect(() => {
    if (prevActiveScreenRef.current === activeScreen) return;
    prevActiveScreenRef.current = activeScreen;
    if (collapsed) return;
    scheduleAutoCollapse();
  }, [activeScreen, collapsed]);

  useEffect(() => () => clearAutoCollapseTimer(), []);

  function handleSidebarPointerEnter() {
    isPointerInsideRef.current = true;
    clearAutoCollapseTimer();
  }

  function handleSidebarPointerLeave() {
    isPointerInsideRef.current = false;
    if (!isFocusInsideRef.current && !collapsed) scheduleAutoCollapse();
  }

  function handleSidebarFocusIn() {
    isFocusInsideRef.current = true;
    clearAutoCollapseTimer();
  }

  function handleSidebarFocusOut(event) {
    // Ignore focus moving between two elements inside the sidebar itself;
    // only treat it as "left" once focus actually lands outside the nav.
    if (event.currentTarget.contains(event.relatedTarget)) return;
    isFocusInsideRef.current = false;
    if (!isPointerInsideRef.current && !collapsed) scheduleAutoCollapse();
  }

  useEffect(() => {
    try { localStorage.setItem(ERP_SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch { /* per-viewer convenience only */ }
  }, [collapsed]);

  useEffect(() => {
    try { localStorage.setItem(ERP_SIDEBAR_OPEN_SECTIONS_KEY, JSON.stringify([...openKeys])); } catch { /* per-viewer convenience only */ }
  }, [openKeys]);

  // Keep the active screen's section open if navigation lands on a screen
  // whose section the user had collapsed (e.g. deep link / dev-screen
  // auto-route) -- once per screen change, not fighting the user's own
  // later collapse of that same section.
  useEffect(() => {
    didAutoOpen.current = false;
  }, [activeScreen]);
  useEffect(() => {
    if (didAutoOpen.current || !activeSection) return;
    if (!openKeys.has(activeSection.key)) {
      didAutoOpen.current = true;
      setOpenKeys((prev) => new Set(prev).add(activeSection.key));
    }
  }, [activeSection, openKeys]);

  function toggleSection(key) {
    setOpenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  return (
    <nav
      className={`erp-sidebar${collapsed ? ' erp-sidebar-collapsed' : ''}`}
      aria-label="Main navigation"
      onPointerEnter={handleSidebarPointerEnter}
      onPointerLeave={handleSidebarPointerLeave}
      onFocus={handleSidebarFocusIn}
      onBlur={handleSidebarFocusOut}
    >
      <button
        type="button"
        className="erp-sidebar-collapse-toggle"
        onClick={() => {
          // Manual toggle always wins: cancel any pending auto-collapse so
          // it can't fire moments after (or fight) what the user just did.
          clearAutoCollapseTimer();
          setCollapsed((v) => !v);
        }}
        aria-expanded={!collapsed}
        title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d={collapsed ? 'M9 6l6 6-6 6' : 'M15 6l-6 6 6 6'} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <div className="erp-sidebar-sections">
        {sections.map((section) => {
          const isSingle = section.items.length === 1;
          const isOpen = openKeys.has(section.key);
          const sectionActive = section.items.some((i) => i.id === activeScreen);

          if (isSingle) {
            const [only] = section.items;
            return (
              <button
                key={section.key}
                type="button"
                className={`erp-nav-section-button erp-nav-leaf${only.id === activeScreen ? ' active' : ''}`}
                onClick={() => onSelect(only.id)}
                aria-current={only.id === activeScreen ? 'page' : undefined}
                title={collapsed ? section.label : undefined}
              >
                <SectionIcon name={section.icon} />
                <span className="erp-nav-label">{section.label}</span>
              </button>
            );
          }

          return (
            <div key={section.key} className="erp-nav-section">
              <button
                type="button"
                className={`erp-nav-section-button${sectionActive ? ' active' : ''}`}
                aria-expanded={isOpen}
                onClick={() => (collapsed ? onSelect(section.items[0].id) : toggleSection(section.key))}
                title={collapsed ? section.label : undefined}
              >
                <SectionIcon name={section.icon} />
                <span className="erp-nav-label">{section.label}</span>
                {!collapsed && (
                  <svg viewBox="0 0 24 24" aria-hidden="true" className={`erp-nav-caret${isOpen ? ' open' : ''}`}>
                    <path d="M8 10l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
              {!collapsed && isOpen && (
                <div className="erp-nav-submenu" role="group" aria-label={section.label}>
                  {section.items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={item.id === activeScreen ? 'active' : ''}
                      aria-current={item.id === activeScreen ? 'page' : undefined}
                      onClick={() => onSelect(item.id)}
                    >
                      <span className="erp-nav-label">{item.label}</span>
                      {item.hint && <span className="erp-nav-hint">{item.hint}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </nav>
  );
}
