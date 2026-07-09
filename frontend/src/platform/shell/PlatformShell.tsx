import { useCallback, useEffect, useState } from 'react'
import { moduleRegistry } from '../modules/ModuleRegistry'
import { Ribbon } from '../ribbon/Ribbon'
import { NavigationRail } from '../navigation/NavigationRail'
import { WorkspaceTabs } from '../workspace/WorkspaceTabs'
import { WorkspaceHost } from '../workspace/WorkspaceHost'
import { PlatformStatusBar } from '../statusbar/PlatformStatusBar'
import { GlobalErrorDialog } from '../errors/GlobalErrorDialog'
import { ErrorBoundary } from '../errors/ErrorBoundary'
import { keyboardManager } from '../keyboard/KeyboardManager'
import { UniNotification } from '../ui/UniNotification'
import '../ui/uni-ui.css'
import './platform-shell.css'

/**
 * The reusable desktop shell — ribbon, nav rail, workspace tabs, module host,
 * status bar. Knows nothing about any specific module; everything it renders
 * comes from moduleRegistry entries and their contributions. Mounted at
 * /platform-shell-preview as a full-page route (not nested inside the
 * existing AppShell) so it can be built and compared side-by-side without
 * touching the live app.
 */
export function PlatformShell() {
  const [modules] = useState(() => moduleRegistry.list())
  const [openModuleIds, setOpenModuleIds] = useState<string[]>([])
  const [activeModuleId, setActiveModuleId] = useState<string | undefined>(undefined)

  const openModule = useCallback((moduleId: string) => {
    setOpenModuleIds((prev) => (prev.includes(moduleId) ? prev : [...prev, moduleId]))
    setActiveModuleId(moduleId)
  }, [])

  const closeModule = useCallback((moduleId: string) => {
    setOpenModuleIds((prev) => {
      const next = prev.filter((id) => id !== moduleId)
      setActiveModuleId((current) => (current === moduleId ? next[next.length - 1] : current))
      return next
    })
  }, [])

  // Global keyboard shortcuts (Ctrl+S/F/P/N, F2, F5, Esc, ...) are registered
  // via keyboardManager.register() by modules/shell code and consulted from
  // this single document-level listener, so shortcuts never conflict between
  // modules the way ad hoc per-component onKeyDown handlers can.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      keyboardManager.handle(event)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Electron's main process asks open modules to save state before actually
  // quitting (see electron/main.ts's before-quit handler). Per-module
  // saveState hooks run inside each ModuleHost's own lifecycle controller, so
  // there's nothing further to flush at the shell level yet — this just acks
  // so shutdown isn't held up by main's bounded wait.
  useEffect(() => window.uninex?.onBeforeQuit(() => window.uninex?.quit()), [])

  const openModules = openModuleIds
    .map((id) => moduleRegistry.get(id))
    .filter((module) => module !== undefined)
  const activeModule = activeModuleId ? moduleRegistry.get(activeModuleId) : undefined
  const ribbonContributions = activeModule?.ribbon ? [activeModule.ribbon] : []

  return (
    <div className="platform-shell">
      <Ribbon contributions={ribbonContributions} />
      <div className="platform-shell__body">
        <NavigationRail modules={modules} activeModuleId={activeModuleId} onSelect={openModule} />
        <div className="platform-shell__workspace">
          <WorkspaceTabs
            openModules={openModules}
            activeModuleId={activeModuleId}
            onSelect={setActiveModuleId}
            onClose={closeModule}
          />
          <ErrorBoundary scope="platform-shell">
            <WorkspaceHost activeModule={activeModule} />
          </ErrorBoundary>
        </div>
      </div>
      <PlatformStatusBar />
      <GlobalErrorDialog />
      <UniNotification />
    </div>
  )
}
