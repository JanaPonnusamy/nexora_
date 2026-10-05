import { execSync } from 'node:child_process';

const port = process.env.NEXORA_DEV_PORT || 5173;
const apiHealthUrl = process.env.NEXORA_API_HEALTH_URL || 'http://127.0.0.1:8000/health';

// Vite becoming reachable is not enough: the old launcher opened Electron
// after a fixed five-second backend delay, so a cold/loaded API produced a
// visible error before the same requests eventually succeeded. Wait for both
// dependencies and fail with a useful timeout instead of opening a broken UI.
execSync(`wait-on --timeout 60000 http://127.0.0.1:${port} http-get://${apiHealthUrl.replace(/^https?:\/\//, '')}`, {
  stdio: 'inherit'
});
// ELECTRON_RUN_AS_NODE (set persistently in this environment) makes electron.exe
// launch as plain Node instead of the Electron app, so `require('electron')`
// never yields the app/BrowserWindow API. Must be entirely absent from the
// child's env (not just falsy) or Electron still boots in Node mode.
const { ELECTRON_RUN_AS_NODE, ...cleanEnv } = process.env;
execSync('electron .', { stdio: 'inherit', env: cleanEnv });
