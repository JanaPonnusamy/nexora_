import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const frontendSrc = path.resolve(rootDir, '../../frontend/src');
const frontendModules = path.resolve(rootDir, '../../frontend/node_modules');
const apiClient = path.normalize(path.resolve(frontendSrc, 'services/apiClient.ts'));
const authContext = path.normalize(path.resolve(frontendSrc, 'contexts/AuthContext.tsx'));
const webApiClient = path.resolve(rootDir, 'src/bridge/webApiClient.js');
const webAuthContext = path.resolve(rootDir, 'src/bridge/webAuthContext.jsx');

function sameFile(candidate, target) {
  return path.normalize(candidate).toLowerCase() === path.normalize(target).toLowerCase();
}

function bridgeFrontendModules() {
  return {
    name: 'nextech-web-bridge',
    enforce: 'pre',
    resolveId(source, importer) {
      if (!importer || !source.startsWith('.')) return null;
      const from = importer.split('?')[0];
      const base = path.normalize(path.resolve(path.dirname(from), source));
      const candidates = [base, `${base}.ts`, `${base}.tsx`, `${base}.js`, `${base}.jsx`];
      if (candidates.some((file) => sameFile(file, apiClient))) return webApiClient;
      if (candidates.some((file) => sameFile(file, authContext))) return webAuthContext;
      return null;
    },
  };
}

export default defineConfig({
  plugins: [bridgeFrontendModules(), react()],
  base: './',
  resolve: {
    alias: {
      '@web': frontendSrc,
      react: path.resolve(rootDir, 'node_modules/react'),
      'react-dom': path.resolve(rootDir, 'node_modules/react-dom'),
      'react-router-dom': path.resolve(rootDir, 'node_modules/react-router-dom'),
      'bootstrap/dist/css/bootstrap.min.css': path.resolve(frontendModules, 'bootstrap/dist/css/bootstrap.min.css'),
      'bootstrap-icons/font/bootstrap-icons.css': path.resolve(frontendModules, 'bootstrap-icons/font/bootstrap-icons.css'),
    },
    dedupe: ['react', 'react-dom', 'react-router-dom'],
    modules: [
      path.resolve(rootDir, 'node_modules'),
      frontendModules,
    ],
  },
  server: {
    port: 5183,
    strictPort: true,
    fs: {
      allow: [path.resolve(rootDir, '../..')],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
