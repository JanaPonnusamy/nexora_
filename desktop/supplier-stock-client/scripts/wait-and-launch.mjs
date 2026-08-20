import { execSync } from 'node:child_process';

const port = process.env.NEXORA_DEV_PORT || 5173;
execSync(`wait-on http://127.0.0.1:${port}`, { stdio: 'inherit' });
// ELECTRON_RUN_AS_NODE (set persistently in this environment) makes electron.exe
// launch as plain Node instead of the Electron app, so `require('electron')`
// never yields the app/BrowserWindow API. Must be entirely absent from the
// child's env (not just falsy) or Electron still boots in Node mode.
const { ELECTRON_RUN_AS_NODE, ...cleanEnv } = process.env;
// Forward any extra args (e.g. --stock-only) through to the Electron app so
// `dev:stock` can launch the Stock Check window.
const extraArgs = process.argv.slice(2).join(' ');
execSync(`electron .${extraArgs ? ' ' + extraArgs : ''}`, { stdio: 'inherit', env: cleanEnv });
