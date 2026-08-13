import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
// Tokens first: shell.css and every page stylesheet read the --nx-* values.
import { initTheme } from './design-system/applyTheme'
import './styles/shell.css'
import './index.css'
import './design-system/styles.css'
import App from './App.tsx'

// Paint the stored theme before the first render so the shell never flashes
// the wrong one.
initTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
