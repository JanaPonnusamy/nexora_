import { readFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const pkg = JSON.parse(readFileSync(fileURLToPath(new URL('./package.json', import.meta.url)), 'utf-8'));

export default defineConfig({
  base: './',
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version)
  },
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: Number(process.env.NEXORA_DEV_PORT) || 5173,
    strictPort: true
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Electron 22 (last Windows 7/8-capable release) ships Chromium 108, so the
    // renderer bundle must not emit syntax newer than that.
    target: 'chrome108'
  }
});
