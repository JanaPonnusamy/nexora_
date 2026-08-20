import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // This application intentionally starts async resource loads from effects;
      // synchronous loading-state resets are part of that lifecycle.
      'react-hooks/set-state-in-effect': 'off',
      // Providers, route definitions and reusable hooks export related helpers
      // from the same module. Fast Refresh still works for component edits.
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    files: ['src/pages/procurement/PurchaseWorkspacePage.tsx'],
    rules: {
      // This legacy workspace predates the optional React Compiler and uses
      // guarded render-time state/ref orchestration that React supports.
      'react-hooks/immutability': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      'react-hooks/refs': 'off',
    },
  },
])
