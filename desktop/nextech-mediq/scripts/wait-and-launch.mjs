import { execSync } from 'node:child_process';

const port = process.env.NEXTECH_DEV_PORT || 5183;

// Wait for Vite's dev server before opening Electron, so we never show a
// blank/broken window on a cold start. Same pattern as
// supplier-stock-client/scripts/wait-and-launch.mjs.
execSync(`wait-on --timeout 60000 http://127.0.0.1:${port}`, { stdio: 'inherit' });

// ELECTRON_RUN_AS_NODE (set persistently in some environments) makes
// electron.exe launch as plain Node instead of the Electron app, so
// `require('electron')` never yields the app/BrowserWindow API. Must be
// entirely absent from the child's env (not just falsy) or Electron still
// boots in Node mode. Same gotcha as supplier-stock-client.
const { ELECTRON_RUN_AS_NODE, ...cleanEnv } = process.env;
execSync('electron .', { stdio: 'inherit', env: cleanEnv });
