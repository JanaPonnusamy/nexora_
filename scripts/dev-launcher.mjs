import { spawn, spawnSync } from 'node:child_process';
import { createConnection } from 'node:net';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import readline from 'node:readline';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const children = [];
let stopping = false;
const log = (message, stream = process.stdout) => stream.write(`[launcher] ${message}\n`);

function prefixLines(stream, name, destination) {
  readline.createInterface({ input: stream }).on('line', line => destination.write(`[${name}] ${line}\n`));
}

function start(name, command, args, cwd, env = {}) {
  log(`Starting ${name}...`);
  const child = spawn(command, args, {
    cwd, env: { ...process.env, ...env }, windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.serviceName = name;
  prefixLines(child.stdout, name, process.stdout);
  prefixLines(child.stderr, name, process.stderr);
  children.push(child);
  return child;
}

function portIsOpen(port) {
  return new Promise(resolve => {
    const socket = createConnection({ host: '127.0.0.1', port });
    const finish = result => { socket.destroy(); resolve(result); };
    socket.setTimeout(300);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
  });
}

async function waitFor(name, port, child, timeoutMs = 90000) {
  log(`Waiting for ${name} on port ${port}...`);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`${name} exited before port ${port} became ready (exit code ${child.exitCode}).`);
    if (await portIsOpen(port)) { log(`${name} is ready.`); return; }
    await new Promise(resolve => setTimeout(resolve, 300));
  }
  throw new Error(`Timed out waiting for ${name} on port ${port}.`);
}

function stopAll(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  log('Stopping all Nexora development processes...');
  for (const child of [...children].reverse()) {
    if (child.exitCode === null && child.pid) {
      spawnSync('taskkill.exe', ['/pid', String(child.pid), '/t', '/f'], { windowsHide: true, stdio: 'ignore' });
    }
  }
  process.exit(exitCode);
}

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));

function watchForUnexpectedExit(child) {
  child.once('exit', code => {
    if (!stopping) {
      log(`${child.serviceName} stopped unexpectedly (exit code ${code}).`, process.stderr);
      stopAll(code || 1);
    }
  });
}

async function ensureRunning(name, port, command, args, cwd, env) {
  if (await portIsOpen(port)) {
    log(`${name} already running on port ${port}, leaving it alone.`);
    return;
  }
  const child = start(name, command, args, cwd, env);
  await waitFor(name, port, child);
  watchForUnexpectedExit(child);
}

async function main() {
  const venvPython = join(root, 'backend', '.venv', 'Scripts', 'python.exe');
  const python = existsSync(venvPython) ? venvPython : 'python.exe';

  console.log('Nexora Development Control');
  console.log('==========================');
  console.log('API             http://127.0.0.1:8000');
  console.log('Web frontend    http://127.0.0.1:5173');
  console.log('Supplier client http://127.0.0.1:5180');
  console.log('Press Ctrl+C once to stop everything.\n');

  await ensureRunning('backend', 8000, python, ['-m', 'uvicorn', 'api.app:app', '--host', '0.0.0.0', '--port', '8000', '--reload'], join(root, 'backend'));

  await ensureRunning('frontend', 5173, process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', 'npm.cmd', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173', '--strictPort'], join(root, 'frontend'));

  await ensureRunning('supplier', 5180, process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', 'npm.cmd', 'run', 'dev'], join(root, 'desktop', 'supplier-stock-client'), { NEXORA_DEV_PORT: '5180' });

  log('All services are running (started or already up).');
}

main().catch(error => {
  log(error.message, process.stderr);
  stopAll(1);
});
