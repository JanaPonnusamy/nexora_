import { useEffect, useState } from 'react'
import type { ModuleDefinition } from './types'
import { ModuleLifecycleController } from './ModuleLifecycleController'
import { eventBus } from '../events/EventBus'
import { errorService } from '../errors/ErrorService'

interface ModuleHostProps {
  definition: ModuleDefinition
}

/**
 * Drives one module instance through its lifecycle (see
 * ModuleLifecycleController) as it mounts/unmounts inside the workspace, and
 * only renders the module's component once activation has actually
 * completed — a module doing async setup in initialize()/load() won't flash
 * a half-ready UI.
 */
export function ModuleHost({ definition }: ModuleHostProps) {
  // Tracks which module id has finished activating, rather than a plain
  // boolean reset synchronously at the top of the effect — avoids the
  // cascading-render setState-in-effect pattern; readiness is instead
  // derived by comparing against the current definition at render time.
  const [readyModuleId, setReadyModuleId] = useState<string | null>(null)

  useEffect(() => {
    const controller = new ModuleLifecycleController(definition)
    let cancelled = false
    controller
      .mount()
      .then(() => {
        if (cancelled) return
        setReadyModuleId(definition.id)
        eventBus.emit('module.activated', { moduleId: definition.id })
      })
      .catch((err: unknown) => {
        errorService.report(definition.id, `Failed to activate module "${definition.title}"`, err)
      })

    return () => {
      cancelled = true
      eventBus.emit('module.deactivated', { moduleId: definition.id })
      void controller.unmount()
    }
    // Only re-run when the module identity itself changes — `definition` is
    // expected to be a stable registry entry, not re-created per render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [definition.id])

  if (readyModuleId !== definition.id) return null

  const Component = definition.component
  return <Component moduleId={definition.id} />
}
