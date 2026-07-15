import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import electron from 'vite-plugin-electron/simple'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // The API the dev server proxies to. Defaults to the local backend; override
  // with VITE_DEV_API_TARGET when the API runs on another host/port.
  const apiTarget = env.VITE_DEV_API_TARGET || 'http://localhost:8000'

  // The Electron host only builds/launches under `vite --mode electron`
  // (see the `electron:dev` script) so the plain `npm run dev` / `npm run
  // build` workflow the web deployment relies on is completely unaffected.
  const isElectron = mode === 'electron'
  // main.ts builds to genuine ESM (matches root package.json's "type":
  // "module", so plain .js output resolves correctly). preload.ts is forced
  // to a `.cjs` extension because it's genuinely CommonJS output (electron's
  // own bundler target for preload scripts) — the extension makes that
  // unambiguous regardless of the root "type" setting.
  const nodeExternal = ['electron-log', 'electron-log/main', 'electron-window-state']

  return {
    plugins: [
      react(),
      ...(isElectron
        ? [
            electron({
              main: {
                entry: 'electron/main.ts',
                // Terminals hosted inside an Electron app (VS Code's integrated
                // terminal, this one included) set ELECTRON_RUN_AS_NODE=1 for
                // their own child processes. If that leaks into the spawned
                // dev Electron process it runs as plain Node — no Chromium, no
                // `app`/`BrowserWindow`, no window ever opens. Strip it here so
                // the spawned Electron always boots as a real Electron app.
                onstart({ startup }) {
                  const { ELECTRON_RUN_AS_NODE: _unused, ...cleanEnv } = process.env
                  startup(['.', '--no-sandbox'], { env: cleanEnv })
                },
                vite: {
                  build: {
                    outDir: 'dist-electron',
                    rollupOptions: { external: nodeExternal },
                  },
                },
              },
              preload: {
                input: 'electron/preload.ts',
                vite: {
                  build: {
                    outDir: 'dist-electron',
                    rollupOptions: { output: { entryFileNames: 'preload.cjs' } },
                  },
                },
              },
            }),
          ]
        : []),
    ],
    server: {
      // Proxy the API + health routes to the backend so the SPA can call them
      // same-origin (relative URLs). This removes cross-origin CORS from the dev
      // workflow and works no matter which host/IP opens the SPA.
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
        '/health': { target: apiTarget, changeOrigin: true },
      },
    },
  }
})
