import { useMemo } from 'react'
import { logger } from '../logging/Logger'
import { errorService } from '../errors/ErrorService'
import { eventBus, type PlatformEventMap } from '../events/EventBus'

/**
 * Convenience bundle of platform services pre-scoped to one module's id, so
 * module code doesn't repeat the moduleId at every logger/error/event call
 * site. This is the "BaseModule" the platform spec calls for — a thin hook
 * rather than a base class, matching how every other integration point in
 * this codebase (useAccess, useTheme, useAuth) is a hook, not inheritance.
 */
export function useBaseModule(moduleId: string) {
  return useMemo(
    () => ({
      log: {
        info: (message: string, data?: unknown) => logger.info(moduleId, message, data),
        warn: (message: string, data?: unknown) => logger.warn(moduleId, message, data),
        error: (message: string, data?: unknown) => logger.error(moduleId, message, data),
      },
      reportError: (message: string, cause?: unknown) => errorService.report(moduleId, message, cause),
      emit: <K extends keyof PlatformEventMap>(event: K, payload: PlatformEventMap[K]) =>
        eventBus.emit(event, payload),
      on: <K extends keyof PlatformEventMap>(event: K, handler: (payload: PlatformEventMap[K]) => void) =>
        eventBus.on(event, handler),
    }),
    [moduleId],
  )
}
