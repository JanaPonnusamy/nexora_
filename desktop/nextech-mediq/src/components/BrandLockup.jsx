import React from 'react';
import { useTheme } from '../themes/ThemeContext.jsx';
import mark from '../assets/branding/svg/nextech-mediq-app-icon.svg';

// The lockup is the app-icon mark plus live text, so the "AI-Powered"
// caption under the name stays legible at sidebar size and follows the theme.
export function BrandLockup({ variant = 'lockup', className = '', forceTheme }) {
  const { effectiveTheme } = useTheme();
  const theme = forceTheme || effectiveTheme;
  if (variant === 'mark') {
    return (
      <img
        className={`ntm-brand ntm-brand--mark ${className}`.trim()}
        src={mark}
        alt="NexTech MediQ Workspace"
      />
    );
  }
  return (
    <span
      className={`ntm-brand ntm-brand--lockup ntm-brand--on-${theme === 'light' ? 'light' : 'dark'} ${className}`.trim()}
      role="img"
      aria-label="NexTech MediQ Workspace, AI-Powered"
    >
      <img className="ntm-brand__mark" src={mark} alt="" />
      <span className="ntm-brand__text">
        <span className="ntm-brand__name">
          NexTech <b>MediQ</b>
        </span>
        <span className="ntm-brand__caption">
          <i aria-hidden="true">✦</i> AI-Powered Workspace
        </span>
      </span>
    </span>
  );
}
