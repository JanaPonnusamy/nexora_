import { execSync } from 'node:child_process';

const port = process.env.NEXORA_DEV_PORT || 5173;
execSync(`wait-on http://127.0.0.1:${port}`, { stdio: 'inherit' });
execSync('electron .', { stdio: 'inherit' });
