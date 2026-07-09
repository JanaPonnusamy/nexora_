import { useCallback, useEffect, useState } from 'react'
import { moduleRegistry } from '../modules/ModuleRegistry'
import { Ribbon } from '../ribbon/Ribbon'
import { NavigationRail } from '../navigation/NavigationRail'
import { WorkspaceTabs } from '../workspace/WorkspaceTabs'
import { WorkspaceHost } from '../workspace/WorkspaceHost'
import { PlatformStatusBar } from '../statusbar/PlatformStatusBar'
import { GlobalErrorDialog } from '../errors/GlobalErrorDialog'
import { ErrorBoundary } from '../errors/ErrorBoundary'
import { errorService } from '../errors/ErrorService'
import { keyboardManager } from '../keyboard/KeyboardManager'
import { loadLayout, saveLayout } from '../layout/LayoutPersistence'
import { UniNotification } from '../ui/UniNotification'
import '../ui/uni-ui.css'
import './platform-shell.css'

const WORKSPACE_LAYOUT_KEY = 'workspace'

interface WorkspaceState {
  openModuleIds: string[]
  activeModuleId: string | undefined
}

// Restores which tabs were open and which was active last session ("users
// should return to exactly the same workspace after restarting"). Stale ids
// (a module that existed in a previous build but was removed) are dropped
// rather than left as broken tabs.
function restoreWorkspaceState(): WorkspaceState {
  const restored = loadLayout<{ openModuleIds: string[]; activeModuleId: string | null }>(WORKSPACE_LAYOUT_KEY, {
    openModuleIds: [],
    activeModuleId: null,
  })
  const openModuleIds = restored.openModuleIds.filter((id) => moduleRegistry.has(id))
  const activeModuleId =
    restored.activeModuleId && openModuleIds.includes(restored.activeModuleId)
      ? restored.activeModuleId
      : openModuleIds[0]
  return { openModuleIds, activeModuleId }
}

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
  const [workspace, setWorkspace] = useState<WorkspaceState>(restoreWorkspaceState)
  const [reloadToken, setReloadToken] = useState(0)
  const { openModuleIds, activeModuleId } = workspace

  const openModule = useCallback((moduleId: string) => {
    setWorkspace((prev) => ({
      openModuleIds: prev.openModuleIds.includes(moduleId) ? prev.openModuleIds : [...prev.openModuleIds, moduleId],
      activeModuleId: moduleId,
    }))
  }, [])

  const closeModule = useCallback((moduleId: string) => {
    setWorkspace((prev) => {
      const openModuleIds = prev.openModuleIds.filter((id) => id !== moduleId)
      const activeModuleId =
        prev.activeModuleId === moduleId ? openModuleIds[openModuleIds.length - 1] : prev.activeModuleId
      return { openModuleIds, activeModuleId }
    })
  }, [])

  const setActiveModuleId = useCallback((moduleId: string) => {
    setWorkspace((prev) => ({ ...prev, activeModuleId: moduleId }))
  }, [])

  // Persist which tabs are open and which is active — see restoreWorkspaceState.
  useEffect(() => {
    saveLayout(WORKSPACE_LAYOUT_KEY, { openModuleIds, activeModuleId: activeModuleId ?? null })
  }, [openModuleIds, activeModuleId])

  // Global keyboard shortcuts are registered via keyboardManager.register()
  // (by the shell here, or by modules) and consulted from this single
  // document-level listener, so shortcuts never conflict between modules the
  // way ad hoc per-component onKeyDown handlers can. Esc/F5 are the only
  // combos with an unambiguous *shell-level* meaning; Ctrl+S/F/N/P/F2/Enter
  // are reserved for modules to register themselves once they exist — the
  // registry's duplicate-id guard (see KeyboardManager.register) is what
  // actually prevents conflicts, not any hardcoded shell behavior for them.
  useEffect(() => {
    const unregisterEscape = keyboardManager.register('escape', () => {
      setWorkspace((prev) => {
        if (!prev.activeModuleId) return prev
        const openModuleIds = prev.openModuleIds.filter((id) => id !== prev.activeModuleId)
        return { openModuleIds, activeModuleId: openModuleIds[openModuleIds.length - 1] }
      })
    })
    const unregisterReload = keyboardManager.register('f5', (event) => {
      event.preventDefault()
      setReloadToken((token) => token + 1)
    })
    return () => {
      unregisterEscape()
      unregisterReload()
    }
  }, [])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      keyboardManager.handle(event)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Anything that reaches window.onerror/unhandledrejection slipped past both
  // a module's own try/catch and the ErrorBoundary (which only catches render
  // errors) — it still needs to surface through the one centralized
  // ErrorService rather than vanishing into the browser console.
  useEffect(() => {
    function handleWindowError(event: ErrorEvent) {
      errorService.report('window', event.message, event.error ?? event)
    }
    function handleRejection(event: PromiseRejectionEvent) {
      errorService.report('window', 'Unhandled promise rejection', event.reason)
    }
    window.addEventListener('error', handleWindowError)
    window.addEventListener('unhandledrejection', handleRejection)
    return () => {
      window.removeEventListener('error', handleWindowError)
      window.removeEventListener('unhandledrejection', handleRejection)
    }
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
            <WorkspaceHost key={activeModule ? `${activeModule.id}:${reloadToken}` : 'empty'} activeModule={activeModule} />
          </ErrorBoundary>
        </div>
      </div>
      <PlatformStatusBar />
      <GlobalErrorDialog />
      <UniNotification />
    </div>
  )
}
