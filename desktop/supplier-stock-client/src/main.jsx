import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';
import { loadSettings } from './state/session.js';
import { applyTheme } from './theme.js';

// Apply the saved/resolved theme before React mounts so the Electron window
// never flashes light while starting in dark mode.
applyTheme(loadSettings().themePreference);

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
