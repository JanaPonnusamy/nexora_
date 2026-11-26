import React from 'react';
import { Icon } from './icons.jsx';
import dashboard from '../assets/ai/icon-dashboard.webp';
import inventory from '../assets/ai/icon-inventory.webp';
import procurement from '../assets/ai/icon-procurement.webp';
import reports from '../assets/ai/icon-reports.webp';
import ai from '../assets/ai/icon-ai.webp';
import admin from '../assets/ai/icon-admin.webp';

// 3D glass icons generated for the nav groups (OpenAI gpt-image-1.5, 2026-11).
// Keyed by the same names the line-icon set uses, so callers can pass a
// nav group's `icon` straight through; anything without a 3D version
// falls back to the line icon.
const ICONS_3D = Object.freeze({ dashboard, inventory, procurement, reports, spark: ai, admin });

export function has3DIcon(name) {
  return Boolean(ICONS_3D[name]);
}

export function Icon3D({ name, size = 20, className = '' }) {
  const src = ICONS_3D[name];
  if (!src) return <Icon name={name} size={size} className={className} />;
  return (
    <img
      className={`ntm-icon3d ${className}`.trim()}
      src={src}
      width={size}
      height={size}
      alt=""
      draggable="false"
    />
  );
}
