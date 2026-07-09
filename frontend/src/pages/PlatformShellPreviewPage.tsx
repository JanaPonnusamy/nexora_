import '../platform/modules/registerModules'
import { PlatformShell } from '../platform/shell/PlatformShell'
import { eventBus } from '../platform/events/EventBus'
import { keyboardManager } from '../platform/keyboard/KeyboardManager'
import { moduleRegistry } from '../platform/modules/ModuleRegistry'

// Dev-only debug hook for stress-testing leak-hunting (listener counts,
// registry state) from outside the app — e.g. a Playwright script. Never
// present in a production build (import.meta.env.DEV is false there, and
// Vite dead-code-eliminates the branch).
if (import.meta.env.DEV) {
  ;(window as unknown as { __uninexDebug?: unknown }).__uninexDebug = { eventBus, keyboardManager, moduleRegistry }
}

/**
 * Full-page mount for the Desktop Platform shell, separate from the existing
 * AppShell route tree. Lets the platform be built and compared side-by-side
 * with the live app without touching anything it depends on.
 */
export default function PlatformShellPreviewPage() {
  return <PlatformShell />
}
