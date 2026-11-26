import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';
import { hydrateSession } from '../services/sessionStore.js';

const root = createRoot(document.getElementById('root'));
hydrateSession().finally(() => {
  root.render(<App />);
});
