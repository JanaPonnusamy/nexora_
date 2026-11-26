import React from 'react';
import { useTheme } from '../themes/ThemeContext.jsx';
import { THEME_IDS, themeById } from '../themes/themeLogic.js';
import { GlassDropdown } from '../ui/glass.jsx';
import { Icon } from '../ui/icons.jsx';

export function ThemeSelector() {
  const { preference, theme, setPreference } = useTheme();

  return (
    <GlassDropdown
      label={(
        <span className="ntm-theme-trigger">
          <Icon name="monitor" size={15} />
          <span>{theme?.label || 'Theme'}</span>
        </span>
      )}
    >
      <div className="ntm-theme-menu" role="group" aria-label="Theme">
        {THEME_IDS.map((id) => {
          const item = themeById(id);
          const active = preference === id;
          return (
            <button
              key={id}
              type="button"
              role="menuitemradio"
              aria-checked={active}
              className={`ntm-theme-menu__item${active ? ' is-active' : ''}`}
              onClick={() => setPreference(id)}
            >
              <span className="ntm-theme-menu__dot" style={{ background: item.accent }} />
              {item.label}
            </button>
          );
        })}
        <button
          type="button"
          role="menuitemradio"
          aria-checked={preference === 'system'}
          className={`ntm-theme-menu__item${preference === 'system' ? ' is-active' : ''}`}
          onClick={() => setPreference('system')}
        >
          Match system
        </button>
      </div>
    </GlassDropdown>
  );
}
