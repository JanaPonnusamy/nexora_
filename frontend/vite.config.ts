import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // The API the dev server proxies to. Defaults to the local backend; override
  // with VITE_DEV_API_TARGET when the API runs on another host/port.
  const apiTarget = env.VITE_DEV_API_TARGET || 'http://localhost:8000'

  return {
    plugins: [react()],
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
